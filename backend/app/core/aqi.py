"""US EPA Air Quality Index computation.

Implements the official EPA methodology explicitly (not an approximation):

    pollutant concentration
        -> pollutant-specific breakpoint lookup
        -> linear piecewise interpolation -> pollutant sub-index
    overall AQI = max(sub-indices)

Breakpoint tables follow the *updated* EPA AQI breakpoints effective 2024
(final PM NAAQS revision). Reference: https://www.airnow.gov/aqi/aqi-basics/

Concentrations:
    pm25/pm10 are accepted in ug/m3.
    Gases are accepted in ug/m3 (default) or ppb/ppm; when given in mass
    units they are converted at 25 C / 1 atm before index lookup.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Breakpoint tables: (low_conc, high_conc, low_index, high_index) tuples.
# ---------------------------------------------------------------------------

BREAKPOINTS: Dict[str, list] = {
    "pm25": [  # ug/m3, 24-hour average
        (0.0, 9.0, 0, 50),
        (9.1, 35.4, 51, 100),
        (35.5, 125.4, 101, 150),
        (125.5, 225.4, 151, 200),
        (225.5, 325.4, 201, 300),
        (325.5, 425.4, 301, 500),
    ],
    "pm10": [  # ug/m3, 24-hour average
        (0, 54, 0, 50),
        (55, 154, 51, 100),
        (155, 254, 101, 150),
        (255, 354, 151, 200),
        (355, 424, 201, 300),
        (425, 604, 301, 500),
    ],
    "o3": [  # ppb, 8-hour average — EPA table ends at 200 ppb
        (0, 54, 0, 50),
        (55, 70, 51, 100),
        (71, 85, 101, 150),
        (86, 105, 151, 200),
        (106, 200, 201, 300),
    ],
    "no2": [  # ppb, 1-hour average
        (0, 53, 0, 50),
        (54, 100, 51, 100),
        (101, 360, 101, 150),
        (361, 649, 151, 200),
        (650, 1249, 201, 300),
        (1250, 2049, 301, 500),
    ],
    "so2": [  # ppb, 1-hour average
        (0, 35, 0, 50),
        (36, 75, 51, 100),
        (76, 185, 101, 150),
        (186, 304, 151, 200),
        (305, 604, 201, 300),
        (605, 1004, 301, 500),
    ],
    "co": [  # ppm, 8-hour average
        (0.0, 4.4, 0, 50),
        (4.5, 9.4, 51, 100),
        (9.5, 12.4, 101, 150),
        (12.5, 15.4, 151, 200),
        (15.5, 30.4, 201, 300),
        (30.5, 50.4, 301, 500),
    ],
}

# Mass-volume conversion factors at 25 C, 1 atm: ug/m3 per 1 ppb.
UGM3_PER_PPB = {"no2": 1.88, "so2": 2.62, "o3": 1.96}
# CO is usually reported in mg/m3: mg/m3 per 1 ppm.
MG_M3_PER_PPM_CO = 1.145

SUPPORTED_POLLUTANTS = tuple(BREAKPOINTS.keys())

# EPA-defined averaging periods per pollutant. An AQI computed from a
# concentration averaged over a different window is NOT a standard-derived
# AQI and must be flagged as such.
STANDARD_AVERAGING_PERIODS: Dict[str, str] = {
    "pm25": "24-hour",
    "pm10": "24-hour",
    "o3": "8-hour",
    "no2": "1-hour",
    "so2": "1-hour",
    "co": "8-hour",
}

# EPA-prescribed concentration rounding/truncation BEFORE breakpoint lookup:
#   pm25 -> truncate to 1 decimal place
#   pm10 -> truncate to integer
#   o3   -> truncate to integer (ppb)
#   no2  -> truncate to integer (ppb)
#   so2  -> truncate to integer (ppb)
#   co   -> truncate to 1 decimal place (ppm)
_DECIMALS_BEFORE_LOOKUP: Dict[str, int] = {
    "pm25": 1,
    "pm10": 0,
    "o3": 0,
    "no2": 0,
    "so2": 0,
    "co": 1,
}


def preprocess_concentration(pollutant: str, concentration: float) -> float:
    """Apply the EPA-prescribed truncation for a pollutant.

    EPA AQI methodology truncates (never rounds up) concentrations before the
    breakpoint lookup. Truncation toward zero at the prescribed precision is
    applied here so boundary values land in the correct band deterministically.
    """
    pollutant = pollutant.lower()
    if pollutant not in _DECIMALS_BEFORE_LOOKUP:
        raise ValueError(f"Unknown pollutant {pollutant!r}")
    decimals = _DECIMALS_BEFORE_LOOKUP[pollutant]
    factor = 10 ** decimals
    return math.trunc(float(concentration) * factor) / factor


def validate_averaging_period(pollutant: str, averaging_period: Optional[str]) -> str:
    """Return the effective averaging period, validating against the standard.

    Accepts flexible spellings ("24h", "24-hour", "24 h"). Raises ValueError
    when the window contradicts the EPA standard for the pollutant — silently
    computing an 'AQI' from the wrong window would be scientifically invalid.
    """
    standard = STANDARD_AVERAGING_PERIODS[pollutant]
    if averaging_period is None or averaging_period == "unknown":
        # Caller did not assert an aggregation window; allowed but must be
        # surfaced as non-standard by calculate_aqi_detailed().
        return "unknown"
    compact = averaging_period.strip().lower().replace(" ", "").replace("-", "")
    aliases = {
        "1h": "1-hour", "1hour": "1-hour",
        "8h": "8-hour", "8hour": "8-hour",
        "24h": "24-hour", "24hour": "24-hour",
    }
    normalised = aliases.get(compact)
    if normalised != standard:
        raise ValueError(
            f"{pollutant} AQI requires {standard} averaging "
            f"(got {averaging_period!r})"
        )
    return normalised


def _normalise_unit(unit: str) -> str:
    u = unit.lower().strip()
    aliases = {
        "µg/m³": "ugm3", "μg/m³": "ugm3", "µg/m3": "ugm3", "μg/m3": "ugm3",
        "ug/m3": "ugm3", "mg/m³": "mgm3", "mg/m3": "mgm3",
    }
    return aliases.get(u, u)


def convert_to_index_unit(pollutant: str, value: float, unit: str) -> float:
    """Convert a concentration into the unit the breakpoint table expects.

        pm25 / pm10 : "ugm3"
        no2 / so2   : "ugm3" or "ppb"
        o3          : "ugm3" or "ppb"
        co          : "mgm3" or "ppm"
    """
    pollutant = pollutant.lower()
    unit_key = _normalise_unit(unit)

    if pollutant in ("pm25", "pm10"):
        if unit_key == "ugm3":
            return float(value)
        raise ValueError(f"Unsupported unit {unit!r} for {pollutant}")

    if pollutant == "co":
        if unit_key == "ppm":
            return float(value)
        if unit_key == "mgm3":
            return float(value) / MG_M3_PER_PPM_CO
        raise ValueError(f"Unsupported unit {unit!r} for co")

    if pollutant in UGM3_PER_PPB:
        if unit_key == "ppb":
            return float(value)
        if unit_key == "ugm3":
            return float(value) / UGM3_PER_PPB[pollutant]
        raise ValueError(f"Unsupported unit {unit!r} for {pollutant}")

    raise ValueError(f"Unknown pollutant {pollutant!r}")


def _interpolate(concentration: float, table: list) -> Optional[int]:
    """Piecewise-linear interpolation; None when outside the standard range."""
    for clo, chi, ilo, ihi in table:
        if clo <= concentration <= chi:
            return int(round((ihi - ilo) / (chi - clo) * (concentration - clo) + ilo))
    return None  # outside the published table — caller must flag it


@dataclass
class AQIResult:
    """A fully-provenanced AQI computation.

    Institutional consumers must inspect ``methodology_status``:
      - "standard"               : within the EPA breakpoint table, standard
                                   averaging period asserted
      - "non_standard_averaging" : computed but input was not aggregated over
                                   the EPA-defined window
      - "out_of_standard_range"  : beyond the published table — NO value is
                                   extrapolated
    """

    pollutant: str
    aqi: Optional[int]
    concentration: Optional[float]   # post-truncation value used
    unit: str                        # index-unit after conversion
    averaging_period: str            # effective period ("unknown" allowed)
    standard: str = "EPA"
    methodology_status: str = "standard"
    n_source_observations: int = 0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "pollutant": self.pollutant,
            "aqi": self.aqi,
            "concentration": self.concentration,
            "unit": self.unit,
            "averaging_period": self.averaging_period,
            "standard": self.standard,
            "methodology_status": self.methodology_status,
            "n_source_observations": self.n_source_observations,
            "notes": list(self.notes),
        }


def calculate_aqi_detailed(
    pollutant: str,
    concentration: Optional[float],
    standard: str = "EPA",
    unit: Optional[str] = None,
    averaging_period: Optional[str] = None,
    n_source_observations: int = 0,
) -> AQIResult:
    """Full-fidelity AQI computation with explicit scientific provenance.

    Pipeline: raw concentration -> EPA-prescribed truncation -> unit
    conversion -> breakpoint lookup -> interpolation -> AQIResult carrying
    methodology status. Never extrapolates beyond the published tables.
    """
    if standard.upper() != "EPA":
        raise LookupError(f"Unsupported AQI standard: {standard!r}")

    pollutant = pollutant.lower()
    if pollutant not in BREAKPOINTS:
        raise ValueError(
            f"Unknown pollutant {pollutant!r}; supported: {SUPPORTED_POLLUTANTS}"
        )

    result_unit = (
        "ppm" if pollutant == "co"
        else ("ppb" if pollutant in UGM3_PER_PPB else "ug/m3")
    )

    if concentration is None:
        return AQIResult(
            pollutant=pollutant, aqi=None, concentration=None, unit=result_unit,
            averaging_period="unknown", standard=standard.upper(),
            methodology_status="missing_input",
            notes=["no concentration available"],
        )
    concentration = float(concentration)
    if concentration < 0:
        raise ValueError(f"Concentration must be non-negative, got {concentration}")

    # 1. Unit conversion into the breakpoint's index unit...
    if unit is None:
        unit = "mgm3" if pollutant == "co" else "ugm3"
    converted = convert_to_index_unit(pollutant, float(concentration), unit)

    # 2. ...then EPA-prescribed truncation IN THAT UNIT (never rounds up).
    truncated_in_index_unit = preprocess_concentration(pollutant, converted)

    # 3. Averaging-period semantics.
    effective_period = validate_averaging_period(pollutant, averaging_period)
    status_notes: List[str] = []
    if effective_period == "unknown":
        status = "non_standard_averaging"
        status_notes.append(
            f"input not verified as {STANDARD_AVERAGING_PERIODS[pollutant]} averaged; "
            "AQI is indicative only"
        )
    else:
        status = "standard"

    # 4. Breakpoint lookup — never extrapolate beyond the published range.
    index = _interpolate(truncated_in_index_unit, BREAKPOINTS[pollutant])
    if index is None:
        status = "out_of_standard_range"
        table_lo = BREAKPOINTS[pollutant][0][0]
        table_hi = BREAKPOINTS[pollutant][-1][1]
        status_notes.append(
            f"{pollutant} concentration {truncated_in_index_unit:g} {result_unit} lies "
            f"outside the published EPA breakpoint table ({table_lo:g}-{table_hi:g} "
            f"{result_unit}); no extrapolation performed"
        )

    return AQIResult(
        pollutant=pollutant,
        aqi=index,
        concentration=truncated_in_index_unit,
        unit=result_unit,
        averaging_period=effective_period,
        standard=standard.upper(),
        methodology_status=status,
        n_source_observations=n_source_observations,
        notes=status_notes,
    )


def calculate_aqi(
    pollutant: str,
    concentration: Optional[float],
    standard: str = "EPA",
    unit: Optional[str] = None,
    averaging_period: Optional[str] = None,
) -> Optional[int]:
    """Convenience wrapper around :func:`calculate_aqi_detailed`.

    Prefer the detailed form in institutional contexts where methodology
    status must be surfaced. Returns the integer sub-index or None.
    """
    return calculate_aqi_detailed(
        pollutant, concentration, standard=standard, unit=unit,
        averaging_period=averaging_period,
    ).aqi


def calculate_overall_aqi(
    pollutants: Dict[str, Optional[float]],
    standard: str = "EPA",
    units: Optional[Dict[str, str]] = None,
    averaging_periods: Optional[Dict[str, str]] = None,
    source_observation_counts: Optional[Dict[str, int]] = None,
) -> dict:
    """Overall AQI = max of available pollutant sub-indices (EPA method).

    Returns a fully-provenanced record:

        {
          "aqi": <int|None>,
          "standard": "EPA",
          "methodology_status": "standard" | "non_standard_averaging"
                                | "partially_out_of_standard_range"
                                | "no_usable_data",
          "dominant_pollutant": "pm25",
          "sub_indices": [AQIResult.to_dict(), ...],
        }

    Status aggregation is deliberately conservative: any non-standard or
    out-of-range sub-index demotes the overall status so institutional
    consumers can never mistake an indicative number for a standard-derived one.
    """
    units = units or {}
    periods = averaging_periods or {}
    counts = source_observation_counts or {}

    sub_results = [
        calculate_aqi_detailed(
            name,
            value,
            standard=standard,
            unit=units.get(name),
            averaging_period=periods.get(name),
            n_source_observations=counts.get(name, 0),
        )
        for name, value in pollutants.items()
        if value is not None
    ]
    computable = [r for r in sub_results if r.aqi is not None]

    if not computable:
        return {
            "aqi": None,
            "standard": standard.upper(),
            "methodology_status": "no_usable_data",
            "dominant_pollutant": None,
            "sub_indices": [r.to_dict() for r in sub_results],
        }

    dominant = max(computable, key=lambda r: r.aqi)
    statuses = {r.methodology_status for r in sub_results}
    if "out_of_standard_range" in statuses:
        overall_status = "partially_out_of_standard_range"
    elif "non_standard_averaging" in statuses:
        overall_status = "non_standard_averaging"
    else:
        overall_status = "standard"

    return {
        "aqi": dominant.aqi,
        "standard": standard.upper(),
        "methodology_status": overall_status,
        "dominant_pollutant": dominant.pollutant,
        "sub_indices": [r.to_dict() for r in sub_results],
    }


def aqi_category(aqi: Optional[int]) -> str:
    """Human-readable EPA category label for an AQI value."""
    if aqi is None:
        return "Unknown"
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Moderate"
    if aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    if aqi <= 200:
        return "Unhealthy"
    if aqi <= 300:
        return "Very Unhealthy"
    return "Hazardous"

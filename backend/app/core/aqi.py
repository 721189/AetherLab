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

from typing import Dict, Optional

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
    "o3": [  # ppb, 8-hour average
        (0, 54, 0, 50),
        (55, 70, 51, 100),
        (71, 85, 101, 150),
        (86, 105, 151, 200),
        (106, 200, 201, 300),
        (201, 400, 301, 500),  # extrapolated tail (EPA table ends at 200)
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
    """Piecewise-linear interpolation of concentration onto an AQI scale."""
    for clo, chi, ilo, ihi in table:
        if clo <= concentration <= chi:
            return int(round((ihi - ilo) / (chi - clo) * (concentration - clo) + ilo))
    lowest, highest = table[0], table[-1]
    if concentration < lowest[0]:
        return int(lowest[2])
    if concentration > highest[1]:
        return int(highest[3])
    return None


def calculate_aqi(
    pollutant: str,
    concentration: Optional[float],
    standard: str = "EPA",
    unit: Optional[str] = None,
) -> Optional[int]:
    """Compute the sub-index AQI for a single pollutant.

    Args:
        pollutant: one of ``pm25, pm10, o3, no2, so2, co``.
        concentration: observed concentration.
        standard: only ``"EPA"`` (US) is implemented; explicit so the
            methodology is never implicit at call sites.
        unit: input unit (defaults per pollutant: ``mgm3`` for co, else
            ``ugm3``).

    Returns the integer AQI sub-index or None for missing values.
    Raises ValueError for unknown pollutants/units/negative concentrations
    and LookupError for unsupported standards.
    """
    if standard.upper() != "EPA":
        raise LookupError(f"Unsupported AQI standard: {standard!r}")
    if concentration is None:
        return None
    concentration = float(concentration)
    if concentration < 0:
        raise ValueError(f"Concentration must be non-negative, got {concentration}")

    pollutant = pollutant.lower()
    if pollutant not in BREAKPOINTS:
        raise ValueError(
            f"Unknown pollutant {pollutant!r}; supported: {SUPPORTED_POLLUTANTS}"
        )
    if unit is None:
        unit = "mgm3" if pollutant == "co" else "ugm3"

    converted = convert_to_index_unit(pollutant, concentration, unit)
    return _interpolate(converted, BREAKPOINTS[pollutant])


def calculate_overall_aqi(
    pollutants: Dict[str, Optional[float]],
    standard: str = "EPA",
    units: Optional[Dict[str, str]] = None,
) -> Optional[int]:
    """Overall AQI = max of available pollutant sub-indices (EPA method).

    Pollutants with missing/None values are skipped. Returns None when no
    usable pollutant measurement exists.
    """
    units = units or {}
    sub_indices = [
        idx
        for name, value in pollutants.items()
        if value is not None
        and (idx := calculate_aqi(name, value, standard=standard, unit=units.get(name)))
        is not None
    ]
    return max(sub_indices) if sub_indices else None


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

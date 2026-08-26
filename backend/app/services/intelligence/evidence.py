"""Environmental intelligence: the evidence layer between data and the LLM.

Architecture:

    user question
        -> plan_query()            (deterministic query planner)
        -> EvidenceBuilder.build() (retrieve observations from OUR database)
        -> aggregate / derive      (stats, AQI record, uncertainty)
        -> EvidenceSet             (observations + metrics + citations)
        -> format_evidence_context()
        -> LLM (grounded system prompt)
        -> answer + citations

This is what makes the assistant an *environmental intelligence system*
rather than a generic chatbot with data access: every claim the model makes
is anchored to retrieved observations with provenance and uncertainty.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.environmental_observation import EnvironmentalObservationRecord

# question keyword -> canonical variable(s)
_VARIABLE_KEYWORDS = {
    "temperature": ["temperature", "temp", "hot", "cold", "warm"],
    "humidity": ["humidity", "humid"],
    "wind": ["wind"],
    "pressure": ["pressure"],
    "aqi": ["aqi", "air quality", "pollution level"],
    "pm25": ["pm2.5", "pm25", "fine particulate"],
    "pm10": ["pm10", "particulate"],
    "no2": ["no2", "nitrogen dioxide"],
    "o3": ["o3", "ozone"],
    "so2": ["so2", "sulphur dioxide", "sulfur dioxide"],
}

# Generic words allowed immediately after "in" that are not locations.
_NON_LOCATIONS = {"the", "general", "recent", "your", "this", "terms", "real", "india"}


@dataclass
class QueryPlan:
    """What the user is asking about, derived deterministically."""

    location_name: Optional[str] = None
    variables: List[str] = field(default_factory=list)
    window_hours: int = 72
    # "FOUND" | "NOT_FOUND" | "OPEN" (no location mentioned)
    location_status: str = "OPEN"
    # The location token the user named, even when we have no data for it.
    requested_location: Optional[str] = None


def plan_query(question: str, known_locations: List[str]) -> QueryPlan:
    """Extract location + variables from a natural-language question.

    Deliberately rule-based (fast, auditable, zero-cost): the LLM only ever
    sees structured evidence and never guesses which data to fetch.

    ``location_status`` distinguishes three cases so downstream code never
    conflates "no location mentioned" (OPEN) with "user named a region we
    don't monitor" (NOT_FOUND) — the latter must NOT silently query every
    location.
    """
    q = question.lower()
    plan = QueryPlan()

    found = None
    for location in known_locations:
        if location.lower() in q:
            found = location
            break

    if found is not None:
        plan.location_name = found
        plan.location_status = "FOUND"
    else:
        # Heuristic: the user named a specific place we don't monitor
        # ("NO2 in London?"). Detect a capitalized proper noun after "in" and
        # mark it NOT_FOUND rather than widening the query to every location.
        import re

        m = re.search(r"in\s+([A-Z][A-Za-z][\w\s]*)", question)
        if m:
            candidate = m.group(1).strip().strip("?.").strip()
            # Only treat it as a requested-but-unmonitored location when it
            # is not a known filler word.
            first = candidate.split()[0].lower()
            if candidate and first not in _NON_LOCATIONS:
                plan.requested_location = candidate
                plan.location_status = "NOT_FOUND"
            else:
                plan.location_status = "OPEN"
        else:
            plan.location_status = "OPEN"

    for variable, keywords in _VARIABLE_KEYWORDS.items():
        if any(k in q for k in keywords):
            plan.variables.append(variable)

    if "week" in q:
        plan.window_hours = 24 * 7
    elif "month" in q:
        plan.window_hours = 24 * 30

    return plan


@dataclass
class SourceReference:
    source: str
    dataset: Optional[str]
    variable: str
    observed_at: Optional[str]
    averaging_period: str
    provenance: Dict[str, Any] = field(default_factory=dict)

    def cite(self) -> str:
        stamp = f" @ {self.observed_at}" if self.observed_at else ""
        dataset = f" [{self.dataset}]" if self.dataset else ""
        return f"{self.source}{dataset}:{self.variable}{stamp}"


@dataclass
class DerivedMetric:
    name: str
    value: Optional[float]
    unit: str
    method: str
    uncertainty: Optional[float] = None
    confidence: float = 1.0
    n_observations: int = 0
    methodology_status: str = "standard"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "method": self.method,
            "uncertainty": self.uncertainty,
            "confidence": round(self.confidence, 3),
            "n_observations": self.n_observations,
            "methodology_status": self.methodology_status,
        }


@dataclass
class EvidenceSet:
    """Everything the LLM may ground its answer on -- nothing more."""

    question: str
    plan: QueryPlan
    observations: List[Dict[str, Any]]
    derived_metrics: List["DerivedMetric"]
    source_references: List[SourceReference]
    window_start: Optional[datetime]
    window_end: Optional[datetime]
    data_completeness: float   # 0..1 fraction of requested variables found
    overall_confidence: float  # 0..1
    location_status: str = "OPEN"  # FOUND | NOT_FOUND | OPEN
    requested_location: Optional[str] = None
    notes: List[str] = field(default_factory=list)


def _unit_for(name: str) -> str:
    return {
        "temperature": "celsius", "feels_like": "celsius",
        "humidity": "percent", "pressure": "hPa", "wind_speed": "m/s",
        "pm25": "ug/m3", "pm10": "ug/m3", "no2": "ug/m3", "o3": "ug/m3",
        "so2": "ug/m3", "co": "mg/m3", "aqi_nowcast": "index",
    }.get(name, "unknown")


class EvidenceBuilder:
    """Retrieves and aggregates stored environmental data into an EvidenceSet.

    Reads ONLY the canonical ``environmental_observations`` table — never the
    legacy flattened snapshot — so every evidence item carries the full
    provenance chain: source, dataset, product, processing level, acquisition
    time, averaging period, quality and uncertainty (Step 6).
    """

    POLLUTANTS = ("pm25", "pm10", "no2", "o3", "so2", "co")

    def __init__(self, db: Session):
        self.db = db

    def _known_locations(self) -> List[str]:
        rows = (
            self.db.query(EnvironmentalObservationRecord.location_name)
            .distinct()
            .limit(200)
            .all()
        )
        return [r[0] for r in rows if r[0]]

    def build(self, question: str) -> EvidenceSet:
        plan = plan_query(question, self._known_locations())
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=plan.window_hours)

        # ---- Step 8: unmonitored location must NOT widen to all locations ---
        if plan.location_status == "NOT_FOUND":
            name = plan.requested_location or "that location"
            supported = sorted({loc for loc in self._known_locations() if loc})
            return EvidenceSet(
                question=question,
                plan=plan,
                observations=[],
                derived_metrics=[],
                source_references=[],
                window_start=None,
                window_end=None,
                data_completeness=0.0,
                overall_confidence=0.0,
                location_status="NOT_FOUND",
                requested_location=plan.requested_location,
                notes=[
                    f"No monitored data available for {name}.",
                    (
                        "Supported regions: " + ", ".join(supported[:20])
                        if supported
                        else "No locations are monitored yet."
                    ),
                ],
            )

        query = (
            self.db.query(EnvironmentalObservationRecord)
            .filter(EnvironmentalObservationRecord.observed_at >= cutoff)
        )
        if plan.location_name:
            query = query.filter(
                EnvironmentalObservationRecord.location_name == plan.location_name
            )
        records = (
            query.order_by(EnvironmentalObservationRecord.observed_at.desc())
            .limit(500)
            .all()
        )

        series: Dict[str, List[float]] = {}
        units: Dict[str, str] = {}
        references: List[SourceReference] = []
        observation_payloads: List[Dict[str, Any]] = []
        wanted = set(plan.variables or [])

        for rec in records:
            if rec.value is None:
                continue
            variable = rec.variable
            series.setdefault(variable, []).append(float(rec.value))
            units.setdefault(variable, rec.unit)

            # Full provenance payload per observation (Steps 6+7): the LLM can
            # trace every number back to its source scene.
            observation_payloads.append(
                {
                    "variable": variable,
                    "value": rec.value,
                    "unit": rec.unit,
                    "source": rec.source,
                    "dataset": rec.dataset,
                    "product": rec.product,
                    "processing_level": rec.processing_level,
                    "location": rec.location_name,
                    "observed_at": (
                        rec.observed_at.isoformat() if rec.observed_at else None
                    ),
                    "acquisition_time": (
                        rec.acquisition_time.isoformat()
                        if rec.acquisition_time
                        else None
                    ),
                    "averaging_period": rec.averaging_period,
                    "quality": rec.quality,
                    "uncertainty": rec.uncertainty,
                    "provenance": rec.provenance or {},
                }
            )

            references.append(
                SourceReference(
                    source=rec.source,
                    dataset=rec.dataset or rec.product,
                    variable=variable,
                    observed_at=(
                        rec.observed_at.isoformat() if rec.observed_at else None
                    ),
                    averaging_period=rec.averaging_period,
                    provenance=rec.provenance or {},
                )
            )

        # ---- derived metrics ------------------------------------------------
        metrics: List[DerivedMetric] = []
        confidences: List[float] = []
        for name, values in series.items():
            if not values:
                continue
            mean = statistics.fmean(values)
            spread = statistics.pstdev(values) if len(values) > 1 else 0.0
            confidence = min(1.0, 0.6 + 0.1 * min(len(values), 4))
            confidences.append(confidence)
            metrics.append(
                DerivedMetric(
                    name=f"{name}_mean",
                    value=round(mean, 2),
                    unit=units.get(name, _unit_for(name)),
                    method="arithmetic_mean",
                    uncertainty=round(spread, 2),
                    confidence=confidence,
                    n_observations=len(values),
                )
            )

        # AQI nowcast from the most recent pollutant observations (labelled
        # honestly when inputs are instantaneous / non-standard EPA window).
        latest_pollutants: Dict[str, float] = {}
        pollutant_windows: Dict[str, str] = {}
        for rec in records:
            if rec.variable in self.POLLUTANTS and rec.value is not None:
                if rec.variable not in latest_pollutants:
                    latest_pollutants[rec.variable] = float(rec.value)
                    pollutant_windows[rec.variable] = rec.averaging_period
        if latest_pollutants and (not wanted or "aqi" in wanted):
            from app.core.aqi import calculate_overall_aqi

            record = calculate_overall_aqi(
                latest_pollutants, averaging_periods=pollutant_windows
            )
            metrics.append(
                DerivedMetric(
                    name="aqi_nowcast",
                    value=record["aqi"],
                    unit="index",
                    method="EPA breakpoint max-sub-index",
                    confidence=0.7,  # instantaneous inputs, non-standard window
                    n_observations=len(latest_pollutants),
                    methodology_status=record["methodology_status"],
                )
            )

        # ---- completeness / overall confidence ------------------------------
        expected = wanted or set(series.keys())
        completeness = (
            len([v for v in expected if v in series]) / len(expected)
            if expected and wanted
            else (1.0 if not wanted else 0.0)
        )
        overall_confidence = (
            statistics.fmean(confidences) if confidences else 0.5
        ) * (completeness if wanted else 1.0)

        notes: List[str] = []
        if not records:
            notes.append("No stored observations matched this question.")
        if plan.variables and completeness < 1.0:
            missing = sorted(expected - set(series.keys()))
            notes.append(f"Variables without data: {', '.join(missing)}")

        return EvidenceSet(
            question=question,
            plan=plan,
            observations=observation_payloads[:50],
            derived_metrics=metrics,
            source_references=references[:20],
            window_start=cutoff,
            window_end=now,
            data_completeness=round(completeness, 2),
            overall_confidence=round(overall_confidence, 2),
            location_status=plan.location_status,
            requested_location=plan.requested_location,
            notes=notes,
        )


# ---------------------------------------------------------------------------
# Step 9: two explicit AI modes.
#
#   GENERAL_CHAT            -> plain LLM chat (no evidence machinery)
#   ENVIRONMENTAL_ANALYSIS  -> EvidenceBuilder -> EvidenceSet -> grounded LLM
#
# An environmental question with NO usable evidence must never fall through
# to generic chat (that is exactly how hallucinated numbers happen) — it
# gets an explicit "insufficient environmental evidence" instruction instead.
# ---------------------------------------------------------------------------

GENERAL_CHAT = "GENERAL_CHAT"
ENVIRONMENTAL_ANALYSIS = "ENVIRONMENTAL_ANALYSIS"


def classify_mode(question: str) -> str:
    """Deterministically decide whether a message needs the evidence layer.

    A question is environmental when it mentions a monitored variable, AQI,
    or air/weather quality. Everything else is ordinary chat.
    """
    q = question.lower()
    for keywords in _VARIABLE_KEYWORDS.values():
        if any(k in q for k in keywords):
            return ENVIRONMENTAL_ANALYSIS
    if any(
        phrase in q
        for phrase in (
            "air quality", "pollution", "weather", "environment",
            "satellite", "emission", "monitor", "observation",
        )
    ):
        return ENVIRONMENTAL_ANALYSIS
    return GENERAL_CHAT


def format_evidence_context(evidence: EvidenceSet) -> str:
    """Render the EvidenceSet as a grounded system-prompt appendix.

    Every observation is rendered with its full measurement + provenance chain
    (value, unit, source dataset/product, acquisition time, quality,
    processing level) so the model can trace each conclusion back to data.
    """
    lines = [
        "You are answering using ONLY the verified evidence below.",
        "Cite sources as [source:variable @ timestamp].",
        "If the evidence does not cover something, say so explicitly.",
        "",
        f"Evidence window: {evidence.window_start:%Y-%m-%d %H:%M} UTC .. "
        f"{evidence.window_end:%Y-%m-%d %H:%M} UTC"
        if evidence.window_start
        else "Evidence window: none (no data)",
        "Location filter: "
        + (evidence.plan.location_name or "all monitored locations"),
        f"Data completeness: {evidence.data_completeness:.0%}; "
        f"overall confidence: {evidence.overall_confidence:.2f}",
    ]

    # ---- Actual observations with full provenance (Step 7) -----------------
    if evidence.observations:
        lines += ["", "Observations (trace every claim to these):"]
        for obs in evidence.observations[:15]:
            acquired = obs.get("acquisition_time") or obs.get("observed_at")
            parts = [
                f"{obs['variable']} = {obs['value']} {obs['unit']}",
                f"source: {obs['source']}",
            ]
            if obs.get("dataset"):
                parts.append(f"dataset: {obs['dataset']}")
            if obs.get("product"):
                parts.append(f"product: {obs['product']}")
            if obs.get("processing_level"):
                parts.append(f"processing: {obs['processing_level']}")
            if acquired:
                parts.append(f"acquired: {acquired}")
            parts.append(f"quality: {obs.get('quality', 'unknown')}")
            if obs.get("uncertainty") is not None:
                parts.append(f"uncertainty: +/-{obs['uncertainty']} {obs['unit']}")
            if obs.get("averaging_period"):
                parts.append(f"window: {obs['averaging_period']}")
            lines.append("- " + "; ".join(parts))

    if evidence.derived_metrics:
        lines += ["", "Derived metrics:"]
        for metric in evidence.derived_metrics:
            d = metric.to_dict()
            unc = f" +/- {d['uncertainty']}" if d["uncertainty"] is not None else ""
            inputs = ", ".join(
                o["variable"] for o in evidence.observations[:5]
            ) or "stored observations"
            lines.append(
                f"- {d['name']} = {d['value']} {d['unit']}{unc} "
                f"(method={d['method']}; n={d['n_observations']}, "
                f"confidence={d['confidence']}, "
                f"status={d['methodology_status']}; inputs: {inputs})"
            )
    if evidence.notes:
        lines += ["", "Data caveats:"]
        lines += [f"- {note}" for note in evidence.notes]
    if evidence.source_references:
        lines += ["", "Source references:"]
        seen = dict.fromkeys(ref.cite() for ref in evidence.source_references)
        lines += [f"- {cite}" for cite in seen]
    return "\n".join(lines)
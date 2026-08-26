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

from app.models.environmental_reading import EnvironmentalReading

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


@dataclass
class QueryPlan:
    """What the user is asking about, derived deterministically."""

    location_name: Optional[str] = None
    variables: List[str] = field(default_factory=list)
    window_hours: int = 72


def plan_query(question: str, known_locations: List[str]) -> QueryPlan:
    """Extract location + variables from a natural-language question.

    Deliberately rule-based (fast, auditable, zero-cost): the LLM only ever
    sees structured evidence and never guesses which data to fetch.
    """
    q = question.lower()
    plan = QueryPlan()

    for location in known_locations:
        if location.lower() in q:
            plan.location_name = location
            break

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
    notes: List[str] = field(default_factory=list)


def _unit_for(name: str) -> str:
    return {
        "temperature": "celsius", "feels_like": "celsius",
        "humidity": "percent", "pressure": "hPa", "wind_speed": "m/s",
        "pm25": "ug/m3", "pm10": "ug/m3", "no2": "ug/m3", "o3": "ug/m3",
        "so2": "ug/m3", "co": "mg/m3", "aqi_nowcast": "index",
    }.get(name, "unknown")


class EvidenceBuilder:
    """Retrieves and aggregates stored environmental data into an EvidenceSet."""

    def __init__(self, db: Session):
        self.db = db

    def _known_locations(self) -> List[str]:
        rows = (
            self.db.query(EnvironmentalReading.location_name)
            .distinct()
            .limit(200)
            .all()
        )
        return [r[0] for r in rows]

    def build(self, question: str) -> EvidenceSet:
        plan = plan_query(question, self._known_locations())
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=plan.window_hours)

        query = (
            self.db.query(EnvironmentalReading)
            .filter(EnvironmentalReading.recorded_at >= cutoff.replace(tzinfo=None))
        )
        if plan.location_name:
            query = query.filter(
                EnvironmentalReading.location_name == plan.location_name
            )
        readings = (
            query.order_by(EnvironmentalReading.recorded_at.desc()).limit(500).all()
        )

        series: Dict[str, List[float]] = {}
        references: List[SourceReference] = []
        observation_payloads: List[Dict[str, Any]] = []
        wanted = set(plan.variables or [])
        fields_of_interest = {
            "temperature", "feels_like", "humidity", "pressure",
            "wind_speed", "pm25", "pm10", "no2", "o3", "co", "so2",
        }
        for reading in readings:
            for name in fields_of_interest:
                value = getattr(reading, name, None)
                if value is None:
                    continue
                if wanted and name not in wanted and not (
                    {"aqi"} & wanted and name in ("pm25", "pm10", "no2")
                ):
                    continue
                series.setdefault(name, []).append(float(value))

            references.append(
                SourceReference(
                    source=reading.source,
                    dataset=None,
                    variable=",".join(sorted(series)) or "snapshot",
                    observed_at=reading.recorded_at.isoformat(),
                    averaging_period="unknown",
                    provenance={"reading_id": reading.id},
                )
            )
            observation_payloads.append(
                {
                    "location": reading.location_name,
                    "source": reading.source,
                    "recorded_at": reading.recorded_at.isoformat(),
                    "temperature": reading.temperature,
                    "humidity": reading.humidity,
                    "aqi": reading.aqi,
                    "pm25": reading.pm25,
                    "pm10": reading.pm10,
                }
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
                    unit=_unit_for(name),
                    method="arithmetic_mean",
                    uncertainty=round(spread, 2),
                    confidence=confidence,
                    n_observations=len(values),
                )
            )

        # AQI nowcast from the most recent pollutant snapshot (labelled honestly).
        latest_with_aqi = next((r for r in readings if r.aqi is not None), None)
        if latest_with_aqi and (not wanted or "aqi" in wanted):
            pollutants = {
                v: getattr(latest_with_aqi, v)
                for v in ("pm25", "pm10", "no2", "o3", "so2", "co")
                if getattr(latest_with_aqi, v) is not None
            }
            if pollutants:
                from app.core.aqi import calculate_overall_aqi

                record = calculate_overall_aqi(pollutants)
                metrics.append(
                    DerivedMetric(
                        name="aqi_nowcast",
                        value=record["aqi"],
                        unit="index",
                        method="EPA breakpoint max-sub-index",
                        confidence=0.7,  # instantaneous inputs, non-standard window
                        n_observations=len(pollutants),
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
        if not readings:
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
            notes=notes,
        )


def format_evidence_context(evidence: EvidenceSet) -> str:
    """Render the EvidenceSet as a grounded system-prompt appendix."""
    lines = [
        "You are answering using ONLY the verified evidence below.",
        "Cite sources as [source:variable @ timestamp].",
        "If the evidence does not cover something, say so explicitly.",
        "",
        f"Evidence window: {evidence.window_start:%Y-%m-%d %H:%M} UTC .. "
        f"{evidence.window_end:%Y-%m-%d %H:%M} UTC",
        "Location filter: "
        + (evidence.plan.location_name or "all monitored locations"),
        f"Data completeness: {evidence.data_completeness:.0%}; "
        f"overall confidence: {evidence.overall_confidence:.2f}",
    ]
    if evidence.derived_metrics:
        lines += ["", "Derived metrics:"]
        for metric in evidence.derived_metrics:
            d = metric.to_dict()
            unc = f" +/- {d['uncertainty']}" if d["uncertainty"] is not None else ""
            lines.append(
                f"- {d['name']} = {d['value']} {d['unit']}{unc} "
                f"(n={d['n_observations']}, confidence={d['confidence']}, "
                f"status={d['methodology_status']})"
            )
    if evidence.notes:
        lines += ["", "Data caveats:"]
        lines += [f"- {note}" for note in evidence.notes]
    if evidence.source_references:
        lines += ["", "Source references:"]
        seen = dict.fromkeys(ref.cite() for ref in evidence.source_references)
        lines += [f"- {cite}" for cite in seen]
    return "\n".join(lines)
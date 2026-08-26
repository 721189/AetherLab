"""Tests for the evidence-grounded intelligence layer (items 21-22)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.intelligence import (
    EvidenceBuilder,
    format_evidence_context,
    plan_query,
)


def seed(db_session):
    """Two locations, two timestamps, weather + pollutants."""
    from app.models.environmental_reading import EnvironmentalReading

    base = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = [
        EnvironmentalReading(
            location_name="Delhi", lat=28.61, lon=77.21, source="openaq",
            pm25=40.0, no2=50.0, aqi=113,
            recorded_at=base - timedelta(hours=1),
        ),
        EnvironmentalReading(
            location_name="Delhi", lat=28.61, lon=77.21, source="openweather",
            temperature=30.0, humidity=55, recorded_at=base,
        ),
        EnvironmentalReading(
            location_name="Mumbai", lat=19.07, lon=72.87, source="openweather",
            temperature=27.0, recorded_at=base,
        ),
    ]
    db_session.add_all(rows)
    db_session.commit()


class TestQueryPlanner:
    def test_extracts_location_and_variables(self):
        plan = plan_query("How hot is Delhi this week?", ["Delhi", "Mumbai"])
        assert plan.location_name == "Delhi"
        assert "temperature" in plan.variables
        assert plan.window_hours == 24 * 7

    def test_unknown_location_yields_open_plan(self):
        plan = plan_query("air quality overview", ["Delhi"])
        assert plan.location_name is None
        assert "aqi" in plan.variables


class TestEvidenceBuilder:
    def test_builds_derived_metrics_with_uncertainty(self, db_session):
        seed(db_session)
        evidence = EvidenceBuilder(db_session).build("temperature trend in Delhi")

        names = {m.name for m in evidence.derived_metrics}
        assert "temperature_mean" in names
        temp = next(m for m in evidence.derived_metrics if m.name == "temperature_mean")
        assert temp.value == 30.0
        assert temp.n_observations >= 1
        assert 0 < temp.confidence <= 1.0

    def test_aqi_nowcast_carries_methodology_status(self, db_session):
        seed(db_session)
        evidence = EvidenceBuilder(db_session).build("Delhi air quality (AQI)")
        nowcast = next(
            (m for m in evidence.derived_metrics if m.name == "aqi_nowcast"), None
        )
        assert nowcast is not None
        # Instantaneous inputs -> honestly labelled non-standard.
        assert nowcast.methodology_status == "non_standard_averaging"
        assert nowcast.confidence < 1.0

    def test_location_filtering_excludes_other_cities(self, db_session):
        seed(db_session)
        evidence = EvidenceBuilder(db_session).build("humidity in Delhi")
        locations = {o["location"] for o in evidence.observations}
        assert locations <= {"Delhi"}

    def test_no_data_reports_caveat_and_zero_confidence(self, db_session):
        evidence = EvidenceBuilder(db_session).build("temperature in Delhi")
        assert evidence.observations == []
        assert any("No stored observations" in n for n in evidence.notes)

    def test_completeness_reported_for_missing_variables(self, db_session):
        seed(db_session)
        evidence = EvidenceBuilder(db_session).build("pm25 and o3 in Delhi")
        assert 0.0 <= evidence.data_completeness < 1.0
        assert any("without data" in n for n in evidence.notes)


class TestGroundedContext:
    def test_context_includes_citations_and_confidence(self, db_session):
        seed(db_session)
        evidence = EvidenceBuilder(db_session).build("air quality in Delhi")
        context = format_evidence_context(evidence)
        assert "overall confidence" in context
        assert "Source references:" in context
        assert "openaq" in context or "openweather" in context

    def test_chat_flow_injects_evidence_into_system_prompt(self, db_session):
        seed(db_session)
        from app.services.conversation_service import ConversationService

        service = ConversationService(db_session)
        grounded = service._grounded_system_prompt(
            "temperature in Delhi", "base prompt"
        )
        assert "GROUNDING EVIDENCE" in grounded
        assert grounded.startswith("base prompt")

    def test_grounded_prompt_degrades_gracefully_without_data(self, db_session):
        from app.services.conversation_service import ConversationService

        service = ConversationService(db_session)
        prompt = service._grounded_system_prompt(
            "completely unrelated question about quantum physics", "base"
        )
        # No relevant observations -> plain prompt, no grounding block.
        assert prompt == "base"


class TestUncertaintyModel:
    def test_observation_schema_has_uncertainty_fields(self):
        from app.schemas.environmental import EnvironmentalObservation

        obs = EnvironmentalObservation(
            source="nasa",
            variable="temperature",
            value=31.2,
            unit="celsius",
            latitude=0.0,
            longitude=0.0,
            uncertainty=1.0,
            confidence=0.8,
            quality_score=80.0,
            data_completeness=2 / 3,
        )
        assert obs.confidence == 0.8
        assert obs.quality_score == 80.0

    def test_confidence_bounds_are_enforced(self):
        from pydantic import ValidationError

        from app.schemas.environmental import EnvironmentalObservation

        with pytest.raises(ValidationError):
            EnvironmentalObservation(
                source="openaq", variable="pm25", value=10.0, unit="ug/m3",
                latitude=0.0, longitude=0.0, confidence=1.5,  # out of bounds
            )

    def test_persistence_roundtrips_uncertainty(self, db_session):
        from app.schemas.environmental import EnvironmentalObservation
        from app.services.environmental import EnvironmentalObservationRepository

        repo = EnvironmentalObservationRepository(db_session)
        record = repo.create_from(
            EnvironmentalObservation(
                source="openaq", variable="pm25", value=12.5, unit="ug/m3",
                latitude=0.0, longitude=0.0,
                uncertainty=2.0, confidence=0.85, quality_score=85.0,
                data_completeness=0.5,
            )
        )
        assert record.confidence == 0.85
        assert record.uncertainty == 2.0
        assert record.data_completeness == 0.5
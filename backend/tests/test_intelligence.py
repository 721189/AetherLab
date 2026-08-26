"""Tests for the evidence-grounded intelligence layer (items 21-22, Phase 4)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.services.intelligence import (
    ENVIRONMENTAL_ANALYSIS,
    GENERAL_CHAT,
    EvidenceBuilder,
    classify_mode,
    format_evidence_context,
    plan_query,
)


def _obs(variable, value, unit, source, location, lat, lon, **kw):
    """Build a canonical EnvironmentalObservationRecord for tests."""
    from app.models.environmental_observation import (
        EnvironmentalObservationRecord,
    )

    return EnvironmentalObservationRecord(
        variable=variable,
        value=value,
        unit=unit,
        source=source,
        location_name=location,
        latitude=lat,
        longitude=lon,
        observed_at=kw.pop(
            "observed_at", datetime.now(timezone.utc) - timedelta(hours=1)
        ),
        averaging_period=kw.pop("averaging_period", "unknown"),
        quality=kw.pop("quality", "unverified"),
        provenance=kw.pop("provenance", {}),
        quality_flags={},
        observation_hash=kw.pop("observation_hash", None) or uuid4().hex,
        **kw,
    )


def seed(db_session):
    """Two locations; weather + pollutants as CANONICAL observations."""
    rows = [
        _obs("pm25", 40.0, "ug/m3", "openaq", "Delhi", 28.61, 77.21,
             provenance={"site_id": "DL-1"}),
        _obs("no2", 50.0, "ug/m3", "openaq", "Delhi", 28.61, 77.21),
        _obs("temperature", 30.0, "celsius", "openweather", "Delhi",
             28.61, 77.21),
        _obs("humidity", 55.0, "percent", "openweather", "Delhi",
             28.61, 77.21),
        # Sentinel-style satellite observation with full provenance.
        _obs("no2_column", 1.8e-4, "mol/m2", "copernicus", "Delhi",
             28.61, 77.21,
             dataset="SENTINEL-5P", product="L2__NO2___",
             processing_level="L2", acquisition_time=datetime.now(timezone.utc),
             provenance={"scene_id": "S5P_TEST_SCENE"}),
        _obs("temperature", 27.0, "celsius", "openweather", "Mumbai",
             19.07, 72.87),
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
        assert plan.location_status == "OPEN"


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
        # Nothing seeded -> "Delhi" is an UNMONITORED location (Step 8), so
        # the builder must refuse to query every location and say so.
        evidence = EvidenceBuilder(db_session).build("temperature in Delhi")
        assert evidence.observations == []
        assert evidence.location_status == "NOT_FOUND"
        assert any(
            "No monitored data available for Delhi" in n for n in evidence.notes
        )

    def test_open_query_with_empty_db_reports_no_stored_observations(
        self, db_session
    ):
        """A location-less environmental question over an empty database."""
        evidence = EvidenceBuilder(db_session).build("how is the air quality?")
        assert evidence.location_status == "OPEN"
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


class TestCanonicalEvidenceSource:
    """Step 6: EvidenceBuilder reads canonical observations, not readings."""

    def test_observation_payloads_carry_full_provenance(self, db_session):
        seed(db_session)
        evidence = EvidenceBuilder(db_session).build("air quality in Delhi")
        assert evidence.observations, "expected observations from canonical table"
        required = {
            "source", "dataset", "product", "variable", "value", "unit",
            "location", "observed_at", "acquisition_time",
            "averaging_period", "quality", "uncertainty", "provenance",
        }
        for obs in evidence.observations:
            assert required <= set(obs.keys()), f"missing keys in {obs}"

    def test_satellite_provenance_survives_into_evidence(self, db_session):
        seed(db_session)
        evidence = EvidenceBuilder(db_session).build("air quality in Delhi")
        s5p = next(
            (o for o in evidence.observations if o["source"] == "copernicus"),
            None,
        )
        assert s5p is not None
        assert s5p["dataset"] == "SENTINEL-5P"
        assert s5p["product"] == "L2__NO2___"
        assert s5p["processing_level"] == "L2"
        assert s5p["acquisition_time"] is not None

    def test_series_built_from_variable_rows_not_flat_columns(self, db_session):
        """Non-weather variables (e.g. no2_column) need no schema change."""
        seed(db_session)
        evidence = EvidenceBuilder(db_session).build("air quality in Delhi")
        variables = {o["variable"] for o in evidence.observations}
        assert "no2_column" in variables


class TestLLMContextTraceability:
    """Step 7: the LLM sees actual observations with provenance chains."""

    def test_context_lists_values_units_sources_and_processing(self, db_session):
        seed(db_session)
        evidence = EvidenceBuilder(db_session).build("air quality in Delhi")
        context = format_evidence_context(evidence)
        assert "pm25 = 40.0 ug/m3" in context
        assert "source: openaq" in context
        assert "dataset: SENTINEL-5P" in context
        assert "processing: L2" in context
        assert "quality:" in context

    def test_derived_metrics_state_their_inputs_and_method(self, db_session):
        seed(db_session)
        evidence = EvidenceBuilder(db_session).build("temperature in Delhi")
        context = format_evidence_context(evidence)
        metric = next(
            m for m in evidence.derived_metrics if m.name == "temperature_mean"
        )
        assert metric.method == "arithmetic_mean"
        assert "method=arithmetic_mean" in context
        assert "inputs:" in context


class TestUnknownLocationBehaviour:
    """Step 8: unmonitored locations must NOT silently query everything."""

    def test_unmonitored_location_is_detected_as_not_found(self, db_session):
        seed(db_session)  # Delhi / Mumbai only — no London
        evidence = EvidenceBuilder(db_session).build("NO2 in London?")
        assert evidence.location_status == "NOT_FOUND"
        assert evidence.requested_location == "London"
        assert evidence.observations == []
        assert any(
            "No monitored data available for London" in n for n in evidence.notes
        )

    def test_unmonitored_location_lists_supported_regions(self, db_session):
        seed(db_session)
        evidence = EvidenceBuilder(db_session).build("NO2 in London?")
        joined = " ".join(evidence.notes)
        assert "Supported regions" in joined
        assert "Delhi" in joined and "Mumbai" in joined

    def test_no_location_mentioned_stays_open_and_queries_all(self, db_session):
        seed(db_session)
        evidence = EvidenceBuilder(db_session).build("how is the air quality?")
        assert evidence.location_status == "OPEN"
        assert evidence.observations


class TestGroundedVsGenericModes:
    """Step 9: GENERAL_CHAT and ENVIRONMENTAL_ANALYSIS are separate paths."""

    def test_non_environmental_question_is_general_chat(self):
        assert classify_mode("what is the capital of France?") == GENERAL_CHAT
        assert classify_mode("write me a haiku about coffee") == GENERAL_CHAT

    def test_environmental_question_routes_to_analysis_mode(self):
        assert classify_mode("how bad is the air quality in Delhi?") == (
            ENVIRONMENTAL_ANALYSIS
        )
        assert classify_mode("is it hot in Mumbai today?") == ENVIRONMENTAL_ANALYSIS
        assert classify_mode("show me satellite NO2 data") == ENVIRONMENTAL_ANALYSIS

    def test_env_question_without_data_refuses_to_hallucinate(self, db_session):
        from app.services.conversation_service import ConversationService

        service = ConversationService(db_session)  # nothing seeded
        # No location named -> OPEN query over an empty DB -> refusal prompt.
        prompt = service._grounded_system_prompt(
            "what is the current air quality?", "base"
        )
        assert "ENVIRONMENTAL ANALYSIS MODE" in prompt
        assert "Insufficient environmental evidence" in prompt
        assert "do NOT fabricate" in prompt

    def test_unmonitored_location_prompt_names_the_gap(self, db_session):
        from app.services.conversation_service import ConversationService

        seed(db_session)
        service = ConversationService(db_session)
        prompt = service._grounded_system_prompt("NO2 in London?", "base")
        assert "No monitored data available for London" in prompt
        assert "Do NOT invent or estimate values" in prompt

    def test_generic_chat_never_touches_the_evidence_layer(self, db_session):
        from app.services.conversation_service import ConversationService

        service = ConversationService(db_session)
        prompt = service._grounded_system_prompt("tell me a joke", "base")
        assert prompt == "base"
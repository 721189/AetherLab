"""Tests for the US EPA Air Quality Index implementation.

Reference values are computed from the official EPA breakpoint tables
(https://www.airnow.gov/aqi/aqi-basics/). These are the kind of known-answer
tests an AQI calculator needs before it can be trusted in production.
"""

import pytest

from app.core.aqi import (
    aqi_category,
    calculate_aqi,
    calculate_aqi_detailed,
    calculate_overall_aqi,
    convert_to_index_unit,
)


class TestPM25KnownValues:
    """PM2.5 (ug/m3, 24h): breakpoints 0-9.0 | 9.1-35.4 | 35.5-125.4 ..."""

    def test_zero_is_zero(self):
        assert calculate_aqi("pm25", 0.0) == 0

    @pytest.mark.parametrize(
        "conc,expected",
        [
            (9.0, 50),      # Good/Moderate boundary
            (12.0, 56),     # interpolation inside 9.1-35.4
            (35.4, 100),    # Moderate/USG boundary
            (35.5, 101),    # first step into USG
            (55.5, 112),    # interpolation inside 35.5-125.4
            (125.4, 150),
            (125.5, 151),
            (225.5, 201),
            (425.4, 500),   # last published breakpoint
            (425.5, None),  # beyond the table -> NO extrapolation
            (900.0, None),  # beyond the table -> flagged out_of_standard_range
        ],
    )
    def test_reference_points(self, conc, expected):
        assert calculate_aqi("pm25", conc) == expected


class TestOtherPollutants:
    def test_pm10_boundaries(self):
        assert calculate_aqi("pm10", 54) == 50
        assert calculate_aqi("pm10", 154) == 100
        assert calculate_aqi("pm10", 155) == 101

    def test_o3_ppb(self):
        assert calculate_aqi("o3", 54, unit="ppb") == 50
        # 70 ppb is the top of the Moderate band.
        assert calculate_aqi("o3", 70, unit="ppb") == 100
        assert calculate_aqi("o3", 71, unit="ppb") == 101

    def test_no2_ppb(self):
        assert calculate_aqi("no2", 53, unit="ppb") == 50
        assert calculate_aqi("no2", 100, unit="ppb") == 100

    def test_so2_ppb(self):
        assert calculate_aqi("so2", 35, unit="ppb") == 50

    def test_co_ppm(self):
        assert calculate_aqi("co", 4.4, unit="ppm") == 50
        assert calculate_aqi("co", 9.4, unit="ppm") == 100


class TestUnitConversion:
    def test_no2_mass_to_ppb(self):
        # 18.8 ug/m3 = 10 ppb -> well inside Good band.
        ppb = convert_to_index_unit("no2", 18.8, "ug/m3")
        assert ppb == pytest.approx(10.0)
        assert calculate_aqi("no2", 18.8, unit="ug/m3") == calculate_aqi(
            "no2", 10, unit="ppb"
        )

    def test_o3_default_unit_is_ugm3(self):
        # Default for gases is ug/m3: 196 ug/m3 == 100 ppb.
        assert calculate_aqi("o3", 196.0) == calculate_aqi(
            "o3", 100, unit="ppb"
        )

    def test_co_mgm3_to_ppm(self):
        # 11.45 mg/m3 == 10 ppm.
        ppm = convert_to_index_unit("co", 11.45, "mg/m3")
        assert ppm == pytest.approx(10.0)
        assert calculate_aqi("co", 11.45, unit="mg/m3") == calculate_aqi(
            "co", 10, unit="ppm"
        )

    def test_invalid_units_raise(self):
        with pytest.raises(ValueError):
            convert_to_index_unit("pm25", 10, "ppb")
        with pytest.raises(ValueError):
            convert_to_index_unit("no2", 10, "mg/m3")
        with pytest.raises(ValueError):
            calculate_aqi("ozone", 10)


class TestOverallAQI:
    def test_max_of_sub_indices(self):
        # pm25 40 -> ~113 dominates over pm10 60 (~53).
        overall = calculate_overall_aqi({"pm25": 40.0, "pm10": 60.0})
        assert overall["aqi"] == calculate_aqi("pm25", 40.0)
        assert overall["aqi"] > 100
        assert overall["dominant_pollutant"] == "pm25"

    def test_missing_pollutants_are_skipped(self):
        assert calculate_overall_aqi({"pm25": None, "no2": None})["aqi"] is None
        # Mixed present/missing still works.
        assert calculate_overall_aqi({"pm25": None, "pm10": 54})["aqi"] == 50

    def test_empty(self):
        record = calculate_overall_aqi({})
        assert record["aqi"] is None
        assert record["methodology_status"] == "no_usable_data"

    def test_overall_record_carries_methodology_status(self):
        record = calculate_overall_aqi(
            {"pm25": 12.0},
            averaging_periods={"pm25": "24-hour"},
        )
        assert record["methodology_status"] == "standard"
        sub = record["sub_indices"][0]
        assert sub["averaging_period"] == "24-hour"


class TestTruncationRules:
    """EPA prescribes truncation (never rounding up) before the lookup."""

    def test_pm25_truncates_to_one_decimal(self):
        from app.core.aqi import preprocess_concentration

        assert preprocess_concentration("pm25", 12.349) == 12.3   # not 12.3->12.35
        assert preprocess_concentration("pm25", 12.35) == 12.3    # truncates DOWN

    def test_pm10_truncates_to_integer(self):
        from app.core.aqi import preprocess_concentration

        assert preprocess_concentration("pm10", 154.9) == 154.0

    def test_o3_truncates_to_integer_ppb(self):
        from app.core.aqi import preprocess_concentration

        assert preprocess_concentration("o3", 70.9) == 70.0

    def test_truncation_affects_boundary_results(self):
        # 9.05 ug/m3 truncates to 9.0 -> exactly the Good/Moderate boundary.
        assert calculate_aqi("pm25", 9.05) == 50


class TestOutOfStandardRange:
    def test_beyond_table_returns_no_value_and_flags_it(self):
        result = calculate_aqi_detailed("o3", 250, unit="ppb",
                                        averaging_period="8h")
        assert result.aqi is None  # EPA table ends at 200 ppb
        assert result.methodology_status == "out_of_standard_range"
        assert "no extrapolation performed" in " ".join(result.notes)

    def test_pm25_beyond_425_is_flagged_not_capped(self):
        result = calculate_aqi_detailed("pm25", 500.0)
        assert result.aqi is None
        assert result.methodology_status == "out_of_standard_range"

    def test_within_table_still_standard(self):
        result = calculate_aqi_detailed("pm25", 12.0)
        assert result.aqi == 56
        assert result.methodology_status == "non_standard_averaging"  # no window asserted

        standard = calculate_aqi_detailed(
            "pm25", 12.0, averaging_period="24-hour"
        )
        assert standard.methodology_status == "standard"


class TestAveragingPeriodSemantics:
    def test_wrong_window_raises(self):
        with pytest.raises(ValueError):
            calculate_aqi("pm25", 12.0, averaging_period="1-hour")

    def test_correct_window_accepted(self):
        assert calculate_aqi("pm25", 12.0, averaging_period="24h") == 56

    def test_missing_window_flags_non_standard(self):
        result = calculate_aqi_detailed("no2", 100, unit="ppb")
        assert result.methodology_status == "non_standard_averaging"

    def test_overall_demotes_on_any_nonstandard_input(self):
        record = calculate_overall_aqi(
            {"pm25": 12.0, "pm10": 50.0},
            averaging_periods={"pm25": "24-hour"},  # pm10 window unknown
        )
        assert record["methodology_status"] == "non_standard_averaging"


class TestValidation:
    def test_missing_value_returns_none(self):
        assert calculate_aqi("pm25", None) is None

    def test_negative_concentration_raises(self):
        with pytest.raises(ValueError):
            calculate_aqi("pm25", -1)

    def test_unsupported_standard_raises(self):
        with pytest.raises(LookupError):
            calculate_aqi("pm25", 10, standard="EU")

    def test_methodology_is_explicit_at_call_site(self):
        # The standard kwarg exists so methodology is never implicit.
        assert calculate_aqi("pm25", 12.0, standard="EPA") == 56


class TestCategory:
    @pytest.mark.parametrize(
        "aqi,label",
        [
            (0, "Good"),
            (50, "Good"),
            (51, "Moderate"),
            (100, "Moderate"),
            (101, "Unhealthy for Sensitive Groups"),
            (150, "Unhealthy for Sensitive Groups"),
            (200, "Unhealthy"),
            (300, "Very Unhealthy"),
            (301, "Hazardous"),
            (None, "Unknown"),
        ],
    )
    def test_labels(self, aqi, label):
        assert aqi_category(aqi) == label

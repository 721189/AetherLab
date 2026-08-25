"""Tests for the US EPA Air Quality Index implementation.

Reference values are computed from the official EPA breakpoint tables
(https://www.airnow.gov/aqi/aqi-basics/). These are the kind of known-answer
tests an AQI calculator needs before it can be trusted in production.
"""

import pytest

from app.core.aqi import (
    aqi_category,
    calculate_aqi,
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
            (500.0, 500),   # capped at table max
            (900.0, 500),   # beyond-table clamp
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
        assert overall == calculate_aqi("pm25", 40.0)
        assert overall > 100

    def test_missing_pollutants_are_skipped(self):
        assert calculate_overall_aqi({"pm25": None, "no2": None}) is None
        # Mixed present/missing still works.
        assert calculate_overall_aqi({"pm25": None, "pm10": 54}) == 50

    def test_empty(self):
        assert calculate_overall_aqi({}) is None


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

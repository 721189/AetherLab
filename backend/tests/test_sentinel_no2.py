"""Scientific-integrity tests for Sentinel-5P / TROPOMI NO2 aggregation.

These verify the EO processing core (Step 14 pipeline):

    raw NO2 pixels -> quality filter -> invalid pixels removed
                   -> AOI filter      -> spatial aggregation -> canonical value

The aggregation runs on plain NumPy arrays so the full pipeline is unit-tested
without downloading a single Sentinel-5P product.
"""

import numpy as np
import pytest

from app.services.processing.sentinel_no2 import (
    DEFAULT_QA_THRESHOLD,
    NO2_DATA_VAR,
    NO2_LAT_VAR,
    NO2_LON_VAR,
    NO2_QA_VAR,
    aggregate_tropomi_no2,
    extract_no2_from_arrays,
)


def _grid_around(target_lat, target_lon, n=9, step_km=2.0):
    """n x n pixel grid of lat/lon centred on a target point."""
    lat_step = step_km * 0.009
    lon_step = step_km * 0.011
    offs = np.arange(n) - n // 2
    lats = target_lat + offs * lat_step
    lons = target_lon + offs * lon_step
    lat, lon = np.meshgrid(lats, lons)
    return lat.ravel(), lon.ravel()


def _no2_product(
    target_lat=28.61,
    target_lon=77.21,
    n=9,
    good_qa=0.85,
    bad_qa=0.1,
    value=1.2e-4,
):
    """Synthetic TROPOMI product: values, qa, lat, lon as flat 1-D arrays."""
    lat, lon = _grid_around(target_lat, target_lon, n=n)
    values = np.full(lat.size, value, dtype=float)
    qa = np.full(lat.size, good_qa, dtype=float)
    values_full = np.append(values, value)
    qa_full = np.append(qa, bad_qa)
    lat_full = np.append(lat, target_lat + 5.0)  # ~550 km away
    lon_full = np.append(lon, target_lon)
    return {
        NO2_DATA_VAR: values_full,
        NO2_QA_VAR: qa_full,
        NO2_LAT_VAR: lat_full,
        NO2_LON_VAR: lon_full,
    }
class TestQualityFilter:
    """Quality flagging must happen BEFORE any pixels are combined."""

    def test_bad_qa_pixel_is_discarded_and_reported(self):
        product = _no2_product()
        result = aggregate_tropomi_no2(
            product[NO2_DATA_VAR],
            product[NO2_QA_VAR],
            product[NO2_LAT_VAR],
            product[NO2_LON_VAR],
            target_lat=28.61,
            target_lon=77.21,
        )
        # 81 in-grid pixels pass, the 1 distant bad-QA pixel must be rejected.
        assert result["methodology"]["pixels_input"] == 82
        assert result["methodology"]["pixels_used"] == 81
        assert result["methodology"]["pixels_rejected"] == 1
        assert result["value"] == pytest.approx(1.2e-4)

    def test_threshold_above_all_qa_raises(self):
        product = _no2_product(good_qa=0.85)
        with pytest.raises(ValueError, match="No valid TROPOMI NO2 pixels"):
            aggregate_tropomi_no2(
                product[NO2_DATA_VAR],
                product[NO2_QA_VAR],
                product[NO2_LAT_VAR],
                product[NO2_LON_VAR],
                target_lat=28.61,
                target_lon=77.21,
                qa_threshold=0.95,
            )

    def test_nan_pixels_are_excluded_from_aggregation(self):
        lat, lon = _grid_around(28.61, 77.21, n=5)
        values = np.full(lat.size, 1.2e-4, dtype=float)
        qa = np.full(lat.size, 0.9, dtype=float)
        values[3] = np.nan
        qa[3] = np.nan

        result = aggregate_tropomi_no2(
            values, qa, lat, lon, target_lat=28.61, target_lon=77.21
        )
        assert result["methodology"]["pixels_used"] == 24  # 25 - 1 non-finite
        assert result["value"] == pytest.approx(1.2e-4)


class TestAoiFilter:
    def test_distant_valid_pixels_outside_radius_are_excluded(self):
        product = _no2_product()
        # Tight radius keeps only the central ~5x5 block of the 9x9 grid.
        result = aggregate_tropomi_no2(
            product[NO2_DATA_VAR],
            product[NO2_QA_VAR],
            product[NO2_LAT_VAR],
            product[NO2_LON_VAR],
            target_lat=28.61,
            target_lon=77.21,
            max_km=5.0,
        )
        assert result["methodology"]["aoi_radius_km"] == 5.0
        assert result["methodology"]["pixels_used"] < 81
        assert result["value"] == pytest.approx(1.2e-4)

    def test_target_away_from_any_pixel_raises(self):
        product = _no2_product()
        with pytest.raises(ValueError, match="within"):
            aggregate_tropomi_no2(
                product[NO2_DATA_VAR],
                product[NO2_QA_VAR],
                product[NO2_LAT_VAR],
                product[NO2_LON_VAR],
                target_lat=0.0,
                target_lon=0.0,
            )
class TestAggregationMethodology:
    def test_median_is_reported_in_methodology(self):
        product = _no2_product()
        result = aggregate_tropomi_no2(
            product[NO2_DATA_VAR],
            product[NO2_QA_VAR],
            product[NO2_LAT_VAR],
            product[NO2_LON_VAR],
            28.61,
            77.21,
        )
        assert result["methodology"]["aggregation"] == "median"
        assert result["unit"] == "mol/m2"

    def test_mean_method_option(self):
        product = _no2_product()
        result = aggregate_tropomi_no2(
            product[NO2_DATA_VAR],
            product[NO2_QA_VAR],
            product[NO2_LAT_VAR],
            product[NO2_LON_VAR],
            28.61,
            77.21,
            method="mean",
        )
        assert result["methodology"]["aggregation"] == "mean"
        assert result["value"] == pytest.approx(1.2e-4)

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError, match="equal-length"):
            aggregate_tropomi_no2(
                np.array([1.0, 2.0]),
                np.array([0.9]),
                np.array([28.0]),
                np.array([77.0]),
                28.61,
                77.21,
            )


class TestExtractSeam:
    """extract_no2_from_arrays (the NetCDF seam) must be honest."""

    def test_extract_delegates_to_core(self):
        product = _no2_product()
        direct = aggregate_tropomi_no2(
            product[NO2_DATA_VAR],
            product[NO2_QA_VAR],
            product[NO2_LAT_VAR],
            product[NO2_LON_VAR],
            28.61,
            77.21,
        )
        extracted = extract_no2_from_arrays(product, 28.61, 77.21)
        assert extracted["value"] == pytest.approx(direct["value"])
        assert extracted["methodology"] == direct["methodology"]

    def test_missing_no2_variable_raises_loudly(self):
        product = _no2_product()
        del product[NO2_DATA_VAR]
        with pytest.raises(ValueError, match="required variable"):
            extract_no2_from_arrays(product, 28.61, 77.21)

    def test_missing_qa_layer_refuses_to_aggregate_unfiltered(self):
        product = _no2_product()
        del product[NO2_QA_VAR]
        with pytest.raises(ValueError, match="refusing to aggregate unfiltered"):
            extract_no2_from_arrays(product, 28.61, 77.21)
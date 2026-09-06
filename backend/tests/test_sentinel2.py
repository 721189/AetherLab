"""Tests for Sentinel-2 NDVI processing + temporal change detection."""

import math

import numpy as np
import pytest

from app.services.processing.sentinel2 import (
    NDVIBaseline,
    NDVIResult,
    aggregate_ndvi,
    analyze_temporal_change,
    compute_ndvi,
)


class TestComputeNdvi:
    def test_basic_ndvi(self):
        red = [0.1, 0.1, 0.1]
        nir = [0.8, 0.8, 0.8]
        ndvi = compute_ndvi(red, nir)
        expected = (0.8 - 0.1) / (0.8 + 0.1)
        np.testing.assert_allclose(ndvi, [expected] * 3, atol=1e-9)

    def test_water_ndvi(self):
        red = [0.4, 0.5]
        nir = [0.1, 0.2]
        ndvi = compute_ndvi(red, nir)
        assert ndvi[0] < 0
        assert ndvi[1] < 0

    def test_zero_denominator_becomes_nan(self):
        red = [0.0, 0.0]
        nir = [0.0, 0.0]
        ndvi = compute_ndvi(red, nir)
        assert all(np.isnan(ndvi))

    def test_valid_mask(self):
        red = [0.1, 0.1]
        nir = [0.8, 0.8]
        ndvi = compute_ndvi(red, nir, valid=[True, False])
        assert np.isfinite(ndvi[0])
        assert np.isnan(ndvi[1])

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError, match="identical shape"):
            compute_ndvi([0.1, 0.2], [0.8])

    def test_2d_input_flattens(self):
        red = [[0.1, 0.2], [0.1, 0.2]]
        nir = [[0.8, 0.7], [0.8, 0.7]]
        ndvi = compute_ndvi(red, nir)
        assert ndvi.ndim == 1
        assert ndvi.shape[0] == 4

    def test_mixed_valid_invalid_pixels(self):
        # index 0: normal (0.8-0.1)/(0.8+0.1) = finite
        # index 1: nir + red = 0 -> NaN
        # index 2: nir + red = 0 -> NaN
        # index 3: normal (0.6-0.1)/(0.6+0.1) = finite
        red = [0.1, 0.2, 0.0, 0.1]
        nir = [0.8, -0.2, 0.0, 0.6]
        ndvi = compute_ndvi(red, nir)
        assert np.isfinite(ndvi[0])
        assert np.isnan(ndvi[1])
        assert np.isnan(ndvi[2])
        assert np.isfinite(ndvi[3])
class TestAggregateNdvi:
    def test_full_scene(self):
        ndvi = compute_ndvi([0.1, 0.1, 0.1], [0.8, 0.8, 0.8])
        result = aggregate_ndvi(ndvi)
        assert isinstance(result, NDVIResult)
        assert result.pixels_input == 3
        assert result.pixels_used == 3
        assert result.pixels_rejected == 0
        assert result.unit == "index"

    def test_partial_rejection(self):
        raw = np.array([0.5, 0.6, np.nan, 0.7, np.nan])
        result = aggregate_ndvi(raw)
        assert result.pixels_input == 5
        assert result.pixels_used == 3
        assert result.pixels_rejected == 2
        assert result.mean == pytest.approx(np.mean([0.5, 0.6, 0.7]))
        assert result.minimum == pytest.approx(0.5)
        assert result.maximum == pytest.approx(0.7)

    def test_all_rejected_raises(self):
        raw = np.array([np.nan, np.nan])
        with pytest.raises(ValueError, match="No usable NDVI pixels"):
            aggregate_ndvi(raw)

    def test_single_pixel(self):
        raw = np.array([0.42])
        result = aggregate_ndvi(raw)
        assert result.mean == pytest.approx(0.42)
        assert result.std == pytest.approx(0.0)

    def test_to_dict_rounds(self):
        raw = np.array([0.12345678])
        result = aggregate_ndvi(raw)
        d = result.to_dict()
        assert d["mean"] == 0.1235
class TestAnalyzeTemporalChange:
    def _current(self, mean):
        return NDVIResult(
            mean=mean, median=mean, minimum=mean, maximum=mean,
            std=0.0, pixel_count=10, pixels_input=10, pixels_used=10,
            pixels_rejected=0,
        )

    def test_no_change(self):
        current = self._current(0.5)
        baseline = NDVIBaseline(mean=0.5, std=0.1, n_observations=10)
        result = analyze_temporal_change(current, baseline)
        assert result.delta_ndvi == pytest.approx(0.0)
        assert result.z_score == pytest.approx(0.0)
        assert result.anomaly is False

    def test_significant_increase_anomaly(self):
        current = self._current(0.8)
        baseline = NDVIBaseline(mean=0.3, std=0.1, n_observations=10)
        result = analyze_temporal_change(current, baseline)
        assert result.delta_ndvi == pytest.approx(0.5)
        assert result.z_score == pytest.approx(5.0)
        assert result.anomaly is True

    def test_significant_decrease_anomaly(self):
        current = self._current(0.1)
        baseline = NDVIBaseline(mean=0.6, std=0.1, n_observations=10)
        result = analyze_temporal_change(current, baseline)
        assert result.delta_ndvi == pytest.approx(-0.5)
        assert result.anomaly is True

    def test_moderate_change_not_anomaly(self):
        current = self._current(0.55)
        baseline = NDVIBaseline(mean=0.5, std=0.1, n_observations=10)
        result = analyze_temporal_change(current, baseline)
        assert result.z_score == pytest.approx(0.5)
        assert result.anomaly is False

    def test_zero_baseline_mean(self):
        current = self._current(0.3)
        baseline = NDVIBaseline(mean=0.0, std=0.1, n_observations=10)
        result = analyze_temporal_change(current, baseline)
        assert math.isnan(result.percentage_change)
        assert result.delta_ndvi == pytest.approx(0.3)

    def test_zero_baseline_std_with_movement(self):
        current = self._current(0.5)
        baseline = NDVIBaseline(mean=0.3, std=0.0, n_observations=10)
        result = analyze_temporal_change(current, baseline)
        assert math.isinf(result.z_score)
        assert result.anomaly is True

    def test_zero_baseline_std_no_movement(self):
        current = self._current(0.3)
        baseline = NDVIBaseline(mean=0.3, std=0.0, n_observations=10)
        result = analyze_temporal_change(current, baseline)
        assert result.z_score == pytest.approx(0.0)
        assert result.anomaly is False

    def test_custom_z_threshold(self):
        current = self._current(0.5)
        baseline = NDVIBaseline(mean=0.3, std=0.1, n_observations=10)
        assert analyze_temporal_change(current, baseline, z_threshold=1.9).anomaly is True
        assert analyze_temporal_change(current, baseline, z_threshold=2.1).anomaly is False

    def test_percentage_change_sign(self):
        current = self._current(0.4)
        baseline = NDVIBaseline(mean=0.5, std=0.1, n_observations=10)
        result = analyze_temporal_change(current, baseline)
        assert result.percentage_change == pytest.approx(-20.0)

    def test_to_dict_structure(self):
        current = self._current(0.6)
        baseline = NDVIBaseline(mean=0.4, std=0.1, n_observations=10)
        result = analyze_temporal_change(current, baseline)
        d = result.to_dict()
        assert "current" in d
        assert "baseline" in d
        assert "delta_ndvi" in d
        assert "anomaly" in d
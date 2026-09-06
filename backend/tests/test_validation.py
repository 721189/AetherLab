"""Tests for the NO2 validation benchmark (MAE, RMSE, bias, correlation)."""

import math

import pytest

from app.services.processing.validation import (
    ValidationResult,
    describe,
    pearson,
    validate_no2,
)


class TestPearson:
    def test_perfect_positive_correlation(self):
        x = [1.0, 2.0, 3.0, 4.0]
        y = [1.0, 2.0, 3.0, 4.0]
        assert pearson(x, y) == pytest.approx(1.0)

    def test_perfect_negative_correlation(self):
        x = [1.0, 2.0, 3.0, 4.0]
        y = [4.0, 3.0, 2.0, 1.0]
        assert pearson(x, y) == pytest.approx(-1.0)

    def test_no_correlation(self):
        x = [1.0, 2.0, 3.0, 4.0]
        y = [2.0, 2.0, 2.0, 2.0]  # constant -> undefined
        assert pearson(x, y) is None

    def test_too_few_pairs(self):
        assert pearson([1.0], [2.0]) is None
        assert pearson([], []) is None

    def test_mismatched_lengths(self):
        assert pearson([1.0, 2.0], [1.0]) is None


class TestValidateNo2:
    def test_perfect_prediction(self):
        ref = [1.0, 2.0, 3.0, 4.0, 5.0]
        pred = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = validate_no2(pred, ref)
        assert result.n == 5
        assert result.mae == pytest.approx(0.0)
        assert result.rmse == pytest.approx(0.0)
        assert result.bias == pytest.approx(0.0)
        assert result.correlation == pytest.approx(1.0)
        assert result.missing_pct == pytest.approx(0.0)

    def test_known_bias(self):
        # Predicted is always 0.5 above reference
        ref = [1.0, 2.0, 3.0]
        pred = [1.5, 2.5, 3.5]
        result = validate_no2(pred, ref)
        assert result.bias == pytest.approx(0.5)
        assert result.mae == pytest.approx(0.5)
        assert result.rmse == pytest.approx(0.5)

    def test_with_missing_predictions(self):
        ref = [1.0, 2.0, 3.0, 4.0]
        pred = [1.0, None, 3.0, None]
        result = validate_no2(pred, ref)
        assert result.n == 2
        assert result.n_predicted == 2
        assert result.n_reference == 4
        assert result.missing_pct == pytest.approx(0.5)

    def test_with_missing_reference(self):
        ref = [1.0, None, 3.0, None]
        pred = [1.0, 2.0, 3.0, 4.0]
        result = validate_no2(pred, ref)
        assert result.n == 2

    def test_all_missing(self):
        ref = [1.0, 2.0, 3.0]
        pred = [None, None, None]
        result = validate_no2(pred, ref)
        assert result.n == 0
        assert math.isnan(result.mae)
        assert math.isnan(result.rmse)
        assert result.correlation is None
        assert any("No valid prediction pairs" in n for n in result.notes)

    def test_nan_predicted_treated_as_missing(self):
        ref = [1.0, 2.0, 3.0]
        pred = [1.0, float("nan"), 3.0]
        result = validate_no2(pred, ref)
        assert result.n == 2

    def test_inf_predicted_treated_as_missing(self):
        ref = [1.0, 2.0, 3.0]
        pred = [1.0, float("inf"), 3.0]
        result = validate_no2(pred, ref)
        assert result.n == 2

    def test_provisional_correlation_note(self):
        ref = [1.0, 2.0, 3.0]
        pred = [1.0, 2.0, 3.0]
        result = validate_no2(pred, ref)
        assert any("Fewer than 5 pairs" in n for n in result.notes)

    def test_high_missing_rate_note(self):
        ref = [1.0, 2.0, 3.0, 4.0]
        pred = [1.0, None, None, None]
        result = validate_no2(pred, ref)
        assert any("unpredicted" in n for n in result.notes)

    def test_label_in_notes(self):
        ref = [1.0, 2.0]
        pred = [1.0, 2.0]
        result = validate_no2(pred, ref, label="TROPOMI benchmark")
        assert "TROPOMI benchmark" in result.notes

    def test_rmse_penalizes_outliers(self):
        # Same total absolute error but one large spike -> higher RMSE
        # Equal errors: [1,1,1] -> MSE = (1+1+1)/3 = 1, RMSE = 1.0
        # One spike:   [0,0,2] -> MSE = (0+0+4)/3 = 1.333, RMSE ≈ 1.155
        ref = [0.0, 0.0, 0.0]
        pred = [1.0, 1.0, 1.0]
        result_equal = validate_no2(pred, ref)
        pred2 = [0.0, 0.0, 2.0]
        result_spike = validate_no2(pred2, ref)
        assert result_spike.rmse > result_equal.rmse
class TestDescribe:
    def test_describe_format(self):
        result = ValidationResult(
            n=10, mae=0.5, rmse=0.7, bias=0.1,
            correlation=0.95, missing_pct=0.1,
            n_predicted=10, n_reference=10, notes=[],
        )
        s = describe(result)
        assert "n=10" in s
        assert "MAE=" in s
        assert "r=0.95" in s
        assert "missing=10.0%" in s

    def test_describe_no_correlation(self):
        result = ValidationResult(
            n=1, mae=0.0, rmse=0.0, bias=0.0,
            correlation=None, missing_pct=0.0,
            n_predicted=1, n_reference=1, notes=[],
        )
        s = describe(result)
        assert "r=n/a" in s
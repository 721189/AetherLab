# Anomaly Detection — Temporal NDVI Change Analysis

## Model

Z-score statistical test comparing current NDVI against a historical baseline.

## Inputs

- `current`: NDVIResult for the current observation window
- `baseline`: NDVIBaseline containing the historical mean, std, and observation count
- `z_threshold`: sigma threshold (default 2.5)

## Equations

Delta: `delta = current_mean - baseline_mean`

Percentage change: `pct = (delta / |baseline_mean|) * 100` (NaN if baseline_mean ≈ 0)

Z-score: `z = delta / baseline_std` (if std > 0; if std = 0 and delta ≠ 0, z = ±inf)

Anomaly flag: `|z| > z_threshold`

## Units

- delta_ndvi: dimensionless (index)
- percentage_change: percent (%)
- z_score: standard deviations (sigma)

## Known limitations

- Requires a representative historical baseline; sparse baselines (n < 5) are unreliable
- Assumes baseline distribution is approximately normal (justified by Central Limit Theorem for n > 30)
- Does not account for seasonality — a phenological shift may be flagged as an anomaly

## Validation dataset

Reference cases in `backend/tests/test_sentinel2.py::TestAnalyzeTemporalChange`:

- Significant decrease (mean shifts from 0.7 to 0.2, std 0.1): z = -5.0, anomaly = True
- Moderate change (0.55 vs baseline 0.5±0.1): z = 0.5, anomaly = False
- Zero baseline mean: percentage_change = NaN, delta still computed
- Zero baseline std with movement: z = +inf, anomaly = True
- Zero baseline std no movement: z = 0.0, anomaly = False
- Custom z_threshold (1.9 vs 2.1): threshold sensitivity verified

## Acceptance error

- Z-score must match the reference formula exactly
- percentage_change must be NaN when baseline_mean ≈ 0
- Anomaly flag must flip correctly at the z_threshold boundary

## Code reference

`backend/app/services/processing/sentinel2.py`: `analyze_temporal_change(current, baseline, z_threshold=2.5)`
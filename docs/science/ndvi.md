# NDVI — Normalized Difference Vegetation Index

## Model

Per-pixel NDVI computed from Sentinel-2 MSI surface reflectance bands:

    NDVI = (NIR - Red) / (NIR + Red)

where Red = B04 (band 4, ~665 nm) and NIR = B08 (band 8, ~842 nm).

## Inputs

- Sentinel-2 L1C/L2A surface reflectance — B04 (red) and B08 (NIR) bands
- Optional per-pixel quality mask (cloud/shadow — e.g. from the Sentinel-2 QA band or `scipy.ndimage` morphological operations)

## Assumptions

- Surface reflectance values are atmospherically corrected (L2A). If L1C top-of-atmosphere reflectance is used instead, NDVI will be systematically biased low.
- Cloud/shadow pixels are masked out before aggregation. Unmasked cloud pixels inflate NDVI (high NIR reflectance over clouds), while shadow pixels deflate it.

## Equations

Per-pixel computation:

    NDVI_pixel = (B08_pixel - B04_pixel) / (B08_pixel + B04_pixel)

Pixels where B08 + B04 = 0 (or where the quality mask marks them invalid) are set to NaN and excluded from the spatial aggregate.

Spatial aggregation over the AOI:

    mean_ndvi    = mean(all valid pixels)
    median_ndvi  = median(all valid pixels)
    std_ndvi     = standard deviation of valid pixels
    pixel_count  = number of valid pixels included in the aggregate

A physics guard enforces `-1.0 <= NDVI <= 1.0`; values outside this range (caused by atmospheric residuals or sensor noise) are treated as invalid and NaN-masked.

## Units

- NDVI: dimensionless (unit = "index")
- Bands: surface reflectance (0–1, no units)

## Resolution

- 10 m spatial resolution (Sentinel-2 MSI, B04 and B08 are both 10 m bands)
- Temporal revisit: ~2–5 days at the equator (Sentinel-2A + 2B constellation)

## Known limitations

- NDVI saturates in dense vegetation (canopy cover > 80%); it cannot distinguish between high LAI values. Use EVI or other indices for dense-canopy applications.
- The quality mask is optional; if none is supplied, only the physics guard ([-1, 1]) and finite-value check are applied — cloud pixels may inflate the result.
- Aggregation is a simple mean/median; spatial autocorrelation in remote sensing data means the effective sample size is lower than `pixel_count`.

## Validation dataset

Reference cases in `backend/tests/test_sentinel2.py` assert:

- Known NDVI values from synthetic B04/B08 arrays match hand-computed expectations
- Cloud-masked pixels are excluded from the aggregate
- Zero-denominator (B04 + B08 = 0) pixels yield NaN and are not averaged in
- Empty or fully-rejected scenes raise `ValueError` (no silent zero-fill)

## Acceptance error

- Per-pixel NDVI must equal the reference formula to within ±0.001
- Spatial mean/median must match a NumPy reference computation to within ±0.0
- `pixels_used + pixels_rejected == pixels_input` (no dropped pixels)
- `min >= -1.0` and `max <= 1.0` (physics guard enforced)

## Code reference

`backend/app/services/processing/sentinel2.py`
- `compute_ndvi(red, nir, valid_mask) -> np.ndarray`
- `aggregate_ndvi(ndvi_array) -> NDVIResult`
- `analyze_temporal_change(current, baseline, z_threshold=2.5) -> TemporalChangeResult`

## Related

- **Tactical/RF module**: This module does **NOT** implement the Gaussian plume model, MGRS coordinate conversion, or RF diagnostic calculations described in the v1.0 production plan. Those features were listed as future work but have not yet been implemented in `aetherlab-integration`. A `docs/science/tactical_rf.md` stub has been created to document this gap — see Phase 11.
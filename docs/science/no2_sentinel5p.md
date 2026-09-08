# NO2 — Sentinel-5P / TROPOMI Tropospheric Column

## Model

Aggregation of Sentinel-5P/TROPOMI NO2 tropospheric column data over an AOI (point buffer).

## Inputs

- `values`: raw NO2 tropospheric column values (mol/m²)
- `qa`: per-pixel TROPOMI quality-assurance value (0..1)
- `latitudes`, `longitudes`: per-pixel geolocation (1-D arrays, equal length)
- `target_lat`, `target_lon`: point of interest
- `max_km`: inclusion radius (default 15.0 km)
- `qa_threshold`: minimum QA to keep a pixel (default 0.5 — TROPOMI community standard)
- `method`: "median" (robust to outliers, default) or "mean"

## Assumptions

- QA < threshold pixels are unreliable (clouds, poor fit) and are always excluded — never averaged in.
- The 15 km radius captures the local representativeness of the Sentinel-5P pixel (which is ~7×7 km at nadir, larger at scan edges).
- Median is preferred over mean for pollutant columns because urban pollution fields are highly skewed (point sources, traffic corridors).

## Equations

Quality filter: `keep = finite(values, qa, lat, lon) & (qa >= qa_threshold)`

AOI filter: `inside = keep & (distance(pixel, target) <= max_km)`

Aggregation: `result = median(values[inside])` (or mean if method="mean")

## Units

- NO2: mol/m² (dry-air slant column / tropospheric column)
- QA: dimensionless (0..1)
- Distance: km

## Resolution

- ~7 × 7 km (nadir, Sentinel-5P TROPOMI)
- 10 m × 3.5 m ground pixels across-track / along-track
- Daily global coverage

## Known limitations

- TROPOMI NO2 is a column measurement — it does not represent ground-level concentration.
- The QA threshold is binary; intermediate-quality pixels (e.g. QA 0.49) are fully discarded.
- Median aggregation loses information about the spatial distribution within the AOI.

## Validation dataset

Reference cases in `backend/tests/test_sentinel_no2.py` assert:

- Pixels with QA < threshold are excluded from the aggregate
- Pixels outside max_km radius are excluded
- Correct pixel counts (input, used, rejected) are reported in methodology
- ValueError raised when no pixels survive filtering
- Both "median" and "mean" methods return correct values

## Acceptance error

- Quality-filtered median must match NumPy reference exactly
- pixels_used + pixels_rejected == pixels_input
- ValueError must be raised for empty/over-filtered scenes (no silent zero-fill)

## Code reference

`backend/app/services/processing/sentinel_no2.py`:
- `aggregate_tropomi_no2(values, qa, latitudes, longitudes, target_lat, target_lon, ...)`
- `extract_no2_from_arrays(product_arrays, target_lat, target_lon, ...)`
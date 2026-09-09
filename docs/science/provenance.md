# Provenance & Scientific Correctness

Every environmental, satellite, and RF result in AetherLab carries **unambiguous source attribution**. This document defines the provenance model and the invariants that guarantee scientific correctness.

## The Provenance Chain

```
RAW DATA -> NORMALIZATION -> PROVENANCE -> QUALITY/UNCERTAINTY
    -> SCIENTIFIC DERIVATION -> EVIDENCE -> AI -> HUMAN-READABLE RESULT
```

At every step, the chain is preserved. No observation exists without a complete answer to:

- **Where** did this number come from? (source, dataset, product)
- **When** was it measured? (observed_at, acquisition_time, retrieved_at)
- **How** was it processed? (processing_level, methodology)
- **How good** is it? (uncertainty, confidence, quality_score, quality_flags)
- **Can I reproduce it?** (provenance bundle)

## Timestamp Semantics

Every observation carries three distinct timestamps:

## Provider Provenance Profiles

### OpenWeather (current weather API)

| Field | Value |
|-------|-------|
| dataset | `OpenWeather Current Weather API` |
| product | `current` |
| processing_level | `L2` (processed product) |
| resolution | `point` |
| averaging_period | `instantaneous` |
| uncertainty | `None` (provider doesn't publish per-variable uncertainty) |
| confidence | `0.9` |
| quality_flags | clouds_pct, visibility_m, weather_id |

**Reproducibility**: The `provenance` bundle includes `station_id`, `raw_dt`, `timezone_offset_sec`, and the exact endpoint URL. Re-fetching with these parameters returns the identical payload.

### OpenAQ v3 (air quality)

| Field | Value |
|-------|-------|
| dataset | `OpenAQ v3` |
| product | `latest` |
| processing_level | `L2` |
| resolution | `point` (station-level) |
| averaging_period | `instantaneous` |
| uncertainty | `None` |
| confidence | `0.85` |
| quality_flags | is_mobile, is_analysis |

**Reproducibility**: The `provenance` bundle includes `site_id`, `sensor_id`, `parameter`, `units`, and `radius_m`. The exact API call can be reconstructed.

### NASA POWER (MERRA-2 reanalysis)

| Field | Value |
|-------|-------|
| dataset | `POWER (MERRA-2 reanalysis) {code}` |
| product | `reanalysis-daily-point` |
| processing_level | `L3` (gridded reanalysis) |
| resolution | `0.5° x 0.625° (~55 km)` |
| averaging_period | `24-hour` |
| uncertainty | `1.0` for temperature, `None` otherwise |
| confidence | `0.8` (model assimilation, not in-situ) |

**Critical distinction**: NASA POWER values are **model-derived reanalysis**, NOT direct measurements. The `confidence=0.8` and `processing_level=L3` make this unambiguous. Never compare these directly with in-situ station data without accounting for the methodological difference.

### Copernicus CDSE (Sentinel-5P NO₂)


## Derived Metrics & Methodology

When AetherLab derives a value from raw observations (e.g., AQI), the derived metric carries its own provenance:

```python
DerivedMetric(
    name="overall_aqi",
    value=42.0,
    unit="index",
    method="EPA-breakpoint",
    n_observations=3,
    confidence=0.85,
    methodology_status="standard",  # or "non_standard_averaging"
    inputs=[...]  # raw observation IDs
)
```

**Methodology status** is critical:
- `standard` — derived using the canonical methodology (EPA breakpoints for standard averaging windows)
- `non_standard_averaging` — derived but with non-standard inputs (e.g., instantaneous OpenAQ values fed into an EPA-daily methodology)
- `experimental` — new/untested derivation

Consumers **must** check `methodology_status` before making claims. The evidence layer does this automatically and labels non-standard results as "indicative" in the LLM output.

## Uncertainty Model

| Field | Type | Meaning |
|-------|------|---------|
| `uncertainty` | `float | None` | ± in the same unit as the value. `None` = unknown (NOT zero) |
| `confidence` | `float (0..1)` | Overall confidence in this single observation |
| `quality_score` | `float (0..100)` | Numeric quality score complementing the quality flag |
| `data_completeness` | `float (0..1)` | Fraction of expected variables actually delivered |

**Rule**: `uncertainty = None` means "the provider didn't tell us." It never means "zero uncertainty." False precision (claiming `uncertainty = 0` when unknown) is a scientific error.

## Quality Flags

Provider-specific quality information lives in `quality_flags` (JSONB). Examples:

- **OpenWeather**: `{"clouds_pct": 40, "visibility_m": 10000, "weather_id": 800}`
- **OpenAQ**: `{"is_mobile": false, "is_analysis": true}`
- **NASA POWER**: `{"fill_value_masked": true}` — fill values were excluded
- **Copernicus**: `{"cloud_cover_unavailable": true, "online_status": "true"}`

## Immutability

Once persisted, the `provenance` bundle is **never mutated**. It represents the state at ingestion time. Corrections or re-processing create new observation rows (with new `observation_hash` values) rather than modifying existing ones.

## The `observation_hash` (Idempotency)

Every observation is tagged with a SHA-256 hash of its canonical dedup key:

```
source + dataset + product + scene_id + variable + location + observed_at
```

This key **excludes** the numeric value and retrieval time — the same measurement (same source scene, variable, place, time) hashes identically across retries. The hash is a `UNIQUE` constraint, so duplicate ingestions are impossible.

## Audit Trail

To trace any number shown to a user:

1. Start with the `EnvironmentalObservationRecord` (DB row)
2. Read `provenance` — the immutable provider-provenance bundle
3. Read `source`, `dataset`, `product`, `processing_level` — the source attribution
4. Read `observed_at`, `acquisition_time`, `retrieved_at` — the timestamp semantics
5. Read `uncertainty`, `confidence`, `quality_score` — the quality model
6. For derived metrics, read `methodology` and `methodology_status` — the derivation chain

This chain is the **scientific paper** behind every number.

| Field | Value |
|-------|-------|
| dataset | `Sentinel-5P TROPOMI L2__NO2` |
| product | `L2__NO2` |
| processing_level | `L2` |
| resolution | `5.5 km x 7 km` |
| averaging_period | `instantaneous` (satellite overpass) |
| uncertainty | From NetCDF variable attributes |
| confidence | `0.7` (remote sensing retrieval) |

**Reproducibility**: The `provenance` bundle includes `scene_id`, `product`, `processing`, and `request_url`. The exact Sentinel-5P scene can be re-downloaded.


| Field | Meaning | Example |
|-------|---------|---------|
| `observed_at` | When the phenomenon was measured by the source | Sensor reading time, satellite overpass |
| `acquisition_time` | When the raw data was acquired (may differ from observed for derived products) | Satellite scene acquisition vs. processed value |
| `retrieved_at` | When AetherLab fetched it | Audit trail for data freshness |

All timestamps are **timezone-aware UTC**. Naive datetimes from providers are assumed UTC and tagged accordingly (see `EnvironmentalObservationRepository._utc()`).

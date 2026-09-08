# AetherLab architecture

## Data pipeline

```
RAW DATA -> NORMALIZATION -> PROVENANCE -> QUALITY/UNCERTAINTY
    -> SCIENTIFIC DERIVATION -> EVIDENCE -> AI -> HUMAN-READABLE RESULT
```

## Components

- **Frontend**: Next.js 15 app -> `lib/api/client.ts` -> FastAPI `/api/v1`
- **API**: FastAPI with JWT auth, rate limiting, pagination
- **Database**: PostgreSQL (source of truth) + Alembic migrations
- **Cache**: Redis (provider response cache, rate limits, job coordination)
- **Workers**: Celery + beat for scheduled ingestion
- **Providers**: OpenWeather, OpenAQ v3, NASA POWER, Copernicus CDSE, Sentinel-2
- **Intelligence**: EvidenceBuilder -> EvidenceSet -> grounded LLM answer
- **Storage**: PostgreSQL (metadata, provenance, results, hashes) + S3-compatible object store (GeoTIFF/NetCDF rasters). See `docs/storage.md`.

## Operations

- **CI** (`.github/workflows/ci.yml`): hermetic unit suite on every push to `main`/`development`/`release/*`, plus an integration tier against real PostgreSQL + Redis.
- **Provider smoke** (`.github/workflows/provider-smoke.yml`): nightly live contract tests against OpenAQ, OpenWeather, NASA, CDSE, Sentinel-2, and the LLM provider — catches provider-side schema drift that mocks cannot see. Opt-in via `RUN_PROVIDER_SMOKE=1`.

## Key invariants

- No fabricated environmental values — missing data returns `null` + status.
- Every observation carries provenance (provider, timestamp, location, unit).
- Environmental questions without evidence produce no numerical claims.

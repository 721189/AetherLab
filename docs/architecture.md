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

## Branch strategy

```
aetherlab-integration  (active development, all PRs land here)
        │
        ▼  (freeze + CI green on exact SHA)
release/v1.0           (stabilization, fix-forward only)
        │
        ▼  (merge, no squash)
main                   (production, tagged releases only)
```

- `aetherlab-integration` is the **integration branch** — all feature work and PRs target it.
- `main` is **production-only** — receives merges from `release/*` branches, never direct pushes.
- `release/*` branches are cut from `aetherlab-integration` when it's time to freeze.
- See `docs/deployment/staged-deployment.md` for the full promotion chain.

## Operations

- **CI** (`.github/workflows/ci.yml`): hermetic unit suite on every push to `main`, `development`, `aetherlab-integration`, and `release/*`, plus an integration tier against real PostgreSQL + Redis. `workflow_dispatch` allows running the exact matrix against any commit SHA for promotion gating (see `docs/deployment/ci-verification.md`).
- **Provider smoke** (`.github/workflows/provider-smoke.yml`): nightly live contract tests against OpenAQ, OpenWeather, NASA, CDSE, Sentinel-2, and the LLM provider — catches provider-side schema drift that mocks cannot see. Opt-in via `RUN_PROVIDER_SMOKE=1`.
- **Backup/restore** (`docs/operations/backup-restore.md`): required restore-testing cadence before every staging → production promotion.

## Key invariants

- No fabricated environmental values — missing data returns `null` + status.
- Every observation carries **full provenance** (source, dataset, product, processing_level, resolution, acquisition_time, observed_at, retrieved_at, uncertainty, confidence, quality_score, quality_flags, reproducibility bundle). See `docs/science/provenance.md`.
- Environmental questions without evidence produce no numerical claims.
- Derived metrics (AQI, etc.) carry explicit `methodology_status` — `standard`, `non_standard_averaging`, or `experimental` — so consumers never mistake indicative values for canonical ones.
- `uncertainty = None` means "unknown", never "zero". False precision is a scientific error.

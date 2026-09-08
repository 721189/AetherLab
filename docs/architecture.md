# AetherLab architecture

## Data pipeline

```
RAW DATA -> NORMALIZATION -> PROVENANCE -> QUALITY/UNCERTAINTY
    -> SCIENTIFIC DERIVATION -> EVIDENCE -> AI -> HUMAN-READABLE RESULT
```

## Components

- **Frontend**: Next.js 16 app -> `lib/api/client.ts` -> FastAPI `/api/v1`
- **API**: FastAPI with JWT auth, rate limiting, pagination
- **Database**: PostgreSQL (source of truth) + Alembic migrations
- **Cache**: Redis (provider response cache, rate limits, job coordination)
- **Workers**: Celery + beat for scheduled ingestion
- **Providers**: OpenWeather, OpenAQ v3, NASA POWER, Copernicus CDSE, Sentinel-2
- **Intelligence**: EvidenceBuilder -> EvidenceSet -> grounded LLM answer

## Key invariants

- No fabricated environmental values — missing data returns `null` + status.
- Every observation carries provenance (provider, timestamp, location, unit).
- Environmental questions without evidence produce no numerical claims.

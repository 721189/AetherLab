# Satellite storage architecture

## The problem

Sentinel-2 L1C tiles are ~800 MB each. A single AOI over a month can easily
produce tens of GB of GeoTIFF/NetCDF. Storing those inside PostgreSQL bloats
the database, makes backups slow, and defeats the purpose of a transactional
store.

## The split

```
PostgreSQL (source of truth)          Object storage (S3-compatible)
─────────────────────────────         ─────────────────────────────────
users                                 raw Sentinel-2 L1C tiles (GeoTIFF)
projects                              Sentinel-5P NO2 products (NetCDF)
agents                                processed NDVI rasters (GeoTIFF)
conversations / messages              derived anomaly maps
monitored locations
environmental_observations            ← metadata rows point here via
derived metrics                         object_key / provenance.asset_url
jobs / audit events
```

**PostgreSQL** owns *metadata, provenance, results, hashes*.  
**Object storage** owns the *multi-GB binary assets*.

A `satellite_product` row never contains bytes — it contains an
`object_key` (e.g. `sentinel2/S2A_20260820_T44QMA_L1C.tif`) plus provenance,
and the bytes live in the bucket. This keeps the database small and lets the
object store scale independently.

## Config

Object storage is configured via `app.core.config.Settings` (all optional —
empty values disable it entirely):

| Env var | Purpose |
|---|---|
| `OBJECT_STORE_ENDPOINT` | S3-compatible endpoint URL |
| `OBJECT_STORE_BUCKET` | Bucket name |
| `OBJECT_STORE_ACCESS_KEY` | Access key |
| `OBJECT_STORE_SECRET_KEY` | Secret key |
| `OBJECT_STORE_REGION` | AWS region (or `auto` for MinIO) |
| `OBJECT_STORE_SECURE` | TLS on/off |

## Implementation notes

- Use `boto3` / `aiobotocore` against any S3-compatible API (AWS S3, MinIO,
  R2, GCS-interop).
- Always store a SHA-256 checksum alongside the object — enables dedup and
  integrity verification on retrieval.
- Prefer presigned URLs for downloads; never proxy multi-GB assets through
  the API server.
- The `observation_hash` column on `environmental_observations` already
  provides idempotent ingestion — re-fetching the same scene never inserts
  a duplicate row.

## Migration path

1. Add a `satellite_products` table (metadata + `object_key` + checksum).
2. Stand up a local MinIO via `docker compose` for dev.
3. Wire `Sentinel2Provider.retrieve()` to upload decoded rasters to the
   bucket and persist the `object_key` in the DB.
4. Serve downloads via presigned URLs from the API.

Until step 1 lands, the object-store config fields are inert — the system
continues to work with metadata-only storage.
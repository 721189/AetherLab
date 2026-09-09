# Backup & restore testing

Backups that have never been restored are not backups — they are hopes.
This procedure makes restore-testing a required, repeatable gate.

## Tooling

- `scripts/backup-db.sh [out-dir]` — custom-format `pg_dump` + SHA-256
  sidecar + `pg_restore --list` verification. Fails loudly on any error.
- `scripts/restore-db.sh <dump> [target-db]` — restores into a **scratch**
  database by default, verifies checksums, table presence, and alembic state.
  Refuses to touch the live database unless `AETHERLAB_RESTORE_ALLOW_LIVE=1`.

Required env: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
(optional `POSTGRES_HOST`, `POSTGRES_PORT`).

## Cadence

| When | What |
|---|---|
| Before every staging → production promotion | Fresh backup + scratch restore (`RESTORE_OK`) |
| Nightly (production) | Automated `backup-db.sh`; alert on non-zero exit |
| Monthly | Full rehearsal: restore nightly dump to scratch, point a staging API at it, run smoke tests |

## What "tested" means

A restore counts as tested only when `restore-db.sh` prints `RESTORE_OK`
**and** the restored scratch database passes:

1. `alembic heads` shows a single head and `alembic current` matches the
   deployed migration version,
2. row-count sanity on `environmental_observations` / `monitored_locations`
   (non-zero where production is expected non-empty),
3. the app boots against the restored DB (`APP_ENV=staging`) and `/health`
   reports healthy.

Record the `BACKUP_OK` / `RESTORE_OK` lines in the release notes for the
promotion they gate.

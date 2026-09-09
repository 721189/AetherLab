#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# AetherLab PostgreSQL backup script.
#
# Usage:
#   POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=... ./scripts/backup-db.sh [out-dir]
#
# Produces a timestamped custom-format dump plus a SHA-256 checksum file, then
# verifies the dump is listable by pg_restore. Exits non-zero on any failure
# so CI / cron detects a broken backup instead of archiving garbage.
# ---------------------------------------------------------------------------
set -euo pipefail

OUT_DIR="${1:-./backups}"
PGUSER="${POSTGRES_USER:?POSTGRES_USER is required}"
export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
PGDATABASE="${POSTGRES_DB:?POSTGRES_DB is required}"
PGHOST="${POSTGRES_HOST:-localhost}"
PGPORT="${POSTGRES_PORT:-5432}"

mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP="$OUT_DIR/aetherlab-${PGDATABASE}-${STAMP}.dump"

pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" \
  --format=custom --compress=9 --no-owner --file="$DUMP"

# Integrity: checksum + verify the archive is readable by pg_restore.
sha256sum "$DUMP" > "${DUMP}.sha256"
pg_restore --list "$DUMP" > /dev/null

echo "BACKUP_OK $DUMP"

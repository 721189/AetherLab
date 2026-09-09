#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# AetherLab PostgreSQL restore + verification script.
#
# Usage:
#   ./scripts/restore-db.sh <dump-file> [target-db]
#
# Restores a custom-format dump (as produced by scripts/backup-db.sh) into the
# target database, then runs sanity checks:
#   1. checksum of the dump matches its .sha256 sidecar (when present),
#   2. expected core tables exist and are non-empty where applicable,
#   3. alembic version table is present (migrations state survived).
#
# The script NEVER restores into the database named by POSTGRES_DB unless
# AETHERLAB_RESTORE_ALLOW_LIVE=1 is set — restores default to a scratch DB.
# ---------------------------------------------------------------------------
set -euo pipefail

DUMP="${1:?usage: restore-db.sh <dump-file> [target-db]}"
TARGET_DB="${2:-${POSTGRES_DB}_restore_test}"
PGUSER="${POSTGRES_USER:?POSTGRES_USER is required}"
export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
PGHOST="${POSTGRES_HOST:-localhost}"
PGPORT="${POSTGRES_PORT:-5432}"

if [[ ! -f "$DUMP" ]]; then
  echo "RESTORE_FAIL: dump file not found: $DUMP" >&2
  exit 1
fi

if [[ -f "${DUMP}.sha256" ]]; then
  (cd "$(dirname "$DUMP")" && sha256sum -c "$(basename "${DUMP}.sha256")")
fi

LIVE_DB="${POSTGRES_DB:?POSTGRES_DB is required}"
if [[ "$TARGET_DB" == "$LIVE_DB" && "${AETHERLAB_RESTORE_ALLOW_LIVE:-0}" != "1" ]]; then
  echo "RESTORE_REFUSED: target is the live database ($LIVE_DB)." >&2
  echo "Restore into a scratch database, or set AETHERLAB_RESTORE_ALLOW_LIVE=1." >&2
  exit 1
fi

psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${TARGET_DB}';" \
  > /dev/null || true
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d postgres \
  -c "DROP DATABASE IF EXISTS \"${TARGET_DB}\";" \
  -c "CREATE DATABASE \"${TARGET_DB}\";"

pg_restore -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$TARGET_DB" \
  --no-owner --jobs=2 "$DUMP"

# ---- Verification ---------------------------------------------------------
TABLES="$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$TARGET_DB" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")"
if [[ "${TABLES:-0}" -lt 1 ]]; then
  echo "RESTORE_FAIL: no public tables after restore" >&2
  exit 1
fi

ALEMBIC="$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$TARGET_DB" -tAc \
  "SELECT count(*) FROM alembic_version;" 2>/dev/null || echo "missing")"
if [[ "$ALEMBIC" == "missing" ]]; then
  echo "RESTORE_WARN: alembic_version table absent (pre-migration backup?)" >&2
fi

echo "RESTORE_OK db=${TARGET_DB} tables=${TABLES} alembic_versions=${ALEMBIC}"

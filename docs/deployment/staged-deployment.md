# Staged deployment: development → release/v1.0 → staging → production

Promotion chain (strictly one direction, never skip a stage):

```
development  →  release/v1.0  →  staging  →  production
   (daily)        (freeze)       (mirror)      (tag)
```

## Stage definitions

| Stage | Branch / ref | Environment | Purpose |
|---|---|---|---|
| Dev | `development` | `APP_ENV=development` | Active development; CI (SQLite + PG tiers) must be green |
| Freeze | `release/v1.0` | `APP_ENV=staging`-like | Feature freeze; only fix-forward release blockers |
| Staging | `release/v1.0` deployed | `APP_ENV=staging`, prod-shaped data | Full rehearsal: migrations, backup/restore, smoke tests |
| Production | tag `v1.0.0` on `main` | `APP_ENV=production` | Real users; every safety check fails closed |

`APP_ENV=staging` behaves like production for safety checks (no demo-city
fallback, no memory rate-limiter fallback) but allows non-prod secrets.

## Promotion gates

A stage may promote **only** when all of these hold:

1. **CI green** on the exact commit (see `docs/deployment/ci-verification.md`):
   backend-unit + backend-postgres + frontend jobs.
2. **Migrations rehearsed**: `alembic upgrade head` applied cleanly against a
   staging-shaped database; `alembic heads` shows a single head.
3. **Backup taken + restore tested** immediately before touching production
   (see `docs/operations/backup-restore.md`).
4. **Provider smoke** (`provider-smoke.yml`, nightly or manual dispatch) green
   for all live contract tests.
5. **No fail-open fallbacks**: `discover_locations()` raises (never seeds demo
   cities) when the monitored-locations table is empty; evidence grounding
   fails closed; rate limiter uses Redis storage.

## Release procedure (v1.0.0)

1. Freeze: cut `release/v1.0` from `development`; CI green on the branch.
2. Rehearse: deploy the branch commit to staging; run migrations, smoke tests,
   backup + restore rehearsal.
3. Merge `release/v1.0` → `main` (fast-forward or merge commit, no squash —
   keep the rehearsed SHAs intact).
4. Tag `v1.0.0` on `main`; deploy the **tag**, not a branch tip.
5. Post-deploy: verify `/health`, Flower worker liveness, Beat schedule firing,
   Sentry release marked.

## Rollback

- Database: restore the pre-deploy backup (procedure in
  `docs/operations/backup-restore.md`); migrations roll back via
  `alembic downgrade -1` **only** when the migration declares a safe
  downgrade, otherwise restore-from-backup is the rollback.
- Code: redeploy the previous tag. Never force-push `main` to "undo".

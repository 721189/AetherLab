# Running CI against an exact commit (e.g. f8ed45f)

The `CI` workflow resolves `workflow_dispatch` so any ref — branch, tag, or
full commit SHA — can be validated on demand. This is how a release candidate
commit is proven green *before* it is merged or tagged.

## Procedure (GitHub UI)

1. Open **Actions → CI → Run workflow**.
2. In **"Use workflow from"**, select the branch that contains the commit
   (e.g. `aetherlab-integration`).
3. Enter the full SHA (e.g. the `f8ed45f` release candidate) — dispatching by
   SHA checks out exactly that commit.
4. Confirm all three jobs pass:
   - **Backend – pytest (SQLite)**: hermetic unit/API tier.
   - **Backend – integration (PostgreSQL + Redis)**: real migrations,
     constraints, token rotation, Redis-backed limiter/cache.
   - **Frontend – typecheck + build**: `tsc --noEmit`, `npm run lint`,
     `npm run build`.

## Promotion rule

A commit may promote (`development → release/v1.0 → staging → production`,
see `staged-deployment.md`) **only** if the CI run against its exact SHA is
green. A green run on a *different* (e.g. later) commit does not qualify an
earlier SHA — re-run against the SHA being promoted.

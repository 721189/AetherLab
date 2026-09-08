# Git branching policy

## Branches

| Branch | Purpose |
|---|---|
| `main` | Always deployable. Protected. |
| `development` | Active integration work. |
| `release/v1.0` | Stabilization for the v1.0 release. |
| `feature/*` | Isolated feature work. |

## Rules

- No direct push to `main`.
- All changes via pull request with required review.
- CI must pass before merge.
- Tagged releases only from `main`.

## Source of truth

`main` must always represent a buildable, deployable system.

# Experimental Atmospheric Analytics — Status & Qualification Requirements

## Current state

**NOT YET IMPLEMENTED — and must remain clearly labelled as experimental until
independently validated.**

The v1.0 production plan described a Tactical/RF diagnostic module containing:

- Gaussian plume dispersion model
- Atmospheric refractivity / M-units calculations
- Radar horizon multiplier
- MGRS coordinate conversion
- RF signal propagation classification

**Search results for `gaussian.*plume`, `tactical`, `MGRS`, `rf_diagnostic`,
`radar_horizon`, `atmospheric_refractivity` in the entire codebase: 0 matches.**

There is no tactical/RF processing code in `aetherlab-integration` or any other
branch. The plan's Phase 11 ("Fix the Tactical/RF module before calling it
operational") does not apply to the current state of the repository.

## Why "Experimental Atmospheric Analytics" — not "Operational Radar Intelligence"

The Gaussian plume equation itself is a meaningful physical model. The
*operational interpretation* layered on top of it is not validated:

| Component | Issue |
|---|---|
| MGRS coordinate conversion | Approximate, not a true WGS84 → UTM → MGRS projection |
| Atmospheric regime classification | Heuristic thresholds, not a physical model |
| Radar horizon multiplier | Fixed multiplier, not a real vertical refractivity profile |
| RF classification language | Strong operational/tactical claims unsupported by validation |

Scientific confidence must never be stronger than the underlying model. Until
each component is validated against reference data, the module must be labelled
**Experimental Atmospheric Analytics** — never "operational" or "tactical".

## Qualification requirements (before removing the "experimental" label)

If this module is built, it must satisfy **all** of the following before any
operational claims are made:

1. **MGRS conversion** — use a proper geospatial library (e.g. `mgrs` or
   `pyproj`) for true WGS84 → UTM → MGRS projection. No approximations.
2. **Atmospheric refractivity** — implement the ITU-R model with a real
   vertical refractivity profile, not heuristic regime classes.
3. **Radar horizon** — compute from the actual refractivity profile, not a
   fixed multiplier.
4. **Gaussian plume** — document the model (equations, assumptions), define
   inputs/units/resolution, list known limitations, provide validation test
   vectors, and specify acceptance error — following the same pattern as the
   NDVI, AQI, and anomaly-detection docs in this directory.
5. **Validation dataset** — every algorithm gets known input → expected output
   → error tolerance, tested against reference cases.
6. **Honest labelling** — UI and API responses must say "Experimental
   Atmospheric Analytics" until independent validation is complete.

## Documentation pattern

Follow the same scientific documentation pattern as the other `docs/science/`
modules:

1. Document the model (equations, assumptions)
2. Define inputs, units, resolution
3. List known limitations
4. Provide validation test vectors
5. Specify acceptance error

Until then, AetherLab is a pure environmental-observation platform (air quality,
weather, satellite NDVI). It does not provide RF/tactical diagnostics.
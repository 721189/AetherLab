# Tactical/RF Module — Status

## Current state

**NOT YET IMPLEMENTED.**

The v1.0 production plan described a Tactical/RF diagnostic module containing:

- Gaussian plume dispersion model
- Atmospheric refractivity / M-units calculations
- Radar horizon multiplier
- MGRS coordinate conversion
- RF signal propagation classification

**Search results for `gaussian.*plume`, `tactical`, `MGRS`, `rf_diagnostic`, `radar_horizon`, `atmospheric_refractivity` in the entire codebase: 0 matches.**

There is no tactical/RF processing code in `aetherlab-integration` or any other branch. The plan's Phase 11 ("Fix the Tactical/RF module before calling it operational") does not apply to the current state of the repository.

## If/when implemented

If this module is built in the future, it should follow the same scientific documentation pattern as the NDVI, AQI, and anomaly-detection docs in this directory:

1. Document the model (equations, assumptions)
2. Define inputs, units, resolution
3. List known limitations
4. Provide validation test vectors
5. Specify acceptance error

Until then, AetherLab is a pure environmental-observation platform (air quality, weather, satellite NDVI). It does not provide RF/tactical diagnostics.
# AQI — Air Quality Index

## Model

US EPA breakpoint methodology. Each pollutant concentration is mapped to an
index value via piecewise-linear interpolation between published breakpoints,
then the overall AQI is the maximum sub-index.

## Inputs

- `pm25`, `pm10`, `no2`, `o3`, `so2`, `co` — concentrations in ug/m3 (CO in mg/m3)
- `averaging_periods` — per-pollutant window (e.g. `pm25` = 24h, `o3` = 8h)

## Assumptions

- OpenAQ "latest" values are **instantaneous sensor readings**, NOT EPA-averaged
  windows. Every AQI derived from them carries
  `methodology_status = "non_standard_averaging"` and is labelled **indicative**.
- Concentrations beyond the published EPA breakpoint tables return **no value**
  rather than an invented one.

## Equations

For a pollutant with concentration `c` falling between breakpoints
`(BP_lo, BP_hi) -> (I_lo, I_hi)`:

    I = I_lo + (I_hi - I_lo) * (c - BP_lo) / (BP_hi - BP_lo)

Overall AQI = max(I_pm25, I_pm10, I_no2, I_o3, I_so2, I_co)

## Units

- PM2.5, PM10, NO2, O3, SO2: ug/m3
- CO: mg/m3

## Resolution

Depends on the underlying sensor network (typically 1 km – 10 km for OpenAQ
station data).

## Known limitations

- Instantaneous readings can over/under-estimate true 24h-averaged AQI.
- Spatial representativeness is limited to the nearest monitoring station.
- Not a substitute for regulatory-grade monitoring.

## Validation dataset

Reference cases in `backend/tests/test_aqi.py` assert known breakpoint
boundaries (e.g. PM2.5 = 12.0 ug/m3 -> AQI 50).

## Acceptance error

Index values must match EPA reference tables exactly at breakpoint boundaries;
interpolation must be monotonic between them.

"""Sentinel-5P / TROPOMI NO2 quality-filtered aggregation.

This is the scientific core surfaced when "actually extracting NO2" — it turns
raw swath pixels into ONE robust canonical observation by:

    raw NO2 pixels  ->  quality filtering  ->  invalid pixels removed
                     ->  AOI filter (radius around target point)
                     ->  spatial aggregation  ->  canonical observation

The methodology (quality filter, input/used pixel counts, aggregation method)
is reported explicitly so an institutional reviewer can audit exactly how a
number was produced.

The aggregation runs on plain NumPy arrays so it is fully unit-testable without
downloading a single TROPOMI product.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

# Default TROPOMI L2 variable names inside the NetCDF product.
NO2_DATA_VAR = "nitrogendioxide_tropospheric_column"  # mol/m2
NO2_QA_VAR = "qa_value"  # 0..1 quality-assurance value
NO2_LAT_VAR = "latitude"
NO2_LON_VAR = "longitude"
DEFAULT_QA_THRESHOLD = 0.5  # TROPOMI community standard: discard QA < 0.5


def _distance_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    """Great-circle arc distance (haversine) between two points, in km."""
    phi1 = math.radians(a_lat)
    phi2 = math.radians(b_lat)
    dphi = math.radians(b_lat - a_lat)
    dlambda = math.radians(b_lon - a_lon)
    hav = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(hav), math.sqrt(1 - hav))
    return 6371.0 * c  # mean Earth radius, km
def aggregate_tropomi_no2(
    values,
    qa,
    latitudes,
    longitudes,
    target_lat: float,
    target_lon: float,
    *,
    max_km: float = 15.0,
    qa_threshold: float = DEFAULT_QA_THRESHOLD,
    method: str = "median",
) -> dict:
    """Quality-filtered median/mean of valid TROPOMI NO2 pixels near a point.

    Args:
        values: raw NO2 column values (mol/m2), one per ground pixel.
        qa: per-pixel quality-assurance value (0..1).
        latitudes/longitudes: per-pixel geolocation.
        target_lat/target_lon: the point of interest.
        max_km: inclusion radius around the target (AOI filter).
        qa_threshold: minimum QA value to keep a pixel.
        method: ``"median"`` (robust to outliers) or ``"mean"``.

    Returns a dict of ``{"value", "unit", "methodology"}`` where methodology
    records the exact filtering/aggregation recipe and pixel counts.
    """
    import numpy as np

    values = np.asarray(values, dtype=float)
    qa = np.asarray(qa, dtype=float)
    lat = np.asarray(latitudes, dtype=float)
    lon = np.asarray(longitudes, dtype=float)

    if not (values.ndim == 1 and values.shape == qa.shape == lat.shape == lon.shape):
        raise ValueError("values/qa/lat/lon must be equal-length 1-D arrays")

    _pixels_input = int(values.size)

    finite = (
        np.isfinite(values) & np.isfinite(qa) & np.isfinite(lat) & np.isfinite(lon)
    )
    # Quality filter: TROPOMI QA value. A QA < threshold means the retrieval
    # should be discarded (clouds, poor fitting...) — never averaged in.
    keep = finite & (qa >= qa_threshold)
    sel_idx = np.nonzero(keep)[0]

    # AOI filter: keep only pixels within `max_km` of the target point.
    dist = np.asarray(
        [_distance_km(lat[i], lon[i], target_lat, target_lon) for i in sel_idx],
        dtype=float,
    )
    inside = sel_idx[dist <= max_km]
    pixels_used = int(inside.size)

    if pixels_used == 0:
        raise ValueError(
            f"No valid TROPOMI NO2 pixels within {max_km:g} km of "
            f"({target_lat},{target_lon}) after QA threshold {qa_threshold:g} "
            f"(checked {_pixels_input} pixels)."
        )

    valid_values = values[inside]
    result = float(np.median(valid_values)) if method == "median" else float(np.mean(valid_values))

    methodology = {
        "quality_filter": f"TROPOMI qa_value >= {qa_threshold:g}",
        "pixels_input": _pixels_input,
        "pixels_used": pixels_used,
        "pixels_rejected": _pixels_input - pixels_used,
        "aggregation": method,
        "aoi_radius_km": max_km,
    }
    return {"value": result, "unit": "mol/m2", "methodology": methodology}
def extract_no2_from_arrays(
    product_arrays: dict,
    target_lat: float,
    target_lon: float,
    *,
    max_km: float = 15.0,
    qa_threshold: float = DEFAULT_QA_THRESHOLD,
    method: str = "median",
) -> dict:
    """Aggregate NO2 from an in-memory mapping of variable-name -> 1-D arrays.

    This is the seam used by the CDSE provider after it decodes a NetCDF
    product (with xarray): callers hand it the flattened arrays and it yields
    the same audited aggregation as :func:`aggregate_tropomi_no2`.
    """
    if NO2_DATA_VAR not in product_arrays:
        raise ValueError(
            f"product missing required variable {NO2_DATA_VAR!r}; "
            "cannot extract NO2"
        )
    qa = product_arrays.get(NO2_QA_VAR)
    if qa is None:
        raise ValueError(
            f"product has no {NO2_QA_VAR!r} layer; refusing to aggregate "
            "unfiltered NO2 (scientific integrity)"
        )
    return aggregate_tropomi_no2(
        product_arrays[NO2_DATA_VAR],
        qa,
        product_arrays[NO2_LAT_VAR],
        product_arrays[NO2_LON_VAR],
        target_lat,
        target_lon,
        max_km=max_km,
        qa_threshold=qa_threshold,
        method=method,
    )
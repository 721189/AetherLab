"""Sentinel-2 NDVI processing + temporal change detection (Phase 10).

Steps 17 & 18:

    Sentinel-2
        -> Red band (B04) + NIR band (B08)
        -> quality / cloud masking
        -> NDVI = (NIR - Red) / (NIR + Red)
        -> spatial aggregation -> mean/median/min/max/std/pixel_count

    NDVI today vs historical baseline
        -> delta_ndvi, percentage_change, z_score, anomaly flag

The module is deliberately pure NumPy so the scientific core is unit-testable
without downloading a single Sentinel-2 product.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

# Sentinel-2 MSI 10 m surface-reflectance bands used for NDVI.
RED_BAND = "B04"
NIR_BAND = "B08"
NDVI_UNIT = "index"


@dataclass
class NDVIResult:
    """Spatially aggregated NDVI over the AOI (Step 17)."""

    mean: float
    median: float
    minimum: float
    maximum: float
    std: float
    pixel_count: int
    pixels_input: int
    pixels_used: int
    pixels_rejected: int
    unit: str = NDVI_UNIT

    def to_dict(self) -> dict:
        return {
            "mean": round(self.mean, 4),
            "median": round(self.median, 4),
            "min": round(self.minimum, 4),
            "max": round(self.maximum, 4),
            "std": round(self.std, 4),
            "pixel_count": self.pixel_count,
            "unit": self.unit,
            "pixels_input": self.pixels_input,
            "pixels_used": self.pixels_used,
            "pixels_rejected": self.pixels_rejected,
        }


@dataclass
class NDVIBaseline:
    """Historical baseline used for step 18 change detection."""

    mean: float
    std: float
    n_observations: int


@dataclass
class TemporalChangeResult:
    """Step 18 — current NDVI vs a historical baseline."""

    delta_ndvi: float
    percentage_change: float  # relative to the baseline mean
    z_score: float
    anomaly: bool
    baseline: NDVIBaseline
    current: NDVIResult

    def to_dict(self) -> dict:
        return {
            "current": {
                "mean_ndvi": round(self.current.mean, 4),
                "pixel_count": self.current.pixel_count,
            },
            "baseline": {
                "mean": round(self.baseline.mean, 4),
                "std": round(self.baseline.std, 4),
                "n_observations": self.baseline.n_observations,
            },
            "delta_ndvi": round(self.delta_ndvi, 4),
            "percentage_change": round(self.percentage_change, 2),
            "z_score": round(self.z_score, 2),
            "anomaly": self.anomaly,
        }


# ---------------------------------------------------------------------------
# Core — Step 17
# ---------------------------------------------------------------------------
def compute_ndvi(red: Sequence[float], nir: Sequence[float], valid: Optional[Sequence[bool]] = None) -> np.ndarray:
    """Per-pixel NDVI = (NIR - Red) / (NIR + Red).

    Args:
        red: Sentinel-2 B04 (red) surface reflectance per pixel.
        nir: Sentinel-2 B08 (NIR) surface reflectance per pixel.
        valid: optional per-pixel boolean mask (True == usable). Pixels that
            are invalid, or where NIR + Red == 0 (division by zero), or whose
            NDVI falls outside [-1, 1] are set to NaN and excluded downstream.

    Returns:
        A ``float`` ndarray of shape `(N,)` (flattened) with NDVI values;
        unusable pixels carry NaN so aggregation can never mix them in.
    """
    red = np.asarray(red, dtype=float)
    nir = np.asarray(nir, dtype=float)
    if red.shape != nir.shape:
        raise ValueError("red and nir bands must have identical shape")
    if red.ndim != 1:
        red = red.ravel()
        nir = nir.ravel()

    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = (nir - red) / (nir + red)

    # Physics guard: NDVI cannot live outside [-1, 1]; NaN denominator or
    # outside-range -> mark unusable.
    valid_pixel = np.isfinite(ndvi) & (ndvi >= -1.0) & (ndvi <= 1.0)
    if valid is not None:
        v = np.asarray(valid, dtype=bool)
        if v.shape != red.shape:
            raise ValueError("valid mask must match the band shape")
        valid_pixel &= v.ravel()

    return np.where(valid_pixel, ndvi, np.nan)


def aggregate_ndvi(ndvi: np.ndarray) -> NDVIResult:
    """Spatially aggregate NDVI pixels, reporting the full statistics bundle.

    Never average invalid (NaN) pixels in. Pixels with NaN are *rejected* and
    counted so an auditor can see how much of the AOI actually contributed to
    the number.
    """
    values = ndvi.reshape(-1)
    pixels_input = int(values.size)
    usable = values[np.isfinite(values)]
    pixels_used = int(usable.size)
    pixels_rejected = pixels_input - pixels_used

    if pixels_used == 0:
        raise ValueError("No usable NDVI pixels after masking (empty or fully rejected scene)")

    return NDVIResult(
        mean=float(np.mean(usable)),
        median=float(np.median(usable)),
        minimum=float(np.min(usable)),
        maximum=float(np.max(usable)),
        std=float(np.std(usable)),
        pixel_count=pixels_used,
        pixels_input=pixels_input,
        pixels_used=pixels_used,
        pixels_rejected=pixels_rejected,
    )


# ---------------------------------------------------------------------------
# Step 18 — temporal change detection
# ---------------------------------------------------------------------------
def analyze_temporal_change(
    current: NDVIResult,
    baseline: NDVIBaseline,
    z_threshold: float = 2.5,
) -> TemporalChangeResult:
    """Compare today's NDVI against a historical baseline.

    ``z_score = (current_mean - baseline_mean) / baseline_std``; when the
    absolute z-score exceeds ``z_threshold`` (default 2.5 sigma) the change is
    flagged as an anomaly. ``percentage_change`` is relative to the baseline
    mean (guard against a zero/negative baseline).
    """
    delta = current.mean - baseline.mean
    if abs(baseline.mean) < 1e-12:
        pct_change = float("nan")
    else:
        pct_change = (delta / abs(baseline.mean)) * 100.0

    if baseline.std and math.isfinite(baseline.std) and baseline.std > 1e-12:
        z_score = delta / baseline.std
    elif abs(delta) < 1e-12:
        z_score = 0.0
    else:
        # No measurable baseline spread but the value moved: treat as a strong
        # signal rather than pretending there is no signal.
        z_score = float("inf")

    return TemporalChangeResult(
        delta_ndvi=delta,
        percentage_change=pct_change,
        z_score=z_score,
        anomaly=abs(z_score) > z_threshold,
        baseline=baseline,
        current=current,
    )
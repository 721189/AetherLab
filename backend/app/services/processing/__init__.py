"""Geospatial / EO data-processing helpers (quality-filtered aggregation).

Kept separate from the provider adapters so the scientific pipeline is a pure,
independently-testable module: no HTTP, no CDSE auth, no file I/O in the core
aggregation logic.
"""

from app.services.processing.sentinel_no2 import (
    aggregate_tropomi_no2,
    extract_no2_from_arrays,
)
from app.services.processing.sentinel2 import (
    NDVIResult,
    analyze_temporal_change,
    aggregate_ndvi,
    compute_ndvi,
)
from app.services.processing.validation import (
    ValidationResult,
    validate_no2,
)

__all__ = [
    "aggregate_tropomi_no2",
    "extract_no2_from_arrays",
    "NDVIResult",
    "analyze_temporal_change",
    "aggregate_ndvi",
    "compute_ndvi",
    "ValidationResult",
    "validate_no2",
]
"""Sentinel-5P validation benchmark (Phase 9).

Do not stop when extraction works — build a benchmark.

For a selected region we compare AetherLab NO2 against a reference /
product value and report standard skill metrics:

    MAE              mean absolute error
    RMSE             root mean square error
    bias             mean signed error (AetherLab - reference)
    correlation      Pearson r between predicted and reference
    missing %        fraction of the reference series we failed to predict

The validator is deliberately pure (no HTTP / CDSE / file I/O): it operates
on aligned value sequences, so the same code validates a real TROPOMI scene
or a synthetic fixture in tests.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence


@dataclass
class ValidationResult:
    """Skill metrics for one predicted-vs-reference comparison."""

    n: int  # number of aligned pairs actually compared
    mae: float
    rmse: float
    bias: float  # mean(AetherLab - reference)
    # Pearson correlation; None when n < 2 or either series is constant.
    correlation: Optional[float]
    missing_pct: float  # fraction of the reference series with no prediction
    n_predicted: int
    n_reference: int
    notes: List[str] = field(default_factory=list)


def pearson(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    """Pearson product-moment correlation coefficient.

    Returns None when the number of pairs is too small (< 2) or either
    series has zero variance (correlation is undefined there).
    """
    if len(x) != len(y) or len(x) < 2:
        return None
    mx = statistics.fmean(x)
    my = statistics.fmean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den_x = math.sqrt(sum((a - mx) ** 2 for a in x))
    den_y = math.sqrt(sum((b - my) ** 2 for b in y))
    if den_x == 0.0 or den_y == 0.0:
        return None
    return num / (den_x * den_y)


def _clean(predicted: Sequence[Optional[float]]) -> List[Optional[float]]:
    """Map None/NaN predicted values to None (treated as missing)."""
    cleaned: List[Optional[float]] = []
    for p in predicted:
        if p is None:
            cleaned.append(None)
            continue
        try:
            v = float(p)
        except (TypeError, ValueError):
            cleaned.append(None)
            continue
        if math.isnan(v) or math.isinf(v):
            cleaned.append(None)  # invalid predicts are "missing", never used
        else:
            cleaned.append(v)
    return cleaned


def validate_no2(
    predicted: Sequence[Optional[float]],
    reference: Sequence[Optional[float]],
    *,
    label: str = "",
) -> ValidationResult:
    """Compare AetherLab NO2 predictions against a reference series.

    Args:
        predicted: AetherLab NO2 values aligned 1:1 with ``reference``.
            None / NaN entries count as *missing predictions*.
        reference: reference / product values (same order).
        label: optional human-readable name for error messages / notes.

    Returns:
        :class:`ValidationResult` with MAE, RMSE, bias, correlation and the
        missing fraction. If *no* prediction could be made at all (all
        missing), the error metrics are NaN and ``notes`` explains why rather
        than silently reporting a perfect score.
    """
    pred = _clean(predicted)
    ref: List[Optional[float]] = []
    for r in reference:
        if r is None:
            ref.append(None)
            continue
        try:
            v = float(r)
        except (TypeError, ValueError):
            ref.append(None)
            continue
        ref.append(v if math.isfinite(v) else None)

    n_reference = len(ref)
    pairs: List[tuple[float, float]] = []
    missing = 0
    for p, r in zip(pred, ref):
        if p is not None and r is not None:
            pairs.append((p, r))
        else:
            missing += 1

    notes: List[str] = []
    if label:
        notes.append(label)
    missing_pct = (missing / n_reference) if n_reference else 0.0

    if not pairs:
        notes.append("No valid prediction pairs to compare.")
        return ValidationResult(
            n=0,
            mae=math.nan,
            rmse=math.nan,
            bias=math.nan,
            correlation=None,
            missing_pct=missing_pct,
            n_predicted=len([p for p in pred if p is not None]),
            n_reference=n_reference,
            notes=notes,
        )

    diffs = [p - r for p, r in pairs]
    n = len(pairs)
    mae = statistics.fmean(abs(d) for d in diffs)
    rmse = math.sqrt(statistics.fmean(d * d for d in diffs))
    bias = statistics.fmean(diffs)
    corr = pearson([p for p, _ in pairs], [r for _, r in pairs])

    if n < 5:
        notes.append("Fewer than 5 pairs — correlation is provisional.")
    if missing_pct > 0.25:
        notes.append(
            f"Over {missing_pct:.0%} of the reference went unpredicted."
        )

    return ValidationResult(
        n=n,
        mae=mae,
        rmse=rmse,
        bias=bias,
        correlation=corr,
        missing_pct=missing_pct,
        n_predicted=len([p for p in pred if p is not None]),
        n_reference=n_reference,
        notes=notes,
    )


def describe(result: ValidationResult) -> str:
    """A single-string summary of a benchmark result (for logs / reports)."""
    corr = f"{result.correlation:.3f}" if result.correlation is not None else "n/a"
    return (
        f"n={result.n} MAE={result.mae:.4g} RMSE={result.rmse:.4g} "
        f"bias={result.bias:+.4g} r={corr} missing={result.missing_pct:.1%}"
    )
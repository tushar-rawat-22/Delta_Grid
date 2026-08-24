from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass
from statistics import NormalDist
from typing import Sequence

_EULER_MASCHERONI = 0.5772156649015329
_STANDARD_NORMAL = NormalDist()


@dataclass(frozen=True)
class SearchAdjustedSharpeReport:
    """Diagnostic-only search-adjusted Sharpe inference."""

    status: str
    diagnostic_only: bool
    observations: int
    periods_per_year: int
    trial_count: int
    period_sharpe: float | None
    annualized_sharpe: float | None
    skewness: float | None
    kurtosis: float | None
    lag1_autocorrelation: float | None
    trial_sharpe_std: float | None
    expected_max_period_sharpe: float | None
    probabilistic_sharpe_ratio: float | None
    deflated_sharpe_ratio: float | None

    def to_dict(self) -> dict[str, bool | float | int | str | None]:
        return asdict(self)


def _finite(values: Sequence[float], *, label: str) -> list[float]:
    clean = [float(value) for value in values]
    if any(not math.isfinite(value) for value in clean):
        raise ValueError(f"{label} must contain only finite values")
    return clean


def _sample_moments(values: Sequence[float]) -> tuple[float, float, float, float]:
    size = len(values)
    if size < 4:
        raise ValueError("at least four observations are required")
    mean = statistics.fmean(values)
    deviations = [value - mean for value in values]
    second = statistics.fmean(value * value for value in deviations)
    if second <= 0:
        raise ValueError("returns must have positive variance")

    third = statistics.fmean(value**3 for value in deviations)
    fourth = statistics.fmean(value**4 for value in deviations)
    raw_skew = third / (second**1.5)
    skewness = math.sqrt(size * (size - 1)) / (size - 2) * raw_skew

    raw_excess = fourth / (second * second) - 3.0
    corrected_excess = (
        (size - 1)
        / ((size - 2) * (size - 3))
        * ((size + 1) * raw_excess + 6.0)
    )
    kurtosis = corrected_excess + 3.0
    sample_std = math.sqrt(
        sum(value * value for value in deviations) / (size - 1)
    )
    return mean, sample_std, skewness, kurtosis


def _lag1_autocorrelation(values: Sequence[float]) -> float | None:
    if len(values) < 3:
        return None
    left = values[:-1]
    right = values[1:]
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    numerator = sum(
        (x - left_mean) * (y - right_mean)
        for x, y in zip(left, right)
    )
    left_ss = sum((x - left_mean) ** 2 for x in left)
    right_ss = sum((y - right_mean) ** 2 for y in right)
    denominator = math.sqrt(left_ss * right_ss)
    return numerator / denominator if denominator > 0 else None


def probabilistic_sharpe_ratio(
    *,
    period_sharpe: float,
    benchmark_period_sharpe: float,
    observations: int,
    skewness: float,
    kurtosis: float,
) -> float:
    """Return the probability that estimated period Sharpe exceeds a benchmark."""
    if observations < 2:
        raise ValueError("observations must be at least two")
    values = (
        period_sharpe,
        benchmark_period_sharpe,
        skewness,
        kurtosis,
    )
    if any(not math.isfinite(value) for value in values):
        raise ValueError("Sharpe inputs must be finite")

    variance_adjustment = (
        1.0
        - skewness * period_sharpe
        + ((kurtosis - 1.0) / 4.0) * period_sharpe * period_sharpe
    )
    if variance_adjustment <= 0:
        raise ValueError("Sharpe sampling variance adjustment must be positive")
    statistic = (
        (period_sharpe - benchmark_period_sharpe)
        * math.sqrt(observations - 1)
        / math.sqrt(variance_adjustment)
    )
    return _STANDARD_NORMAL.cdf(statistic)


def expected_maximum_sharpe(trial_period_sharpes: Sequence[float]) -> float:
    """Expected best period Sharpe under a zero-skill search with this trial spread."""
    trials = _finite(trial_period_sharpes, label="trial_period_sharpes")
    trial_count = len(trials)
    if trial_count < 1:
        raise ValueError("at least one trial Sharpe is required")
    if trial_count == 1:
        return 0.0

    trial_std = statistics.stdev(trials)
    if trial_std == 0:
        return 0.0
    first_quantile = _STANDARD_NORMAL.inv_cdf(1.0 - 1.0 / trial_count)
    second_quantile = _STANDARD_NORMAL.inv_cdf(
        1.0 - 1.0 / (trial_count * math.e)
    )
    return trial_std * (
        (1.0 - _EULER_MASCHERONI) * first_quantile
        + _EULER_MASCHERONI * second_quantile
    )


def build_search_adjusted_sharpe_report(
    returns: Sequence[float],
    *,
    trial_period_sharpes: Sequence[float],
    periods_per_year: int,
) -> SearchAdjustedSharpeReport:
    """Build PSR/DSR diagnostics without changing research admission decisions."""
    if isinstance(periods_per_year, bool) or periods_per_year <= 0:
        raise ValueError("periods_per_year must be a positive integer")
    if int(periods_per_year) != periods_per_year:
        raise ValueError("periods_per_year must be a positive integer")

    clean_returns = _finite(returns, label="returns")
    trials = _finite(trial_period_sharpes, label="trial_period_sharpes")
    if not trials:
        raise ValueError("at least one trial Sharpe is required")

    common = {
        "diagnostic_only": True,
        "observations": len(clean_returns),
        "periods_per_year": int(periods_per_year),
        "trial_count": len(trials),
    }
    trial_sharpe_std = statistics.stdev(trials) if len(trials) > 1 else 0.0
    if len(clean_returns) < 4:
        return SearchAdjustedSharpeReport(
            status="INSUFFICIENT_OBSERVATIONS",
            **common,
            period_sharpe=None,
            annualized_sharpe=None,
            skewness=None,
            kurtosis=None,
            lag1_autocorrelation=_lag1_autocorrelation(clean_returns),
            trial_sharpe_std=trial_sharpe_std,
            expected_max_period_sharpe=None,
            probabilistic_sharpe_ratio=None,
            deflated_sharpe_ratio=None,
        )

    try:
        mean, sample_std, skewness, kurtosis = _sample_moments(clean_returns)
    except ValueError as exc:
        if str(exc) != "returns must have positive variance":
            raise
        return SearchAdjustedSharpeReport(
            status="ZERO_VARIANCE_RETURNS",
            **common,
            period_sharpe=None,
            annualized_sharpe=None,
            skewness=None,
            kurtosis=None,
            lag1_autocorrelation=_lag1_autocorrelation(clean_returns),
            trial_sharpe_std=trial_sharpe_std,
            expected_max_period_sharpe=None,
            probabilistic_sharpe_ratio=None,
            deflated_sharpe_ratio=None,
        )

    period_sharpe = mean / sample_std
    expected_max = expected_maximum_sharpe(trials)
    psr = probabilistic_sharpe_ratio(
        period_sharpe=period_sharpe,
        benchmark_period_sharpe=0.0,
        observations=len(clean_returns),
        skewness=skewness,
        kurtosis=kurtosis,
    )
    dsr = probabilistic_sharpe_ratio(
        period_sharpe=period_sharpe,
        benchmark_period_sharpe=expected_max,
        observations=len(clean_returns),
        skewness=skewness,
        kurtosis=kurtosis,
    )
    return SearchAdjustedSharpeReport(
        status="COMPLETE",
        **common,
        period_sharpe=period_sharpe,
        annualized_sharpe=period_sharpe * math.sqrt(int(periods_per_year)),
        skewness=skewness,
        kurtosis=kurtosis,
        lag1_autocorrelation=_lag1_autocorrelation(clean_returns),
        trial_sharpe_std=trial_sharpe_std,
        expected_max_period_sharpe=expected_max,
        probabilistic_sharpe_ratio=psr,
        deflated_sharpe_ratio=dsr,
    )

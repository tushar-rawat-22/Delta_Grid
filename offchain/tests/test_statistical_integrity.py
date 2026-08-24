from __future__ import annotations

import math

import pytest

from offchain.research.statistical_integrity import (
    build_search_adjusted_sharpe_report,
    expected_maximum_sharpe,
    probabilistic_sharpe_ratio,
)


RETURNS = [
    0.010, -0.005, 0.008, -0.002, 0.006,
    0.004, -0.003, 0.007, 0.002, -0.001,
] * 10


def test_probabilistic_sharpe_is_half_at_its_benchmark() -> None:
    probability = probabilistic_sharpe_ratio(
        period_sharpe=0.2,
        benchmark_period_sharpe=0.2,
        observations=100,
        skewness=0.0,
        kurtosis=3.0,
    )
    assert probability == pytest.approx(0.5)


def test_one_trial_has_no_search_inflation() -> None:
    report = build_search_adjusted_sharpe_report(
        RETURNS,
        trial_period_sharpes=[0.12],
        periods_per_year=365,
    )
    assert report.status == "COMPLETE"
    assert report.diagnostic_only is True
    assert report.expected_max_period_sharpe == pytest.approx(0.0)
    assert report.deflated_sharpe_ratio == pytest.approx(
        report.probabilistic_sharpe_ratio
    )


def test_more_variable_search_deflates_confidence() -> None:
    report = build_search_adjusted_sharpe_report(
        RETURNS,
        trial_period_sharpes=[value / 100 for value in range(-20, 21)],
        periods_per_year=365,
    )
    assert report.expected_max_period_sharpe is not None
    assert report.expected_max_period_sharpe > 0
    assert report.probabilistic_sharpe_ratio is not None
    assert report.deflated_sharpe_ratio is not None
    assert report.deflated_sharpe_ratio < report.probabilistic_sharpe_ratio


def test_report_exposes_non_normality_and_serial_dependence_inputs() -> None:
    report = build_search_adjusted_sharpe_report(
        RETURNS,
        trial_period_sharpes=[0.05, 0.08, 0.12, 0.15],
        periods_per_year=365,
    )
    assert report.skewness is not None and math.isfinite(report.skewness)
    assert report.kurtosis is not None and math.isfinite(report.kurtosis)
    assert report.lag1_autocorrelation is not None
    assert -1.0 <= report.lag1_autocorrelation <= 1.0
    assert report.period_sharpe is not None
    assert report.annualized_sharpe == pytest.approx(
        report.period_sharpe * math.sqrt(365)
    )


def test_insufficient_and_zero_variance_inputs_are_not_overstated() -> None:
    short = build_search_adjusted_sharpe_report(
        [0.01, -0.01, 0.02],
        trial_period_sharpes=[0.1],
        periods_per_year=365,
    )
    assert short.status == "INSUFFICIENT_OBSERVATIONS"
    assert short.probabilistic_sharpe_ratio is None
    assert short.deflated_sharpe_ratio is None

    flat = build_search_adjusted_sharpe_report(
        [0.01] * 10,
        trial_period_sharpes=[0.1, 0.2],
        periods_per_year=365,
    )
    assert flat.status == "ZERO_VARIANCE_RETURNS"
    assert flat.period_sharpe is None
    assert flat.deflated_sharpe_ratio is None


def test_invalid_inputs_fail_closed() -> None:
    with pytest.raises(ValueError, match="finite"):
        build_search_adjusted_sharpe_report(
            [0.01, float("nan"), 0.02, 0.03],
            trial_period_sharpes=[0.1],
            periods_per_year=365,
        )
    with pytest.raises(ValueError, match="one trial"):
        build_search_adjusted_sharpe_report(
            RETURNS,
            trial_period_sharpes=[],
            periods_per_year=365,
        )
    with pytest.raises(ValueError, match="positive integer"):
        build_search_adjusted_sharpe_report(
            RETURNS,
            trial_period_sharpes=[0.1],
            periods_per_year=0,
        )


def test_expected_maximum_increases_with_trial_dispersion() -> None:
    narrow = expected_maximum_sharpe([0.09, 0.10, 0.11, 0.10])
    wide = expected_maximum_sharpe([-0.2, 0.0, 0.2, 0.4])
    assert wide > narrow >= 0

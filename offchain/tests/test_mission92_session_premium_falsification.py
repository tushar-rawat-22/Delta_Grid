from __future__ import annotations

import numpy as np

from offchain.backtest.mission92_session_premium_falsification import (
    choose_candidate,
    holm_adjust,
    load_pair_costs,
    maximum_drawdown_pct,
    profit_factor_metrics,
)


def test_pair_specific_cost_loading() -> None:
    snapshot = {
        "status": "PASS",
        "instrument": "SPOT_ONLY",
        "combined_spot_perpetual_cost_used": False,
        "pair_costs": {
            "BTC/USDT": {
                "normal_round_trip_cost_bps": 26,
                "conservative_round_trip_cost_bps": 34,
                "severe_round_trip_cost_bps": 62,
            },
            "ETH/USDT": {
                "normal_round_trip_cost_bps": 27,
                "conservative_round_trip_cost_bps": 36,
                "severe_round_trip_cost_bps": 67,
            },
            "SOL/USDT": {
                "normal_round_trip_cost_bps": 30,
                "conservative_round_trip_cost_bps": 42,
                "severe_round_trip_cost_bps": 82,
            },
        },
    }

    costs = load_pair_costs(snapshot)

    assert costs["BTC/USDT"] == {
        "normal": 26.0,
        "conservative": 34.0,
        "severe": 62.0,
    }

    assert costs["SOL/USDT"][
        "conservative"
    ] == 42.0


def test_profit_factor() -> None:
    value, unbounded = profit_factor_metrics(
        np.asarray(
            [0.02, -0.01, 0.03, -0.01],
            dtype=float,
        )
    )

    assert value == 2.5
    assert unbounded is False


def test_unbounded_profit_factor() -> None:
    value, unbounded = profit_factor_metrics(
        np.asarray(
            [0.01, 0.02],
            dtype=float,
        )
    )

    assert value is None
    assert unbounded is True


def test_drawdown_is_positive() -> None:
    drawdown = maximum_drawdown_pct(
        np.asarray(
            [0.02, -0.01, -0.02, 0.01],
            dtype=float,
        )
    )

    assert drawdown > 0.0


def test_holm_adjustment() -> None:
    adjusted = holm_adjust(
        {
            "A": 0.01,
            "B": 0.04,
            "C": 0.20,
        }
    )

    assert adjusted == {
        "A": 0.03,
        "B": 0.08,
        "C": 0.20,
    }


def test_selection_uses_conservative_mean() -> None:
    summaries = {
        "A": {
            "normal": {
                "total_net_return_pct": 2.0,
            },
            "conservative": {
                "trade_count": 120,
                "total_net_return_pct": 1.0,
                "profit_factor": 1.20,
                "profit_factor_unbounded": False,
                "maximum_drawdown_pct": 3.0,
                "mean_net_return_bps": 1.0,
            },
        },
        "B": {
            "normal": {
                "total_net_return_pct": 3.0,
            },
            "conservative": {
                "trade_count": 120,
                "total_net_return_pct": 2.0,
                "profit_factor": 1.30,
                "profit_factor_unbounded": False,
                "maximum_drawdown_pct": 4.0,
                "mean_net_return_bps": 2.0,
            },
        },
    }

    assert choose_candidate(summaries) == "B"

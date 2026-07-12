from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path

from offchain.backtest.mission90_directional_strategy_tournament import (
    CHARTER_ID,
    CONSERVATIVE_SCENARIO,
    DECISION_CONTINUE,
    DECISION_REJECT,
    DECISION_SPOT,
    EVALUATION_PROTOCOL,
    HOUR_MS,
    MISSION91_PAUSED,
    MISSION91_READY,
    NAV_BANDS,
    NORMAL_SCENARIO,
    PRIMARY_NAV_BAND,
    SEVERE_SCENARIO,
    SYMBOLS,
    VARIANTS,
    MarketSeries,
    build_charter_payload,
    build_directional_cost_profiles,
    choose_candidate,
    decision_for_selection,
    desired_direction,
    ensure_schema,
    funding_cash_flow_usd,
    lock_json_envelope,
    maximum_drawdown_pct,
    protocol_hash,
    simulate_variant,
    target_notional,
)


def fake_contract() -> dict:
    return {
        "initial_cost_assumptions": {
            "spot_entry_fee_bps": 10,
            "spot_exit_fee_bps": 10,
            "perpetual_entry_fee_bps": 5,
            "perpetual_exit_fee_bps": 5,
            "spot_slippage_per_side_bps": 2,
            "perpetual_slippage_per_side_bps": 2,
            "cost_reduction_after_results_allowed": False,
        },
        "research_splits": [
            {
                "name": "development",
                "start": "2024-01-01T00:00:00+00:00",
                "end_exclusive": "2025-07-01T00:00:00+00:00",
            },
            {
                "name": "validation",
                "start": "2025-07-01T00:00:00+00:00",
                "end_exclusive": "2026-01-01T00:00:00+00:00",
            },
            {
                "name": "untouched_holdout",
                "start": "2026-01-01T00:00:00+00:00",
                "end_exclusive": "2026-07-01T00:00:00+00:00",
            },
        ],
    }


def synthetic_series(
    symbol: str,
    instrument: str,
    hours_count: int = 800,
    slope: float = 0.08,
) -> MarketSeries:
    start = 1_700_000_000_000 // HOUR_MS * HOUR_MS
    hours = [start + index * HOUR_MS for index in range(hours_count)]
    closes = [100.0 + slope * index for index in range(hours_count)]
    opens = [value - slope / 2 for value in closes]
    highs = [value * 1.002 for value in closes]
    lows = [value * 0.998 for value in closes]
    prefix = [0.0]
    for close in closes:
        prefix.append(prefix[-1] + close)
    funding = {}
    if instrument == "PERPETUAL":
        for index in range(8, hours_count, 8):
            funding[hours[index]] = {
                "actual_time_ms": hours[index],
                "funding_rate": 0.0001,
                "mark_price": closes[index],
            }
    return MarketSeries(
        symbol=symbol,
        instrument=instrument,
        start_ms=hours[0],
        end_ms=hours[-1] + HOUR_MS,
        hours=hours,
        open_price=opens,
        high_price=highs,
        low_price=lows,
        close_price=closes,
        hour_to_index={hour: index for index, hour in enumerate(hours)},
        prefix_close=prefix,
        funding_by_hour=funding,
        regime_by_hour={hour: "MEDIUM_VOLATILITY" for hour in hours},
    )


def synthetic_data() -> dict[tuple[str, str], MarketSeries]:
    return {
        (symbol, instrument): synthetic_series(symbol, instrument)
        for symbol in SYMBOLS
        for instrument in ("SPOT", "PERPETUAL")
    }


def dummy_result(
    variant: dict,
    scenario: str,
    nav_band: str,
    return_pct: float = 10.0,
) -> dict:
    return {
        "variant_id": variant["variant_id"],
        "family": variant["family"],
        "instrument": variant["instrument"],
        "scenario_code": scenario,
        "nav_band": nav_band,
        "closed_trade_count": 24,
        "net_pnl_usd": 3000.0,
        "net_return_pct": return_pct,
        "annualized_return_pct": 7.0,
        "sharpe_ratio": 1.2,
        "maximum_drawdown_pct": 8.0,
        "calmar_ratio": 0.875,
        "turnover_multiple": 8.0,
        "positive_asset_count": 3,
        "maximum_asset_contribution_pct": 40.0,
        "maximum_quarter_contribution_pct": 30.0,
        "cost_to_positive_gross_profit_ratio": 0.2,
        "funding_pnl_usd": 0.0,
        "net_pnl_by_quarter": {"2024-Q1": 1.0, "2024-Q2": 1.0},
        "daily_equity": [],
        "trades": [],
    }


def dummy_result_matrix(return_pct: float = 10.0):
    output = {}
    for variant in VARIANTS:
        for scenario in (NORMAL_SCENARIO, CONSERVATIVE_SCENARIO, SEVERE_SCENARIO):
            for band in NAV_BANDS:
                output[(variant["variant_id"], scenario, band["nav_band"])] = (
                    dummy_result(variant, scenario, band["nav_band"], return_pct)
                )
    return output


def benchmarks():
    return {
        "CASH": {
            "net_return_pct": 0.0,
            "maximum_drawdown_pct": 0.0,
            "calmar_ratio": 0.0,
            "sharpe_ratio": 0.0,
        },
        "BTC_SPOT_BUY_HOLD": {
            "net_return_pct": 5.0,
            "maximum_drawdown_pct": 20.0,
            "calmar_ratio": 0.3,
            "sharpe_ratio": 0.4,
        },
        "EQUAL_WEIGHT_SPOT_BUY_HOLD": {
            "net_return_pct": 6.0,
            "maximum_drawdown_pct": 18.0,
            "calmar_ratio": 0.35,
            "sharpe_ratio": 0.45,
        },
    }


def test_variant_budget_and_family_counts() -> None:
    assert len(VARIANTS) == 12
    counts = {}
    for variant in VARIANTS:
        counts[variant["family"]] = counts.get(variant["family"], 0) + 1
    assert counts == {
        "SPOT_TREND": 4,
        "PERPETUAL_TREND": 4,
        "VOLATILITY_BREAKOUT": 4,
    }


def test_variant_ids_and_neighbors_are_closed() -> None:
    identifiers = {variant["variant_id"] for variant in VARIANTS}
    assert len(identifiers) == 12
    for variant in VARIANTS:
        assert set(variant["neighbor_ids"]) <= identifiers
        assert variant["variant_id"] not in variant["neighbor_ids"]


def test_protocol_hash_is_deterministic() -> None:
    assert protocol_hash(EVALUATION_PROTOCOL) == protocol_hash(
        json.loads(json.dumps(EVALUATION_PROTOCOL))
    )


def test_protocol_seals_validation_and_holdout() -> None:
    boundary = EVALUATION_PROTOCOL["research_boundary"]
    assert boundary["validation_rows_allowed"] == 0
    assert boundary["holdout_rows_allowed"] == 0
    assert boundary["live_trading_allowed"] is False
    assert boundary["capital_deployment_allowed"] is False


def test_directional_cost_profile_count_and_monotonicity() -> None:
    profiles = build_directional_cost_profiles(fake_contract())
    assert len(profiles) == 54
    for instrument in ("SPOT", "PERPETUAL"):
        for symbol in SYMBOLS:
            normal = profiles[(NORMAL_SCENARIO, instrument, symbol, PRIMARY_NAV_BAND)]
            conservative = profiles[
                (CONSERVATIVE_SCENARIO, instrument, symbol, PRIMARY_NAV_BAND)
            ]
            severe = profiles[(SEVERE_SCENARIO, instrument, symbol, PRIMARY_NAV_BAND)]
            assert normal.entry_cost_bps + normal.exit_cost_bps < (
                conservative.entry_cost_bps + conservative.exit_cost_bps
            )
            assert conservative.entry_cost_bps + conservative.exit_cost_bps < (
                severe.entry_cost_bps + severe.exit_cost_bps
            )


def test_directional_cost_model_is_single_leg() -> None:
    profiles = build_directional_cost_profiles(fake_contract())
    profile = profiles[(CONSERVATIVE_SCENARIO, "SPOT", "BTCUSDT", PRIMARY_NAV_BAND)]
    assert profile.instrument == "SPOT"
    assert profile.entry_cost_bps > 0
    assert profile.exit_cost_bps > 0
    assert "SINGLE_LEG" in profile.uncertainty_label


def test_positive_funding_long_pays_and_short_receives() -> None:
    assert funding_cash_flow_usd(1, 10_000.0, 0.0001) == -1.0
    assert funding_cash_flow_usd(-1, 10_000.0, 0.0001) == 1.0


def test_spot_return_signal_never_shorts() -> None:
    series = synthetic_series("BTCUSDT", "SPOT", slope=-0.08)
    variant = next(item for item in VARIANTS if item["variant_id"] == "SPOT_RETURN_168")
    assert desired_direction(variant, series, 400, 0) == 0


def test_perpetual_return_signal_can_short() -> None:
    series = synthetic_series("BTCUSDT", "PERPETUAL", slope=-0.08)
    variant = next(item for item in VARIANTS if item["variant_id"] == "PERP_RETURN_168")
    assert desired_direction(variant, series, 400, 0) == -1


def test_target_notional_never_exceeds_cap() -> None:
    series = synthetic_series("BTCUSDT", "SPOT")
    result = target_notional(series, 400, 10_000.0)
    assert 0.0 <= result <= 10_000.0


def test_lock_json_envelope_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "protocol.json"
    first = lock_json_envelope(path, "protocol", {"a": 1}, "LOCKED", "2026-07-12T00:00:00+00:00")
    second = lock_json_envelope(path, "protocol", {"a": 1}, "LOCKED", "2026-07-13T00:00:00+00:00")
    assert first == second


def test_schema_creation(tmp_path: Path) -> None:
    path = tmp_path / "mission90.db"
    ensure_schema(path)
    with sqlite3.connect(path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "mission90_protocols",
        "mission90_directional_cost_profiles",
        "mission90_runs",
        "mission90_variant_results",
        "mission90_variant_gates",
        "mission90_selected_trade_ledger",
        "mission90_strategy_charters",
        "mission90_reports",
    } <= tables


def test_maximum_drawdown_calculation() -> None:
    equity = [(1, 100.0), (2, 120.0), (3, 90.0), (4, 110.0)]
    assert maximum_drawdown_pct(equity) == 25.0


def test_choose_candidate_selects_at_most_one() -> None:
    selected, gates, eligible = choose_candidate(
        VARIANTS,
        dummy_result_matrix(),
        benchmarks(),
    )
    assert selected is not None
    assert selected["variant_id"] in eligible
    assert len(gates) == 12
    assert len([selected]) == 1


def test_no_candidate_rejects_directional_hypotheses() -> None:
    results = dummy_result_matrix(return_pct=-5.0)
    selected, gates, _ = choose_candidate(VARIANTS, results, benchmarks())
    assert selected is None
    decision, mission91, _ = decision_for_selection(selected, gates, results)
    assert decision == DECISION_REJECT
    assert mission91 != MISSION91_READY


def test_insufficient_sample_can_continue_without_validation() -> None:
    results = dummy_result_matrix(return_pct=5.0)
    gates = {
        variant["variant_id"]: [
            {
                "gate_name": "MINIMUM_CLOSED_TRADES",
                "gate_status": "FAIL",
                "mandatory": True,
            }
        ]
        for variant in VARIANTS
    }
    decision, mission91, _ = decision_for_selection(None, gates, results)
    assert decision == DECISION_CONTINUE
    assert mission91 == MISSION91_PAUSED


def test_charter_payload_locks_no_retuning() -> None:
    variant = deepcopy(VARIANTS[0])
    result = dummy_result(variant, CONSERVATIVE_SCENARIO, PRIMARY_NAV_BAND)
    payload = build_charter_payload(
        protocol_digest="abc",
        decision=DECISION_SPOT,
        selected=variant,
        selected_result=result,
        mission91_status=MISSION91_READY,
        next_workstream="MISSION91_FIXED_VALIDATION_AND_ROBUSTNESS_PACK",
        contract=fake_contract(),
    )
    assert payload["charter_id"] == CHARTER_ID
    assert payload["mission91_evaluation"]["parameter_retuning_allowed"] is False
    assert payload["mission91_evaluation"]["validation_performance_already_read"] is False
    assert payload["mission91_evaluation"]["holdout_performance_already_read"] is False


def test_simulation_is_deterministic_and_uses_delayed_entry() -> None:
    data = synthetic_data()
    profiles = build_directional_cost_profiles(fake_contract())
    variant = next(item for item in VARIANTS if item["variant_id"] == "SPOT_MA_24_168")
    first = simulate_variant(data, variant, profiles, CONSERVATIVE_SCENARIO, PRIMARY_NAV_BAND)
    second = simulate_variant(data, variant, profiles, CONSERVATIVE_SCENARIO, PRIMARY_NAV_BAND)
    comparable_first = {key: value for key, value in first.items() if key != "daily_equity"}
    comparable_second = {key: value for key, value in second.items() if key != "daily_equity"}
    assert comparable_first == comparable_second
    assert first["trades"]
    start = data[("BTCUSDT", "SPOT")].start_ms
    for trade in first["trades"]:
        entry_index = (trade["entry_time_ms"] - start) // HOUR_MS
        assert entry_index % 4 == 1

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from offchain.backtest.mission89_baseline_strategy_falsification import (
    DECISION_ADVANCE,
    DECISION_CONTINUE,
    DECISION_REJECT,
    EVALUATION_PROTOCOL,
    MISSION90_NOT_AUTHORIZED,
    MISSION90_PAUSED,
    MISSION90_READY,
    CostProfile,
    SymbolData,
    Variant,
    calculate_pbo,
    create_variants,
    deflated_sharpe_probability,
    determine_decision,
    ensure_schema,
    lock_protocol,
    parameter_neighbors,
    protocol_hash,
    simulate_symbol,
    strictly_next_hour,
)
from offchain.research.funding_carry_research_contract import (
    MISSION85_CONTRACT,
)

HOUR_MS = 3_600_000
START_MS = 1_704_067_200_000


def make_symbol_data() -> SymbolData:
    hours = list(range(START_MS, START_MS + 40 * HOUR_MS, HOUR_MS))
    funding = {
        hour: {
            "actual_time_ms": hour,
            "funding_rate": 0.0001,
            "mark_price": 100.0,
        }
        for index, hour in enumerate(hours)
        if index in {0, 8, 16, 24, 32}
    }
    return SymbolData(
        symbol="BTCUSDT",
        start_ms=START_MS,
        end_ms=START_MS + 40 * HOUR_MS,
        hours=hours,
        spot_open={hour: 100.0 for hour in hours},
        perpetual_open={hour: 100.0 for hour in hours},
        mark_open={hour: 100.0 for hour in hours},
        funding_by_hour=funding,
        volatility_regime_by_hour={
            hour: "MEDIUM_VOLATILITY" for hour in hours
        },
    )


def zero_cost_profile() -> CostProfile:
    return CostProfile(
        scenario_code="TEST",
        symbol="BTCUSDT",
        notional_band="TEST",
        per_leg_notional_usd=1000.0,
        entry_cost_bps=0.0,
        exit_cost_bps=0.0,
        modeled_rebalance_cost_bps=0.0,
        hedge_delay_cost_bps=0.0,
        partial_fill_cost_bps=0.0,
        funding_reconciliation_buffer_bps=0.0,
        operational_buffer_bps=0.0,
        assumed_rebalance_count=1,
    )


def test_protocol_hash_is_deterministic() -> None:
    assert protocol_hash(EVALUATION_PROTOCOL) == protocol_hash(
        json.loads(json.dumps(EVALUATION_PROTOCOL))
    )


def test_protocol_keeps_holdout_sealed() -> None:
    assert (
        EVALUATION_PROTOCOL["evaluation_windows"]["untouched_holdout"]
        == "SEALED_AND_FORBIDDEN"
    )
    assert EVALUATION_PROTOCOL["research_boundary"]["holdout_rows_allowed"] == 0


def test_contract_has_twelve_variants() -> None:
    variants = create_variants(MISSION85_CONTRACT)
    assert len(variants) == 12
    assert len({variant.variant_id for variant in variants}) == 12


def test_strictly_next_hour_never_returns_same_hour() -> None:
    assert strictly_next_hour(START_MS) == START_MS + HOUR_MS
    assert strictly_next_hour(START_MS + 5) == START_MS + HOUR_MS


def test_trigger_funding_is_not_collected() -> None:
    result = simulate_symbol(
        data=make_symbol_data(),
        variant=Variant("V01", 0.5, 50.0, 14),
        profile=zero_cost_profile(),
        funding_lookback_settlements=3,
        exit_after_nonpositive_settlements=2,
        emergency_exit_basis_bps=150.0,
        rebalance_delta_drift_pct=1.0,
    )
    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    assert trade["entry_time_ms"] == START_MS + 17 * HOUR_MS
    assert trade["funding_settlement_count"] == 2
    assert trade["funding_pnl_usd"] == pytest.approx(0.2)


def test_cashflow_ledger_reconciles() -> None:
    result = simulate_symbol(
        data=make_symbol_data(),
        variant=Variant("V01", 0.5, 50.0, 14),
        profile=zero_cost_profile(),
        funding_lookback_settlements=3,
        exit_after_nonpositive_settlements=2,
        emergency_exit_basis_bps=150.0,
        rebalance_delta_drift_pct=1.0,
    )
    trade = result["trades"][0]
    gross = (
        trade["spot_pnl_usd"]
        + trade["perpetual_pnl_usd"]
        + trade["funding_pnl_usd"]
    )
    costs = sum(
        trade[field]
        for field in (
            "entry_cost_usd",
            "exit_cost_usd",
            "rebalance_cost_usd",
            "hedge_delay_cost_usd",
            "partial_fill_cost_usd",
            "funding_reconciliation_cost_usd",
            "operational_cost_usd",
        )
    )
    assert trade["gross_pnl_usd"] == pytest.approx(gross)
    assert trade["net_pnl_usd"] == pytest.approx(gross - costs)


def test_parameter_neighbors_are_immediate_only() -> None:
    variants = create_variants(MISSION85_CONTRACT)
    selected = variants[0]
    neighbor_ids = parameter_neighbors(selected, variants)
    assert len(neighbor_ids) >= 2
    assert selected.variant_id not in neighbor_ids


def test_pbo_is_bounded() -> None:
    results = {
        "V01": {"net_pnl_by_quarter": {"Q1": 3, "Q2": 2, "Q3": 1, "Q4": 0}},
        "V02": {"net_pnl_by_quarter": {"Q1": 0, "Q2": 1, "Q3": 2, "Q4": 3}},
        "V03": {"net_pnl_by_quarter": {"Q1": 1, "Q2": 1, "Q3": 1, "Q4": 1}},
    }
    value = calculate_pbo(results)
    assert 0.0 <= value <= 1.0


def test_deflated_sharpe_probability_is_bounded() -> None:
    value = deflated_sharpe_probability(
        [0.01, 0.02, -0.005, 0.015, 0.007],
        [0.1, 0.2, 0.05, -0.1],
        12,
    )
    assert 0.0 <= value <= 1.0


def test_no_candidate_rejects_strategy() -> None:
    decision, status, _ = determine_decision(
        selected=None,
        gates=[],
        validation_closed_positions=0,
        dsr_sample_size=0,
        protocol=EVALUATION_PROTOCOL,
    )
    assert decision == DECISION_REJECT
    assert status == MISSION90_NOT_AUTHORIZED


def test_insufficient_evidence_pauses_holdout() -> None:
    decision, status, _ = determine_decision(
        selected=Variant("V01", 0.5, 25.0, 7),
        gates=[],
        validation_closed_positions=5,
        dsr_sample_size=5,
        protocol=EVALUATION_PROTOCOL,
    )
    assert decision == DECISION_CONTINUE
    assert status == MISSION90_PAUSED


def test_passing_mandatory_gates_advances() -> None:
    decision, status, _ = determine_decision(
        selected=Variant("V01", 0.5, 25.0, 7),
        gates=[
            {
                "gate_status": "PASS",
                "mandatory": True,
            }
        ],
        validation_closed_positions=12,
        dsr_sample_size=12,
        protocol=EVALUATION_PROTOCOL,
    )
    assert decision == DECISION_ADVANCE
    assert status == MISSION90_READY


def test_failed_mandatory_gate_rejects() -> None:
    decision, status, _ = determine_decision(
        selected=Variant("V01", 0.5, 25.0, 7),
        gates=[
            {
                "gate_status": "FAIL",
                "mandatory": True,
            }
        ],
        validation_closed_positions=12,
        dsr_sample_size=12,
        protocol=EVALUATION_PROTOCOL,
    )
    assert decision == DECISION_REJECT
    assert status == MISSION90_NOT_AUTHORIZED


def test_protocol_lock_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "protocol.json"
    first = lock_protocol(path, locked_at="2026-07-12T00:00:00+00:00")
    second = lock_protocol(path, locked_at="2026-07-12T01:00:00+00:00")
    assert first == second


def test_schema_is_created(tmp_path: Path) -> None:
    db_path = tmp_path / "mission89.db"
    ensure_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "mission89_protocols",
        "mission89_runs",
        "mission89_variant_results",
        "mission89_selected_trade_ledger",
        "mission89_gates",
        "mission89_reports",
    }.issubset(tables)

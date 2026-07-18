from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal, getcontext
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "contracts" / "ALPHA_SEARCH_B_PROTOCOL_V1.json"
RESET_PATH = ROOT / "contracts" / "DELTAGRID_PRODUCT_RESET_V1.json"
EXPECTED_HASH = "ee82fdb3758028cfa6455ffa610cbff46855890ded65cc2175801897fe509469"
EXPECTED_IDS = [
    "BTC_SELF_FLOW_PERSISTENCE_60M",
    "BTC_SELF_FLOW_PERSISTENCE_120M",
    "BTC_FLOW_LEADS_ETH_60M",
    "BTC_FLOW_LEADS_SOL_60M",
]


def load(path: Path = CONTRACT_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_hash(value: dict) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def nearest_rank(values: list[Decimal], probability: Decimal) -> Decimal:
    rank = math.ceil(probability * len(values))
    return sorted(values)[rank - 1]


def test_identity_hash_and_zero_evidence_access() -> None:
    contract = load()
    assert contract["status"] == "PROTOCOL_LOCKED_DATA_NOT_ACCESSED"
    assert contract["economic_family_count"] == 1
    core = dict(contract)
    assert core.pop("contract_hash_sha256") == EXPECTED_HASH
    assert canonical_hash(core) == EXPECTED_HASH
    assert "derived_seed" not in json.dumps(core).lower()
    mutated = json.loads(json.dumps(core))
    mutated["candidates"][0]["holding_minutes"] = 61
    mutated_hash = canonical_hash(mutated)
    assert mutated_hash != EXPECTED_HASH
    for candidate_id in EXPECTED_IDS:
        original = hashlib.sha256(f"{EXPECTED_HASH}:{candidate_id}".encode()).hexdigest()
        changed = hashlib.sha256(f"{mutated_hash}:{candidate_id}".encode()).hexdigest()
        assert original[:16] != changed[:16]
    access = contract["evidence_access"]
    assert access == {
        "market_data_accessed": False,
        "market_return_fields_accessed": 0,
        "strategy_results_evaluated": 0,
        "pnl_metrics_evaluated": 0,
        "validation_performance_accessed": False,
        "holdout_performance_accessed": False,
        "result_metrics_embedded": False,
    }


def test_revised_flow_only_candidates_are_exact() -> None:
    contract = load()
    candidates = contract["candidates"]
    assert [item["candidate_id"] for item in candidates] == EXPECTED_IDS
    assert [item["holding_minutes"] for item in candidates] == [60, 120, 60, 60]
    assert [item["target_pair"] for item in candidates] == [
        "BTCUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT"
    ]
    signals = " ".join(part for item in candidates for part in item["signal"])
    assert "return" not in signals.lower()
    exclusions = contract["candidate_exclusions"]
    assert exclusions["price_return_entry_threshold"] is False
    for field in (
        "reversal", "breakout", "momentum_tail", "mean_reversion",
        "machine_learning", "market_making", "maker_fill_assumption",
    ):
        assert exclusions[field] is False


def test_trade_flow_interpretation_and_source_boundary() -> None:
    data = load()["data_contract"]
    assert data["interpretation"] == "AGGREGATED_TRADE_FLOW_PROXY"
    assert data["pairs"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert data["official_checksums_required"] is True
    assert data["timestamp_units"] == ["MILLISECOND", "POST_2025_MICROSECOND"]
    assert data["raw_archives_location"] == "OUTSIDE_GIT"
    for field in (
        "not_order_book_imbalance", "not_queue_imbalance",
        "not_complete_order_flow", "not_maker_fill_evidence",
    ):
        assert data[field] is True


def test_nearest_rank_strict_ties_and_trailing_coverage() -> None:
    stats = load()["causal_statistics"]
    assert stats["window_expected_minutes"] == 43_200
    assert stats["minimum_complete_observations"] == 38_880
    assert stats["minimum_coverage_fraction"] == 0.9
    assert stats["window_excludes_current_minute"] is True
    assert stats["signal_candle"] == "FULLY_CLOSED_MINUTE_T"
    assert stats["quantile_method"] == "NEAREST_RANK_EMPIRICAL"
    assert nearest_rank(
        [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")],
        Decimal("0.5"),
    ) == Decimal("2")
    threshold = Decimal("2")
    assert not (Decimal("2") > threshold)
    assert stats["strict_threshold_comparisons"] is True
    assert stats["backfill_allowed"] is False
    assert stats["interpolation_allowed"] is False
    assert stats["minimum_positive_gap_observations"] == 1000


def test_revised_chronological_splits_and_single_holdout() -> None:
    contract = load()
    splits = contract["splits"]
    assert splits["warmup"]["start"] == "2022-06-01T00:00:00Z"
    assert splits["development"] == {
        "start": "2022-07-01T00:00:00Z",
        "end": "2024-06-30T23:59:59Z", "months": 24, "quarters": 8,
    }
    assert splits["validation"]["months"] == 12
    assert splits["validation"]["quarters"] == 4
    assert splits["sealed_holdout"]["start"] == "2025-07-01T00:00:00Z"
    assert splits["sealed_holdout"]["end"] == "2026-06-30T23:59:59Z"
    assert splits["sealed_holdout"]["quarters"] == 4
    assert contract["change_control"]["holdout_access_limit"] == 1


def test_cooldown_collision_and_no_monthly_target() -> None:
    policy = load()["turnover_and_collisions"]
    assert policy["maximum_global_open_positions"] == 1
    assert policy["cooldown_after_exit_minutes"] == 1440
    assert policy["signals_during_position_or_cooldown"] == "REJECT_AND_COUNT"
    assert policy["eligible_signal_choice"] == "FIRST_CHRONOLOGICALLY_ELIGIBLE"
    assert policy["candidate_evaluations_independent"] is True
    assert policy["cross_candidate_signals_interact"] is False
    assert policy["monthly_trade_target"] is None
    assert policy["averaging_down"] is False
    assert policy["stacking"] is False


def test_stop_execution_timing_and_costs() -> None:
    contract = load()
    execution = contract["execution"]
    assert [execution[name]["entry_minute_offset"] for name in (
        "normal", "conservative", "severe"
    )] == [1, 2, 3]
    assert execution["protective_stop_rate"] == "0.015"
    assert execution["entry_convention"] == "ENTER_AT_OPEN_OF_MINUTE_E"
    assert execution["stop_monitoring_starts"] == "MINUTE_E_NO_STOP_FREE_ENTRY_MINUTE"
    assert 10 + 60 == 70 and 10 + 120 == 130
    barrier = Decimal("98.5")
    assert Decimal("98.5") <= barrier  # entry-minute breach triggers
    assert min(Decimal("97"), barrier) == Decimal("97")
    assert min(Decimal("99"), barrier) == barrier
    assert execution["stop_fill"] == "min(next_minute_open, stop_barrier)"
    assert execution["stop_precedes_scheduled_exit"] is True
    assert execution["stop_due_at_scheduled_exit_open_precedence"] == "STOP_EXIT"
    assert execution["holding_duration_starts_at_actual_entry"] is True
    assert execution["missing_next_minute_invalidates_trade_and_dataset_gate"] is True
    assert contract["costs"]["round_trip_bps"] == {
        "BTCUSDT": {"normal": 26, "conservative": 34, "severe": 62},
        "ETHUSDT": {"normal": 27, "conservative": 36, "severe": 67},
        "SOLUSDT": {"normal": 30, "conservative": 42, "severe": 82},
    }
    assert contract["costs"]["entry_allocation_fraction"] == 0.5
    assert contract["costs"]["exit_allocation_fraction"] == 0.5
    assert contract["costs"]["component_attribution_status"] == (
        "COMPONENT_LEVEL_COST_ATTRIBUTION_REQUIRES_SEPARATE_EXTRACTION"
    )


def test_decimal_severe_cost_risk_sizing_and_reserve() -> None:
    getcontext().prec = 40
    contract = load()
    capital = contract["capital"]
    costs = contract["costs"]["round_trip_bps"]
    expected = {
        "BTCUSDT": Decimal(5000) / Decimal(212),
        "ETHUSDT": Decimal(5000) / Decimal(217),
        "SOLUSDT": Decimal(625) / Decimal(29),
    }
    for pair, ceiling in expected.items():
        rate = Decimal("0.015") + Decimal(costs[pair]["severe"]) / Decimal(10_000)
        assert Decimal("0.50") / rate == ceiling
        assert ceiling < Decimal(capital["absolute_deployed_capital_ceiling_usd"])
        assert Decimal("100") - ceiling >= Decimal("20")
        assert capital["reference_stake_ceiling_usd"][pair]["exact"] in {
            "5000/212", "5000/217", "625/29"
        }
    assert capital["planned_risk_budget_usd"] == "0.50"
    assert capital["exchange_stake_and_quantity_rounding"] == "DOWN"
    diagnostic = capital["two_position_diagnostic"]
    assert diagnostic["combined_planned_risk_budget_usd"] == "0.50"
    assert diagnostic["candidate_selection_or_rescue_allowed"] is False


def test_replication_and_inherited_quarterly_gates() -> None:
    contract = load()
    replication = contract["replication"]
    assert replication["minimum_positive_replication_assets"] == 1
    assert replication["required_stages"] == ["DEVELOPMENT", "VALIDATION", "HOLDOUT"]
    assert replication["selects_candidate"] is False
    assert replication["rescues_candidate"] is False
    floors = replication["minimum_completed_trades"]
    assert floors == {"development": 120, "validation": 60, "holdout": 60}
    assert all(floors[stage] >= floor for stage, floor in floors.items())
    assert not all(floors[stage] - 1 >= floor for stage, floor in floors.items())
    assert replication["sample_floor_failure_rejects_replication_gate"] is True
    gates = contract["sample_and_calendar_gates"]
    assert gates["development"]["minimum_positive_quarters"] == 5
    assert gates["development"]["total_quarters"] == 8
    for stage in ("validation", "holdout"):
        assert gates[stage]["minimum_trades"] == 120
        assert gates[stage]["minimum_months_with_five_trades"] == 9
        assert gates[stage]["minimum_positive_quarters"] == 3
        assert gates[stage]["total_quarters"] == 4
        assert gates[stage]["maximum_drawdown_pct"] == 10
        assert gates[stage]["maximum_positive_quarter_concentration"] == 0.35


def test_exact_null_control_seed_strata_resampling_and_p_value() -> None:
    contract = load()
    null = contract["null_control"]
    assert null["mandatory"] is True and null["deployable"] is False
    assert null["repetitions"] == 5000
    assert null["strata"] == ["target_pair", "calendar_month", "utc_hour_of_day"]
    assert null["eligibility_universe"] == [
        "target_pair_data_completeness", "required_synchronized_source_pair_completeness",
        "warmup_completion", "causal_feature_availability",
        "nonzero_required_denominators", "relevant_trailing_history_minimums",
    ]
    assert null["observed_candidate_position_or_cooldown_path_affects_base_universe"] is False
    assert null["placebo_path_rules_applied_after_sampling"] is True
    assert null["maximum_resampling_attempts_per_repetition"] == 100
    assert null["collision_policy"] == "DISCARD_ENTIRE_REPETITION_AND_RESAMPLE"
    assert null["holm_family_size"] == 4
    assert (1 + 24) / (1 + null["repetitions"]) == 25 / 5001
    expected_seeds = {
        "BTC_SELF_FLOW_PERSISTENCE_60M": 15772981974708257581,
        "BTC_SELF_FLOW_PERSISTENCE_120M": 2309872680883579238,
        "BTC_FLOW_LEADS_ETH_60M": 9109486944927767718,
        "BTC_FLOW_LEADS_SOL_60M": 11328349288296130266,
    }
    for candidate_id, expected in expected_seeds.items():
        assert str(expected) not in json.dumps(contract)
        digest = hashlib.sha256(f"{EXPECTED_HASH}:{candidate_id}".encode()).hexdigest()
        assert int(digest[:16], 16) == expected


def test_accounting_edge_cases_and_marked_drawdown() -> None:
    accounting = load()["accounting"]
    assert accounting["promotion_metric_basis"] == (
        "SCENARIO_NET_TRADE_AND_ACCOUNT_PNL_AFTER_SCENARIO_COSTS"
    )
    assert set(accounting["net_based_metrics"]) == {
        "profit_factor", "expectancy", "winner_concentration", "quarter_concentration",
        "best_month_removal", "largest_winner_removal", "drawdown",
    }
    assert Decimal("4") / Decimal("5") == Decimal("0.8")
    assert accounting["gross_to_net_retention_nonpositive_gross_profit"] == "FAIL"
    assert accounting["positive_profit_zero_loss"] == "POSITIVE_INFINITY_UNBOUNDED"
    assert accounting["zero_profit_zero_loss"] == "ZERO_AND_FAIL"
    assert accounting["top_one_percent_winner_count"] == (
        "max(1, ceil(0.01 * winning_trade_count))"
    )
    assert max(1, math.ceil(0.01 * 1)) == 1
    assert max(1, math.ceil(0.01 * 101)) == 2
    assert accounting["no_positive_quarter"] == "FAIL"
    assert accounting["equity_frequency"] == "ONE_MINUTE"
    assert accounting["marked_to_market_equity"] == [
        "cash", "open_position_market_value", "entry_costs_paid", "exit_costs_when_paid"
    ]


def test_reset_and_research_safety_remain_authoritative() -> None:
    reset = load(RESET_PATH)
    program = reset["final_research_budget"]["programs"][1]
    assert program["status"] == "PROTOCOL_LOCKED_DATA_NOT_ACCESSED"
    assert program["protocol_hash_sha256"] == EXPECTED_HASH
    assert reset["final_research_budget"]["remaining_new_economic_families"] == 1
    assert reset["final_research_budget"]["programs"][0]["status"] == (
        "REJECTED_BEFORE_STRATEGY_BUILD"
    )
    assert reset["mission_numbering"] == "RETIRED"
    assert reset["capital_policy"]["leverage"] == 1
    assert reset["capital_policy"]["maximum_open_positions"] == 1
    assert reset["current_state"]["validated_profitable_strategy"] is False
    boundary = load()["research_boundary"]
    for field in (
        "freqtrade_implementation_authorized_now", "live_trading_authorized",
        "capital_deployment_authorized", "futures_authorized", "shorting_authorized",
    ):
        assert boundary[field] is False

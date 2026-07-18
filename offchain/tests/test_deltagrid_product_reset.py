from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

CONTRACT = (
    ROOT
    / "contracts"
    / "DELTAGRID_PRODUCT_RESET_V1.json"
)


def load_contract() -> dict:
    return json.loads(
        CONTRACT.read_text(encoding="utf-8")
    )


def test_product_reset_is_money_first_and_finite() -> None:
    contract = load_contract()

    assert contract["status"] == "ACTIVE"
    assert contract["mission_numbering"] == "RETIRED"

    budget = contract["final_research_budget"]

    assert budget["maximum_new_economic_families"] == 2
    assert budget["remaining_new_economic_families"] == 1
    assert budget["maximum_variants_per_family"] == 4
    assert budget["rescue_cycles_after_rejection"] == 0
    assert budget["parameter_changes_after_market_results"] is False
    assert budget["threshold_relaxation_after_failure"] is False
    assert budget["reopening_rejected_families"] is False


def test_infrastructure_is_frozen() -> None:
    freeze = load_contract()["infrastructure_freeze"]

    assert freeze["new_dashboards"] is False
    assert freeze["new_agent_frameworks"] is False
    assert freeze["new_execution_engines"] is False
    assert freeze["new_evidence_subsystems"] is False
    assert freeze["new_ui_work"] is False
    assert freeze["new_live_trading_features"] is False


def test_candidate_requires_real_validation() -> None:
    gates = load_contract()["candidate_promotion_gates"]

    assert gates[
        "positive_after_conservative_costs_on_development"
    ] is True

    assert gates[
        "positive_after_conservative_costs_on_validation"
    ] is True

    assert gates[
        "positive_after_conservative_costs_on_holdout"
    ] is True

    assert gates[
        "exact_freqtrade_ledger_parity_required"
    ] is True

    assert gates["lookahead_bias_allowed"] is False
    assert gates["recursive_instability_allowed"] is False


def test_forward_test_and_capital_limits_are_strict() -> None:
    contract = load_contract()

    forward = contract["forward_testing_gate"]

    assert forward["required"] is True
    assert forward["minimum_calendar_days"] == 90
    assert forward["minimum_closed_trades"] == 12
    assert forward[
        "both_calendar_and_trade_requirements_must_pass"
    ] is True

    capital = contract["capital_policy"]

    assert capital["live_pilot_capital_usd_maximum"] == 100
    assert capital["leverage"] == 1
    assert capital["trading_mode"] == "SPOT_ONLY"
    assert capital["maximum_open_positions"] == 1
    assert capital["averaging_down_allowed"] is False
    assert capital["martingale_allowed"] is False
    assert capital["capital_scaling_automatic"] is False


def test_next_action_is_alpha_search_b_preimplementation_review() -> None:
    contract = load_contract()

    assert contract["next_action"] == (
        "ALPHA_SEARCH_B_PREIMPLEMENTATION_RED_TEAM_AND_PROTOCOL_LOCK"
    )

    programs = contract[
        "final_research_budget"
    ]["programs"]

    assert programs[0]["program_id"] == (
        "ALPHA_SEARCH_A_MACRO_RISK_REGIME"
    )

    assert programs[0]["status"] == (
        "REJECTED_BEFORE_STRATEGY_BUILD"
    )
    assert programs[0]["rescue_cycles_used"] == 0
    assert programs[0]["further_rescue_authorized"] is False
    assert programs[0]["rejection_reason"] == (
        "required causal first-availability evidence unavailable "
        "under the frozen protocol"
    )

    assert programs[1]["status"] == "AUTHORIZED_NEXT"

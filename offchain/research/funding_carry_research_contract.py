"""Mission 85: Crypto Funding-Carry Research Charter.

Mission 85 preregisters a falsifiable delta-neutral funding/basis carry
hypothesis before Mission 86 collects additional real-market data.

This module locks:

- the economic hypothesis;
- the exact asset and venue universe;
- observable entry and exit rules;
- the parameter budget;
- development, validation, and untouched holdout periods;
- conservative initial cost assumptions;
- rejection criteria;
- change-control rules;
- fail-closed safety restrictions.

It performs no data ingestion, backtesting, model training, model promotion,
live signal generation, exchange execution, signing, leverage deployment,
private-key use, paid API use, or capital deployment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from copy import deepcopy
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


CONTRACT_ID = "mission85-crypto-funding-carry-charter-v1"
CONTRACT_VERSION = 1
MISSION_NAME = "Mission 85 Crypto Funding-Carry Research Charter"
CONTRACT_STATUS = "LOCKED_BEFORE_REAL_MARKET_DATA_COLLECTION"

LEGACY_MODEL_PROMOTION_STATUS = (
    "RETIRED_UNBUILT_AFTER_MISSION84_CLOSURE"
)

MISSION85_STATUS = "COMPLETE_RESEARCH_CHARTER_LOCKED"
MISSION86_STATUS = "READY_FOR_REAL_MARKET_DATA_FOUNDATION_ONLY"

GLOBAL_VERDICT = "MISSION85_CHARTER_LOCKED_NO_ALPHA_CLAIM"
NEXT_MISSION = "Mission 86 Real-Market Data Foundation"

LIVE_TRADING = "DISABLED"
LIVE_ORDER_SENT = 0
CAPITAL_DEPLOYMENT = "BLOCKED"

DEFAULT_DB_PATH = Path("offchain/deltagrid.db")
DEFAULT_CONTRACT_PATH = Path(
    "offchain/research/contracts/"
    "mission85_funding_carry_charter_v1.json"
)

CHECK_PASS = "PASS"
CHECK_FAIL = "FAIL"


MISSION85_CONTRACT: dict[str, Any] = {
    "contract_id": CONTRACT_ID,
    "contract_version": CONTRACT_VERSION,
    "mission_name": MISSION_NAME,
    "contract_status": CONTRACT_STATUS,
    "legacy_plan_resolution": {
        "legacy_plan_name": "Mission 85 Model Promotion Engine",
        "legacy_plan_status": LEGACY_MODEL_PROMOTION_STATUS,
        "reason": (
            "Mission 84 closed with zero real-data validated alpha "
            "candidates and zero training-eligible candidates."
        ),
    },
    "research_objective": {
        "priority": "FALSIFICATION_BEFORE_PROMOTION",
        "null_hypothesis": (
            "A fully collateralized long-spot short-perpetual strategy "
            "does not produce positive net risk-adjusted carry after "
            "conservative execution costs and basis risk."
        ),
        "alternative_hypothesis": (
            "Persistent positive funding may produce positive net carry "
            "after conservative costs for at least two of BTC, ETH, and "
            "SOL without excessive concentration or drawdown."
        ),
        "profitability_assumed": False,
        "profitability_claim_allowed": False,
    },
    "economic_mechanism": {
        "payer": (
            "Directional perpetual-market participants paying positive "
            "funding to maintain leveraged long exposure."
        ),
        "position": "LONG_SPOT_SHORT_USDT_PERPETUAL",
        "potential_return_sources": [
            "positive_perpetual_funding_received",
            "controlled_basis_convergence",
        ],
        "principal_risks": [
            "funding_rate_reversal",
            "basis_expansion",
            "temporary_unhedged_exposure",
            "fees_and_slippage",
            "liquidity_deterioration",
            "venue_outage",
            "collateral_mismatch",
            "liquidation_risk",
        ],
    },
    "venue": {
        "venue_name": "BINANCE",
        "spot_market": "BINANCE_SPOT_PUBLIC_REST",
        "perpetual_market": "BINANCE_USDS_M_PUBLIC_REST",
        "single_venue_research": True,
        "public_market_data_only": True,
        "private_api_required": False,
    },
    "universe": {
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "spot_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "perpetual_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "quote_asset": "USDT",
        "asset_count": 3,
    },
    "data_contract": {
        "canonical_interval": "1h",
        "derived_intervals": ["4h", "1d"],
        "start_time": "2024-01-01T00:00:00+00:00",
        "end_time_exclusive": "2026-07-01T00:00:00+00:00",
        "timezone": "UTC",
        "required_streams": [
            "spot_ohlcv",
            "perpetual_ohlcv",
            "mark_price_ohlcv",
            "index_price_ohlcv",
            "funding_rates",
        ],
        "allow_synthetic_data": False,
        "allow_offline_sample": False,
        "allow_sample_fallback": False,
        "allow_silent_substitution": False,
        "preserve_raw_responses": True,
        "require_response_hashes": True,
        "require_source_provenance": True,
    },
    "research_splits": [
        {
            "name": "development",
            "start": "2024-01-01T00:00:00+00:00",
            "end_exclusive": "2025-07-01T00:00:00+00:00",
            "parameter_tuning_allowed": True,
            "maximum_holdout_reads": None,
        },
        {
            "name": "validation",
            "start": "2025-07-01T00:00:00+00:00",
            "end_exclusive": "2026-01-01T00:00:00+00:00",
            "parameter_tuning_allowed": False,
            "maximum_holdout_reads": None,
        },
        {
            "name": "untouched_holdout",
            "start": "2026-01-01T00:00:00+00:00",
            "end_exclusive": "2026-07-01T00:00:00+00:00",
            "parameter_tuning_allowed": False,
            "maximum_holdout_reads": 1,
        },
    ],
    "observable_signal_contract": {
        "basis_definition": (
            "10000 * (perpetual_mark_price / spot_price - 1)"
        ),
        "funding_signal_source": (
            "TRAILING_SETTLED_FUNDING_RATES_ONLY"
        ),
        "funding_lookback_settlements": 3,
        "entry_decision_timing": (
            "AFTER_A_FUNDING_SETTLEMENT_USING_ONLY_INFORMATION "
            "AVAILABLE_AT_OR_BEFORE_THE_DECISION_TIMESTAMP"
        ),
        "future_funding_rate_use_allowed": False,
        "lookahead_allowed": False,
    },
    "strategy_rules": {
        "position_direction": "LONG_SPOT_SHORT_PERPETUAL",
        "spot_borrowing_allowed": False,
        "fully_collateralized_research": True,
        "perpetual_leverage_cap": 1.0,
        "target_delta": 0.0,
        "target_notional_ratio": 1.0,
        "rebalance_delta_drift_pct": 1.0,
        "entry_requires_positive_trailing_funding": True,
        "exit_after_nonpositive_funding_settlements": 2,
        "emergency_exit_absolute_basis_bps": 150.0,
        "machine_learning_allowed": False,
        "automatic_strategy_reweighting_allowed": False,
    },
    "parameter_budget": {
        "minimum_trailing_funding_rate_bps": [0.5, 1.0, 2.0],
        "maximum_absolute_entry_basis_bps": [25.0, 50.0],
        "maximum_holding_days": [7, 14],
        "maximum_total_variants": 12,
        "evaluate_all_predeclared_variants": True,
        "post_holdout_tuning_allowed": False,
    },
    "initial_cost_assumptions": {
        "status": (
            "CONSERVATIVE_INITIAL_LOCK_PENDING_MISSION88_CALIBRATION"
        ),
        "spot_entry_fee_bps": 10.0,
        "spot_exit_fee_bps": 10.0,
        "perpetual_entry_fee_bps": 5.0,
        "perpetual_exit_fee_bps": 5.0,
        "spot_slippage_per_side_bps": 2.0,
        "perpetual_slippage_per_side_bps": 2.0,
        "rebalance_cost_bps": 2.0,
        "stress_cost_multiplier": 2.0,
        "cost_reduction_after_results_allowed": False,
    },
    "predeclared_rejection_criteria": {
        "reject_if_aggregate_net_return_after_base_costs_nonpositive": True,
        "reject_if_aggregate_net_return_after_stress_costs_nonpositive": True,
        "require_positive_untouched_holdout_after_stress_costs": True,
        "minimum_positive_asset_count": 2,
        "maximum_single_asset_pnl_contribution_pct": 60.0,
        "maximum_strategy_drawdown_pct": 10.0,
        "minimum_untouched_holdout_closed_positions": 12,
        "maximum_probability_of_backtest_overfitting": 0.20,
        "minimum_deflated_sharpe_probability": 0.95,
        "require_parameter_neighbourhood_stability": True,
        "require_no_single_period_dependency": True,
        "maximum_single_quarter_pnl_contribution_pct": 50.0,
    },
    "change_control": {
        "semantic_change_requires_new_contract_version": True,
        "parameter_change_after_holdout_invalidates_holdout": True,
        "cost_reduction_after_holdout_invalidates_holdout": True,
        "asset_addition_after_holdout_invalidates_holdout": True,
        "holdout_reuse_allowed": False,
        "failed_strategy_may_not_be_rescued_with_machine_learning": True,
    },
    "allowed_decisions": [
        "ACCEPT_FOR_LIVE_SHADOW_PAPER_EXECUTION",
        "CONTINUE_COLLECTING_EVIDENCE",
        "REVISE_CONTRACT_AND_INVALIDATE_EXISTING_HOLDOUT",
        "REJECT_STRATEGY",
    ],
    "mission86_authorization": {
        "authorized_scope": (
            "PUBLIC_REAL_MARKET_DATA_COLLECTION_AND_CERTIFICATION_ONLY"
        ),
        "backtesting_authorized": False,
        "model_training_authorized": False,
        "model_promotion_authorized": False,
        "live_trading_authorized": False,
        "capital_deployment_authorized": False,
    },
    "safety": {
        "live_trading": LIVE_TRADING,
        "live_order_sent": LIVE_ORDER_SENT,
        "capital_deployment": CAPITAL_DEPLOYMENT,
        "private_keys_allowed": False,
        "signing_allowed": False,
        "paid_api_allowed": False,
        "real_orders_allowed": False,
        "leverage_above_one_allowed": False,
        "model_training_allowed": False,
        "model_promotion_allowed": False,
        "profitability_claim_allowed": False,
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def contract_hash(contract: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        canonical_json(contract).encode("utf-8")
    ).hexdigest()


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        raise ValueError(
            f"timestamp must include a timezone: {value}"
        )

    return parsed.astimezone(timezone.utc)


def parameter_variants(
    contract: Mapping[str, Any],
) -> list[dict[str, float | int]]:
    budget = contract.get("parameter_budget", {})

    funding_values = budget.get(
        "minimum_trailing_funding_rate_bps",
        [],
    )
    basis_values = budget.get(
        "maximum_absolute_entry_basis_bps",
        [],
    )
    holding_values = budget.get(
        "maximum_holding_days",
        [],
    )

    return [
        {
            "minimum_trailing_funding_rate_bps": funding,
            "maximum_absolute_entry_basis_bps": basis,
            "maximum_holding_days": holding,
        }
        for funding, basis, holding in product(
            funding_values,
            basis_values,
            holding_values,
        )
    ]


def make_check(
    category: str,
    name: str,
    passed: bool,
    observed: Any,
    expected: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_category": category,
        "check_name": name,
        "check_status": CHECK_PASS if passed else CHECK_FAIL,
        "observed_value": str(observed),
        "expected_value": str(expected),
        "check_reason": reason,
    }


def validate_contract(
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(
        category: str,
        name: str,
        passed: bool,
        observed: Any,
        expected: Any,
        reason: str,
    ) -> None:
        checks.append(
            make_check(
                category,
                name,
                passed,
                observed,
                expected,
                reason,
            )
        )

    check(
        "IDENTITY",
        "CONTRACT_ID",
        contract.get("contract_id") == CONTRACT_ID,
        contract.get("contract_id"),
        CONTRACT_ID,
        "The contract must use the authoritative Mission 85 identifier.",
    )

    check(
        "IDENTITY",
        "CONTRACT_VERSION",
        contract.get("contract_version") == CONTRACT_VERSION,
        contract.get("contract_version"),
        CONTRACT_VERSION,
        "The first locked charter must use version 1.",
    )

    legacy = contract.get("legacy_plan_resolution", {})

    check(
        "GOVERNANCE",
        "LEGACY_MODEL_PROMOTION_RETIRED",
        legacy.get("legacy_plan_status")
        == LEGACY_MODEL_PROMOTION_STATUS,
        legacy.get("legacy_plan_status"),
        LEGACY_MODEL_PROMOTION_STATUS,
        "The unbuilt model-promotion plan must not remain active.",
    )

    objective = contract.get("research_objective", {})

    check(
        "HYPOTHESIS",
        "FALSIFICATION_PRIORITY",
        objective.get("priority")
        == "FALSIFICATION_BEFORE_PROMOTION",
        objective.get("priority"),
        "FALSIFICATION_BEFORE_PROMOTION",
        "Mission 85 must attempt to disprove rather than assume alpha.",
    )

    check(
        "HYPOTHESIS",
        "PROFITABILITY_NOT_ASSUMED",
        objective.get("profitability_assumed") is False
        and objective.get("profitability_claim_allowed") is False,
        (
            objective.get("profitability_assumed"),
            objective.get("profitability_claim_allowed"),
        ),
        (False, False),
        "The charter must not assume or claim profitability.",
    )

    venue = contract.get("venue", {})

    check(
        "SCOPE",
        "SINGLE_PUBLIC_VENUE",
        venue.get("venue_name") == "BINANCE"
        and venue.get("single_venue_research") is True
        and venue.get("public_market_data_only") is True
        and venue.get("private_api_required") is False,
        venue,
        "Binance public market data only",
        "Mission 85 must keep the initial research venue narrow.",
    )

    universe = contract.get("universe", {})
    symbols = universe.get("symbols", [])

    expected_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    check(
        "SCOPE",
        "EXACT_THREE_ASSET_UNIVERSE",
        symbols == expected_symbols
        and universe.get("spot_symbols") == expected_symbols
        and universe.get("perpetual_symbols") == expected_symbols
        and universe.get("asset_count") == 3,
        symbols,
        expected_symbols,
        "The initial universe must be exactly BTC, ETH, and SOL.",
    )

    data_contract = contract.get("data_contract", {})

    required_streams = {
        "spot_ohlcv",
        "perpetual_ohlcv",
        "mark_price_ohlcv",
        "index_price_ohlcv",
        "funding_rates",
    }

    check(
        "DATA",
        "REQUIRED_STREAMS_COMPLETE",
        set(data_contract.get("required_streams", []))
        == required_streams,
        sorted(data_contract.get("required_streams", [])),
        sorted(required_streams),
        "Mission 86 must collect every stream needed for carry research.",
    )

    check(
        "DATA",
        "CANONICAL_INTERVAL_LOCKED",
        data_contract.get("canonical_interval") == "1h"
        and data_contract.get("derived_intervals")
        == ["4h", "1d"],
        (
            data_contract.get("canonical_interval"),
            data_contract.get("derived_intervals"),
        ),
        ("1h", ["4h", "1d"]),
        "One-hour bars are canonical; higher intervals are derived.",
    )

    prohibited_data_flags = (
        "allow_synthetic_data",
        "allow_offline_sample",
        "allow_sample_fallback",
        "allow_silent_substitution",
    )

    prohibited_data_safe = all(
        data_contract.get(field) is False
        for field in prohibited_data_flags
    )

    check(
        "DATA",
        "NO_SYNTHETIC_OR_FALLBACK_DATA",
        prohibited_data_safe,
        {
            field: data_contract.get(field)
            for field in prohibited_data_flags
        },
        {field: False for field in prohibited_data_flags},
        "Real-market validation cannot consume fixtures or sample fallback.",
    )

    check(
        "DATA",
        "PROVENANCE_AND_HASHES_REQUIRED",
        data_contract.get("preserve_raw_responses") is True
        and data_contract.get("require_response_hashes") is True
        and data_contract.get("require_source_provenance") is True,
        {
            "preserve_raw_responses": data_contract.get(
                "preserve_raw_responses"
            ),
            "require_response_hashes": data_contract.get(
                "require_response_hashes"
            ),
            "require_source_provenance": data_contract.get(
                "require_source_provenance"
            ),
        },
        True,
        "Every future dataset must be reproducible and attributable.",
    )

    split_error = ""
    split_valid = True

    try:
        data_start = parse_utc(data_contract["start_time"])
        data_end = parse_utc(
            data_contract["end_time_exclusive"]
        )

        splits = contract.get("research_splits", [])

        expected_names = [
            "development",
            "validation",
            "untouched_holdout",
        ]

        if [row.get("name") for row in splits] != expected_names:
            split_valid = False
            split_error = "unexpected split names or ordering"
        else:
            previous_end = data_start

            for row in splits:
                start = parse_utc(row["start"])
                end = parse_utc(row["end_exclusive"])

                if start != previous_end:
                    split_valid = False
                    split_error = (
                        f"gap or overlap before {row['name']}"
                    )
                    break

                if end <= start:
                    split_valid = False
                    split_error = (
                        f"non-positive duration for {row['name']}"
                    )
                    break

                previous_end = end

            if previous_end != data_end:
                split_valid = False
                split_error = "splits do not cover the full data window"

    except (KeyError, TypeError, ValueError) as exc:
        split_valid = False
        split_error = str(exc)

    check(
        "RESEARCH_DESIGN",
        "CHRONOLOGICAL_SPLITS_CONTIGUOUS",
        split_valid,
        split_error or "contiguous",
        "contiguous development, validation, holdout",
        "The research splits must be chronological and non-overlapping.",
    )

    splits = contract.get("research_splits", [])
    holdout = splits[-1] if len(splits) == 3 else {}

    check(
        "RESEARCH_DESIGN",
        "UNTOUCHED_HOLDOUT_SINGLE_USE",
        holdout.get("name") == "untouched_holdout"
        and holdout.get("parameter_tuning_allowed") is False
        and holdout.get("maximum_holdout_reads") == 1,
        holdout,
        {
            "parameter_tuning_allowed": False,
            "maximum_holdout_reads": 1,
        },
        "The final holdout must remain untouched until final evaluation.",
    )

    signal = contract.get("observable_signal_contract", {})

    check(
        "RESEARCH_DESIGN",
        "NO_LOOKAHEAD_SIGNAL",
        signal.get("funding_signal_source")
        == "TRAILING_SETTLED_FUNDING_RATES_ONLY"
        and signal.get("future_funding_rate_use_allowed") is False
        and signal.get("lookahead_allowed") is False,
        signal,
        "trailing settled funding only",
        "Future funding information must never enter an entry decision.",
    )

    rules = contract.get("strategy_rules", {})

    check(
        "STRATEGY",
        "DELTA_NEUTRAL_DIRECTION",
        rules.get("position_direction")
        == "LONG_SPOT_SHORT_PERPETUAL"
        and rules.get("target_delta") == 0.0
        and rules.get("target_notional_ratio") == 1.0,
        {
            "position_direction": rules.get("position_direction"),
            "target_delta": rules.get("target_delta"),
            "target_notional_ratio": rules.get(
                "target_notional_ratio"
            ),
        },
        {
            "position_direction": "LONG_SPOT_SHORT_PERPETUAL",
            "target_delta": 0.0,
            "target_notional_ratio": 1.0,
        },
        "The initial hypothesis is fully hedged funding carry.",
    )

    check(
        "STRATEGY",
        "NO_LEVERAGE_OR_BORROWING",
        rules.get("spot_borrowing_allowed") is False
        and rules.get("fully_collateralized_research") is True
        and rules.get("perpetual_leverage_cap") == 1.0,
        {
            "spot_borrowing_allowed": rules.get(
                "spot_borrowing_allowed"
            ),
            "fully_collateralized_research": rules.get(
                "fully_collateralized_research"
            ),
            "perpetual_leverage_cap": rules.get(
                "perpetual_leverage_cap"
            ),
        },
        "fully collateralized and leverage <= 1",
        "Research must not depend on leverage.",
    )

    check(
        "STRATEGY",
        "NO_MACHINE_LEARNING_OR_REWEIGHTING",
        rules.get("machine_learning_allowed") is False
        and rules.get(
            "automatic_strategy_reweighting_allowed"
        )
        is False,
        {
            "machine_learning_allowed": rules.get(
                "machine_learning_allowed"
            ),
            "automatic_strategy_reweighting_allowed": rules.get(
                "automatic_strategy_reweighting_allowed"
            ),
        },
        False,
        "The baseline must remain deterministic.",
    )

    variants = parameter_variants(contract)
    budget = contract.get("parameter_budget", {})

    check(
        "OVERFITTING",
        "PARAMETER_BUDGET_EXACTLY_TWELVE",
        len(variants) == 12
        and budget.get("maximum_total_variants") == 12
        and budget.get("evaluate_all_predeclared_variants") is True
        and budget.get("post_holdout_tuning_allowed") is False,
        len(variants),
        12,
        "The search budget must remain small and preregistered.",
    )

    costs = contract.get("initial_cost_assumptions", {})

    cost_fields = (
        "spot_entry_fee_bps",
        "spot_exit_fee_bps",
        "perpetual_entry_fee_bps",
        "perpetual_exit_fee_bps",
        "spot_slippage_per_side_bps",
        "perpetual_slippage_per_side_bps",
        "rebalance_cost_bps",
    )

    check(
        "COSTS",
        "CONSERVATIVE_COSTS_POSITIVE",
        all(
            float(costs.get(field, 0.0)) > 0.0
            for field in cost_fields
        )
        and float(costs.get("stress_cost_multiplier", 0.0))
        >= 2.0
        and costs.get(
            "cost_reduction_after_results_allowed"
        )
        is False,
        {
            field: costs.get(field)
            for field in (
                *cost_fields,
                "stress_cost_multiplier",
            )
        },
        "positive costs and stress multiplier >= 2",
        "Zero-cost or result-driven cost assumptions are prohibited.",
    )

    rejection = contract.get(
        "predeclared_rejection_criteria",
        {},
    )

    required_rejection_fields = (
        "reject_if_aggregate_net_return_after_base_costs_nonpositive",
        "reject_if_aggregate_net_return_after_stress_costs_nonpositive",
        "require_positive_untouched_holdout_after_stress_costs",
        "require_parameter_neighbourhood_stability",
        "require_no_single_period_dependency",
    )

    check(
        "GOVERNANCE",
        "REJECTION_CRITERIA_LOCKED",
        all(
            rejection.get(field) is True
            for field in required_rejection_fields
        )
        and rejection.get("minimum_positive_asset_count") == 2
        and rejection.get(
            "maximum_probability_of_backtest_overfitting"
        )
        <= 0.20
        and rejection.get(
            "minimum_deflated_sharpe_probability"
        )
        >= 0.95,
        rejection,
        "strict preregistered rejection criteria",
        "The strategy must be rejected when evidence is inadequate.",
    )

    change_control = contract.get("change_control", {})

    check(
        "GOVERNANCE",
        "HOLDOUT_CHANGE_CONTROL",
        change_control.get(
            "semantic_change_requires_new_contract_version"
        )
        is True
        and change_control.get(
            "parameter_change_after_holdout_invalidates_holdout"
        )
        is True
        and change_control.get("holdout_reuse_allowed") is False
        and change_control.get(
            "failed_strategy_may_not_be_rescued_with_machine_learning"
        )
        is True,
        change_control,
        "new version and invalidated holdout after semantic change",
        "Mission results may not be rescued by moving the goalposts.",
    )

    authorization = contract.get(
        "mission86_authorization",
        {},
    )

    check(
        "MISSION_GATE",
        "MISSION86_DATA_ONLY_AUTHORIZATION",
        authorization.get("authorized_scope")
        == (
            "PUBLIC_REAL_MARKET_DATA_COLLECTION_AND_"
            "CERTIFICATION_ONLY"
        )
        and authorization.get("backtesting_authorized") is False
        and authorization.get("model_training_authorized") is False
        and authorization.get("model_promotion_authorized") is False
        and authorization.get("live_trading_authorized") is False
        and authorization.get(
            "capital_deployment_authorized"
        )
        is False,
        authorization,
        "data collection and certification only",
        "Mission 85 must not authorize backtesting or trading.",
    )

    safety = contract.get("safety", {})

    expected_safety = {
        "live_trading": LIVE_TRADING,
        "live_order_sent": LIVE_ORDER_SENT,
        "capital_deployment": CAPITAL_DEPLOYMENT,
        "private_keys_allowed": False,
        "signing_allowed": False,
        "paid_api_allowed": False,
        "real_orders_allowed": False,
        "leverage_above_one_allowed": False,
        "model_training_allowed": False,
        "model_promotion_allowed": False,
        "profitability_claim_allowed": False,
    }

    safety_valid = all(
        safety.get(field) == expected
        for field, expected in expected_safety.items()
    )

    check(
        "SAFETY",
        "ALL_SAFETY_LOCKS_ACTIVE",
        safety_valid,
        safety,
        expected_safety,
        "Mission 85 must remain research-only and fail closed.",
    )

    fail_count = sum(
        row["check_status"] == CHECK_FAIL
        for row in checks
    )
    pass_count = sum(
        row["check_status"] == CHECK_PASS
        for row in checks
    )

    return {
        "valid": fail_count == 0,
        "contract_hash": contract_hash(contract),
        "parameter_variant_count": len(variants),
        "check_count": len(checks),
        "pass_check_count": pass_count,
        "fail_check_count": fail_count,
        "safety_breach_count": 0 if safety_valid else 1,
        "checks": checks,
    }


def ensure_schema(db_path: str | Path) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS mission85_research_contracts (
                contract_id TEXT PRIMARY KEY,
                contract_version INTEGER NOT NULL,
                first_locked_at TEXT NOT NULL,
                last_verified_at TEXT NOT NULL,
                mission_name TEXT NOT NULL,
                contract_status TEXT NOT NULL,
                contract_hash TEXT NOT NULL,
                universe_count INTEGER NOT NULL,
                parameter_variant_count INTEGER NOT NULL,
                legacy_model_promotion_status TEXT NOT NULL,
                mission86_status TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                contract_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS
                mission85_research_contract_runs (
                lock_run_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                contract_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                contract_hash TEXT NOT NULL,
                mission85_status TEXT NOT NULL,
                legacy_model_promotion_status TEXT NOT NULL,
                universe_count INTEGER NOT NULL,
                parameter_variant_count INTEGER NOT NULL,
                check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                mission86_status TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                next_mission TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                summary_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS
                mission85_research_contract_checks (
                check_id TEXT PRIMARY KEY,
                lock_run_label TEXT NOT NULL,
                contract_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                check_category TEXT NOT NULL,
                check_name TEXT NOT NULL,
                check_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                expected_value TEXT NOT NULL,
                check_reason TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS
                mission85_research_contract_reports (
                report_label TEXT PRIMARY KEY,
                lock_run_label TEXT NOT NULL,
                contract_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                contract_hash TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                next_mission TEXT NOT NULL,
                report_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            );
            """
        )
        conn.commit()


def _write_locked_contract(
    output_path: str | Path,
    contract: Mapping[str, Any],
    contract_hash_value: str,
    locked_at: str,
) -> dict[str, Any]:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    envelope = {
        "contract": contract,
        "contract_hash_sha256": contract_hash_value,
        "contract_status": CONTRACT_STATUS,
        "locked_at": locked_at,
    }

    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))

        if existing.get("contract_hash_sha256") != contract_hash_value:
            raise RuntimeError(
                "Mission 85 contract file already exists with a "
                "different hash. Create a new contract version instead."
            )

        if existing.get("contract") != contract:
            raise RuntimeError(
                "Mission 85 contract payload differs despite matching "
                "the expected output path."
            )

        return existing

    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(
            envelope,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)

    return envelope


def _insert_row(
    conn: sqlite3.Connection,
    table: str,
    row: Mapping[str, Any],
    columns: Sequence[str],
) -> None:
    placeholders = ",".join("?" for _ in columns)
    column_sql = ",".join(columns)

    conn.execute(
        f"INSERT INTO {table} ({column_sql}) "
        f"VALUES ({placeholders})",
        tuple(row[column] for column in columns),
    )


def _markdown_report(summary: Mapping[str, Any]) -> str:
    return f"""# Mission 85 Crypto Funding-Carry Research Charter

- Lock run: {summary['lock_run_label']}
- Contract ID: {summary['contract_id']}
- Contract hash: {summary['contract_hash']}
- Mission 85 status: {summary['mission85_status']}
- Legacy model-promotion plan: {summary['legacy_model_promotion_status']}
- Universe count: {summary['universe_count']}
- Parameter variants: {summary['parameter_variant_count']}
- Checks: {summary['pass_check_count']} passed, {summary['fail_check_count']} failed
- Safety breaches: {summary['safety_breach_count']}
- Mission 86 status: {summary['mission86_status']}
- Global verdict: {summary['global_verdict']}
- Next mission: {summary['next_mission']}

Mission 85 locks a falsification-first research charter. It does not establish
alpha, authorize backtesting, authorize model training, authorize live
trading, or make a profitability claim.
"""


def lock_contract(
    db_path: str | Path,
    contract_path: str | Path = DEFAULT_CONTRACT_PATH,
    lock_run_label: str = "mission85-local-check",
    report_label: str = "mission85-local-check-report",
    contract: Mapping[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    locked_contract = deepcopy(
        MISSION85_CONTRACT
        if contract is None
        else dict(contract)
    )

    validation = validate_contract(locked_contract)

    if not validation["valid"]:
        failed = [
            row["check_name"]
            for row in validation["checks"]
            if row["check_status"] == CHECK_FAIL
        ]
        raise ValueError(
            "Mission 85 contract validation failed: "
            + ", ".join(failed)
        )

    created_at = created_at or utc_now()
    hash_value = validation["contract_hash"]

    envelope = _write_locked_contract(
        contract_path,
        locked_contract,
        hash_value,
        created_at,
    )

    first_locked_at = str(envelope["locked_at"])

    ensure_schema(db_path)

    summary: dict[str, Any] = {
        "lock_run_label": lock_run_label,
        "report_label": report_label,
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "contract_hash": hash_value,
        "created_at": created_at,
        "mission85_status": MISSION85_STATUS,
        "legacy_model_promotion_status": (
            LEGACY_MODEL_PROMOTION_STATUS
        ),
        "universe_count": 3,
        "parameter_variant_count": validation[
            "parameter_variant_count"
        ],
        "check_count": validation["check_count"],
        "pass_check_count": validation["pass_check_count"],
        "fail_check_count": validation["fail_check_count"],
        "safety_breach_count": validation[
            "safety_breach_count"
        ],
        "mission86_status": MISSION86_STATUS,
        "global_verdict": GLOBAL_VERDICT,
        "next_mission": NEXT_MISSION,
        "live_trading": LIVE_TRADING,
        "live_order_sent": LIVE_ORDER_SENT,
        "capital_deployment": CAPITAL_DEPLOYMENT,
    }

    markdown = _markdown_report(summary)

    with sqlite3.connect(Path(db_path)) as conn:
        conn.row_factory = sqlite3.Row

        existing = conn.execute(
            """
            SELECT contract_hash
            FROM mission85_research_contracts
            WHERE contract_id = ?
            """,
            (CONTRACT_ID,),
        ).fetchone()

        if existing is not None:
            existing_hash = str(existing["contract_hash"])

            if existing_hash != hash_value:
                raise RuntimeError(
                    "Mission 85 database already contains a different "
                    "contract hash. A new version is required."
                )

            conn.execute(
                """
                UPDATE mission85_research_contracts
                SET last_verified_at = ?
                WHERE contract_id = ?
                """,
                (created_at, CONTRACT_ID),
            )
        else:
            conn.execute(
                """
                INSERT INTO mission85_research_contracts (
                    contract_id,
                    contract_version,
                    first_locked_at,
                    last_verified_at,
                    mission_name,
                    contract_status,
                    contract_hash,
                    universe_count,
                    parameter_variant_count,
                    legacy_model_promotion_status,
                    mission86_status,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    contract_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    CONTRACT_ID,
                    CONTRACT_VERSION,
                    first_locked_at,
                    created_at,
                    MISSION_NAME,
                    CONTRACT_STATUS,
                    hash_value,
                    3,
                    validation["parameter_variant_count"],
                    LEGACY_MODEL_PROMOTION_STATUS,
                    MISSION86_STATUS,
                    LIVE_TRADING,
                    LIVE_ORDER_SENT,
                    CAPITAL_DEPLOYMENT,
                    canonical_json(locked_contract),
                ),
            )

        conn.execute(
            """
            DELETE FROM mission85_research_contract_checks
            WHERE lock_run_label = ?
            """,
            (lock_run_label,),
        )
        conn.execute(
            """
            DELETE FROM mission85_research_contract_runs
            WHERE lock_run_label = ?
            """,
            (lock_run_label,),
        )
        conn.execute(
            """
            DELETE FROM mission85_research_contract_reports
            WHERE report_label = ?
            """,
            (report_label,),
        )

        for check_row in validation["checks"]:
            row = {
                "check_id": (
                    f"{lock_run_label}-"
                    f"{check_row['check_name'].lower()}"
                ),
                "lock_run_label": lock_run_label,
                "contract_id": CONTRACT_ID,
                "created_at": created_at,
                **check_row,
            }

            _insert_row(
                conn,
                "mission85_research_contract_checks",
                row,
                (
                    "check_id",
                    "lock_run_label",
                    "contract_id",
                    "created_at",
                    "check_category",
                    "check_name",
                    "check_status",
                    "observed_value",
                    "expected_value",
                    "check_reason",
                ),
            )

        run_row = {
            **summary,
            "summary_json": canonical_json(summary),
        }

        _insert_row(
            conn,
            "mission85_research_contract_runs",
            run_row,
            (
                "lock_run_label",
                "report_label",
                "contract_id",
                "created_at",
                "contract_hash",
                "mission85_status",
                "legacy_model_promotion_status",
                "universe_count",
                "parameter_variant_count",
                "check_count",
                "pass_check_count",
                "fail_check_count",
                "safety_breach_count",
                "mission86_status",
                "global_verdict",
                "next_mission",
                "live_trading",
                "live_order_sent",
                "capital_deployment",
                "summary_json",
            ),
        )

        report = {
            "report_label": report_label,
            "lock_run_label": lock_run_label,
            "contract_id": CONTRACT_ID,
            "created_at": created_at,
            "contract_hash": hash_value,
            "global_verdict": GLOBAL_VERDICT,
            "next_mission": NEXT_MISSION,
            "report_json": canonical_json(
                {
                    **summary,
                    "checks": validation["checks"],
                }
            ),
            "markdown_report": markdown,
        }

        _insert_row(
            conn,
            "mission85_research_contract_reports",
            report,
            tuple(report.keys()),
        )

        conn.commit()

    return {
        **summary,
        "contract_path": str(contract_path),
        "markdown_report": markdown,
    }


def load_locked_contract(
    contract_path: str | Path = DEFAULT_CONTRACT_PATH,
) -> dict[str, Any]:
    path = Path(contract_path)

    if not path.is_file():
        raise FileNotFoundError(
            f"locked Mission 85 contract not found: {path}"
        )

    envelope = json.loads(path.read_text(encoding="utf-8"))
    contract = envelope.get("contract")

    if not isinstance(contract, dict):
        raise ValueError("Mission 85 contract payload is invalid")

    expected_hash = contract_hash(contract)
    stored_hash = envelope.get("contract_hash_sha256")

    if stored_hash != expected_hash:
        raise ValueError("Mission 85 contract hash verification failed")

    validation = validate_contract(contract)

    if not validation["valid"]:
        raise ValueError("Locked Mission 85 contract no longer validates")

    return envelope


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lock the Mission 85 funding-carry research charter."
    )
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
    )
    parser.add_argument(
        "--contract-path",
        default=str(DEFAULT_CONTRACT_PATH),
    )
    parser.add_argument(
        "--lock-run-label",
        default="mission85-local-check",
    )
    parser.add_argument(
        "--report-label",
        default="mission85-local-check-report",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(
        list(argv) if argv is not None else None
    )

    summary = lock_contract(
        db_path=args.db_path,
        contract_path=args.contract_path,
        lock_run_label=args.lock_run_label,
        report_label=args.report_label,
    )

    printable = {
        key: value
        for key, value in summary.items()
        if key != "markdown_report"
    }

    print(json.dumps(printable, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

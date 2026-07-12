"""Mission 88: Execution and Cost Reality Model.

Mission 88 creates a transparent assumption-bounded execution-cost model for
the Mission 85 delta-neutral long-spot short-perpetual research charter.

The model uses:

- the immutable Mission 85 fee and slippage floors;
- explicit symbol-level spread assumptions;
- normal, conservative, and severe stress envelopes;
- three hypothetical per-leg notional bands;
- hedge-delay penalties;
- partial-fill penalties;
- rebalance costs;
- funding-reconciliation uncertainty buffers;
- operational uncertainty buffers.

The dataset does not contain historical order-book depth, queue position, or
true fill latency. Therefore, Mission 88 does not claim measured or precise
historical execution costs. All non-fee microstructure values are explicit,
versioned assumptions.

Mission 88 reads no Mission 86 market bars or funding observations. It performs
no strategy backtest, holdout evaluation, return calculation, parameter
selection, model training, model promotion, signal generation, order
submission, signing, private-key use, paid API use, capital deployment, or
profitability analysis.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from offchain.backtest.mission86_real_market_data_foundation import (
    EXPECTED_CONTRACT_HASH,
    canonical_json,
    load_authoritative_contract,
    sha256_bytes,
)
from offchain.research.funding_carry_research_contract import (
    CAPITAL_DEPLOYMENT,
    CONTRACT_ID,
    LIVE_ORDER_SENT,
    LIVE_TRADING,
)


SOURCE_CERTIFICATION_RUN_LABEL = "mission87-final-check"

EXPECTED_SOURCE_CERTIFICATE_HASH = (
    "e4d78b99417c1acb9bd89e7a8ef175cbf0c0e1219c1f71777401be41b8978819"
)

MODEL_ID = "mission88-assumption-bounded-execution-cost-v1"

MODEL_STATUS = (
    "APPROVED_FOR_BASELINE_FALSIFICATION_WITH_UNCERTAINTY"
)
MISSION88_STATUS = (
    "COMPLETE_ASSUMPTION_BOUNDED_EXECUTION_COST_MODEL"
)
MISSION89_STATUS = (
    "READY_FOR_BASELINE_STRATEGY_FALSIFICATION"
)
MISSION89_AUTHORIZED_SCOPE = (
    "DEVELOPMENT_AND_VALIDATION_BASELINE_FALSIFICATION_ONLY"
)

GLOBAL_VERDICT = (
    "MISSION88_COST_ENVELOPES_LOCKED_NO_EXECUTION_PRECISION_CLAIM"
)
NEXT_MISSION = "Mission 89 Baseline Strategy Falsification"

DEFAULT_DB_PATH = Path("offchain/deltagrid.db")
DEFAULT_CONTRACT_PATH = Path(
    "offchain/research/contracts/"
    "mission85_funding_carry_charter_v1.json"
)
DEFAULT_ARTIFACT_PATH = Path(
    "offchain/data/mission88/cost_model.json"
)

CHECK_PASS = "PASS"
CHECK_FAIL = "FAIL"

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")

SYMBOL_ASSUMPTIONS: dict[str, dict[str, str]] = {
    "BTCUSDT": {
        "liquidity_tier": "TIER_1_ASSUMED",
        "spot_spread_cross_bps": "1.0",
        "perpetual_spread_cross_bps": "1.0",
        "normal_hedge_delay_penalty_bps": "2.0",
        "normal_partial_fill_penalty_bps": "2.0",
    },
    "ETHUSDT": {
        "liquidity_tier": "TIER_1_ASSUMED",
        "spot_spread_cross_bps": "1.5",
        "perpetual_spread_cross_bps": "1.5",
        "normal_hedge_delay_penalty_bps": "3.0",
        "normal_partial_fill_penalty_bps": "3.0",
    },
    "SOLUSDT": {
        "liquidity_tier": "TIER_2_ASSUMED",
        "spot_spread_cross_bps": "3.0",
        "perpetual_spread_cross_bps": "2.5",
        "normal_hedge_delay_penalty_bps": "5.0",
        "normal_partial_fill_penalty_bps": "6.0",
    },
}

NOTIONAL_BANDS: tuple[dict[str, Any], ...] = (
    {
        "notional_band": "MICRO_RESEARCH_1K",
        "rank": 1,
        "per_leg_notional_usd": "1000",
        "slippage_size_multiplier": "1.0",
    },
    {
        "notional_band": "SMALL_RESEARCH_10K",
        "rank": 2,
        "per_leg_notional_usd": "10000",
        "slippage_size_multiplier": "1.5",
    },
    {
        "notional_band": "UPPER_RESEARCH_50K",
        "rank": 3,
        "per_leg_notional_usd": "50000",
        "slippage_size_multiplier": "3.0",
    },
)

SCENARIOS: tuple[dict[str, Any], ...] = (
    {
        "scenario_code": "NORMAL_ASSUMPTION",
        "rank": 1,
        "uncertainty_label": (
            "ASSUMED_NOT_ORDERBOOK_CALIBRATED"
        ),
        "spread_multiplier": "1.0",
        "slippage_multiplier": "1.0",
        "rebalance_multiplier": "1.0",
        "rebalance_count": 1,
        "hedge_delay_multiplier": "1.0",
        "partial_fill_multiplier": "1.0",
        "funding_reconciliation_buffer_bps": "1.0",
        "operational_buffer_bps": "1.0",
        "order_book_calibrated": False,
        "precision_claim_allowed": False,
    },
    {
        "scenario_code": "CONSERVATIVE_ASSUMPTION",
        "rank": 2,
        "uncertainty_label": (
            "CONSERVATIVE_ASSUMPTION_NOT_ORDERBOOK_CALIBRATED"
        ),
        "spread_multiplier": "2.0",
        "slippage_multiplier": "2.5",
        "rebalance_multiplier": "2.5",
        "rebalance_count": 3,
        "hedge_delay_multiplier": "3.0",
        "partial_fill_multiplier": "3.0",
        "funding_reconciliation_buffer_bps": "2.0",
        "operational_buffer_bps": "3.0",
        "order_book_calibrated": False,
        "precision_claim_allowed": False,
    },
    {
        "scenario_code": "SEVERE_STRESS_ASSUMPTION",
        "rank": 3,
        "uncertainty_label": (
            "SEVERE_STRESS_ASSUMPTION_NOT_ORDERBOOK_CALIBRATED"
        ),
        "spread_multiplier": "5.0",
        "slippage_multiplier": "8.0",
        "rebalance_multiplier": "8.0",
        "rebalance_count": 7,
        "hedge_delay_multiplier": "15.0",
        "partial_fill_multiplier": "12.0",
        "funding_reconciliation_buffer_bps": "5.0",
        "operational_buffer_bps": "10.0",
        "order_book_calibrated": False,
        "precision_claim_allowed": False,
    },
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()


def decimal_value(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(
            f"invalid decimal value: {value}"
        ) from exc

    if not result.is_finite():
        raise ValueError(
            f"non-finite decimal value: {value}"
        )

    return result


def decimal_text(value: Decimal) -> str:
    return format(
        value.quantize(Decimal("0.000001")),
        "f",
    )


def ensure_schema(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS
                mission88_cost_model_runs (
                run_label TEXT PRIMARY KEY,
                source_certification_run_label TEXT NOT NULL,
                contract_id TEXT NOT NULL,
                contract_hash TEXT NOT NULL,
                source_certificate_hash TEXT NOT NULL,
                model_id TEXT NOT NULL,
                model_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                model_status TEXT NOT NULL,
                mission88_status TEXT NOT NULL,
                symbol_count INTEGER NOT NULL,
                scenario_count INTEGER NOT NULL,
                notional_band_count INTEGER NOT NULL,
                profile_count INTEGER NOT NULL,
                minimum_total_cost_bps TEXT NOT NULL,
                maximum_total_cost_bps TEXT NOT NULL,
                check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                market_data_rows_read INTEGER NOT NULL,
                holdout_performance_evaluated INTEGER NOT NULL,
                backtesting_performed INTEGER NOT NULL,
                profitability_analyzed INTEGER NOT NULL,
                mission89_status TEXT NOT NULL,
                mission89_authorized_scope TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                next_mission TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                summary_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS
                mission88_cost_scenarios (
                run_label TEXT NOT NULL,
                scenario_code TEXT NOT NULL,
                scenario_rank INTEGER NOT NULL,
                uncertainty_label TEXT NOT NULL,
                order_book_calibrated INTEGER NOT NULL,
                precision_claim_allowed INTEGER NOT NULL,
                scenario_json TEXT NOT NULL,
                PRIMARY KEY (
                    run_label,
                    scenario_code
                )
            );

            CREATE TABLE IF NOT EXISTS
                mission88_cost_profiles (
                run_label TEXT NOT NULL,
                model_hash TEXT NOT NULL,
                scenario_code TEXT NOT NULL,
                scenario_rank INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                notional_band TEXT NOT NULL,
                notional_rank INTEGER NOT NULL,
                per_leg_notional_usd TEXT NOT NULL,
                fully_collateralized_capital_usd TEXT NOT NULL,
                entry_cost_bps TEXT NOT NULL,
                exit_cost_bps TEXT NOT NULL,
                round_trip_execution_bps TEXT NOT NULL,
                rebalance_cost_bps TEXT NOT NULL,
                contingency_cost_bps TEXT NOT NULL,
                total_cost_bps_on_pair_notional TEXT NOT NULL,
                total_cost_bps_on_total_capital TEXT NOT NULL,
                estimated_cost_usd TEXT NOT NULL,
                break_even_gross_carry_bps TEXT NOT NULL,
                profile_hash TEXT NOT NULL,
                assumptions_json TEXT NOT NULL,
                PRIMARY KEY (
                    run_label,
                    scenario_code,
                    symbol,
                    notional_band
                )
            );

            CREATE TABLE IF NOT EXISTS
                mission88_model_checks (
                check_id TEXT PRIMARY KEY,
                run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                check_category TEXT NOT NULL,
                check_name TEXT NOT NULL,
                check_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                expected_value TEXT NOT NULL,
                check_reason TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS
                mission88_cost_model_artifacts (
                run_label TEXT PRIMARY KEY,
                model_id TEXT NOT NULL,
                model_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                artifact_path TEXT NOT NULL,
                artifact_json TEXT NOT NULL,
                model_status TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS
                idx_mission88_profile_lookup
            ON mission88_cost_profiles (
                scenario_code,
                symbol,
                notional_rank
            );
            """
        )
        conn.commit()


def load_source_certification(
    conn: sqlite3.Connection,
    run_label: str = SOURCE_CERTIFICATION_RUN_LABEL,
) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT *
        FROM mission87_certification_runs
        WHERE certification_run_label = ?
        """,
        (run_label,),
    ).fetchone()

    if row is None:
        raise RuntimeError(
            f"Mission 87 source run not found: {run_label}"
        )

    series_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM mission87_series_certifications
            WHERE certification_run_label = ?
            """,
            (run_label,),
        ).fetchone()[0]
    )

    rejected_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM mission87_series_certifications
            WHERE certification_run_label = ?
              AND certification_status != ?
            """,
            (
                run_label,
                (
                    "CERTIFIED_FOR_RESEARCH_"
                    "PENDING_EXECUTION_COST_MODEL"
                ),
            ),
        ).fetchone()[0]
    )

    return {
        **dict(row),
        "persisted_series_count": series_count,
        "persisted_rejected_count": rejected_count,
    }


def validate_source_certification(
    source: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []

    expected = {
        "contract_hash": EXPECTED_CONTRACT_HASH,
        "certificate_hash": (
            EXPECTED_SOURCE_CERTIFICATE_HASH
        ),
        "certification_status": (
            "CERTIFIED_FOR_RESEARCH_"
            "PENDING_EXECUTION_COST_MODEL"
        ),
        "mission87_status": (
            "COMPLETE_REAL_MARKET_DATASET_CERTIFICATION"
        ),
        "certified_series_count": 15,
        "rejected_series_count": 0,
        "quality_check_count": 23,
        "pass_check_count": 23,
        "fail_check_count": 0,
        "safety_breach_count": 0,
        "holdout_performance_evaluated": 0,
        "backtesting_performed": 0,
        "profitability_analyzed": 0,
        "live_trading": "DISABLED",
        "live_order_sent": 0,
        "capital_deployment": "BLOCKED",
    }

    for field, value in expected.items():
        if source.get(field) != value:
            errors.append(
                f"{field} expected {value!r}, "
                f"observed {source.get(field)!r}"
            )

    if source.get("persisted_series_count") != 15:
        errors.append(
            "persisted series count must equal 15"
        )

    if source.get("persisted_rejected_count") != 0:
        errors.append(
            "persisted rejected series count must equal zero"
        )

    return errors


def extract_charter_costs(
    contract: Mapping[str, Any],
) -> dict[str, Decimal]:
    raw = contract.get(
        "initial_cost_assumptions",
        {},
    )

    required = (
        "spot_entry_fee_bps",
        "spot_exit_fee_bps",
        "perpetual_entry_fee_bps",
        "perpetual_exit_fee_bps",
        "spot_slippage_per_side_bps",
        "perpetual_slippage_per_side_bps",
        "rebalance_cost_bps",
        "stress_cost_multiplier",
    )

    missing = [
        field
        for field in required
        if field not in raw
    ]

    if missing:
        raise RuntimeError(
            "Mission 85 cost fields missing: "
            + ", ".join(missing)
        )

    result = {
        field: decimal_value(raw[field])
        for field in required
    }

    if any(value <= 0 for value in result.values()):
        raise RuntimeError(
            "Mission 85 cost floors must be positive"
        )

    if (
        raw.get("cost_reduction_after_results_allowed")
        is not False
    ):
        raise RuntimeError(
            "Mission 85 cost reduction lock is not active"
        )

    return result


def build_cost_profiles(
    contract: Mapping[str, Any],
) -> list[dict[str, Any]]:
    costs = extract_charter_costs(contract)
    profiles: list[dict[str, Any]] = []

    for scenario in sorted(
        SCENARIOS,
        key=lambda item: int(item["rank"]),
    ):
        spread_multiplier = decimal_value(
            scenario["spread_multiplier"]
        )
        slippage_multiplier = decimal_value(
            scenario["slippage_multiplier"]
        )
        rebalance_multiplier = decimal_value(
            scenario["rebalance_multiplier"]
        )
        hedge_multiplier = decimal_value(
            scenario["hedge_delay_multiplier"]
        )
        partial_multiplier = decimal_value(
            scenario["partial_fill_multiplier"]
        )

        for symbol in SYMBOLS:
            symbol_assumptions = (
                SYMBOL_ASSUMPTIONS[symbol]
            )

            spot_spread = decimal_value(
                symbol_assumptions[
                    "spot_spread_cross_bps"
                ]
            )
            perpetual_spread = decimal_value(
                symbol_assumptions[
                    "perpetual_spread_cross_bps"
                ]
            )
            normal_hedge = decimal_value(
                symbol_assumptions[
                    "normal_hedge_delay_penalty_bps"
                ]
            )
            normal_partial = decimal_value(
                symbol_assumptions[
                    "normal_partial_fill_penalty_bps"
                ]
            )

            for band in sorted(
                NOTIONAL_BANDS,
                key=lambda item: int(item["rank"]),
            ):
                size_multiplier = decimal_value(
                    band["slippage_size_multiplier"]
                )
                notional = decimal_value(
                    band["per_leg_notional_usd"]
                )

                spot_entry_fee = costs[
                    "spot_entry_fee_bps"
                ]
                spot_exit_fee = costs[
                    "spot_exit_fee_bps"
                ]
                perpetual_entry_fee = costs[
                    "perpetual_entry_fee_bps"
                ]
                perpetual_exit_fee = costs[
                    "perpetual_exit_fee_bps"
                ]

                spot_slippage = (
                    costs[
                        "spot_slippage_per_side_bps"
                    ]
                    * slippage_multiplier
                    * size_multiplier
                )
                perpetual_slippage = (
                    costs[
                        "perpetual_slippage_per_side_bps"
                    ]
                    * slippage_multiplier
                    * size_multiplier
                )

                spot_spread_cost = (
                    spot_spread
                    * spread_multiplier
                )
                perpetual_spread_cost = (
                    perpetual_spread
                    * spread_multiplier
                )

                entry_cost = (
                    spot_entry_fee
                    + perpetual_entry_fee
                    + spot_spread_cost
                    + perpetual_spread_cost
                    + spot_slippage
                    + perpetual_slippage
                )

                exit_cost = (
                    spot_exit_fee
                    + perpetual_exit_fee
                    + spot_spread_cost
                    + perpetual_spread_cost
                    + spot_slippage
                    + perpetual_slippage
                )

                round_trip = entry_cost + exit_cost

                rebalance_cost = (
                    costs["rebalance_cost_bps"]
                    * rebalance_multiplier
                    * size_multiplier
                    * Decimal(
                        int(
                            scenario[
                                "rebalance_count"
                            ]
                        )
                    )
                )

                hedge_delay_cost = (
                    normal_hedge
                    * hedge_multiplier
                )
                partial_fill_cost = (
                    normal_partial
                    * partial_multiplier
                )
                reconciliation_buffer = decimal_value(
                    scenario[
                        "funding_reconciliation_buffer_bps"
                    ]
                )
                operational_buffer = decimal_value(
                    scenario[
                        "operational_buffer_bps"
                    ]
                )

                contingency = (
                    hedge_delay_cost
                    + partial_fill_cost
                    + reconciliation_buffer
                    + operational_buffer
                )

                total_cost = (
                    round_trip
                    + rebalance_cost
                    + contingency
                )

                fully_collateralized_capital = (
                    notional * Decimal("2")
                )
                estimated_cost_usd = (
                    notional
                    * total_cost
                    / Decimal("10000")
                )
                total_capital_bps = (
                    total_cost / Decimal("2")
                )

                assumptions = {
                    "fee_source": (
                        "MISSION85_LOCKED_CONSERVATIVE_FLOORS"
                    ),
                    "spread_source": (
                        "EXPLICIT_ASSUMPTION_NOT_ORDERBOOK_MEASUREMENT"
                    ),
                    "slippage_source": (
                        "MISSION85_FLOOR_SCALED_BY_ASSUMPTION_ENVELOPE"
                    ),
                    "hedge_delay_source": (
                        "EXPLICIT_ASSUMPTION_NOT_LATENCY_MEASUREMENT"
                    ),
                    "partial_fill_source": (
                        "EXPLICIT_ASSUMPTION_NOT_QUEUE_MEASUREMENT"
                    ),
                    "order_book_calibrated": False,
                    "historical_fill_calibrated": False,
                    "precision_claim_allowed": False,
                    "uncertainty_label": scenario[
                        "uncertainty_label"
                    ],
                    "liquidity_tier": (
                        symbol_assumptions[
                            "liquidity_tier"
                        ]
                    ),
                    "spot_entry_fee_bps": decimal_text(
                        spot_entry_fee
                    ),
                    "spot_exit_fee_bps": decimal_text(
                        spot_exit_fee
                    ),
                    "perpetual_entry_fee_bps": decimal_text(
                        perpetual_entry_fee
                    ),
                    "perpetual_exit_fee_bps": decimal_text(
                        perpetual_exit_fee
                    ),
                    "spot_spread_cost_bps": decimal_text(
                        spot_spread_cost
                    ),
                    "perpetual_spread_cost_bps": decimal_text(
                        perpetual_spread_cost
                    ),
                    "spot_slippage_bps": decimal_text(
                        spot_slippage
                    ),
                    "perpetual_slippage_bps": decimal_text(
                        perpetual_slippage
                    ),
                    "hedge_delay_cost_bps": decimal_text(
                        hedge_delay_cost
                    ),
                    "partial_fill_cost_bps": decimal_text(
                        partial_fill_cost
                    ),
                    "funding_reconciliation_buffer_bps": (
                        decimal_text(
                            reconciliation_buffer
                        )
                    ),
                    "operational_buffer_bps": decimal_text(
                        operational_buffer
                    ),
                    "rebalance_count": int(
                        scenario["rebalance_count"]
                    ),
                    "slippage_size_multiplier": (
                        decimal_text(
                            size_multiplier
                        )
                    ),
                }

                profile = {
                    "scenario_code": (
                        scenario["scenario_code"]
                    ),
                    "scenario_rank": int(
                        scenario["rank"]
                    ),
                    "symbol": symbol,
                    "notional_band": (
                        band["notional_band"]
                    ),
                    "notional_rank": int(
                        band["rank"]
                    ),
                    "per_leg_notional_usd": (
                        decimal_text(notional)
                    ),
                    "fully_collateralized_capital_usd": (
                        decimal_text(
                            fully_collateralized_capital
                        )
                    ),
                    "entry_cost_bps": decimal_text(
                        entry_cost
                    ),
                    "exit_cost_bps": decimal_text(
                        exit_cost
                    ),
                    "round_trip_execution_bps": (
                        decimal_text(round_trip)
                    ),
                    "rebalance_cost_bps": decimal_text(
                        rebalance_cost
                    ),
                    "contingency_cost_bps": decimal_text(
                        contingency
                    ),
                    "total_cost_bps_on_pair_notional": (
                        decimal_text(total_cost)
                    ),
                    "total_cost_bps_on_total_capital": (
                        decimal_text(
                            total_capital_bps
                        )
                    ),
                    "estimated_cost_usd": decimal_text(
                        estimated_cost_usd
                    ),
                    "break_even_gross_carry_bps": (
                        decimal_text(total_cost)
                    ),
                    "assumptions": assumptions,
                }

                profile["profile_hash"] = sha256_bytes(
                    canonical_json(profile).encode(
                        "utf-8"
                    )
                )

                profiles.append(profile)

    return profiles


def validate_profiles(
    profiles: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    charter_costs = extract_charter_costs(contract)

    profile_matrix_complete = (
        len(profiles)
        == len(SYMBOLS)
        * len(SCENARIOS)
        * len(NOTIONAL_BANDS)
    )

    nonnegative = True
    formula_consistent = True
    fees_not_below_charter = True
    uncertainty_explicit = True
    precision_claim_absent = True

    numeric_fields = (
        "entry_cost_bps",
        "exit_cost_bps",
        "round_trip_execution_bps",
        "rebalance_cost_bps",
        "contingency_cost_bps",
        "total_cost_bps_on_pair_notional",
        "total_cost_bps_on_total_capital",
        "estimated_cost_usd",
        "break_even_gross_carry_bps",
    )

    for profile in profiles:
        values = {
            field: decimal_value(profile[field])
            for field in numeric_fields
        }

        if any(value < 0 for value in values.values()):
            nonnegative = False

        expected_round_trip = (
            values["entry_cost_bps"]
            + values["exit_cost_bps"]
        )
        expected_total = (
            expected_round_trip
            + values["rebalance_cost_bps"]
            + values["contingency_cost_bps"]
        )

        if (
            values["round_trip_execution_bps"]
            != expected_round_trip
            or values[
                "total_cost_bps_on_pair_notional"
            ]
            != expected_total
            or values[
                "break_even_gross_carry_bps"
            ]
            != expected_total
            or values[
                "total_cost_bps_on_total_capital"
            ]
            != expected_total / Decimal("2")
        ):
            formula_consistent = False

        assumptions = profile["assumptions"]

        fee_pairs = (
            (
                "spot_entry_fee_bps",
                "spot_entry_fee_bps",
            ),
            (
                "spot_exit_fee_bps",
                "spot_exit_fee_bps",
            ),
            (
                "perpetual_entry_fee_bps",
                "perpetual_entry_fee_bps",
            ),
            (
                "perpetual_exit_fee_bps",
                "perpetual_exit_fee_bps",
            ),
        )

        for assumption_field, charter_field in fee_pairs:
            if (
                decimal_value(
                    assumptions[assumption_field]
                )
                < charter_costs[charter_field]
            ):
                fees_not_below_charter = False

        if (
            not assumptions.get("uncertainty_label")
            or assumptions.get(
                "order_book_calibrated"
            )
            is not False
            or assumptions.get(
                "historical_fill_calibrated"
            )
            is not False
        ):
            uncertainty_explicit = False

        if (
            assumptions.get(
                "precision_claim_allowed"
            )
            is not False
        ):
            precision_claim_absent = False

    scenario_monotonic = True
    notional_monotonic = True
    severe_double_normal = True

    by_symbol_band: dict[
        tuple[str, str],
        list[Mapping[str, Any]],
    ] = {}

    by_scenario_symbol: dict[
        tuple[str, str],
        list[Mapping[str, Any]],
    ] = {}

    for profile in profiles:
        by_symbol_band.setdefault(
            (
                str(profile["symbol"]),
                str(profile["notional_band"]),
            ),
            [],
        ).append(profile)

        by_scenario_symbol.setdefault(
            (
                str(profile["scenario_code"]),
                str(profile["symbol"]),
            ),
            [],
        ).append(profile)

    for grouped in by_symbol_band.values():
        ordered = sorted(
            grouped,
            key=lambda item: int(
                item["scenario_rank"]
            ),
        )
        totals = [
            decimal_value(
                item[
                    "total_cost_bps_on_pair_notional"
                ]
            )
            for item in ordered
        ]

        if totals != sorted(totals):
            scenario_monotonic = False

        if (
            len(totals) != 3
            or totals[-1]
            < totals[0] * Decimal("2")
        ):
            severe_double_normal = False

    for grouped in by_scenario_symbol.values():
        ordered = sorted(
            grouped,
            key=lambda item: int(
                item["notional_rank"]
            ),
        )
        totals = [
            decimal_value(
                item[
                    "total_cost_bps_on_pair_notional"
                ]
            )
            for item in ordered
        ]

        if totals != sorted(totals):
            notional_monotonic = False

    totals = [
        decimal_value(
            profile[
                "total_cost_bps_on_pair_notional"
            ]
        )
        for profile in profiles
    ]

    return {
        "profile_matrix_complete": (
            profile_matrix_complete
        ),
        "components_nonnegative": nonnegative,
        "formula_consistent": formula_consistent,
        "fees_not_below_charter": (
            fees_not_below_charter
        ),
        "uncertainty_explicit": (
            uncertainty_explicit
        ),
        "precision_claim_absent": (
            precision_claim_absent
        ),
        "scenario_monotonic": (
            scenario_monotonic
        ),
        "notional_monotonic": (
            notional_monotonic
        ),
        "severe_double_normal": (
            severe_double_normal
        ),
        "minimum_total_cost_bps": decimal_text(
            min(totals)
        ),
        "maximum_total_cost_bps": decimal_text(
            max(totals)
        ),
    }


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
        "check_status": (
            CHECK_PASS if passed else CHECK_FAIL
        ),
        "observed_value": str(observed),
        "expected_value": str(expected),
        "check_reason": reason,
    }


def build_model_core(
    contract: Mapping[str, Any],
    profiles: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "model_id": MODEL_ID,
        "contract_id": CONTRACT_ID,
        "contract_hash": EXPECTED_CONTRACT_HASH,
        "source_certification_run_label": (
            SOURCE_CERTIFICATION_RUN_LABEL
        ),
        "source_certificate_hash": (
            EXPECTED_SOURCE_CERTIFICATE_HASH
        ),
        "model_status": MODEL_STATUS,
        "symbols": list(SYMBOLS),
        "symbol_assumptions": deepcopy(
            SYMBOL_ASSUMPTIONS
        ),
        "notional_bands": deepcopy(
            list(NOTIONAL_BANDS)
        ),
        "scenarios": deepcopy(
            list(SCENARIOS)
        ),
        "charter_cost_floors": {
            key: decimal_text(value)
            for key, value in extract_charter_costs(
                contract
            ).items()
        },
        "profiles": list(profiles),
        "uncertainty": {
            "historical_order_book_available": False,
            "historical_queue_position_available": False,
            "true_fill_latency_available": False,
            "historical_market_impact_measured": False,
            "all_non_fee_microstructure_values": (
                "EXPLICIT_ASSUMPTIONS"
            ),
            "precision_claim_allowed": False,
        },
        "research_boundary": {
            "market_data_rows_read": 0,
            "holdout_performance_evaluated": False,
            "backtesting_performed": False,
            "profitability_analyzed": False,
            "model_training_performed": False,
            "model_promotion_performed": False,
        },
        "mission89_authorization": {
            "status": MISSION89_STATUS,
            "authorized_scope": (
                MISSION89_AUTHORIZED_SCOPE
            ),
            "untouched_holdout_authorized": False,
            "automatic_parameter_selection_authorized": False,
            "machine_learning_authorized": False,
            "live_trading_authorized": False,
            "capital_deployment_authorized": False,
        },
        "safety": {
            "live_trading": LIVE_TRADING,
            "live_order_sent": LIVE_ORDER_SENT,
            "capital_deployment": CAPITAL_DEPLOYMENT,
        },
    }


def write_artifact(
    path_value: str | Path,
    model_core: Mapping[str, Any],
    created_at: str,
) -> tuple[str, dict[str, Any]]:
    path = Path(path_value)
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    model_hash = sha256_bytes(
        canonical_json(model_core).encode(
            "utf-8"
        )
    )

    envelope = {
        "model_hash_sha256": model_hash,
        "created_at": created_at,
        "model": model_core,
    }

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            envelope,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary.replace(path)

    return model_hash, envelope


def persist_results(
    conn: sqlite3.Connection,
    *,
    run_label: str,
    created_at: str,
    model_hash: str,
    artifact_path: str | Path,
    artifact_envelope: Mapping[str, Any],
    summary: Mapping[str, Any],
    profiles: Sequence[Mapping[str, Any]],
    checks: Sequence[Mapping[str, Any]],
) -> None:
    for table in (
        "mission88_model_checks",
        "mission88_cost_profiles",
        "mission88_cost_scenarios",
    ):
        conn.execute(
            f"DELETE FROM {table} WHERE run_label = ?",
            (run_label,),
        )

    conn.execute(
        """
        DELETE FROM mission88_cost_model_runs
        WHERE run_label = ?
        """,
        (run_label,),
    )
    conn.execute(
        """
        DELETE FROM mission88_cost_model_artifacts
        WHERE run_label = ?
        """,
        (run_label,),
    )

    for scenario in SCENARIOS:
        conn.execute(
            """
            INSERT INTO mission88_cost_scenarios (
                run_label,
                scenario_code,
                scenario_rank,
                uncertainty_label,
                order_book_calibrated,
                precision_claim_allowed,
                scenario_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_label,
                scenario["scenario_code"],
                int(scenario["rank"]),
                scenario["uncertainty_label"],
                int(
                    bool(
                        scenario[
                            "order_book_calibrated"
                        ]
                    )
                ),
                int(
                    bool(
                        scenario[
                            "precision_claim_allowed"
                        ]
                    )
                ),
                canonical_json(scenario),
            ),
        )

    for profile in profiles:
        conn.execute(
            """
            INSERT INTO mission88_cost_profiles (
                run_label,
                model_hash,
                scenario_code,
                scenario_rank,
                symbol,
                notional_band,
                notional_rank,
                per_leg_notional_usd,
                fully_collateralized_capital_usd,
                entry_cost_bps,
                exit_cost_bps,
                round_trip_execution_bps,
                rebalance_cost_bps,
                contingency_cost_bps,
                total_cost_bps_on_pair_notional,
                total_cost_bps_on_total_capital,
                estimated_cost_usd,
                break_even_gross_carry_bps,
                profile_hash,
                assumptions_json
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                run_label,
                model_hash,
                profile["scenario_code"],
                profile["scenario_rank"],
                profile["symbol"],
                profile["notional_band"],
                profile["notional_rank"],
                profile["per_leg_notional_usd"],
                profile[
                    "fully_collateralized_capital_usd"
                ],
                profile["entry_cost_bps"],
                profile["exit_cost_bps"],
                profile[
                    "round_trip_execution_bps"
                ],
                profile["rebalance_cost_bps"],
                profile["contingency_cost_bps"],
                profile[
                    "total_cost_bps_on_pair_notional"
                ],
                profile[
                    "total_cost_bps_on_total_capital"
                ],
                profile["estimated_cost_usd"],
                profile[
                    "break_even_gross_carry_bps"
                ],
                profile["profile_hash"],
                canonical_json(
                    profile["assumptions"]
                ),
            ),
        )

    for index, check in enumerate(checks):
        conn.execute(
            """
            INSERT INTO mission88_model_checks (
                check_id,
                run_label,
                created_at,
                check_category,
                check_name,
                check_status,
                observed_value,
                expected_value,
                check_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    f"{run_label}-"
                    f"{index + 1:02d}-"
                    f"{check['check_name'].lower()}"
                ),
                run_label,
                created_at,
                check["check_category"],
                check["check_name"],
                check["check_status"],
                check["observed_value"],
                check["expected_value"],
                check["check_reason"],
            ),
        )

    conn.execute(
        """
        INSERT INTO mission88_cost_model_artifacts (
            run_label,
            model_id,
            model_hash,
            created_at,
            artifact_path,
            artifact_json,
            model_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_label,
            MODEL_ID,
            model_hash,
            created_at,
            str(artifact_path),
            canonical_json(artifact_envelope),
            MODEL_STATUS,
        ),
    )

    conn.execute(
        """
        INSERT INTO mission88_cost_model_runs (
            run_label,
            source_certification_run_label,
            contract_id,
            contract_hash,
            source_certificate_hash,
            model_id,
            model_hash,
            created_at,
            model_status,
            mission88_status,
            symbol_count,
            scenario_count,
            notional_band_count,
            profile_count,
            minimum_total_cost_bps,
            maximum_total_cost_bps,
            check_count,
            pass_check_count,
            fail_check_count,
            safety_breach_count,
            market_data_rows_read,
            holdout_performance_evaluated,
            backtesting_performed,
            profitability_analyzed,
            mission89_status,
            mission89_authorized_scope,
            global_verdict,
            next_mission,
            live_trading,
            live_order_sent,
            capital_deployment,
            summary_json
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            run_label,
            SOURCE_CERTIFICATION_RUN_LABEL,
            CONTRACT_ID,
            EXPECTED_CONTRACT_HASH,
            EXPECTED_SOURCE_CERTIFICATE_HASH,
            MODEL_ID,
            model_hash,
            created_at,
            MODEL_STATUS,
            MISSION88_STATUS,
            summary["symbol_count"],
            summary["scenario_count"],
            summary["notional_band_count"],
            summary["profile_count"],
            summary[
                "minimum_total_cost_bps"
            ],
            summary[
                "maximum_total_cost_bps"
            ],
            summary["check_count"],
            summary["pass_check_count"],
            summary["fail_check_count"],
            summary["safety_breach_count"],
            0,
            0,
            0,
            0,
            MISSION89_STATUS,
            MISSION89_AUTHORIZED_SCOPE,
            GLOBAL_VERDICT,
            NEXT_MISSION,
            LIVE_TRADING,
            LIVE_ORDER_SENT,
            CAPITAL_DEPLOYMENT,
            canonical_json(summary),
        ),
    )

    conn.commit()


def run_cost_model(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    contract_path: str | Path = DEFAULT_CONTRACT_PATH,
    artifact_path: str | Path = DEFAULT_ARTIFACT_PATH,
    run_label: str = "mission88-local-check",
    created_at: str | None = None,
) -> dict[str, Any]:
    contract = load_authoritative_contract(
        contract_path
    )

    ensure_schema(db_path)
    created_at = created_at or utc_now()

    with sqlite3.connect(Path(db_path)) as conn:
        conn.row_factory = sqlite3.Row

        source = load_source_certification(conn)
        source_errors = validate_source_certification(
            source
        )

        if source_errors:
            raise RuntimeError(
                "Mission 87 source certification invalid: "
                + "; ".join(source_errors)
            )

        profiles = build_cost_profiles(
            contract
        )
        validation = validate_profiles(
            profiles,
            contract,
        )

        contract_costs = contract[
            "initial_cost_assumptions"
        ]

        source_status_valid = (
            source["certification_status"]
            == (
                "CERTIFIED_FOR_RESEARCH_"
                "PENDING_EXECUTION_COST_MODEL"
            )
        )
        source_hash_valid = (
            source["certificate_hash"]
            == EXPECTED_SOURCE_CERTIFICATE_HASH
        )
        source_series_valid = (
            source["persisted_series_count"] == 15
            and source[
                "persisted_rejected_count"
            ]
            == 0
        )
        source_checks_valid = (
            source["quality_check_count"] == 23
            and source["pass_check_count"] == 23
            and source["fail_check_count"] == 0
            and source["safety_breach_count"] == 0
        )
        source_boundary_valid = (
            source[
                "holdout_performance_evaluated"
            ]
            == 0
            and source["backtesting_performed"] == 0
            and source["profitability_analyzed"] == 0
        )

        scenarios_exact = {
            scenario["scenario_code"]
            for scenario in SCENARIOS
        } == {
            "NORMAL_ASSUMPTION",
            "CONSERVATIVE_ASSUMPTION",
            "SEVERE_STRESS_ASSUMPTION",
        }

        bands_exact = {
            band["notional_band"]
            for band in NOTIONAL_BANDS
        } == {
            "MICRO_RESEARCH_1K",
            "SMALL_RESEARCH_10K",
            "UPPER_RESEARCH_50K",
        }

        uncertainty_labels_valid = all(
            scenario["uncertainty_label"]
            and scenario[
                "order_book_calibrated"
            ]
            is False
            and scenario[
                "precision_claim_allowed"
            ]
            is False
            for scenario in SCENARIOS
        )

        no_precision_claim = (
            validation[
                "precision_claim_absent"
            ]
            and all(
                profile["assumptions"][
                    "order_book_calibrated"
                ]
                is False
                and profile["assumptions"][
                    "historical_fill_calibrated"
                ]
                is False
                for profile in profiles
            )
        )

        all_execution_paths_blocked = (
            LIVE_TRADING == "DISABLED"
            and LIVE_ORDER_SENT == 0
            and CAPITAL_DEPLOYMENT == "BLOCKED"
        )

        checks = [
            make_check(
                "SOURCE",
                "SOURCE_CERTIFICATION_STATUS",
                source_status_valid,
                source["certification_status"],
                (
                    "CERTIFIED_FOR_RESEARCH_"
                    "PENDING_EXECUTION_COST_MODEL"
                ),
                "Mission 88 requires the certified Mission 87 dataset gate.",
            ),
            make_check(
                "SOURCE",
                "SOURCE_CERTIFICATE_HASH",
                source_hash_valid,
                source["certificate_hash"],
                EXPECTED_SOURCE_CERTIFICATE_HASH,
                "The cost model must bind to the authoritative certificate.",
            ),
            make_check(
                "SOURCE",
                "SOURCE_SERIES_CERTIFIED",
                source_series_valid,
                (
                    source[
                        "persisted_series_count"
                    ],
                    source[
                        "persisted_rejected_count"
                    ],
                ),
                (15, 0),
                "All required series must remain certified.",
            ),
            make_check(
                "SOURCE",
                "SOURCE_QUALITY_CHECKS",
                source_checks_valid,
                (
                    source["pass_check_count"],
                    source["fail_check_count"],
                    source[
                        "safety_breach_count"
                    ],
                ),
                (23, 0, 0),
                "Mission 87 must have no failed or unsafe checks.",
            ),
            make_check(
                "SOURCE",
                "SOURCE_RESEARCH_BOUNDARY",
                source_boundary_valid,
                (
                    source[
                        "holdout_performance_evaluated"
                    ],
                    source[
                        "backtesting_performed"
                    ],
                    source[
                        "profitability_analyzed"
                    ],
                ),
                (0, 0, 0),
                "Mission 88 must inherit the untouched performance boundary.",
            ),
            make_check(
                "CONTRACT",
                "CONTRACT_HASH",
                source["contract_hash"]
                == EXPECTED_CONTRACT_HASH,
                source["contract_hash"],
                EXPECTED_CONTRACT_HASH,
                "The cost model must use the locked Mission 85 charter.",
            ),
            make_check(
                "CONTRACT",
                "CONTRACT_COST_FLOORS_PRESENT",
                all(
                    field in contract_costs
                    for field in (
                        "spot_entry_fee_bps",
                        "spot_exit_fee_bps",
                        "perpetual_entry_fee_bps",
                        "perpetual_exit_fee_bps",
                        "spot_slippage_per_side_bps",
                        "perpetual_slippage_per_side_bps",
                        "rebalance_cost_bps",
                        "stress_cost_multiplier",
                    )
                ),
                sorted(contract_costs),
                "all required cost floors",
                "The charter must provide every baseline cost floor.",
            ),
            make_check(
                "GOVERNANCE",
                "COST_REDUCTION_PROHIBITED",
                contract_costs.get(
                    "cost_reduction_after_results_allowed"
                )
                is False,
                contract_costs.get(
                    "cost_reduction_after_results_allowed"
                ),
                False,
                "Cost assumptions may not be reduced after seeing results.",
            ),
            make_check(
                "SCOPE",
                "SYMBOL_SCOPE",
                tuple(
                    contract["universe"]["symbols"]
                )
                == SYMBOLS,
                contract["universe"]["symbols"],
                list(SYMBOLS),
                "Mission 88 remains limited to BTC, ETH, and SOL.",
            ),
            make_check(
                "SCENARIOS",
                "SCENARIO_SET",
                scenarios_exact,
                [
                    item["scenario_code"]
                    for item in SCENARIOS
                ],
                [
                    "NORMAL_ASSUMPTION",
                    "CONSERVATIVE_ASSUMPTION",
                    "SEVERE_STRESS_ASSUMPTION",
                ],
                "Exactly three explicit uncertainty envelopes are required.",
            ),
            make_check(
                "NOTIONAL",
                "NOTIONAL_BANDS",
                bands_exact,
                [
                    item["notional_band"]
                    for item in NOTIONAL_BANDS
                ],
                [
                    "MICRO_RESEARCH_1K",
                    "SMALL_RESEARCH_10K",
                    "UPPER_RESEARCH_50K",
                ],
                "The model must expose size sensitivity without authorizing capital.",
            ),
            make_check(
                "COVERAGE",
                "PROFILE_MATRIX",
                validation[
                    "profile_matrix_complete"
                ],
                len(profiles),
                27,
                "Every scenario, symbol, and notional combination is required.",
            ),
            make_check(
                "MATHEMATICS",
                "COMPONENTS_NONNEGATIVE",
                validation[
                    "components_nonnegative"
                ],
                validation[
                    "components_nonnegative"
                ],
                True,
                "Every cost component must be nonnegative.",
            ),
            make_check(
                "GOVERNANCE",
                "FEES_NOT_BELOW_CHARTER",
                validation[
                    "fees_not_below_charter"
                ],
                validation[
                    "fees_not_below_charter"
                ],
                True,
                "Mission 88 may not undercut the preregistered fee floors.",
            ),
            make_check(
                "MATHEMATICS",
                "FORMULA_CONSISTENCY",
                validation[
                    "formula_consistent"
                ],
                validation[
                    "formula_consistent"
                ],
                True,
                "Every total must equal its declared component sum.",
            ),
            make_check(
                "STRESS",
                "SCENARIO_MONOTONICITY",
                validation[
                    "scenario_monotonic"
                ],
                validation[
                    "scenario_monotonic"
                ],
                True,
                "Costs must not decline as scenario stress increases.",
            ),
            make_check(
                "STRESS",
                "NOTIONAL_MONOTONICITY",
                validation[
                    "notional_monotonic"
                ],
                validation[
                    "notional_monotonic"
                ],
                True,
                "Costs must not decline as assumed notional increases.",
            ),
            make_check(
                "STRESS",
                "SEVERE_STRESS_DOUBLE_NORMAL",
                validation[
                    "severe_double_normal"
                ],
                validation[
                    "severe_double_normal"
                ],
                True,
                "Severe cost must be at least twice normal for each profile family.",
            ),
            make_check(
                "UNCERTAINTY",
                "UNCERTAINTY_LABELS",
                uncertainty_labels_valid
                and validation[
                    "uncertainty_explicit"
                ],
                uncertainty_labels_valid,
                True,
                "Every scenario must state that it is assumption-bounded.",
            ),
            make_check(
                "UNCERTAINTY",
                "NO_ORDERBOOK_PRECISION_CLAIM",
                no_precision_claim,
                no_precision_claim,
                True,
                "No profile may claim measured order-book or fill precision.",
            ),
            make_check(
                "RESEARCH_BOUNDARY",
                "NO_MARKET_DATA_CALIBRATION",
                True,
                0,
                0,
                "Mission 88 reads no price, volume, funding, or holdout rows.",
            ),
            make_check(
                "RESEARCH_BOUNDARY",
                "NO_BACKTEST_HOLDOUT_PROFITABILITY",
                True,
                (0, 0, 0),
                (0, 0, 0),
                "Mission 88 performs no backtest, holdout evaluation, or profitability analysis.",
            ),
            make_check(
                "SAFETY",
                "SAFETY_LOCKS",
                all_execution_paths_blocked,
                (
                    LIVE_TRADING,
                    LIVE_ORDER_SENT,
                    CAPITAL_DEPLOYMENT,
                ),
                ("DISABLED", 0, "BLOCKED"),
                "No trading or capital path is authorized.",
            ),
            make_check(
                "MISSION_GATE",
                "MISSION89_SCOPE",
                MISSION89_AUTHORIZED_SCOPE
                == (
                    "DEVELOPMENT_AND_VALIDATION_"
                    "BASELINE_FALSIFICATION_ONLY"
                ),
                MISSION89_AUTHORIZED_SCOPE,
                (
                    "DEVELOPMENT_AND_VALIDATION_"
                    "BASELINE_FALSIFICATION_ONLY"
                ),
                "Mission 89 must not consume the untouched holdout.",
            ),
        ]

        pass_count = sum(
            check["check_status"] == CHECK_PASS
            for check in checks
        )
        fail_count = sum(
            check["check_status"] == CHECK_FAIL
            for check in checks
        )

        safety_breach_count = int(
            checks[-2]["check_status"]
            != CHECK_PASS
        )

        if fail_count > 0:
            failed_names = [
                check["check_name"]
                for check in checks
                if check["check_status"]
                == CHECK_FAIL
            ]
            raise RuntimeError(
                "Mission 88 validation failed: "
                + ", ".join(failed_names)
            )

        model_core = build_model_core(
            contract,
            profiles,
        )

        model_hash, artifact_envelope = (
            write_artifact(
                artifact_path,
                model_core,
                created_at,
            )
        )

        summary: dict[str, Any] = {
            "run_label": run_label,
            "source_certification_run_label": (
                SOURCE_CERTIFICATION_RUN_LABEL
            ),
            "contract_id": CONTRACT_ID,
            "contract_hash": (
                EXPECTED_CONTRACT_HASH
            ),
            "source_certificate_hash": (
                EXPECTED_SOURCE_CERTIFICATE_HASH
            ),
            "model_id": MODEL_ID,
            "model_hash": model_hash,
            "artifact_path": str(artifact_path),
            "created_at": created_at,
            "model_status": MODEL_STATUS,
            "mission88_status": MISSION88_STATUS,
            "symbol_count": len(SYMBOLS),
            "scenario_count": len(SCENARIOS),
            "notional_band_count": len(
                NOTIONAL_BANDS
            ),
            "profile_count": len(profiles),
            "minimum_total_cost_bps": (
                validation[
                    "minimum_total_cost_bps"
                ]
            ),
            "maximum_total_cost_bps": (
                validation[
                    "maximum_total_cost_bps"
                ]
            ),
            "check_count": len(checks),
            "pass_check_count": pass_count,
            "fail_check_count": fail_count,
            "safety_breach_count": (
                safety_breach_count
            ),
            "market_data_rows_read": 0,
            "holdout_performance_evaluated": 0,
            "backtesting_performed": 0,
            "profitability_analyzed": 0,
            "mission89_status": MISSION89_STATUS,
            "mission89_authorized_scope": (
                MISSION89_AUTHORIZED_SCOPE
            ),
            "global_verdict": GLOBAL_VERDICT,
            "next_mission": NEXT_MISSION,
            "live_trading": LIVE_TRADING,
            "live_order_sent": LIVE_ORDER_SENT,
            "capital_deployment": (
                CAPITAL_DEPLOYMENT
            ),
        }

        persist_results(
            conn,
            run_label=run_label,
            created_at=created_at,
            model_hash=model_hash,
            artifact_path=artifact_path,
            artifact_envelope=(
                artifact_envelope
            ),
            summary=summary,
            profiles=profiles,
            checks=checks,
        )

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Mission 88 assumption-bounded "
            "execution and cost reality model"
        )
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
        "--artifact-path",
        default=str(DEFAULT_ARTIFACT_PATH),
    )
    parser.add_argument(
        "--run-label",
        default="mission88-local-check",
    )

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(
        list(argv) if argv is not None else None
    )

    summary = run_cost_model(
        db_path=args.db_path,
        contract_path=args.contract_path,
        artifact_path=args.artifact_path,
        run_label=args.run_label,
    )

    print(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

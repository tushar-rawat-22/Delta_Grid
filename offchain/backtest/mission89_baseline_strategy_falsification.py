"""Mission 89: End-to-End Baseline Strategy Falsification Pack.

Mission 89 evaluates the locked Mission 85 delta-neutral funding-carry
hypothesis on development and validation data only. It binds to the certified
Mission 87 dataset and the assumption-bounded Mission 88 execution-cost model.

The mission locks an evaluation protocol, runs a no-lookahead event-driven
simulator across all twelve preregistered variants, selects at most one
candidate on development data, evaluates the fixed candidate on validation,
performs robustness and overfitting diagnostics, and issues one final decision.

The untouched holdout is never queried. No live signal, order, private key,
signing path, leverage deployment, model training, model promotion, capital
deployment, or forward-profitability claim is permitted.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import sqlite3
import statistics
from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterable, Mapping, Sequence

from offchain.backtest.mission86_real_market_data_foundation import (
    CANONICAL_INTERVAL,
    EXPECTED_CONTRACT_HASH,
    INTERVAL_MS,
    canonical_json,
    load_authoritative_contract,
    parse_utc_ms,
    sha256_bytes,
)
from offchain.research.funding_carry_research_contract import (
    CAPITAL_DEPLOYMENT,
    CONTRACT_ID,
    LIVE_ORDER_SENT,
    LIVE_TRADING,
    parameter_variants,
)


SOURCE_CERTIFICATION_RUN_LABEL = "mission87-final-check"
SOURCE_COST_MODEL_RUN_LABEL = "mission88-final-check"
EXPECTED_SOURCE_CERTIFICATE_HASH = (
    "e4d78b99417c1acb9bd89e7a8ef175cbf0c0e1219c1f71777401be41b8978819"
)
EXPECTED_SOURCE_COST_MODEL_HASH = (
    "398cc556614a97767fea36540556442579f195562a9ed16c18cc9561b78fc8a2"
)

PROTOCOL_ID = "mission89-baseline-falsification-protocol-v1"
PROTOCOL_VERSION = 1
MISSION89_STATUS = "COMPLETE_END_TO_END_BASELINE_FALSIFICATION"
MODEL_SCOPE = "DEVELOPMENT_AND_VALIDATION_ONLY"

DECISION_ADVANCE = "ADVANCE_TO_MISSION90_UNTOUCHED_HOLDOUT"
DECISION_CONTINUE = "CONTINUE_COLLECTING_EVIDENCE_NO_HOLDOUT_ACCESS"
DECISION_REJECT = "REJECT_AND_ARCHIVE_FUNDING_CARRY"

MISSION90_READY = "READY_FOR_SINGLE_USE_UNTOUCHED_HOLDOUT"
MISSION90_PAUSED = "PAUSED_PENDING_ADDITIONAL_EVIDENCE"
MISSION90_NOT_AUTHORIZED = "NOT_AUTHORIZED_STRATEGY_REJECTED"

DEFAULT_DB_PATH = Path("offchain/deltagrid.db")
DEFAULT_CONTRACT_PATH = Path(
    "offchain/research/contracts/mission85_funding_carry_charter_v1.json"
)
DEFAULT_PROTOCOL_PATH = Path(
    "offchain/research/contracts/"
    "mission89_baseline_falsification_protocol_v1.json"
)
DEFAULT_REPORT_PATH = Path(
    "offchain/data/mission89/falsification_report.json"
)

PRIMARY_NOTIONAL_BAND = "SMALL_RESEARCH_10K"
SENSITIVITY_NOTIONAL_BANDS = (
    "MICRO_RESEARCH_1K",
    "UPPER_RESEARCH_50K",
)
PRIMARY_SCENARIO = "NORMAL_ASSUMPTION"
PROMOTION_SCENARIO = "CONSERVATIVE_ASSUMPTION"
DIAGNOSTIC_SCENARIO = "SEVERE_STRESS_ASSUMPTION"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
HOUR_MS = INTERVAL_MS
FUNDING_SETTLEMENTS_PER_DAY = 3

CHECK_PASS = "PASS"
CHECK_FAIL = "FAIL"


EVALUATION_PROTOCOL: dict[str, Any] = {
    "protocol_id": PROTOCOL_ID,
    "protocol_version": PROTOCOL_VERSION,
    "mission": "Mission 89 End-to-End Baseline Strategy Falsification Pack",
    "scope": MODEL_SCOPE,
    "source_lineage": {
        "contract_id": CONTRACT_ID,
        "contract_hash": EXPECTED_CONTRACT_HASH,
        "certification_run_label": SOURCE_CERTIFICATION_RUN_LABEL,
        "certificate_hash": EXPECTED_SOURCE_CERTIFICATE_HASH,
        "cost_model_run_label": SOURCE_COST_MODEL_RUN_LABEL,
        "cost_model_hash": EXPECTED_SOURCE_COST_MODEL_HASH,
    },
    "evaluation_windows": {
        "development": "SELECTION_ALLOWED",
        "validation": "FIXED_CANDIDATE_ONLY",
        "untouched_holdout": "SEALED_AND_FORBIDDEN",
    },
    "notional_policy": {
        "primary_band": PRIMARY_NOTIONAL_BAND,
        "sensitivity_bands": list(SENSITIVITY_NOTIONAL_BANDS),
        "primary_return_denominator": "TOTAL_FULLY_COLLATERALIZED_CAPITAL",
        "pair_notional_return_secondary": True,
    },
    "cost_policy": {
        "normal_role": "BASE_CASE_REPORTING",
        "conservative_role": "MANDATORY_PROMOTION_GATE",
        "severe_role": "DIAGNOSTIC_SURVIVABILITY_ONLY",
        "severe_profitability_required": False,
        "cost_reduction_after_results_allowed": False,
    },
    "timing_policy": {
        "signal_information": "SETTLED_FUNDING_AT_OR_BEFORE_DECISION_ONLY",
        "entry_execution": "STRICTLY_NEXT_HOURLY_BAR_OPEN",
        "exit_execution": "STRICTLY_NEXT_HOURLY_BAR_OPEN",
        "rebalance_execution": "STRICTLY_NEXT_HOURLY_BAR_OPEN",
        "trigger_funding_collectible": False,
        "same_bar_execution_allowed": False,
        "lookahead_allowed": False,
    },
    "strategy_evaluation": {
        "evaluate_all_preregistered_variants": True,
        "expected_variant_count": 12,
        "development_selection_count_maximum": 1,
        "validation_candidate_replacement_allowed": False,
        "post_validation_tuning_allowed": False,
        "machine_learning_rescue_allowed": False,
    },
    "mandatory_validation_gates": {
        "conservative_net_pnl_positive": True,
        "normal_net_pnl_positive": True,
        "minimum_closed_positions": 12,
        "minimum_positive_asset_count": 2,
        "maximum_single_asset_positive_pnl_contribution_pct": 60.0,
        "maximum_single_quarter_positive_pnl_contribution_pct": 50.0,
        "maximum_realized_and_marked_drawdown_pct": 10.0,
        "minimum_active_volatility_regime_count": 2,
        "maximum_single_regime_positive_pnl_contribution_pct": 80.0,
        "minimum_parameter_neighbor_count": 2,
        "minimum_positive_neighbor_fraction": 0.50,
        "maximum_probability_of_backtest_overfitting": 0.20,
        "minimum_deflated_sharpe_probability": 0.95,
    },
    "decision_policy": {
        "advance": DECISION_ADVANCE,
        "continue": DECISION_CONTINUE,
        "reject": DECISION_REJECT,
        "insufficient_evidence_conditions": [
            "validation_closed_positions_below_minimum",
            "statistical_sample_too_small_for_deflated_sharpe",
        ],
        "failed_strategy_archived": True,
    },
    "research_boundary": {
        "holdout_rows_allowed": 0,
        "live_trading_allowed": False,
        "capital_deployment_allowed": False,
        "profitability_claim_allowed": False,
        "model_training_allowed": False,
        "model_promotion_allowed": False,
    },
}


@dataclass(frozen=True)
class Variant:
    variant_id: str
    minimum_trailing_funding_rate_bps: float
    maximum_absolute_entry_basis_bps: float
    maximum_holding_days: int


@dataclass(frozen=True)
class CostProfile:
    scenario_code: str
    symbol: str
    notional_band: str
    per_leg_notional_usd: float
    entry_cost_bps: float
    exit_cost_bps: float
    modeled_rebalance_cost_bps: float
    hedge_delay_cost_bps: float
    partial_fill_cost_bps: float
    funding_reconciliation_buffer_bps: float
    operational_buffer_bps: float
    assumed_rebalance_count: int


@dataclass
class SymbolData:
    symbol: str
    start_ms: int
    end_ms: int
    hours: list[int]
    spot_open: dict[int, float]
    perpetual_open: dict[int, float]
    mark_open: dict[int, float]
    funding_by_hour: dict[int, dict[str, float | int]]
    volatility_regime_by_hour: dict[int, str] = field(default_factory=dict)


@dataclass
class PositionState:
    symbol: str
    entry_decision_time_ms: int
    entry_time_ms: int
    entry_reason: str
    entry_trailing_funding_bps: float
    entry_basis_bps: float
    entry_volatility_regime: str
    spot_entry_price: float
    spot_qty: float
    perpetual_average_entry_price: float
    perpetual_qty: float
    entry_cost_usd: float
    hedge_delay_cost_usd: float
    partial_fill_cost_usd: float
    funding_pnl_usd: float = 0.0
    realized_perpetual_pnl_usd: float = 0.0
    rebalance_cost_usd_paid: float = 0.0
    rebalance_count: int = 0
    nonpositive_funding_streak: int = 0
    funding_settlement_count: int = 0


@dataclass
class PendingAction:
    action: str
    execution_time_ms: int
    reason: str
    decision_time_ms: int
    metadata: dict[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def protocol_hash(protocol: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(protocol).encode("utf-8"))


def strictly_next_hour(timestamp_ms: int) -> int:
    return (int(timestamp_ms) // HOUR_MS + 1) * HOUR_MS


def nearest_hour(timestamp_ms: int) -> int:
    return ((int(timestamp_ms) + HOUR_MS // 2) // HOUR_MS) * HOUR_MS


def quarter_label(timestamp_ms: int) -> str:
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    quarter = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{quarter}"


def safe_ratio(numerator: float, denominator: float, default: float = 0.0) -> float:
    if denominator == 0:
        return default
    return numerator / denominator


def quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("quantile requires at least one value")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def create_variants(contract: Mapping[str, Any]) -> list[Variant]:
    rows = parameter_variants(contract)
    variants: list[Variant] = []
    for index, row in enumerate(rows, start=1):
        variants.append(
            Variant(
                variant_id=f"V{index:02d}",
                minimum_trailing_funding_rate_bps=float(
                    row["minimum_trailing_funding_rate_bps"]
                ),
                maximum_absolute_entry_basis_bps=float(
                    row["maximum_absolute_entry_basis_bps"]
                ),
                maximum_holding_days=int(row["maximum_holding_days"]),
            )
        )
    return variants


def variant_dict(variant: Variant) -> dict[str, Any]:
    return {
        "variant_id": variant.variant_id,
        "minimum_trailing_funding_rate_bps": (
            variant.minimum_trailing_funding_rate_bps
        ),
        "maximum_absolute_entry_basis_bps": (
            variant.maximum_absolute_entry_basis_bps
        ),
        "maximum_holding_days": variant.maximum_holding_days,
    }


def lock_protocol(
    path_value: str | Path,
    protocol: Mapping[str, Any] = EVALUATION_PROTOCOL,
    locked_at: str | None = None,
) -> dict[str, Any]:
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    hash_value = protocol_hash(protocol)
    envelope = {
        "protocol": deepcopy(dict(protocol)),
        "protocol_hash_sha256": hash_value,
        "locked_at": locked_at or utc_now(),
        "status": "LOCKED_BEFORE_MISSION89_RESULT_EVALUATION",
    }
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("protocol_hash_sha256") != hash_value:
            raise RuntimeError(
                "Mission 89 protocol already exists with a different hash"
            )
        if existing.get("protocol") != protocol:
            raise RuntimeError("Mission 89 protocol payload changed after lock")
        return existing
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(envelope, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return envelope


def ensure_schema(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS mission89_protocols (
                protocol_id TEXT PRIMARY KEY,
                protocol_hash TEXT NOT NULL,
                locked_at TEXT NOT NULL,
                protocol_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mission89_runs (
                run_label TEXT PRIMARY KEY,
                protocol_id TEXT NOT NULL,
                protocol_hash TEXT NOT NULL,
                contract_hash TEXT NOT NULL,
                source_certificate_hash TEXT NOT NULL,
                source_cost_model_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                mission89_status TEXT NOT NULL,
                decision TEXT NOT NULL,
                selected_variant_id TEXT,
                development_candidate_count INTEGER NOT NULL,
                development_variant_count INTEGER NOT NULL,
                validation_closed_position_count INTEGER NOT NULL,
                mandatory_gate_count INTEGER NOT NULL,
                passed_mandatory_gate_count INTEGER NOT NULL,
                failed_mandatory_gate_count INTEGER NOT NULL,
                pbo REAL NOT NULL,
                deflated_sharpe_probability REAL NOT NULL,
                holdout_rows_read INTEGER NOT NULL,
                maximum_timestamp_read_ms INTEGER NOT NULL,
                backtesting_performed INTEGER NOT NULL,
                profitability_claimed INTEGER NOT NULL,
                mission90_status TEXT NOT NULL,
                next_workstream TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                report_hash TEXT NOT NULL,
                summary_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mission89_variant_results (
                run_label TEXT NOT NULL,
                split_name TEXT NOT NULL,
                variant_id TEXT NOT NULL,
                scenario_code TEXT NOT NULL,
                notional_band TEXT NOT NULL,
                feasibility_status TEXT NOT NULL,
                closed_position_count INTEGER NOT NULL,
                net_pnl_usd REAL NOT NULL,
                total_capital_return_pct REAL NOT NULL,
                pair_notional_return_pct REAL NOT NULL,
                maximum_drawdown_pct REAL NOT NULL,
                positive_asset_count INTEGER NOT NULL,
                maximum_asset_contribution_pct REAL NOT NULL,
                maximum_quarter_contribution_pct REAL NOT NULL,
                active_regime_count INTEGER NOT NULL,
                maximum_regime_contribution_pct REAL NOT NULL,
                sharpe_ratio REAL NOT NULL,
                result_json TEXT NOT NULL,
                PRIMARY KEY (
                    run_label,
                    split_name,
                    variant_id,
                    scenario_code,
                    notional_band
                )
            );

            CREATE TABLE IF NOT EXISTS mission89_selected_trade_ledger (
                run_label TEXT NOT NULL,
                split_name TEXT NOT NULL,
                scenario_code TEXT NOT NULL,
                notional_band TEXT NOT NULL,
                trade_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                entry_time_ms INTEGER NOT NULL,
                exit_time_ms INTEGER NOT NULL,
                exit_reason TEXT NOT NULL,
                spot_pnl_usd REAL NOT NULL,
                perpetual_pnl_usd REAL NOT NULL,
                funding_pnl_usd REAL NOT NULL,
                entry_cost_usd REAL NOT NULL,
                exit_cost_usd REAL NOT NULL,
                rebalance_cost_usd REAL NOT NULL,
                hedge_delay_cost_usd REAL NOT NULL,
                partial_fill_cost_usd REAL NOT NULL,
                funding_reconciliation_cost_usd REAL NOT NULL,
                operational_cost_usd REAL NOT NULL,
                gross_pnl_usd REAL NOT NULL,
                net_pnl_usd REAL NOT NULL,
                capital_employed_usd REAL NOT NULL,
                trade_json TEXT NOT NULL,
                PRIMARY KEY (
                    run_label,
                    split_name,
                    scenario_code,
                    notional_band,
                    trade_id
                )
            );

            CREATE TABLE IF NOT EXISTS mission89_gates (
                gate_id TEXT PRIMARY KEY,
                run_label TEXT NOT NULL,
                gate_name TEXT NOT NULL,
                gate_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                required_value TEXT NOT NULL,
                mandatory INTEGER NOT NULL,
                gate_reason TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mission89_reports (
                run_label TEXT PRIMARY KEY,
                report_hash TEXT NOT NULL,
                report_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                report_json TEXT NOT NULL
            );
            """
        )
        conn.commit()


def validate_source_lineage(conn: sqlite3.Connection) -> dict[str, Any]:
    certification = conn.execute(
        """
        SELECT *
        FROM mission87_certification_runs
        WHERE certification_run_label = ?
        """,
        (SOURCE_CERTIFICATION_RUN_LABEL,),
    ).fetchone()
    cost_model = conn.execute(
        """
        SELECT *
        FROM mission88_cost_model_runs
        WHERE run_label = ?
        """,
        (SOURCE_COST_MODEL_RUN_LABEL,),
    ).fetchone()
    if certification is None:
        raise RuntimeError("Mission 87 authoritative certification is missing")
    if cost_model is None:
        raise RuntimeError("Mission 88 authoritative cost model is missing")
    certification = dict(certification)
    cost_model = dict(cost_model)
    requirements = [
        certification["contract_hash"] == EXPECTED_CONTRACT_HASH,
        certification["certificate_hash"] == EXPECTED_SOURCE_CERTIFICATE_HASH,
        certification["certification_status"]
        == "CERTIFIED_FOR_RESEARCH_PENDING_EXECUTION_COST_MODEL",
        certification["certified_series_count"] == 15,
        certification["rejected_series_count"] == 0,
        certification["fail_check_count"] == 0,
        certification["safety_breach_count"] == 0,
        cost_model["contract_hash"] == EXPECTED_CONTRACT_HASH,
        cost_model["source_certificate_hash"]
        == EXPECTED_SOURCE_CERTIFICATE_HASH,
        cost_model["model_hash"] == EXPECTED_SOURCE_COST_MODEL_HASH,
        cost_model["model_status"]
        == "APPROVED_FOR_BASELINE_FALSIFICATION_WITH_UNCERTAINTY",
        cost_model["mission89_authorized_scope"]
        == "DEVELOPMENT_AND_VALIDATION_BASELINE_FALSIFICATION_ONLY",
        cost_model["fail_check_count"] == 0,
        cost_model["safety_breach_count"] == 0,
        cost_model["live_trading"] == "DISABLED",
        cost_model["live_order_sent"] == 0,
        cost_model["capital_deployment"] == "BLOCKED",
    ]
    if not all(requirements):
        raise RuntimeError("Mission 87/88 source lineage validation failed")
    return {
        "certification": certification,
        "cost_model": cost_model,
    }


def load_cost_profiles(conn: sqlite3.Connection) -> dict[tuple[str, str, str], CostProfile]:
    rows = conn.execute(
        """
        SELECT *
        FROM mission88_cost_profiles
        WHERE run_label = ?
        ORDER BY scenario_rank, symbol, notional_rank
        """,
        (SOURCE_COST_MODEL_RUN_LABEL,),
    ).fetchall()
    profiles: dict[tuple[str, str, str], CostProfile] = {}
    for row in rows:
        item = dict(row)
        assumptions = json.loads(item["assumptions_json"])
        profile = CostProfile(
            scenario_code=str(item["scenario_code"]),
            symbol=str(item["symbol"]),
            notional_band=str(item["notional_band"]),
            per_leg_notional_usd=float(item["per_leg_notional_usd"]),
            entry_cost_bps=float(item["entry_cost_bps"]),
            exit_cost_bps=float(item["exit_cost_bps"]),
            modeled_rebalance_cost_bps=float(item["rebalance_cost_bps"]),
            hedge_delay_cost_bps=float(assumptions["hedge_delay_cost_bps"]),
            partial_fill_cost_bps=float(assumptions["partial_fill_cost_bps"]),
            funding_reconciliation_buffer_bps=float(
                assumptions["funding_reconciliation_buffer_bps"]
            ),
            operational_buffer_bps=float(assumptions["operational_buffer_bps"]),
            assumed_rebalance_count=max(1, int(assumptions["rebalance_count"])),
        )
        profiles[(profile.scenario_code, profile.symbol, profile.notional_band)] = profile
    if len(profiles) != 27:
        raise RuntimeError(f"expected 27 Mission 88 cost profiles, found {len(profiles)}")
    return profiles


def split_bounds(contract: Mapping[str, Any], split_name: str) -> tuple[int, int]:
    if split_name not in {"development", "validation"}:
        raise ValueError("Mission 89 may read development and validation only")
    rows = {
        str(item["name"]): item
        for item in contract["research_splits"]
    }
    split = rows[split_name]
    start_ms = parse_utc_ms(str(split["start"]))
    end_ms = parse_utc_ms(str(split["end_exclusive"]))
    holdout_start_ms = parse_utc_ms(str(rows["untouched_holdout"]["start"]))
    if end_ms > holdout_start_ms:
        raise RuntimeError("Mission 89 split overlaps the untouched holdout")
    return start_ms, end_ms


def load_split_data(
    conn: sqlite3.Connection,
    contract: Mapping[str, Any],
    split_name: str,
) -> tuple[dict[str, SymbolData], dict[str, Any]]:
    start_ms, end_ms = split_bounds(contract, split_name)
    holdout_start_ms = split_bounds(contract, "validation")[1]
    if end_ms > holdout_start_ms:
        raise RuntimeError("holdout access blocked")
    result: dict[str, SymbolData] = {}
    total_rows = 0
    maximum_timestamp = 0
    for symbol in SYMBOLS:
        stream_maps: dict[str, dict[int, float]] = {}
        for stream in ("spot_ohlcv", "perpetual_ohlcv", "mark_price_ohlcv"):
            rows = conn.execute(
                """
                SELECT open_time_ms, open_price
                FROM mission86_market_bars
                WHERE contract_hash = ?
                  AND stream = ?
                  AND symbol = ?
                  AND interval = ?
                  AND open_time_ms >= ?
                  AND open_time_ms < ?
                ORDER BY open_time_ms
                """,
                (
                    EXPECTED_CONTRACT_HASH,
                    stream,
                    symbol,
                    CANONICAL_INTERVAL,
                    start_ms,
                    end_ms,
                ),
            ).fetchall()
            mapping = {int(row[0]): float(row[1]) for row in rows}
            stream_maps[stream] = mapping
            total_rows += len(rows)
            if rows:
                maximum_timestamp = max(maximum_timestamp, int(rows[-1][0]))
        funding_rows = conn.execute(
            """
            SELECT funding_time_ms, funding_rate, mark_price
            FROM mission86_funding_rates
            WHERE contract_hash = ?
              AND symbol = ?
              AND funding_time_ms >= ?
              AND funding_time_ms < ?
            ORDER BY funding_time_ms
            """,
            (EXPECTED_CONTRACT_HASH, symbol, start_ms, end_ms),
        ).fetchall()
        funding_by_hour: dict[int, dict[str, float | int]] = {}
        for row in funding_rows:
            actual_time = int(row[0])
            slot = nearest_hour(actual_time)
            funding_by_hour[slot] = {
                "actual_time_ms": actual_time,
                "funding_rate": float(row[1]),
                "mark_price": float(row[2]) if row[2] is not None else 0.0,
            }
            maximum_timestamp = max(maximum_timestamp, actual_time)
        total_rows += len(funding_rows)
        hour_set = (
            set(stream_maps["spot_ohlcv"])
            & set(stream_maps["perpetual_ohlcv"])
            & set(stream_maps["mark_price_ohlcv"])
        )
        expected_hours = set(range(start_ms, end_ms, HOUR_MS))
        if hour_set != expected_hours:
            raise RuntimeError(
                f"certified hourly data unexpectedly incomplete for {split_name}/{symbol}"
            )
        result[symbol] = SymbolData(
            symbol=symbol,
            start_ms=start_ms,
            end_ms=end_ms,
            hours=sorted(hour_set),
            spot_open=stream_maps["spot_ohlcv"],
            perpetual_open=stream_maps["perpetual_ohlcv"],
            mark_open=stream_maps["mark_price_ohlcv"],
            funding_by_hour=funding_by_hour,
        )
    if maximum_timestamp >= holdout_start_ms:
        raise RuntimeError("Mission 89 read a timestamp inside the untouched holdout")
    return result, {
        "split_name": split_name,
        "row_count": total_rows,
        "maximum_timestamp_read_ms": maximum_timestamp,
        "holdout_rows_read": 0,
    }


def compute_volatility_thresholds(
    development_data: Mapping[str, SymbolData],
) -> dict[str, tuple[float, float]]:
    thresholds: dict[str, tuple[float, float]] = {}
    for symbol, data in development_data.items():
        returns: deque[float] = deque(maxlen=24)
        vol_values: list[float] = []
        previous: float | None = None
        for hour in data.hours:
            price = data.spot_open[hour]
            if previous is not None and previous > 0 and price > 0:
                returns.append(math.log(price / previous))
            previous = price
            if len(returns) == 24:
                vol_values.append(statistics.pstdev(returns))
        if not vol_values:
            thresholds[symbol] = (0.0, 0.0)
        else:
            thresholds[symbol] = (
                quantile(vol_values, 1 / 3),
                quantile(vol_values, 2 / 3),
            )
    return thresholds


def assign_volatility_regimes(
    data_by_symbol: Mapping[str, SymbolData],
    thresholds: Mapping[str, tuple[float, float]],
) -> None:
    for symbol, data in data_by_symbol.items():
        low_threshold, high_threshold = thresholds[symbol]
        returns: deque[float] = deque(maxlen=24)
        previous: float | None = None
        regimes: dict[int, str] = {}
        for hour in data.hours:
            price = data.spot_open[hour]
            if previous is not None and previous > 0 and price > 0:
                returns.append(math.log(price / previous))
            previous = price
            if len(returns) < 24:
                regimes[hour] = "WARMUP"
                continue
            value = statistics.pstdev(returns)
            if value <= low_threshold:
                regimes[hour] = "LOW_VOLATILITY"
            elif value <= high_threshold:
                regimes[hour] = "MEDIUM_VOLATILITY"
            else:
                regimes[hour] = "HIGH_VOLATILITY"
        data.volatility_regime_by_hour = regimes


def basis_bps(data: SymbolData, hour: int, funding_event: Mapping[str, Any] | None = None) -> float:
    spot = data.spot_open[hour]
    if funding_event is not None and float(funding_event.get("mark_price", 0.0)) > 0:
        mark = float(funding_event["mark_price"])
    else:
        mark = data.mark_open[hour]
    return 10000.0 * (mark / spot - 1.0)


def funding_only_feasibility(
    data_by_symbol: Mapping[str, SymbolData],
    variant: Variant,
    cost_profiles: Mapping[tuple[str, str, str], CostProfile],
) -> dict[str, Any]:
    per_symbol: dict[str, dict[str, Any]] = {}
    feasible_count = 0
    lookback_count = 3
    maximum_settlements = variant.maximum_holding_days * FUNDING_SETTLEMENTS_PER_DAY
    for symbol, data in data_by_symbol.items():
        events = [
            (hour, data.funding_by_hour[hour])
            for hour in sorted(data.funding_by_hour)
        ]
        rates_bps = [float(event[1]["funding_rate"]) * 10000.0 for event in events]
        optimistic_max = -math.inf
        eligible_signal_count = 0
        for index in range(lookback_count - 1, len(events)):
            trailing = statistics.fmean(rates_bps[index - lookback_count + 1 : index + 1])
            hour, event = events[index]
            signal_basis = basis_bps(data, hour, event)
            if trailing < variant.minimum_trailing_funding_rate_bps:
                continue
            if abs(signal_basis) > variant.maximum_absolute_entry_basis_bps:
                continue
            eligible_signal_count += 1
            future_rates = rates_bps[index + 1 : index + 1 + maximum_settlements]
            running_funding = 0.0
            optimistic_funding = 0.0
            for future_rate in future_rates:
                running_funding += future_rate
                optimistic_funding = max(optimistic_funding, running_funding)
            optimistic_basis = max(0.0, signal_basis)
            optimistic_max = max(optimistic_max, optimistic_funding + optimistic_basis)
        if optimistic_max == -math.inf:
            optimistic_max = 0.0
        profile = cost_profiles[(PROMOTION_SCENARIO, symbol, PRIMARY_NOTIONAL_BAND)]
        break_even = (
            profile.entry_cost_bps
            + profile.exit_cost_bps
            + profile.modeled_rebalance_cost_bps
            + profile.hedge_delay_cost_bps
            + profile.partial_fill_cost_bps
            + profile.funding_reconciliation_buffer_bps
            + profile.operational_buffer_bps
        )
        feasible = optimistic_max >= break_even
        feasible_count += int(feasible)
        per_symbol[symbol] = {
            "eligible_signal_count": eligible_signal_count,
            "optimistic_max_gross_carry_bps": optimistic_max,
            "conservative_break_even_bps": break_even,
            "feasible": feasible,
        }
    return {
        "feasible_symbol_count": feasible_count,
        "minimum_required_feasible_symbols": 2,
        "status": "FEASIBLE" if feasible_count >= 2 else "ECONOMICALLY_IMPLAUSIBLE",
        "per_symbol": per_symbol,
    }


def position_mark_to_market(
    position: PositionState,
    spot_price: float,
    perpetual_price: float,
    profile: CostProfile,
) -> float:
    spot_unrealized = position.spot_qty * (spot_price - position.spot_entry_price)
    perpetual_unrealized = position.perpetual_qty * (
        position.perpetual_average_entry_price - perpetual_price
    )
    notional = profile.per_leg_notional_usd
    future_exit_cost = notional * profile.exit_cost_bps / 10000.0
    minimum_rebalance_cost = (
        notional * profile.modeled_rebalance_cost_bps / 10000.0
    )
    remaining_rebalance_cost = max(
        0.0, minimum_rebalance_cost - position.rebalance_cost_usd_paid
    )
    future_reconciliation_cost = (
        notional * profile.funding_reconciliation_buffer_bps / 10000.0
    )
    future_operational_cost = (
        notional * profile.operational_buffer_bps / 10000.0
    )
    return (
        spot_unrealized
        + perpetual_unrealized
        + position.realized_perpetual_pnl_usd
        + position.funding_pnl_usd
        - position.entry_cost_usd
        - position.hedge_delay_cost_usd
        - position.partial_fill_cost_usd
        - position.rebalance_cost_usd_paid
        - remaining_rebalance_cost
        - future_exit_cost
        - future_reconciliation_cost
        - future_operational_cost
    )


def close_position(
    position: PositionState,
    data: SymbolData,
    profile: CostProfile,
    exit_time_ms: int,
    exit_reason: str,
    trade_number: int,
) -> dict[str, Any]:
    spot_exit = data.spot_open[exit_time_ms]
    perpetual_exit = data.perpetual_open[exit_time_ms]
    notional = profile.per_leg_notional_usd
    spot_pnl = position.spot_qty * (spot_exit - position.spot_entry_price)
    perpetual_pnl = (
        position.realized_perpetual_pnl_usd
        + position.perpetual_qty
        * (position.perpetual_average_entry_price - perpetual_exit)
    )
    exit_cost = notional * profile.exit_cost_bps / 10000.0
    unit_rebalance_bps = (
        profile.modeled_rebalance_cost_bps / profile.assumed_rebalance_count
    )
    required_rebalance_bps = max(
        profile.modeled_rebalance_cost_bps,
        position.rebalance_count * unit_rebalance_bps,
    )
    required_rebalance_cost = notional * required_rebalance_bps / 10000.0
    rebalance_top_up = max(
        0.0,
        required_rebalance_cost - position.rebalance_cost_usd_paid,
    )
    total_rebalance_cost = position.rebalance_cost_usd_paid + rebalance_top_up
    funding_reconciliation_cost = (
        notional * profile.funding_reconciliation_buffer_bps / 10000.0
    )
    operational_cost = notional * profile.operational_buffer_bps / 10000.0
    gross_pnl = spot_pnl + perpetual_pnl + position.funding_pnl_usd
    total_cost = (
        position.entry_cost_usd
        + exit_cost
        + total_rebalance_cost
        + position.hedge_delay_cost_usd
        + position.partial_fill_cost_usd
        + funding_reconciliation_cost
        + operational_cost
    )
    net_pnl = gross_pnl - total_cost
    capital = notional * 2.0
    return {
        "trade_id": f"{position.symbol}-{trade_number:05d}",
        "symbol": position.symbol,
        "entry_decision_time_ms": position.entry_decision_time_ms,
        "entry_time_ms": position.entry_time_ms,
        "exit_time_ms": exit_time_ms,
        "entry_reason": position.entry_reason,
        "exit_reason": exit_reason,
        "entry_trailing_funding_bps": position.entry_trailing_funding_bps,
        "entry_basis_bps": position.entry_basis_bps,
        "entry_volatility_regime": position.entry_volatility_regime,
        "spot_entry_price": position.spot_entry_price,
        "spot_exit_price": spot_exit,
        "perpetual_entry_price": position.perpetual_average_entry_price,
        "perpetual_exit_price": perpetual_exit,
        "spot_pnl_usd": spot_pnl,
        "perpetual_pnl_usd": perpetual_pnl,
        "funding_pnl_usd": position.funding_pnl_usd,
        "entry_cost_usd": position.entry_cost_usd,
        "exit_cost_usd": exit_cost,
        "rebalance_cost_usd": total_rebalance_cost,
        "hedge_delay_cost_usd": position.hedge_delay_cost_usd,
        "partial_fill_cost_usd": position.partial_fill_cost_usd,
        "funding_reconciliation_cost_usd": funding_reconciliation_cost,
        "operational_cost_usd": operational_cost,
        "gross_pnl_usd": gross_pnl,
        "net_pnl_usd": net_pnl,
        "capital_employed_usd": capital,
        "return_on_total_capital_pct": 100.0 * safe_ratio(net_pnl, capital),
        "funding_settlement_count": position.funding_settlement_count,
        "rebalance_count": position.rebalance_count,
        "holding_hours": (exit_time_ms - position.entry_time_ms) / HOUR_MS,
        "quarter": quarter_label(exit_time_ms),
    }


def execute_rebalance(
    position: PositionState,
    data: SymbolData,
    profile: CostProfile,
    hour: int,
) -> None:
    spot_price = data.spot_open[hour]
    perpetual_price = data.perpetual_open[hour]
    target_perpetual_qty = position.spot_qty * spot_price / perpetual_price
    delta = target_perpetual_qty - position.perpetual_qty
    if abs(delta) < 1e-15:
        return
    if delta > 0:
        new_qty = position.perpetual_qty + delta
        position.perpetual_average_entry_price = (
            position.perpetual_qty * position.perpetual_average_entry_price
            + delta * perpetual_price
        ) / new_qty
        position.perpetual_qty = new_qty
    else:
        quantity_reduced = min(position.perpetual_qty, abs(delta))
        position.realized_perpetual_pnl_usd += quantity_reduced * (
            position.perpetual_average_entry_price - perpetual_price
        )
        position.perpetual_qty -= quantity_reduced
    unit_bps = profile.modeled_rebalance_cost_bps / profile.assumed_rebalance_count
    position.rebalance_cost_usd_paid += (
        profile.per_leg_notional_usd * unit_bps / 10000.0
    )
    position.rebalance_count += 1


def simulate_symbol(
    data: SymbolData,
    variant: Variant,
    profile: CostProfile,
    funding_lookback_settlements: int,
    exit_after_nonpositive_settlements: int,
    emergency_exit_basis_bps: float,
    rebalance_delta_drift_pct: float,
) -> dict[str, Any]:
    trailing_rates: deque[float] = deque(maxlen=funding_lookback_settlements)
    position: PositionState | None = None
    pending: PendingAction | None = None
    trades: list[dict[str, Any]] = []
    equity_by_hour: dict[int, float] = {}
    cumulative_closed_pnl = 0.0
    trade_number = 0
    last_hour = data.hours[-1]

    for hour in data.hours:
        spot_price = data.spot_open[hour]
        perpetual_price = data.perpetual_open[hour]

        if pending is not None and pending.execution_time_ms == hour:
            if pending.action == "ENTRY" and position is None:
                notional = profile.per_leg_notional_usd
                position = PositionState(
                    symbol=data.symbol,
                    entry_decision_time_ms=pending.decision_time_ms,
                    entry_time_ms=hour,
                    entry_reason=pending.reason,
                    entry_trailing_funding_bps=float(
                        pending.metadata["trailing_funding_bps"]
                    ),
                    entry_basis_bps=float(pending.metadata["basis_bps"]),
                    entry_volatility_regime=str(
                        pending.metadata["volatility_regime"]
                    ),
                    spot_entry_price=spot_price,
                    spot_qty=notional / spot_price,
                    perpetual_average_entry_price=perpetual_price,
                    perpetual_qty=notional / perpetual_price,
                    entry_cost_usd=notional * profile.entry_cost_bps / 10000.0,
                    hedge_delay_cost_usd=(
                        notional * profile.hedge_delay_cost_bps / 10000.0
                    ),
                    partial_fill_cost_usd=(
                        notional * profile.partial_fill_cost_bps / 10000.0
                    ),
                )
                pending = None
            elif pending.action == "EXIT" and position is not None:
                trade_number += 1
                trade = close_position(
                    position,
                    data,
                    profile,
                    hour,
                    pending.reason,
                    trade_number,
                )
                trades.append(trade)
                cumulative_closed_pnl += float(trade["net_pnl_usd"])
                position = None
                pending = None
            elif pending.action == "REBALANCE" and position is not None:
                execute_rebalance(position, data, profile, hour)
                pending = None
            else:
                pending = None

        funding_event = data.funding_by_hour.get(hour)
        if funding_event is not None:
            actual_time = int(funding_event["actual_time_ms"])
            rate = float(funding_event["funding_rate"])
            rate_bps = rate * 10000.0
            trailing_rates.append(rate_bps)
            if position is not None and position.entry_time_ms < actual_time:
                mark = float(funding_event["mark_price"])
                if mark <= 0:
                    mark = data.mark_open[hour]
                position.funding_pnl_usd += position.perpetual_qty * mark * rate
                position.funding_settlement_count += 1
                if rate <= 0:
                    position.nonpositive_funding_streak += 1
                else:
                    position.nonpositive_funding_streak = 0

        if position is not None and pending is None:
            current_basis = basis_bps(data, hour, funding_event)
            holding_ms = hour - position.entry_time_ms
            exit_reason: str | None = None
            if abs(current_basis) >= emergency_exit_basis_bps:
                exit_reason = "EMERGENCY_BASIS_LIMIT"
            elif holding_ms >= variant.maximum_holding_days * 24 * HOUR_MS:
                exit_reason = "MAXIMUM_HOLDING_PERIOD"
            elif (
                funding_event is not None
                and position.nonpositive_funding_streak
                >= exit_after_nonpositive_settlements
            ):
                exit_reason = "NONPOSITIVE_FUNDING_STREAK"
            if exit_reason is not None:
                execution_time = strictly_next_hour(hour)
                if execution_time < data.end_ms:
                    pending = PendingAction(
                        action="EXIT",
                        execution_time_ms=execution_time,
                        reason=exit_reason,
                        decision_time_ms=hour,
                        metadata={},
                    )
            else:
                spot_notional = position.spot_qty * spot_price
                perpetual_notional = position.perpetual_qty * perpetual_price
                drift_pct = 100.0 * abs(spot_notional - perpetual_notional) / max(
                    profile.per_leg_notional_usd, 1e-12
                )
                if drift_pct >= rebalance_delta_drift_pct:
                    execution_time = strictly_next_hour(hour)
                    if execution_time < data.end_ms:
                        pending = PendingAction(
                            action="REBALANCE",
                            execution_time_ms=execution_time,
                            reason="DELTA_DRIFT_LIMIT",
                            decision_time_ms=hour,
                            metadata={"drift_pct": drift_pct},
                        )

        if (
            position is None
            and pending is None
            and funding_event is not None
            and len(trailing_rates) == funding_lookback_settlements
        ):
            trailing_average = statistics.fmean(trailing_rates)
            current_basis = basis_bps(data, hour, funding_event)
            if (
                trailing_average >= variant.minimum_trailing_funding_rate_bps
                and abs(current_basis)
                <= variant.maximum_absolute_entry_basis_bps
            ):
                execution_time = strictly_next_hour(
                    int(funding_event["actual_time_ms"])
                )
                if execution_time < data.end_ms:
                    pending = PendingAction(
                        action="ENTRY",
                        execution_time_ms=execution_time,
                        reason="TRAILING_SETTLED_FUNDING_SIGNAL",
                        decision_time_ms=int(funding_event["actual_time_ms"]),
                        metadata={
                            "trailing_funding_bps": trailing_average,
                            "basis_bps": current_basis,
                            "volatility_regime": data.volatility_regime_by_hour.get(
                                hour, "UNCLASSIFIED"
                            ),
                        },
                    )

        if position is None:
            equity_by_hour[hour] = cumulative_closed_pnl
        else:
            equity_by_hour[hour] = cumulative_closed_pnl + position_mark_to_market(
                position,
                spot_price,
                perpetual_price,
                profile,
            )

    if position is not None:
        trade_number += 1
        trade = close_position(
            position,
            data,
            profile,
            last_hour,
            "FORCED_SPLIT_END_CLOSE",
            trade_number,
        )
        trades.append(trade)
        cumulative_closed_pnl += float(trade["net_pnl_usd"])
        equity_by_hour[last_hour] = cumulative_closed_pnl

    return {
        "symbol": data.symbol,
        "trades": trades,
        "equity_by_hour": equity_by_hour,
        "net_pnl_usd": cumulative_closed_pnl,
    }


def maximum_positive_contribution_pct(values: Mapping[str, float]) -> float:
    positive = [value for value in values.values() if value > 0]
    if not positive:
        return 100.0
    return 100.0 * max(positive) / sum(positive)


def sharpe_ratio(returns: Sequence[float]) -> float:
    if len(returns) < 2:
        return 0.0
    deviation = statistics.stdev(returns)
    if deviation <= 0:
        return 0.0
    return statistics.fmean(returns) / deviation * math.sqrt(len(returns))


def summarize_simulation(
    symbol_results: Sequence[Mapping[str, Any]],
    profile_notional: float,
    scenario_code: str,
    notional_band: str,
    split_name: str,
    variant: Variant,
    feasibility: Mapping[str, Any],
) -> dict[str, Any]:
    trades = [
        trade
        for result in symbol_results
        for trade in result["trades"]
    ]
    net_by_asset = {
        symbol: sum(
            float(trade["net_pnl_usd"])
            for trade in trades
            if trade["symbol"] == symbol
        )
        for symbol in SYMBOLS
    }
    net_by_quarter: dict[str, float] = {}
    net_by_regime: dict[str, float] = {}
    for trade in trades:
        net_by_quarter.setdefault(str(trade["quarter"]), 0.0)
        net_by_quarter[str(trade["quarter"])] += float(trade["net_pnl_usd"])
        regime = str(trade["entry_volatility_regime"])
        net_by_regime.setdefault(regime, 0.0)
        net_by_regime[regime] += float(trade["net_pnl_usd"])

    all_hours = sorted(
        set().union(
            *(set(result["equity_by_hour"]) for result in symbol_results)
        )
    )
    aggregate_equity: list[float] = []
    for hour in all_hours:
        aggregate_equity.append(
            sum(float(result["equity_by_hour"].get(hour, 0.0)) for result in symbol_results)
        )
    peak = 0.0
    maximum_drawdown_usd = 0.0
    for equity in aggregate_equity:
        peak = max(peak, equity)
        maximum_drawdown_usd = max(maximum_drawdown_usd, peak - equity)

    portfolio_capital = profile_notional * 2.0 * len(SYMBOLS)
    total_net = sum(float(trade["net_pnl_usd"]) for trade in trades)
    gross = sum(float(trade["gross_pnl_usd"]) for trade in trades)
    trade_returns = [
        float(trade["net_pnl_usd"]) / float(trade["capital_employed_usd"])
        for trade in trades
    ]
    positive_asset_count = sum(value > 0 for value in net_by_asset.values())
    active_regimes = {
        key: value
        for key, value in net_by_regime.items()
        if key not in {"WARMUP", "UNCLASSIFIED"}
        and any(
            trade["entry_volatility_regime"] == key
            for trade in trades
        )
    }

    component_fields = (
        "spot_pnl_usd",
        "perpetual_pnl_usd",
        "funding_pnl_usd",
        "entry_cost_usd",
        "exit_cost_usd",
        "rebalance_cost_usd",
        "hedge_delay_cost_usd",
        "partial_fill_cost_usd",
        "funding_reconciliation_cost_usd",
        "operational_cost_usd",
    )
    cashflow_totals = {
        field: sum(float(trade[field]) for trade in trades)
        for field in component_fields
    }

    return {
        "split_name": split_name,
        "variant": variant_dict(variant),
        "scenario_code": scenario_code,
        "notional_band": notional_band,
        "per_leg_notional_usd": profile_notional,
        "fully_collateralized_portfolio_capital_usd": portfolio_capital,
        "feasibility": feasibility,
        "closed_position_count": len(trades),
        "gross_pnl_usd": gross,
        "net_pnl_usd": total_net,
        "total_capital_return_pct": 100.0 * safe_ratio(total_net, portfolio_capital),
        "pair_notional_return_pct": 100.0 * safe_ratio(total_net, profile_notional),
        "maximum_drawdown_pct": 100.0 * safe_ratio(
            maximum_drawdown_usd, portfolio_capital
        ),
        "positive_asset_count": positive_asset_count,
        "maximum_asset_contribution_pct": maximum_positive_contribution_pct(
            net_by_asset
        ),
        "maximum_quarter_contribution_pct": maximum_positive_contribution_pct(
            net_by_quarter
        ),
        "active_regime_count": len(active_regimes),
        "maximum_regime_contribution_pct": maximum_positive_contribution_pct(
            active_regimes
        ),
        "net_pnl_by_asset": net_by_asset,
        "net_pnl_by_quarter": net_by_quarter,
        "net_pnl_by_volatility_regime": net_by_regime,
        "cashflow_totals": cashflow_totals,
        "trade_returns": trade_returns,
        "sharpe_ratio": sharpe_ratio(trade_returns),
        "trades": trades,
    }


def simulate_variant(
    data_by_symbol: Mapping[str, SymbolData],
    variant: Variant,
    profiles: Mapping[tuple[str, str, str], CostProfile],
    scenario_code: str,
    notional_band: str,
    split_name: str,
    contract: Mapping[str, Any],
    feasibility: Mapping[str, Any],
) -> dict[str, Any]:
    rules = contract["strategy_rules"]
    signal = contract["observable_signal_contract"]
    symbol_results = []
    for symbol in SYMBOLS:
        profile = profiles[(scenario_code, symbol, notional_band)]
        symbol_results.append(
            simulate_symbol(
                data=data_by_symbol[symbol],
                variant=variant,
                profile=profile,
                funding_lookback_settlements=int(
                    signal["funding_lookback_settlements"]
                ),
                exit_after_nonpositive_settlements=int(
                    rules["exit_after_nonpositive_funding_settlements"]
                ),
                emergency_exit_basis_bps=float(
                    rules["emergency_exit_absolute_basis_bps"]
                ),
                rebalance_delta_drift_pct=float(
                    rules["rebalance_delta_drift_pct"]
                ),
            )
        )
    notional = profiles[(scenario_code, SYMBOLS[0], notional_band)].per_leg_notional_usd
    return summarize_simulation(
        symbol_results=symbol_results,
        profile_notional=notional,
        scenario_code=scenario_code,
        notional_band=notional_band,
        split_name=split_name,
        variant=variant,
        feasibility=feasibility,
    )


def parameter_neighbors(selected: Variant, variants: Sequence[Variant]) -> list[str]:
    funding_values = sorted({v.minimum_trailing_funding_rate_bps for v in variants})
    basis_values = sorted({v.maximum_absolute_entry_basis_bps for v in variants})
    holding_values = sorted({v.maximum_holding_days for v in variants})

    def adjacent(value: float | int, values: Sequence[float | int]) -> set[float | int]:
        index = list(values).index(value)
        output: set[float | int] = set()
        if index > 0:
            output.add(values[index - 1])
        if index + 1 < len(values):
            output.add(values[index + 1])
        return output

    ids: list[str] = []
    for candidate in variants:
        differences = 0
        valid = True
        pairs = (
            (
                selected.minimum_trailing_funding_rate_bps,
                candidate.minimum_trailing_funding_rate_bps,
                funding_values,
            ),
            (
                selected.maximum_absolute_entry_basis_bps,
                candidate.maximum_absolute_entry_basis_bps,
                basis_values,
            ),
            (
                selected.maximum_holding_days,
                candidate.maximum_holding_days,
                holding_values,
            ),
        )
        for selected_value, candidate_value, values in pairs:
            if candidate_value == selected_value:
                continue
            differences += 1
            if candidate_value not in adjacent(selected_value, values):
                valid = False
        if valid and differences == 1:
            ids.append(candidate.variant_id)
    return sorted(ids)


def calculate_pbo(
    development_results: Mapping[str, Mapping[str, Any]],
) -> float:
    variant_ids = sorted(development_results)
    quarters = sorted(
        set().union(
            *(
                set(result["net_pnl_by_quarter"])
                for result in development_results.values()
            )
        )
    )
    if len(variant_ids) < 2 or len(quarters) < 4:
        return 1.0
    half = len(quarters) // 2
    if half == 0:
        return 1.0
    failures = 0
    combinations = 0
    for in_sample in itertools.combinations(quarters, half):
        in_sample_set = set(in_sample)
        out_sample = [quarter for quarter in quarters if quarter not in in_sample_set]
        in_scores = {
            variant_id: sum(
                float(development_results[variant_id]["net_pnl_by_quarter"].get(q, 0.0))
                for q in in_sample
            )
            for variant_id in variant_ids
        }
        selected = max(variant_ids, key=lambda item: (in_scores[item], item))
        out_scores = {
            variant_id: sum(
                float(development_results[variant_id]["net_pnl_by_quarter"].get(q, 0.0))
                for q in out_sample
            )
            for variant_id in variant_ids
        }
        ranked = sorted(variant_ids, key=lambda item: (out_scores[item], item))
        percentile = (ranked.index(selected) + 1) / len(ranked)
        failures += int(percentile <= 0.5)
        combinations += 1
    return failures / combinations if combinations else 1.0


def sample_skewness(values: Sequence[float]) -> float:
    if len(values) < 3:
        return 0.0
    mean = statistics.fmean(values)
    std = statistics.stdev(values)
    if std == 0:
        return 0.0
    n = len(values)
    return n / ((n - 1) * (n - 2)) * sum(((x - mean) / std) ** 3 for x in values)


def sample_kurtosis(values: Sequence[float]) -> float:
    if len(values) < 4:
        return 3.0
    mean = statistics.fmean(values)
    std = statistics.stdev(values)
    if std == 0:
        return 3.0
    n = len(values)
    term1 = (
        n * (n + 1)
        / ((n - 1) * (n - 2) * (n - 3))
        * sum(((x - mean) / std) ** 4 for x in values)
    )
    term2 = 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))
    return term1 - term2 + 3.0


def deflated_sharpe_probability(
    validation_trade_returns: Sequence[float],
    development_sharpes: Sequence[float],
    trial_count: int,
) -> float:
    n = len(validation_trade_returns)
    if n < 3:
        return 0.0
    observed = sharpe_ratio(validation_trade_returns)
    if trial_count <= 1:
        benchmark = 0.0
    else:
        dispersion = (
            statistics.stdev(development_sharpes)
            if len(development_sharpes) >= 2
            else 0.0
        )
        if dispersion <= 0:
            benchmark = 0.0
        else:
            normal = NormalDist()
            gamma = 0.5772156649015329
            z1 = normal.inv_cdf(1.0 - 1.0 / trial_count)
            z2 = normal.inv_cdf(1.0 - 1.0 / (trial_count * math.e))
            benchmark = dispersion * ((1.0 - gamma) * z1 + gamma * z2)
    skew = sample_skewness(validation_trade_returns)
    kurtosis = sample_kurtosis(validation_trade_returns)
    denominator_term = (
        1.0
        - skew * observed
        + ((kurtosis - 1.0) / 4.0) * observed * observed
    )
    if denominator_term <= 0:
        return 0.0
    z_score = (
        (observed - benchmark)
        * math.sqrt(n - 1)
        / math.sqrt(denominator_term)
    )
    return NormalDist().cdf(z_score)


def gate(
    name: str,
    passed: bool,
    observed: Any,
    required: Any,
    reason: str,
    mandatory: bool = True,
) -> dict[str, Any]:
    return {
        "gate_name": name,
        "gate_status": CHECK_PASS if passed else CHECK_FAIL,
        "observed_value": observed,
        "required_value": required,
        "mandatory": mandatory,
        "gate_reason": reason,
    }


def choose_development_candidate(
    variants: Sequence[Variant],
    feasibility: Mapping[str, Mapping[str, Any]],
    development_primary_conservative: Mapping[str, Mapping[str, Any]],
    rejection: Mapping[str, Any],
) -> tuple[Variant | None, list[str]]:
    eligible: list[Variant] = []
    for variant in variants:
        result = development_primary_conservative[variant.variant_id]
        if feasibility[variant.variant_id]["feasible_symbol_count"] < 2:
            continue
        if result["net_pnl_usd"] <= 0:
            continue
        if result["closed_position_count"] < 12:
            continue
        if result["positive_asset_count"] < int(rejection["minimum_positive_asset_count"]):
            continue
        if result["maximum_asset_contribution_pct"] > float(
            rejection["maximum_single_asset_pnl_contribution_pct"]
        ):
            continue
        if result["maximum_quarter_contribution_pct"] > float(
            rejection["maximum_single_quarter_pnl_contribution_pct"]
        ):
            continue
        if result["maximum_drawdown_pct"] > float(
            rejection["maximum_strategy_drawdown_pct"]
        ):
            continue
        eligible.append(variant)
    ordered = sorted(
        eligible,
        key=lambda variant: (
            -float(
                development_primary_conservative[variant.variant_id][
                    "total_capital_return_pct"
                ]
            ),
            float(
                development_primary_conservative[variant.variant_id][
                    "maximum_drawdown_pct"
                ]
            ),
            variant.variant_id,
        ),
    )
    return (ordered[0] if ordered else None), [variant.variant_id for variant in ordered]


def build_validation_gates(
    selected: Variant,
    validation_results: Mapping[tuple[str, str], Mapping[str, Any]],
    all_validation_primary_conservative: Mapping[str, Mapping[str, Any]],
    variants: Sequence[Variant],
    pbo: float,
    dsr_probability: float,
    protocol: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    thresholds = protocol["mandatory_validation_gates"]
    normal = validation_results[(PRIMARY_SCENARIO, PRIMARY_NOTIONAL_BAND)]
    conservative = validation_results[(PROMOTION_SCENARIO, PRIMARY_NOTIONAL_BAND)]
    severe = validation_results[(DIAGNOSTIC_SCENARIO, PRIMARY_NOTIONAL_BAND)]
    neighbor_ids = parameter_neighbors(selected, variants)
    positive_neighbors = [
        variant_id
        for variant_id in neighbor_ids
        if all_validation_primary_conservative[variant_id]["net_pnl_usd"] > 0
    ]
    neighbor_fraction = safe_ratio(len(positive_neighbors), len(neighbor_ids))
    gates = [
        gate(
            "NORMAL_NET_PNL_POSITIVE",
            normal["net_pnl_usd"] > 0,
            normal["net_pnl_usd"],
            "> 0",
            "Base-case validation must remain positive.",
        ),
        gate(
            "CONSERVATIVE_NET_PNL_POSITIVE",
            conservative["net_pnl_usd"] > 0,
            conservative["net_pnl_usd"],
            "> 0",
            "Conservative costs are the mandatory promotion gate.",
        ),
        gate(
            "MINIMUM_CLOSED_POSITIONS",
            conservative["closed_position_count"]
            >= int(thresholds["minimum_closed_positions"]),
            conservative["closed_position_count"],
            thresholds["minimum_closed_positions"],
            "Validation needs enough closed positions for a decision.",
        ),
        gate(
            "MINIMUM_POSITIVE_ASSETS",
            conservative["positive_asset_count"]
            >= int(thresholds["minimum_positive_asset_count"]),
            conservative["positive_asset_count"],
            thresholds["minimum_positive_asset_count"],
            "The result cannot depend on only one asset.",
        ),
        gate(
            "ASSET_CONCENTRATION",
            conservative["maximum_asset_contribution_pct"]
            <= float(
                thresholds[
                    "maximum_single_asset_positive_pnl_contribution_pct"
                ]
            ),
            conservative["maximum_asset_contribution_pct"],
            thresholds[
                "maximum_single_asset_positive_pnl_contribution_pct"
            ],
            "Positive PnL concentration must remain bounded.",
        ),
        gate(
            "QUARTER_CONCENTRATION",
            conservative["maximum_quarter_contribution_pct"]
            <= float(
                thresholds[
                    "maximum_single_quarter_positive_pnl_contribution_pct"
                ]
            ),
            conservative["maximum_quarter_contribution_pct"],
            thresholds[
                "maximum_single_quarter_positive_pnl_contribution_pct"
            ],
            "One quarter cannot explain the result.",
        ),
        gate(
            "MAXIMUM_DRAWDOWN",
            conservative["maximum_drawdown_pct"]
            <= float(thresholds["maximum_realized_and_marked_drawdown_pct"]),
            conservative["maximum_drawdown_pct"],
            thresholds["maximum_realized_and_marked_drawdown_pct"],
            "Marked portfolio drawdown must remain within the charter limit.",
        ),
        gate(
            "VOLATILITY_REGIME_COVERAGE",
            conservative["active_regime_count"]
            >= int(thresholds["minimum_active_volatility_regime_count"]),
            conservative["active_regime_count"],
            thresholds["minimum_active_volatility_regime_count"],
            "The candidate must be observed in more than one volatility regime.",
        ),
        gate(
            "VOLATILITY_REGIME_CONCENTRATION",
            conservative["maximum_regime_contribution_pct"]
            <= float(
                thresholds[
                    "maximum_single_regime_positive_pnl_contribution_pct"
                ]
            ),
            conservative["maximum_regime_contribution_pct"],
            thresholds["maximum_single_regime_positive_pnl_contribution_pct"],
            "Positive PnL cannot come almost entirely from one volatility regime.",
        ),
        gate(
            "PARAMETER_NEIGHBOR_COUNT",
            len(neighbor_ids) >= int(thresholds["minimum_parameter_neighbor_count"]),
            len(neighbor_ids),
            thresholds["minimum_parameter_neighbor_count"],
            "The selected point must have enough immediate preregistered neighbors.",
        ),
        gate(
            "PARAMETER_NEIGHBOR_STABILITY",
            neighbor_fraction
            >= float(thresholds["minimum_positive_neighbor_fraction"]),
            neighbor_fraction,
            thresholds["minimum_positive_neighbor_fraction"],
            "The selected result cannot be an isolated parameter spike.",
        ),
        gate(
            "PROBABILITY_OF_BACKTEST_OVERFITTING",
            pbo
            <= float(thresholds["maximum_probability_of_backtest_overfitting"]),
            pbo,
            thresholds["maximum_probability_of_backtest_overfitting"],
            "Combinatorial development-quarter PBO must remain bounded.",
        ),
        gate(
            "DEFLATED_SHARPE_PROBABILITY",
            dsr_probability
            >= float(thresholds["minimum_deflated_sharpe_probability"]),
            dsr_probability,
            thresholds["minimum_deflated_sharpe_probability"],
            "Validation Sharpe quality must survive multiple-testing deflation.",
        ),
        gate(
            "SEVERE_STRESS_DIAGNOSTIC",
            True,
            severe["net_pnl_usd"],
            "reported only",
            "Severe stress is diagnostic and is not a mandatory profitability gate.",
            mandatory=False,
        ),
    ]
    return gates, {
        "neighbor_ids": neighbor_ids,
        "positive_neighbor_ids": positive_neighbors,
        "positive_neighbor_fraction": neighbor_fraction,
        "severe_stress_net_pnl_usd": severe["net_pnl_usd"],
    }


def determine_decision(
    selected: Variant | None,
    gates: Sequence[Mapping[str, Any]],
    validation_closed_positions: int,
    dsr_sample_size: int,
    protocol: Mapping[str, Any],
) -> tuple[str, str, str]:
    if selected is None:
        return (
            DECISION_REJECT,
            MISSION90_NOT_AUTHORIZED,
            "NEW_ECONOMIC_HYPOTHESIS_CHARTER",
        )
    threshold = int(
        protocol["mandatory_validation_gates"]["minimum_closed_positions"]
    )
    if validation_closed_positions < threshold or dsr_sample_size < 3:
        return (
            DECISION_CONTINUE,
            MISSION90_PAUSED,
            "EXTEND_REAL_MARKET_EVIDENCE_WITHOUT_HOLDOUT_ACCESS",
        )
    failed = [
        item
        for item in gates
        if bool(item["mandatory"]) and item["gate_status"] != CHECK_PASS
    ]
    if failed:
        return (
            DECISION_REJECT,
            MISSION90_NOT_AUTHORIZED,
            "NEW_ECONOMIC_HYPOTHESIS_CHARTER",
        )
    return (
        DECISION_ADVANCE,
        MISSION90_READY,
        "MISSION90_SINGLE_USE_UNTOUCHED_HOLDOUT_DECISION",
    )


def write_report(
    path_value: str | Path,
    report_core: Mapping[str, Any],
    created_at: str,
) -> tuple[str, dict[str, Any]]:
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    hash_value = sha256_bytes(canonical_json(report_core).encode("utf-8"))
    envelope = {
        "report_hash_sha256": hash_value,
        "created_at": created_at,
        "report": report_core,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(envelope, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return hash_value, envelope


def strip_trades(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in result.items()
        if key not in {"trades", "trade_returns"}
    }


def persist_results(
    conn: sqlite3.Connection,
    *,
    run_label: str,
    protocol_envelope: Mapping[str, Any],
    created_at: str,
    summary: Mapping[str, Any],
    all_results: Mapping[tuple[str, str, str, str], Mapping[str, Any]],
    selected_trade_results: Sequence[Mapping[str, Any]],
    gates: Sequence[Mapping[str, Any]],
    report_path: str | Path,
    report_hash: str,
    report_envelope: Mapping[str, Any],
) -> None:
    protocol = protocol_envelope["protocol"]
    protocol_hash_value = protocol_envelope["protocol_hash_sha256"]
    conn.execute(
        """
        INSERT INTO mission89_protocols (
            protocol_id,
            protocol_hash,
            locked_at,
            protocol_json
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(protocol_id) DO UPDATE SET
            protocol_hash = excluded.protocol_hash,
            locked_at = excluded.locked_at,
            protocol_json = excluded.protocol_json
        """,
        (
            PROTOCOL_ID,
            protocol_hash_value,
            protocol_envelope["locked_at"],
            canonical_json(protocol_envelope),
        ),
    )
    for table in (
        "mission89_variant_results",
        "mission89_selected_trade_ledger",
        "mission89_gates",
    ):
        conn.execute(f"DELETE FROM {table} WHERE run_label = ?", (run_label,))
    conn.execute("DELETE FROM mission89_runs WHERE run_label = ?", (run_label,))
    conn.execute("DELETE FROM mission89_reports WHERE run_label = ?", (run_label,))

    for (split_name, variant_id, scenario_code, notional_band), result in all_results.items():
        conn.execute(
            """
            INSERT INTO mission89_variant_results (
                run_label,
                split_name,
                variant_id,
                scenario_code,
                notional_band,
                feasibility_status,
                closed_position_count,
                net_pnl_usd,
                total_capital_return_pct,
                pair_notional_return_pct,
                maximum_drawdown_pct,
                positive_asset_count,
                maximum_asset_contribution_pct,
                maximum_quarter_contribution_pct,
                active_regime_count,
                maximum_regime_contribution_pct,
                sharpe_ratio,
                result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_label,
                split_name,
                variant_id,
                scenario_code,
                notional_band,
                result["feasibility"]["status"],
                result["closed_position_count"],
                result["net_pnl_usd"],
                result["total_capital_return_pct"],
                result["pair_notional_return_pct"],
                result["maximum_drawdown_pct"],
                result["positive_asset_count"],
                result["maximum_asset_contribution_pct"],
                result["maximum_quarter_contribution_pct"],
                result["active_regime_count"],
                result["maximum_regime_contribution_pct"],
                result["sharpe_ratio"],
                canonical_json(strip_trades(result)),
            ),
        )

    for result in selected_trade_results:
        for trade in result["trades"]:
            conn.execute(
                """
                INSERT INTO mission89_selected_trade_ledger (
                    run_label,
                    split_name,
                    scenario_code,
                    notional_band,
                    trade_id,
                    symbol,
                    entry_time_ms,
                    exit_time_ms,
                    exit_reason,
                    spot_pnl_usd,
                    perpetual_pnl_usd,
                    funding_pnl_usd,
                    entry_cost_usd,
                    exit_cost_usd,
                    rebalance_cost_usd,
                    hedge_delay_cost_usd,
                    partial_fill_cost_usd,
                    funding_reconciliation_cost_usd,
                    operational_cost_usd,
                    gross_pnl_usd,
                    net_pnl_usd,
                    capital_employed_usd,
                    trade_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_label,
                    result["split_name"],
                    result["scenario_code"],
                    result["notional_band"],
                    trade["trade_id"],
                    trade["symbol"],
                    trade["entry_time_ms"],
                    trade["exit_time_ms"],
                    trade["exit_reason"],
                    trade["spot_pnl_usd"],
                    trade["perpetual_pnl_usd"],
                    trade["funding_pnl_usd"],
                    trade["entry_cost_usd"],
                    trade["exit_cost_usd"],
                    trade["rebalance_cost_usd"],
                    trade["hedge_delay_cost_usd"],
                    trade["partial_fill_cost_usd"],
                    trade["funding_reconciliation_cost_usd"],
                    trade["operational_cost_usd"],
                    trade["gross_pnl_usd"],
                    trade["net_pnl_usd"],
                    trade["capital_employed_usd"],
                    canonical_json(trade),
                ),
            )

    for index, item in enumerate(gates, start=1):
        conn.execute(
            """
            INSERT INTO mission89_gates (
                gate_id,
                run_label,
                gate_name,
                gate_status,
                observed_value,
                required_value,
                mandatory,
                gate_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{run_label}-{index:02d}-{item['gate_name'].lower()}",
                run_label,
                item["gate_name"],
                item["gate_status"],
                str(item["observed_value"]),
                str(item["required_value"]),
                int(bool(item["mandatory"])),
                item["gate_reason"],
            ),
        )

    conn.execute(
        """
        INSERT INTO mission89_reports (
            run_label,
            report_hash,
            report_path,
            created_at,
            report_json
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            run_label,
            report_hash,
            str(report_path),
            created_at,
            canonical_json(report_envelope),
        ),
    )
    conn.execute(
        """
        INSERT INTO mission89_runs (
            run_label,
            protocol_id,
            protocol_hash,
            contract_hash,
            source_certificate_hash,
            source_cost_model_hash,
            created_at,
            mission89_status,
            decision,
            selected_variant_id,
            development_candidate_count,
            development_variant_count,
            validation_closed_position_count,
            mandatory_gate_count,
            passed_mandatory_gate_count,
            failed_mandatory_gate_count,
            pbo,
            deflated_sharpe_probability,
            holdout_rows_read,
            maximum_timestamp_read_ms,
            backtesting_performed,
            profitability_claimed,
            mission90_status,
            next_workstream,
            live_trading,
            live_order_sent,
            capital_deployment,
            report_hash,
            summary_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_label,
            PROTOCOL_ID,
            protocol_hash_value,
            EXPECTED_CONTRACT_HASH,
            EXPECTED_SOURCE_CERTIFICATE_HASH,
            EXPECTED_SOURCE_COST_MODEL_HASH,
            created_at,
            MISSION89_STATUS,
            summary["decision"],
            summary["selected_variant_id"],
            summary["development_candidate_count"],
            summary["development_variant_count"],
            summary["validation_closed_position_count"],
            summary["mandatory_gate_count"],
            summary["passed_mandatory_gate_count"],
            summary["failed_mandatory_gate_count"],
            summary["pbo"],
            summary["deflated_sharpe_probability"],
            0,
            summary["maximum_timestamp_read_ms"],
            1,
            0,
            summary["mission90_status"],
            summary["next_workstream"],
            LIVE_TRADING,
            LIVE_ORDER_SENT,
            CAPITAL_DEPLOYMENT,
            report_hash,
            canonical_json(summary),
        ),
    )
    conn.commit()


def run_falsification(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    contract_path: str | Path = DEFAULT_CONTRACT_PATH,
    protocol_path: str | Path = DEFAULT_PROTOCOL_PATH,
    report_path: str | Path = DEFAULT_REPORT_PATH,
    run_label: str = "mission89-final-check",
    created_at: str | None = None,
) -> dict[str, Any]:
    created_at = created_at or utc_now()
    contract = load_authoritative_contract(contract_path)
    variants = create_variants(contract)
    if len(variants) != 12:
        raise RuntimeError(f"expected 12 preregistered variants, found {len(variants)}")
    protocol_envelope = lock_protocol(protocol_path, locked_at=created_at)
    if protocol_envelope["protocol_hash_sha256"] != protocol_hash(EVALUATION_PROTOCOL):
        raise RuntimeError("Mission 89 protocol hash mismatch")
    ensure_schema(db_path)

    with sqlite3.connect(Path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        validate_source_lineage(conn)
        profiles = load_cost_profiles(conn)
        development_data, development_read = load_split_data(
            conn, contract, "development"
        )
        validation_data, validation_read = load_split_data(
            conn, contract, "validation"
        )

        volatility_thresholds = compute_volatility_thresholds(development_data)
        assign_volatility_regimes(development_data, volatility_thresholds)
        assign_volatility_regimes(validation_data, volatility_thresholds)

        feasibility_by_variant = {
            variant.variant_id: funding_only_feasibility(
                development_data, variant, profiles
            )
            for variant in variants
        }

        all_results: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        development_primary_conservative: dict[str, dict[str, Any]] = {}
        validation_primary_conservative: dict[str, dict[str, Any]] = {}

        for split_name, data in (
            ("development", development_data),
            ("validation", validation_data),
        ):
            for variant in variants:
                feasibility = feasibility_by_variant[variant.variant_id]
                for scenario_code in (
                    PRIMARY_SCENARIO,
                    PROMOTION_SCENARIO,
                    DIAGNOSTIC_SCENARIO,
                ):
                    for notional_band in (
                        PRIMARY_NOTIONAL_BAND,
                        *SENSITIVITY_NOTIONAL_BANDS,
                    ):
                        result = simulate_variant(
                            data_by_symbol=data,
                            variant=variant,
                            profiles=profiles,
                            scenario_code=scenario_code,
                            notional_band=notional_band,
                            split_name=split_name,
                            contract=contract,
                            feasibility=feasibility,
                        )
                        key = (
                            split_name,
                            variant.variant_id,
                            scenario_code,
                            notional_band,
                        )
                        all_results[key] = result
                        if (
                            scenario_code == PROMOTION_SCENARIO
                            and notional_band == PRIMARY_NOTIONAL_BAND
                        ):
                            if split_name == "development":
                                development_primary_conservative[
                                    variant.variant_id
                                ] = result
                            else:
                                validation_primary_conservative[
                                    variant.variant_id
                                ] = result

        rejection = contract["predeclared_rejection_criteria"]
        selected, development_candidate_ids = choose_development_candidate(
            variants,
            feasibility_by_variant,
            development_primary_conservative,
            rejection,
        )
        pbo = calculate_pbo(development_primary_conservative)

        gates: list[dict[str, Any]] = []
        robustness_details: dict[str, Any] = {}
        selected_results: dict[tuple[str, str], dict[str, Any]] = {}
        dsr_probability = 0.0
        validation_closed_positions = 0
        selected_trade_results: list[dict[str, Any]] = []

        if selected is not None:
            for scenario_code in (
                PRIMARY_SCENARIO,
                PROMOTION_SCENARIO,
                DIAGNOSTIC_SCENARIO,
            ):
                for notional_band in (
                    PRIMARY_NOTIONAL_BAND,
                    *SENSITIVITY_NOTIONAL_BANDS,
                ):
                    development_result = all_results[
                        (
                            "development",
                            selected.variant_id,
                            scenario_code,
                            notional_band,
                        )
                    ]
                    validation_result = all_results[
                        (
                            "validation",
                            selected.variant_id,
                            scenario_code,
                            notional_band,
                        )
                    ]
                    selected_results[(scenario_code, notional_band)] = (
                        validation_result
                    )
                    selected_trade_results.extend(
                        [development_result, validation_result]
                    )
            conservative_validation = selected_results[
                (PROMOTION_SCENARIO, PRIMARY_NOTIONAL_BAND)
            ]
            validation_closed_positions = int(
                conservative_validation["closed_position_count"]
            )
            development_sharpes = [
                float(result["sharpe_ratio"])
                for result in development_primary_conservative.values()
            ]
            dsr_probability = deflated_sharpe_probability(
                conservative_validation["trade_returns"],
                development_sharpes,
                len(variants),
            )
            gates, robustness_details = build_validation_gates(
                selected=selected,
                validation_results=selected_results,
                all_validation_primary_conservative=validation_primary_conservative,
                variants=variants,
                pbo=pbo,
                dsr_probability=dsr_probability,
                protocol=EVALUATION_PROTOCOL,
            )
        else:
            gates = [
                gate(
                    "DEVELOPMENT_CANDIDATE_EXISTS",
                    False,
                    0,
                    ">= 1",
                    "No preregistered variant passed the development selection gate.",
                )
            ]

        decision, mission90_status, next_workstream = determine_decision(
            selected=selected,
            gates=gates,
            validation_closed_positions=validation_closed_positions,
            dsr_sample_size=(
                len(
                    selected_results.get(
                        (PROMOTION_SCENARIO, PRIMARY_NOTIONAL_BAND), {}
                    ).get("trade_returns", [])
                )
                if selected is not None
                else 0
            ),
            protocol=EVALUATION_PROTOCOL,
        )

        mandatory_gates = [item for item in gates if bool(item["mandatory"])]
        passed_mandatory = sum(
            item["gate_status"] == CHECK_PASS for item in mandatory_gates
        )
        failed_mandatory = len(mandatory_gates) - passed_mandatory
        maximum_timestamp_read = max(
            int(development_read["maximum_timestamp_read_ms"]),
            int(validation_read["maximum_timestamp_read_ms"]),
        )
        holdout_start_ms = split_bounds(contract, "validation")[1]
        if maximum_timestamp_read >= holdout_start_ms:
            raise RuntimeError("holdout timestamp was read")

        summary: dict[str, Any] = {
            "run_label": run_label,
            "protocol_id": PROTOCOL_ID,
            "protocol_hash": protocol_envelope["protocol_hash_sha256"],
            "contract_hash": EXPECTED_CONTRACT_HASH,
            "source_certificate_hash": EXPECTED_SOURCE_CERTIFICATE_HASH,
            "source_cost_model_hash": EXPECTED_SOURCE_COST_MODEL_HASH,
            "created_at": created_at,
            "mission89_status": MISSION89_STATUS,
            "decision": decision,
            "selected_variant_id": (
                selected.variant_id if selected is not None else None
            ),
            "selected_variant": (
                variant_dict(selected) if selected is not None else None
            ),
            "development_candidate_count": len(development_candidate_ids),
            "development_candidate_ids": development_candidate_ids,
            "development_variant_count": len(variants),
            "validation_closed_position_count": validation_closed_positions,
            "mandatory_gate_count": len(mandatory_gates),
            "passed_mandatory_gate_count": passed_mandatory,
            "failed_mandatory_gate_count": failed_mandatory,
            "pbo": pbo,
            "deflated_sharpe_probability": dsr_probability,
            "holdout_rows_read": 0,
            "maximum_timestamp_read_ms": maximum_timestamp_read,
            "holdout_start_ms": holdout_start_ms,
            "backtesting_performed": 1,
            "profitability_claimed": 0,
            "mission90_status": mission90_status,
            "next_workstream": next_workstream,
            "live_trading": LIVE_TRADING,
            "live_order_sent": LIVE_ORDER_SENT,
            "capital_deployment": CAPITAL_DEPLOYMENT,
            "read_audit": {
                "development": development_read,
                "validation": validation_read,
            },
            "feasibility_by_variant": feasibility_by_variant,
            "validation_gates": gates,
            "robustness_details": robustness_details,
            "selected_validation_results": {
                f"{scenario}|{band}": strip_trades(result)
                for (scenario, band), result in selected_results.items()
            },
        }

        report_core = {
            "summary": summary,
            "protocol": EVALUATION_PROTOCOL,
            "development_primary_conservative_results": {
                variant_id: strip_trades(result)
                for variant_id, result in development_primary_conservative.items()
            },
            "validation_primary_conservative_results": {
                variant_id: strip_trades(result)
                for variant_id, result in validation_primary_conservative.items()
            },
            "research_boundary": {
                "holdout_rows_read": 0,
                "holdout_evaluated": False,
                "live_trading": LIVE_TRADING,
                "capital_deployment": CAPITAL_DEPLOYMENT,
                "profitability_claimed": False,
            },
        }
        report_hash, report_envelope = write_report(
            report_path, report_core, created_at
        )
        summary["report_hash"] = report_hash
        summary["report_path"] = str(report_path)

        persist_results(
            conn,
            run_label=run_label,
            protocol_envelope=protocol_envelope,
            created_at=created_at,
            summary=summary,
            all_results=all_results,
            selected_trade_results=selected_trade_results,
            gates=gates,
            report_path=report_path,
            report_hash=report_hash,
            report_envelope=report_envelope,
        )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mission 89 end-to-end baseline strategy falsification"
    )
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--contract-path", default=str(DEFAULT_CONTRACT_PATH))
    parser.add_argument("--protocol-path", default=str(DEFAULT_PROTOCOL_PATH))
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--run-label", default="mission89-final-check")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    summary = run_falsification(
        db_path=args.db_path,
        contract_path=args.contract_path,
        protocol_path=args.protocol_path,
        report_path=args.report_path,
        run_label=args.run_label,
    )
    printable = {
        key: value
        for key, value in summary.items()
        if key not in {
            "feasibility_by_variant",
            "validation_gates",
            "selected_validation_results",
            "read_audit",
        }
    }
    print(json.dumps(printable, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

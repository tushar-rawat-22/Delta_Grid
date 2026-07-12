"""Mission 90: Directional Strategy Tournament and Charter Lock.

Mission 90 is a development-only tournament for twelve preregistered,
deterministic directional strategies. It follows Mission 89's evidence-based
rejection and archival of crypto funding carry.

The mission builds a strategy-specific single-leg execution-cost model,
evaluates spot long/flat trend, perpetual long/short trend, and volatility
breakout families on development data only, selects at most one candidate, and
locks an immutable Mission 91 validation charter when a candidate passes every
mandatory gate.

Validation and untouched-holdout performance are never queried. No live
signal, order, private key, signing path, leverage escalation, machine
learning, model promotion, capital deployment, or profitability claim is
permitted.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import sqlite3
import statistics
from collections import defaultdict
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
    LIVE_ORDER_SENT,
    LIVE_TRADING,
)


SOURCE_MISSION89_RUN_LABEL = "mission89-final-check"
EXPECTED_SOURCE_MISSION89_PROTOCOL_HASH = (
    "89a17f61823592f112a5f6d6b61a2015e01646e76e78fb61bd140def72d1738c"
)
EXPECTED_SOURCE_MISSION89_REPORT_HASH = (
    "eb053bdfbac8d59ae4b79f4575c2b2bd90457889f14d5012b30ab84fa6030f48"
)
EXPECTED_SOURCE_CERTIFICATE_HASH = (
    "e4d78b99417c1acb9bd89e7a8ef175cbf0c0e1219c1f71777401be41b8978819"
)
EXPECTED_SOURCE_COST_MODEL_HASH = (
    "398cc556614a97767fea36540556442579f195562a9ed16c18cc9561b78fc8a2"
)

PROTOCOL_ID = "mission90-directional-tournament-protocol-v1"
PROTOCOL_VERSION = 1
CHARTER_ID = "mission90-directional-strategy-charter-v1"
MISSION90_STATUS = "COMPLETE_DIRECTIONAL_STRATEGY_TOURNAMENT_AND_CHARTER_LOCK"

DECISION_SPOT = "LOCK_SPOT_TREND_AND_AUTHORIZE_MISSION91"
DECISION_PERPETUAL = "LOCK_PERPETUAL_TREND_AND_AUTHORIZE_MISSION91"
DECISION_BREAKOUT = "LOCK_VOLATILITY_BREAKOUT_AND_AUTHORIZE_MISSION91"
DECISION_CONTINUE = "CONTINUE_DIRECTIONAL_DATA_COLLECTION_NO_VALIDATION"
DECISION_REJECT = "REJECT_ALL_DIRECTIONAL_HYPOTHESES"
VALID_DECISIONS = {
    DECISION_SPOT,
    DECISION_PERPETUAL,
    DECISION_BREAKOUT,
    DECISION_CONTINUE,
    DECISION_REJECT,
}

MISSION91_READY = "READY_FOR_FIXED_VALIDATION_AND_ROBUSTNESS"
MISSION91_PAUSED = "PAUSED_DIRECTIONAL_EVIDENCE_INSUFFICIENT"
MISSION91_NOT_AUTHORIZED = "NOT_AUTHORIZED_ALL_DIRECTIONAL_HYPOTHESES_REJECTED"

DEFAULT_DB_PATH = Path("offchain/deltagrid.db")
DEFAULT_SOURCE_CONTRACT_PATH = Path(
    "offchain/research/contracts/mission85_funding_carry_charter_v1.json"
)
DEFAULT_PROTOCOL_PATH = Path(
    "offchain/research/contracts/mission90_directional_tournament_protocol_v1.json"
)
DEFAULT_CHARTER_PATH = Path(
    "offchain/research/contracts/mission90_directional_strategy_charter_v1.json"
)
DEFAULT_REPORT_PATH = Path(
    "offchain/data/mission90/directional_tournament_report.json"
)

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
HOUR_MS = INTERVAL_MS
DECISION_INTERVAL_HOURS = 4
STRICT_EXECUTION_DELAY_HOURS = 1
FUNDING_SETTLEMENTS_PER_DAY = 3

PRIMARY_NAV_BAND = "PRIMARY_30K"
NAV_BANDS: tuple[dict[str, Any], ...] = (
    {
        "nav_band": "MICRO_3K",
        "rank": 1,
        "portfolio_nav_usd": 3000.0,
        "per_asset_cap_usd": 1000.0,
        "slippage_size_multiplier": 1.0,
    },
    {
        "nav_band": PRIMARY_NAV_BAND,
        "rank": 2,
        "portfolio_nav_usd": 30000.0,
        "per_asset_cap_usd": 10000.0,
        "slippage_size_multiplier": 1.5,
    },
    {
        "nav_band": "UPPER_150K",
        "rank": 3,
        "portfolio_nav_usd": 150000.0,
        "per_asset_cap_usd": 50000.0,
        "slippage_size_multiplier": 3.0,
    },
)

NORMAL_SCENARIO = "NORMAL_DIRECTIONAL"
CONSERVATIVE_SCENARIO = "CONSERVATIVE_DIRECTIONAL"
SEVERE_SCENARIO = "SEVERE_DIRECTIONAL_STRESS"
COST_SCENARIOS: tuple[dict[str, Any], ...] = (
    {
        "scenario_code": NORMAL_SCENARIO,
        "rank": 1,
        "spread_multiplier": 1.0,
        "slippage_multiplier": 1.0,
        "round_trip_delay_buffer_bps": 1.0,
        "round_trip_operational_buffer_bps": 1.0,
        "exit_stress_buffer_bps": 0.0,
        "mandatory_profitability_gate": False,
    },
    {
        "scenario_code": CONSERVATIVE_SCENARIO,
        "rank": 2,
        "spread_multiplier": 2.0,
        "slippage_multiplier": 2.5,
        "round_trip_delay_buffer_bps": 4.0,
        "round_trip_operational_buffer_bps": 3.0,
        "exit_stress_buffer_bps": 3.0,
        "mandatory_profitability_gate": True,
    },
    {
        "scenario_code": SEVERE_SCENARIO,
        "rank": 3,
        "spread_multiplier": 5.0,
        "slippage_multiplier": 8.0,
        "round_trip_delay_buffer_bps": 15.0,
        "round_trip_operational_buffer_bps": 10.0,
        "exit_stress_buffer_bps": 15.0,
        "mandatory_profitability_gate": False,
    },
)

SPREAD_ASSUMPTIONS_BPS: dict[str, dict[str, float]] = {
    "BTCUSDT": {"SPOT": 1.0, "PERPETUAL": 1.0},
    "ETHUSDT": {"SPOT": 1.5, "PERPETUAL": 1.5},
    "SOLUSDT": {"SPOT": 3.0, "PERPETUAL": 2.5},
}

VARIANTS: tuple[dict[str, Any], ...] = (
    {
        "variant_id": "SPOT_MA_24_168",
        "family": "SPOT_TREND",
        "instrument": "SPOT",
        "signal_type": "MA_CROSS",
        "fast_hours": 24,
        "slow_hours": 168,
        "neutral_buffer_bps": 20.0,
        "minimum_holding_hours": 24,
        "cooldown_hours": 12,
        "complexity_rank": 1,
        "neighbor_ids": ["SPOT_MA_72_336", "SPOT_RETURN_168"],
    },
    {
        "variant_id": "SPOT_MA_72_336",
        "family": "SPOT_TREND",
        "instrument": "SPOT",
        "signal_type": "MA_CROSS",
        "fast_hours": 72,
        "slow_hours": 336,
        "neutral_buffer_bps": 25.0,
        "minimum_holding_hours": 36,
        "cooldown_hours": 12,
        "complexity_rank": 1,
        "neighbor_ids": ["SPOT_MA_24_168", "SPOT_RETURN_336"],
    },
    {
        "variant_id": "SPOT_RETURN_168",
        "family": "SPOT_TREND",
        "instrument": "SPOT",
        "signal_type": "RETURN_TREND",
        "lookback_hours": 168,
        "entry_threshold_bps": 150.0,
        "exit_threshold_bps": 0.0,
        "minimum_holding_hours": 24,
        "cooldown_hours": 12,
        "complexity_rank": 1,
        "neighbor_ids": ["SPOT_MA_24_168", "SPOT_RETURN_336"],
    },
    {
        "variant_id": "SPOT_RETURN_336",
        "family": "SPOT_TREND",
        "instrument": "SPOT",
        "signal_type": "RETURN_TREND",
        "lookback_hours": 336,
        "entry_threshold_bps": 250.0,
        "exit_threshold_bps": 0.0,
        "minimum_holding_hours": 36,
        "cooldown_hours": 12,
        "complexity_rank": 1,
        "neighbor_ids": ["SPOT_MA_72_336", "SPOT_RETURN_168"],
    },
    {
        "variant_id": "PERP_MA_24_168",
        "family": "PERPETUAL_TREND",
        "instrument": "PERPETUAL",
        "signal_type": "MA_CROSS",
        "fast_hours": 24,
        "slow_hours": 168,
        "neutral_buffer_bps": 25.0,
        "minimum_holding_hours": 24,
        "cooldown_hours": 12,
        "complexity_rank": 2,
        "neighbor_ids": ["PERP_MA_72_336", "PERP_RETURN_168"],
    },
    {
        "variant_id": "PERP_MA_72_336",
        "family": "PERPETUAL_TREND",
        "instrument": "PERPETUAL",
        "signal_type": "MA_CROSS",
        "fast_hours": 72,
        "slow_hours": 336,
        "neutral_buffer_bps": 35.0,
        "minimum_holding_hours": 36,
        "cooldown_hours": 12,
        "complexity_rank": 2,
        "neighbor_ids": ["PERP_MA_24_168", "PERP_RETURN_336"],
    },
    {
        "variant_id": "PERP_RETURN_168",
        "family": "PERPETUAL_TREND",
        "instrument": "PERPETUAL",
        "signal_type": "RETURN_TREND",
        "lookback_hours": 168,
        "entry_threshold_bps": 150.0,
        "exit_threshold_bps": 75.0,
        "minimum_holding_hours": 24,
        "cooldown_hours": 12,
        "complexity_rank": 2,
        "neighbor_ids": ["PERP_MA_24_168", "PERP_RETURN_336"],
    },
    {
        "variant_id": "PERP_RETURN_336",
        "family": "PERPETUAL_TREND",
        "instrument": "PERPETUAL",
        "signal_type": "RETURN_TREND",
        "lookback_hours": 336,
        "entry_threshold_bps": 250.0,
        "exit_threshold_bps": 100.0,
        "minimum_holding_hours": 36,
        "cooldown_hours": 12,
        "complexity_rank": 2,
        "neighbor_ids": ["PERP_MA_72_336", "PERP_RETURN_168"],
    },
    {
        "variant_id": "SPOT_BREAKOUT_168_72",
        "family": "VOLATILITY_BREAKOUT",
        "instrument": "SPOT",
        "signal_type": "CHANNEL_BREAKOUT",
        "entry_window_hours": 168,
        "exit_window_hours": 72,
        "minimum_holding_hours": 24,
        "cooldown_hours": 12,
        "complexity_rank": 3,
        "neighbor_ids": ["SPOT_BREAKOUT_336_168", "PERP_BREAKOUT_168_72"],
    },
    {
        "variant_id": "SPOT_BREAKOUT_336_168",
        "family": "VOLATILITY_BREAKOUT",
        "instrument": "SPOT",
        "signal_type": "CHANNEL_BREAKOUT",
        "entry_window_hours": 336,
        "exit_window_hours": 168,
        "minimum_holding_hours": 36,
        "cooldown_hours": 12,
        "complexity_rank": 3,
        "neighbor_ids": ["SPOT_BREAKOUT_168_72", "PERP_BREAKOUT_336_168"],
    },
    {
        "variant_id": "PERP_BREAKOUT_168_72",
        "family": "VOLATILITY_BREAKOUT",
        "instrument": "PERPETUAL",
        "signal_type": "CHANNEL_BREAKOUT",
        "entry_window_hours": 168,
        "exit_window_hours": 72,
        "minimum_holding_hours": 24,
        "cooldown_hours": 12,
        "complexity_rank": 3,
        "neighbor_ids": ["PERP_BREAKOUT_336_168", "SPOT_BREAKOUT_168_72"],
    },
    {
        "variant_id": "PERP_BREAKOUT_336_168",
        "family": "VOLATILITY_BREAKOUT",
        "instrument": "PERPETUAL",
        "signal_type": "CHANNEL_BREAKOUT",
        "entry_window_hours": 336,
        "exit_window_hours": 168,
        "minimum_holding_hours": 36,
        "cooldown_hours": 12,
        "complexity_rank": 3,
        "neighbor_ids": ["PERP_BREAKOUT_168_72", "SPOT_BREAKOUT_336_168"],
    },
)

MANDATORY_GATES: dict[str, Any] = {
    "minimum_conservative_net_return_pct": 0.0,
    "minimum_conservative_sharpe": 0.50,
    "minimum_closed_trade_count": 12,
    "maximum_drawdown_pct": 35.0,
    "minimum_positive_asset_count": 2,
    "maximum_single_asset_positive_contribution_pct": 75.0,
    "maximum_single_quarter_positive_contribution_pct": 65.0,
    "maximum_turnover_multiple": 60.0,
    "maximum_cost_to_positive_gross_profit_ratio": 0.80,
    "minimum_neighbor_count": 1,
    "minimum_positive_neighbor_fraction": 0.50,
    "micro_nav_conservative_return_must_be_positive": True,
    "benchmark_superiority_required": True,
}

EVALUATION_PROTOCOL: dict[str, Any] = {
    "protocol_id": PROTOCOL_ID,
    "protocol_version": PROTOCOL_VERSION,
    "mission": "Mission 90 Directional Strategy Tournament and Charter Lock",
    "source_lineage": {
        "mission89_run_label": SOURCE_MISSION89_RUN_LABEL,
        "mission89_protocol_hash": EXPECTED_SOURCE_MISSION89_PROTOCOL_HASH,
        "mission89_report_hash": EXPECTED_SOURCE_MISSION89_REPORT_HASH,
        "mission85_contract_hash": EXPECTED_CONTRACT_HASH,
        "mission87_certificate_hash": EXPECTED_SOURCE_CERTIFICATE_HASH,
        "mission88_cost_model_hash_methodology_reference": (
            EXPECTED_SOURCE_COST_MODEL_HASH
        ),
    },
    "funding_carry_archive": {
        "status": "ARCHIVED_AFTER_BASELINE_FALSIFICATION",
        "retuning_allowed": False,
        "cost_reduction_allowed": False,
        "machine_learning_rescue_allowed": False,
        "unused_holdout_opening_allowed": False,
    },
    "tournament_scope": {
        "development_performance_allowed": True,
        "validation_performance_allowed": False,
        "untouched_holdout_performance_allowed": False,
        "variant_count": 12,
        "selection_count_maximum": 1,
        "families": [
            "SPOT_TREND",
            "PERPETUAL_TREND",
            "VOLATILITY_BREAKOUT",
        ],
        "excluded_families": [
            "SHORT_HORIZON_MEAN_REVERSION",
            "SCALPING",
            "MARKET_MAKING",
            "ORDER_BOOK_IMBALANCE",
            "BROAD_CROSS_SECTIONAL_STATISTICAL_ARBITRAGE",
            "OPTIONS",
            "MACHINE_LEARNING_PREDICTION",
        ],
    },
    "execution_timing": {
        "signal_source": "COMPLETED_HOURLY_BARS_SAMPLED_EVERY_4_HOURS",
        "signal_execution": "STRICTLY_NEXT_HOURLY_OPEN_AFTER_DECISION",
        "same_bar_execution_allowed": False,
        "lookahead_allowed": False,
        "funding_known_in_advance_allowed": False,
    },
    "portfolio_policy": {
        "primary_nav_band": PRIMARY_NAV_BAND,
        "nav_bands": deepcopy(list(NAV_BANDS)),
        "maximum_gross_exposure_multiple": 1.0,
        "maximum_single_asset_nav_fraction": 1.0 / 3.0,
        "leverage_escalation_allowed": False,
        "pyramiding_allowed": False,
        "martingale_allowed": False,
        "volatility_scaled_entry_sizing": True,
        "target_annualized_volatility": 0.60,
        "volatility_floor": 0.10,
        "volatility_abstention_ceiling": 2.50,
        "resize_threshold_fraction": 0.25,
        "minimum_resize_interval_hours": 24,
    },
    "cost_policy": {
        "model": "MISSION90_SINGLE_LEG_DIRECTIONAL_ASSUMPTION_MODEL",
        "mission88_usage": "METHODOLOGY_REFERENCE_NOT_DIRECT_TWO_LEG_REUSE",
        "normal_role": "DESCRIPTIVE_BASE_CASE",
        "conservative_role": "MANDATORY_CANDIDATE_GATE",
        "severe_role": "DIAGNOSTIC_ONLY",
        "assumptions_are_measured_microstructure": False,
        "cost_reduction_after_results_allowed": False,
    },
    "variants": deepcopy(list(VARIANTS)),
    "mandatory_candidate_gates": deepcopy(MANDATORY_GATES),
    "selection_policy": {
        "eligible_candidates_only": True,
        "ranking_order": [
            "conservative_net_return_pct",
            "calmar_ratio",
            "sharpe_ratio",
            "lower_drawdown",
            "lower_turnover",
            "lower_complexity",
        ],
        "fallback_after_mission91_failure_allowed": False,
        "tie_simplicity_order": [
            "SPOT_TREND",
            "PERPETUAL_TREND",
            "VOLATILITY_BREAKOUT",
        ],
    },
    "research_boundary": {
        "validation_rows_allowed": 0,
        "holdout_rows_allowed": 0,
        "live_trading_allowed": False,
        "capital_deployment_allowed": False,
        "profitability_claim_allowed": False,
        "model_training_allowed": False,
        "model_promotion_allowed": False,
    },
}


@dataclass(frozen=True)
class DirectionalCostProfile:
    scenario_code: str
    scenario_rank: int
    instrument: str
    symbol: str
    nav_band: str
    nav_rank: int
    portfolio_nav_usd: float
    per_asset_cap_usd: float
    entry_cost_bps: float
    exit_cost_bps: float
    uncertainty_label: str


@dataclass
class MarketSeries:
    symbol: str
    instrument: str
    start_ms: int
    end_ms: int
    hours: list[int]
    open_price: list[float]
    high_price: list[float]
    low_price: list[float]
    close_price: list[float]
    hour_to_index: dict[int, int]
    prefix_close: list[float]
    funding_by_hour: dict[int, dict[str, float | int]] = field(default_factory=dict)
    regime_by_hour: dict[int, str] = field(default_factory=dict)


@dataclass
class Position:
    symbol: str
    instrument: str
    direction: int
    entry_time_ms: int
    entry_price: float
    quantity: float
    average_entry_price: float
    initial_notional_usd: float
    current_notional_usd: float
    entry_regime: str
    entry_reason: str
    realized_price_pnl_usd: float = 0.0
    funding_pnl_usd: float = 0.0
    entry_cost_usd: float = 0.0
    rebalance_cost_usd: float = 0.0
    rebalance_count: int = 0
    last_resize_time_ms: int = 0


@dataclass(frozen=True)
class PendingAction:
    execution_time_ms: int
    target_direction: int
    target_notional_usd: float
    reason: str
    decision_time_ms: int


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def protocol_hash(protocol: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(protocol).encode("utf-8"))


def payload_hash(payload: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(payload).encode("utf-8"))


def safe_ratio(numerator: float, denominator: float, default: float = 0.0) -> float:
    if denominator == 0:
        return default
    return numerator / denominator


def quarter_label(timestamp_ms: int) -> str:
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    quarter = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{quarter}"


def nearest_hour(timestamp_ms: int) -> int:
    return ((int(timestamp_ms) + HOUR_MS // 2) // HOUR_MS) * HOUR_MS


def lock_json_envelope(
    path_value: str | Path,
    payload_key: str,
    payload: Mapping[str, Any],
    status: str,
    locked_at: str | None = None,
) -> dict[str, Any]:
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = payload_hash(payload)
    envelope = {
        payload_key: deepcopy(dict(payload)),
        f"{payload_key}_hash_sha256": digest,
        "locked_at": locked_at or utc_now(),
        "status": status,
    }
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get(f"{payload_key}_hash_sha256") != digest:
            raise RuntimeError(f"{path} exists with a different payload hash")
        if existing.get(payload_key) != payload:
            raise RuntimeError(f"{path} payload changed after lock")
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
            CREATE TABLE IF NOT EXISTS mission90_protocols (
                protocol_id TEXT PRIMARY KEY,
                protocol_hash TEXT NOT NULL,
                locked_at TEXT NOT NULL,
                protocol_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mission90_directional_cost_profiles (
                protocol_hash TEXT NOT NULL,
                scenario_code TEXT NOT NULL,
                scenario_rank INTEGER NOT NULL,
                instrument TEXT NOT NULL,
                symbol TEXT NOT NULL,
                nav_band TEXT NOT NULL,
                nav_rank INTEGER NOT NULL,
                portfolio_nav_usd REAL NOT NULL,
                per_asset_cap_usd REAL NOT NULL,
                entry_cost_bps REAL NOT NULL,
                exit_cost_bps REAL NOT NULL,
                uncertainty_label TEXT NOT NULL,
                profile_json TEXT NOT NULL,
                PRIMARY KEY (
                    protocol_hash,
                    scenario_code,
                    instrument,
                    symbol,
                    nav_band
                )
            );

            CREATE TABLE IF NOT EXISTS mission90_runs (
                run_label TEXT PRIMARY KEY,
                protocol_id TEXT NOT NULL,
                protocol_hash TEXT NOT NULL,
                charter_id TEXT NOT NULL,
                charter_hash TEXT NOT NULL,
                source_mission89_protocol_hash TEXT NOT NULL,
                source_mission89_report_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                mission90_status TEXT NOT NULL,
                decision TEXT NOT NULL,
                selected_variant_id TEXT,
                selected_family TEXT,
                development_variant_count INTEGER NOT NULL,
                evaluation_count INTEGER NOT NULL,
                eligible_candidate_count INTEGER NOT NULL,
                development_rows_read INTEGER NOT NULL,
                validation_rows_read INTEGER NOT NULL,
                holdout_rows_read INTEGER NOT NULL,
                maximum_timestamp_read_ms INTEGER NOT NULL,
                validation_start_ms INTEGER NOT NULL,
                pbo REAL NOT NULL,
                selected_deflated_sharpe_probability REAL NOT NULL,
                mission91_status TEXT NOT NULL,
                next_workstream TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                profitability_claimed INTEGER NOT NULL,
                report_hash TEXT NOT NULL,
                summary_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mission90_variant_results (
                run_label TEXT NOT NULL,
                variant_id TEXT NOT NULL,
                family TEXT NOT NULL,
                instrument TEXT NOT NULL,
                scenario_code TEXT NOT NULL,
                nav_band TEXT NOT NULL,
                closed_trade_count INTEGER NOT NULL,
                net_pnl_usd REAL NOT NULL,
                net_return_pct REAL NOT NULL,
                annualized_return_pct REAL NOT NULL,
                sharpe_ratio REAL NOT NULL,
                maximum_drawdown_pct REAL NOT NULL,
                calmar_ratio REAL NOT NULL,
                turnover_multiple REAL NOT NULL,
                positive_asset_count INTEGER NOT NULL,
                maximum_asset_contribution_pct REAL NOT NULL,
                maximum_quarter_contribution_pct REAL NOT NULL,
                cost_to_positive_gross_profit_ratio REAL NOT NULL,
                funding_pnl_usd REAL NOT NULL,
                result_json TEXT NOT NULL,
                PRIMARY KEY (
                    run_label,
                    variant_id,
                    scenario_code,
                    nav_band
                )
            );

            CREATE TABLE IF NOT EXISTS mission90_variant_gates (
                run_label TEXT NOT NULL,
                variant_id TEXT NOT NULL,
                gate_name TEXT NOT NULL,
                gate_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                required_value TEXT NOT NULL,
                mandatory INTEGER NOT NULL,
                gate_reason TEXT NOT NULL,
                PRIMARY KEY (run_label, variant_id, gate_name)
            );

            CREATE TABLE IF NOT EXISTS mission90_selected_trade_ledger (
                run_label TEXT NOT NULL,
                trade_id TEXT NOT NULL,
                variant_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                instrument TEXT NOT NULL,
                direction INTEGER NOT NULL,
                entry_time_ms INTEGER NOT NULL,
                exit_time_ms INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                price_pnl_usd REAL NOT NULL,
                funding_pnl_usd REAL NOT NULL,
                entry_cost_usd REAL NOT NULL,
                rebalance_cost_usd REAL NOT NULL,
                exit_cost_usd REAL NOT NULL,
                gross_pnl_usd REAL NOT NULL,
                net_pnl_usd REAL NOT NULL,
                trade_json TEXT NOT NULL,
                PRIMARY KEY (run_label, trade_id)
            );

            CREATE TABLE IF NOT EXISTS mission90_strategy_charters (
                charter_id TEXT PRIMARY KEY,
                run_label TEXT NOT NULL,
                charter_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                charter_path TEXT NOT NULL,
                charter_json TEXT NOT NULL,
                decision TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mission90_reports (
                run_label TEXT PRIMARY KEY,
                report_hash TEXT NOT NULL,
                report_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                report_json TEXT NOT NULL
            );
            """
        )
        conn.commit()


def validate_source_mission89(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT *
        FROM mission89_runs
        WHERE run_label = ?
        """,
        (SOURCE_MISSION89_RUN_LABEL,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Mission 89 authoritative run is missing")
    source = dict(row)
    requirements = [
        source["protocol_hash"] == EXPECTED_SOURCE_MISSION89_PROTOCOL_HASH,
        source["report_hash"] == EXPECTED_SOURCE_MISSION89_REPORT_HASH,
        source["contract_hash"] == EXPECTED_CONTRACT_HASH,
        source["source_certificate_hash"] == EXPECTED_SOURCE_CERTIFICATE_HASH,
        source["source_cost_model_hash"] == EXPECTED_SOURCE_COST_MODEL_HASH,
        source["mission89_status"]
        == "COMPLETE_END_TO_END_BASELINE_FALSIFICATION",
        source["decision"] == "REJECT_AND_ARCHIVE_FUNDING_CARRY",
        source["selected_variant_id"] is None,
        source["development_candidate_count"] == 0,
        source["holdout_rows_read"] == 0,
        source["mission90_status"] == "NOT_AUTHORIZED_STRATEGY_REJECTED",
        source["next_workstream"] == "NEW_ECONOMIC_HYPOTHESIS_CHARTER",
        source["live_trading"] == "DISABLED",
        source["live_order_sent"] == 0,
        source["capital_deployment"] == "BLOCKED",
        source["profitability_claimed"] == 0,
    ]
    if not all(requirements):
        raise RuntimeError("Mission 89 source lineage validation failed")
    return source


def split_bounds(contract: Mapping[str, Any]) -> tuple[int, int, int]:
    splits = {str(item["name"]): item for item in contract["research_splits"]}
    development_start = parse_utc_ms(str(splits["development"]["start"]))
    development_end = parse_utc_ms(
        str(splits["development"]["end_exclusive"])
    )
    validation_start = parse_utc_ms(str(splits["validation"]["start"]))
    holdout_start = parse_utc_ms(str(splits["untouched_holdout"]["start"]))
    if development_end != validation_start:
        raise RuntimeError("development must end exactly at validation start")
    if not development_start < validation_start < holdout_start:
        raise RuntimeError("invalid Mission 85 split ordering")
    return development_start, validation_start, holdout_start


def load_development_data(
    conn: sqlite3.Connection,
    contract: Mapping[str, Any],
) -> tuple[dict[tuple[str, str], MarketSeries], dict[str, Any]]:
    start_ms, validation_start_ms, holdout_start_ms = split_bounds(contract)
    output: dict[tuple[str, str], MarketSeries] = {}
    total_rows = 0
    maximum_timestamp = 0
    expected_hours = list(range(start_ms, validation_start_ms, HOUR_MS))
    expected_set = set(expected_hours)

    for symbol in SYMBOLS:
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
            (EXPECTED_CONTRACT_HASH, symbol, start_ms, validation_start_ms),
        ).fetchall()
        funding_by_hour: dict[int, dict[str, float | int]] = {}
        for row in funding_rows:
            actual_time = int(row[0])
            funding_by_hour[nearest_hour(actual_time)] = {
                "actual_time_ms": actual_time,
                "funding_rate": float(row[1]),
                "mark_price": float(row[2]) if row[2] is not None else 0.0,
            }
            maximum_timestamp = max(maximum_timestamp, actual_time)
        total_rows += len(funding_rows)

        for instrument, stream in (
            ("SPOT", "spot_ohlcv"),
            ("PERPETUAL", "perpetual_ohlcv"),
        ):
            rows = conn.execute(
                """
                SELECT
                    open_time_ms,
                    open_price,
                    high_price,
                    low_price,
                    close_price
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
                    validation_start_ms,
                ),
            ).fetchall()
            hours = [int(row[0]) for row in rows]
            if set(hours) != expected_set or len(hours) != len(expected_hours):
                raise RuntimeError(
                    f"development data incomplete for {symbol}/{instrument}"
                )
            opens = [float(row[1]) for row in rows]
            highs = [float(row[2]) for row in rows]
            lows = [float(row[3]) for row in rows]
            closes = [float(row[4]) for row in rows]
            if any(
                not (open_ > 0 and high > 0 and low > 0 and close > 0)
                for open_, high, low, close in zip(opens, highs, lows, closes)
            ):
                raise RuntimeError(f"nonpositive OHLC value for {symbol}/{instrument}")
            prefix = [0.0]
            for close in closes:
                prefix.append(prefix[-1] + close)
            output[(symbol, instrument)] = MarketSeries(
                symbol=symbol,
                instrument=instrument,
                start_ms=start_ms,
                end_ms=validation_start_ms,
                hours=hours,
                open_price=opens,
                high_price=highs,
                low_price=lows,
                close_price=closes,
                hour_to_index={hour: index for index, hour in enumerate(hours)},
                prefix_close=prefix,
                funding_by_hour=(funding_by_hour if instrument == "PERPETUAL" else {}),
            )
            total_rows += len(rows)
            maximum_timestamp = max(maximum_timestamp, hours[-1])

    if maximum_timestamp >= validation_start_ms:
        raise RuntimeError("Mission 90 read validation or holdout performance data")
    if validation_start_ms >= holdout_start_ms:
        raise RuntimeError("invalid validation/holdout boundary")

    assign_diagnostic_regimes(output)
    return output, {
        "development_rows_read": total_rows,
        "validation_rows_read": 0,
        "holdout_rows_read": 0,
        "maximum_timestamp_read_ms": maximum_timestamp,
        "validation_start_ms": validation_start_ms,
        "holdout_start_ms": holdout_start_ms,
    }


def rolling_annualized_volatility(series: MarketSeries, index: int, window: int = 72) -> float:
    if index < window:
        return 0.0
    returns: list[float] = []
    for position in range(index - window + 1, index + 1):
        previous = series.close_price[position - 1]
        current = series.close_price[position]
        returns.append(math.log(current / previous))
    if len(returns) < 2:
        return 0.0
    return statistics.pstdev(returns) * math.sqrt(24.0 * 365.0)


def assign_diagnostic_regimes(
    data: Mapping[tuple[str, str], MarketSeries],
) -> None:
    for series in data.values():
        values: list[tuple[int, float]] = []
        for index, hour in enumerate(series.hours):
            value = rolling_annualized_volatility(series, index)
            if value > 0:
                values.append((hour, value))
        if not values:
            series.regime_by_hour = {hour: "WARMUP" for hour in series.hours}
            continue
        ordered = sorted(value for _, value in values)
        low = ordered[int((len(ordered) - 1) / 3)]
        high = ordered[int(2 * (len(ordered) - 1) / 3)]
        regimes: dict[int, str] = {}
        for hour in series.hours:
            index = series.hour_to_index[hour]
            value = rolling_annualized_volatility(series, index)
            if value <= 0:
                regimes[hour] = "WARMUP"
            elif value <= low:
                regimes[hour] = "LOW_VOLATILITY"
            elif value <= high:
                regimes[hour] = "MEDIUM_VOLATILITY"
            else:
                regimes[hour] = "HIGH_VOLATILITY"
        series.regime_by_hour = regimes


def mission85_cost_floors(contract: Mapping[str, Any]) -> dict[str, float]:
    raw = contract["initial_cost_assumptions"]
    required = (
        "spot_entry_fee_bps",
        "spot_exit_fee_bps",
        "perpetual_entry_fee_bps",
        "perpetual_exit_fee_bps",
        "spot_slippage_per_side_bps",
        "perpetual_slippage_per_side_bps",
    )
    if any(key not in raw for key in required):
        raise RuntimeError("Mission 85 directional cost floors are incomplete")
    if raw.get("cost_reduction_after_results_allowed") is not False:
        raise RuntimeError("Mission 85 cost reduction lock is not active")
    return {key: float(raw[key]) for key in required}


def build_directional_cost_profiles(
    contract: Mapping[str, Any],
) -> dict[tuple[str, str, str, str], DirectionalCostProfile]:
    floors = mission85_cost_floors(contract)
    profiles: dict[tuple[str, str, str, str], DirectionalCostProfile] = {}
    for scenario in COST_SCENARIOS:
        for band in NAV_BANDS:
            for symbol in SYMBOLS:
                for instrument in ("SPOT", "PERPETUAL"):
                    fee_entry = floors[
                        "spot_entry_fee_bps"
                        if instrument == "SPOT"
                        else "perpetual_entry_fee_bps"
                    ]
                    fee_exit = floors[
                        "spot_exit_fee_bps"
                        if instrument == "SPOT"
                        else "perpetual_exit_fee_bps"
                    ]
                    base_slippage = floors[
                        "spot_slippage_per_side_bps"
                        if instrument == "SPOT"
                        else "perpetual_slippage_per_side_bps"
                    ]
                    spread = SPREAD_ASSUMPTIONS_BPS[symbol][instrument]
                    spread_cost = spread * float(scenario["spread_multiplier"])
                    slippage_cost = (
                        base_slippage
                        * float(scenario["slippage_multiplier"])
                        * float(band["slippage_size_multiplier"])
                    )
                    half_delay = float(
                        scenario["round_trip_delay_buffer_bps"]
                    ) / 2.0
                    half_operational = float(
                        scenario["round_trip_operational_buffer_bps"]
                    ) / 2.0
                    entry = fee_entry + spread_cost + slippage_cost + half_delay + half_operational
                    exit_ = (
                        fee_exit
                        + spread_cost
                        + slippage_cost
                        + half_delay
                        + half_operational
                        + float(scenario["exit_stress_buffer_bps"])
                    )
                    profile = DirectionalCostProfile(
                        scenario_code=str(scenario["scenario_code"]),
                        scenario_rank=int(scenario["rank"]),
                        instrument=instrument,
                        symbol=symbol,
                        nav_band=str(band["nav_band"]),
                        nav_rank=int(band["rank"]),
                        portfolio_nav_usd=float(band["portfolio_nav_usd"]),
                        per_asset_cap_usd=float(band["per_asset_cap_usd"]),
                        entry_cost_bps=entry,
                        exit_cost_bps=exit_,
                        uncertainty_label=(
                            "ASSUMPTION_BOUNDED_SINGLE_LEG_NOT_ORDERBOOK_CALIBRATED"
                        ),
                    )
                    key = (profile.scenario_code, instrument, symbol, profile.nav_band)
                    profiles[key] = profile
    if len(profiles) != 54:
        raise RuntimeError(f"expected 54 directional cost profiles, found {len(profiles)}")
    validate_directional_cost_profiles(profiles)
    return profiles


def validate_directional_cost_profiles(
    profiles: Mapping[tuple[str, str, str, str], DirectionalCostProfile],
) -> None:
    for instrument in ("SPOT", "PERPETUAL"):
        for symbol in SYMBOLS:
            for band in NAV_BANDS:
                ordered = [
                    profiles[(scenario["scenario_code"], instrument, symbol, band["nav_band"])]
                    for scenario in COST_SCENARIOS
                ]
                totals = [item.entry_cost_bps + item.exit_cost_bps for item in ordered]
                if totals != sorted(totals):
                    raise RuntimeError("directional scenario costs are not monotonic")
            for scenario in COST_SCENARIOS:
                ordered = [
                    profiles[(scenario["scenario_code"], instrument, symbol, band["nav_band"])]
                    for band in NAV_BANDS
                ]
                totals = [item.entry_cost_bps + item.exit_cost_bps for item in ordered]
                if totals != sorted(totals):
                    raise RuntimeError("directional notional costs are not monotonic")


def cost_profile_dict(profile: DirectionalCostProfile) -> dict[str, Any]:
    return {
        "scenario_code": profile.scenario_code,
        "scenario_rank": profile.scenario_rank,
        "instrument": profile.instrument,
        "symbol": profile.symbol,
        "nav_band": profile.nav_band,
        "nav_rank": profile.nav_rank,
        "portfolio_nav_usd": profile.portfolio_nav_usd,
        "per_asset_cap_usd": profile.per_asset_cap_usd,
        "entry_cost_bps": profile.entry_cost_bps,
        "exit_cost_bps": profile.exit_cost_bps,
        "uncertainty_label": profile.uncertainty_label,
    }


def sma(series: MarketSeries, index: int, window: int) -> float:
    if index + 1 < window:
        return 0.0
    total = series.prefix_close[index + 1] - series.prefix_close[index + 1 - window]
    return total / window


def desired_direction(
    variant: Mapping[str, Any],
    series: MarketSeries,
    index: int,
    current_direction: int,
) -> int:
    signal_type = str(variant["signal_type"])
    instrument = str(variant["instrument"])
    current_close = series.close_price[index]

    if signal_type == "MA_CROSS":
        fast = sma(series, index, int(variant["fast_hours"]))
        slow = sma(series, index, int(variant["slow_hours"]))
        if fast <= 0 or slow <= 0:
            return 0
        buffer = float(variant["neutral_buffer_bps"]) / 10000.0
        if fast > slow * (1.0 + buffer):
            return 1
        if fast < slow * (1.0 - buffer):
            return -1 if instrument == "PERPETUAL" else 0
        return current_direction

    if signal_type == "RETURN_TREND":
        lookback = int(variant["lookback_hours"])
        if index < lookback:
            return 0
        previous = series.close_price[index - lookback]
        return_bps = 10000.0 * (current_close / previous - 1.0)
        entry = float(variant["entry_threshold_bps"])
        exit_threshold = float(variant["exit_threshold_bps"])
        if return_bps > entry:
            return 1
        if instrument == "PERPETUAL" and return_bps < -entry:
            return -1
        if current_direction == 1 and return_bps < exit_threshold:
            return 0
        if current_direction == -1 and return_bps > -exit_threshold:
            return 0
        return current_direction

    if signal_type == "CHANNEL_BREAKOUT":
        entry_window = int(variant["entry_window_hours"])
        exit_window = int(variant["exit_window_hours"])
        if index < max(entry_window, exit_window):
            return 0
        entry_high = max(series.high_price[index - entry_window : index])
        entry_low = min(series.low_price[index - entry_window : index])
        exit_high = max(series.high_price[index - exit_window : index])
        exit_low = min(series.low_price[index - exit_window : index])
        if current_direction == 0:
            if current_close > entry_high:
                return 1
            if instrument == "PERPETUAL" and current_close < entry_low:
                return -1
            return 0
        if current_direction == 1 and current_close < exit_low:
            return 0
        if current_direction == -1 and current_close > exit_high:
            return 0
        return current_direction

    raise ValueError(f"unsupported signal type: {signal_type}")


def target_notional(
    series: MarketSeries,
    index: int,
    per_asset_cap_usd: float,
) -> float:
    annualized_vol = rolling_annualized_volatility(series, index)
    if annualized_vol <= 0 or annualized_vol > 2.50:
        return 0.0
    effective_vol = min(max(annualized_vol, 0.10), 2.50)
    scale = min(1.0, max(0.25, 0.60 / effective_vol))
    return per_asset_cap_usd * scale


def execution_cost_usd(notional_usd: float, cost_bps: float) -> float:
    return max(0.0, notional_usd) * max(0.0, cost_bps) / 10000.0


def funding_cash_flow_usd(direction: int, notional_usd: float, funding_rate: float) -> float:
    if direction not in {-1, 1}:
        raise ValueError("funding direction must be long (+1) or short (-1)")
    return -direction * max(0.0, notional_usd) * float(funding_rate)


def current_position_price_pnl(position: Position, price: float) -> float:
    return position.realized_price_pnl_usd + position.direction * position.quantity * (
        price - position.average_entry_price
    )


def close_position(
    position: Position,
    price: float,
    exit_time_ms: int,
    exit_reason: str,
    profile: DirectionalCostProfile,
    trade_number: int,
) -> dict[str, Any]:
    remaining_price_pnl = position.direction * position.quantity * (
        price - position.average_entry_price
    )
    price_pnl = position.realized_price_pnl_usd + remaining_price_pnl
    exit_notional = position.quantity * price
    exit_cost = execution_cost_usd(exit_notional, profile.exit_cost_bps)
    gross_pnl = price_pnl + position.funding_pnl_usd
    total_cost = position.entry_cost_usd + position.rebalance_cost_usd + exit_cost
    net_pnl = gross_pnl - total_cost
    return {
        "trade_id": f"{position.symbol}-{trade_number:05d}",
        "symbol": position.symbol,
        "instrument": position.instrument,
        "direction": position.direction,
        "entry_time_ms": position.entry_time_ms,
        "exit_time_ms": exit_time_ms,
        "entry_price": position.entry_price,
        "exit_price": price,
        "entry_reason": position.entry_reason,
        "exit_reason": exit_reason,
        "entry_regime": position.entry_regime,
        "initial_notional_usd": position.initial_notional_usd,
        "final_notional_usd": exit_notional,
        "price_pnl_usd": price_pnl,
        "funding_pnl_usd": position.funding_pnl_usd,
        "entry_cost_usd": position.entry_cost_usd,
        "rebalance_cost_usd": position.rebalance_cost_usd,
        "exit_cost_usd": exit_cost,
        "gross_pnl_usd": gross_pnl,
        "net_pnl_usd": net_pnl,
        "rebalance_count": position.rebalance_count,
        "holding_hours": (exit_time_ms - position.entry_time_ms) / HOUR_MS,
        "quarter": quarter_label(exit_time_ms),
    }


def resize_position(
    position: Position,
    price: float,
    target_notional_usd: float,
    execution_time_ms: int,
    profile: DirectionalCostProfile,
) -> float:
    target_quantity = target_notional_usd / price
    delta_quantity = target_quantity - position.quantity
    delta_notional = abs(delta_quantity) * price
    if delta_notional <= 0:
        return 0.0
    if delta_quantity > 0:
        new_quantity = position.quantity + delta_quantity
        position.average_entry_price = (
            position.quantity * position.average_entry_price + delta_quantity * price
        ) / new_quantity
        position.quantity = new_quantity
    else:
        reduced = min(position.quantity, abs(delta_quantity))
        position.realized_price_pnl_usd += position.direction * reduced * (
            price - position.average_entry_price
        )
        position.quantity -= reduced
    cost = execution_cost_usd(delta_notional, profile.entry_cost_bps)
    position.rebalance_cost_usd += cost
    position.current_notional_usd = target_notional_usd
    position.rebalance_count += 1
    position.last_resize_time_ms = execution_time_ms
    return delta_notional


def sample_daily_equity(equity_by_hour: Mapping[int, float]) -> list[tuple[int, float]]:
    daily: list[tuple[int, float]] = []
    for hour in sorted(equity_by_hour):
        dt = datetime.fromtimestamp(hour / 1000, tz=timezone.utc)
        if dt.hour == 23:
            daily.append((hour, float(equity_by_hour[hour])))
    if equity_by_hour:
        final_hour = max(equity_by_hour)
        if not daily or daily[-1][0] != final_hour:
            daily.append((final_hour, float(equity_by_hour[final_hour])))
    return daily


def annualized_sharpe(daily_equity: Sequence[tuple[int, float]]) -> float:
    returns: list[float] = []
    for (_, previous), (_, current) in zip(daily_equity, daily_equity[1:]):
        if previous > 0:
            returns.append(current / previous - 1.0)
    if len(returns) < 2:
        return 0.0
    deviation = statistics.stdev(returns)
    if deviation <= 0:
        return 0.0
    return statistics.fmean(returns) / deviation * math.sqrt(365.0)


def maximum_drawdown_pct(daily_equity: Sequence[tuple[int, float]]) -> float:
    peak = 0.0
    maximum = 0.0
    for _, value in daily_equity:
        peak = max(peak, value)
        if peak > 0:
            maximum = max(maximum, 100.0 * (peak - value) / peak)
    return maximum


def maximum_positive_contribution_pct(values: Mapping[str, float]) -> float:
    positive = [float(value) for value in values.values() if float(value) > 0]
    if not positive:
        return 100.0
    return 100.0 * max(positive) / sum(positive)


def simulate_variant(
    data: Mapping[tuple[str, str], MarketSeries],
    variant: Mapping[str, Any],
    profile_map: Mapping[tuple[str, str, str, str], DirectionalCostProfile],
    scenario_code: str,
    nav_band: str,
) -> dict[str, Any]:
    instrument = str(variant["instrument"])
    selected_series = {symbol: data[(symbol, instrument)] for symbol in SYMBOLS}
    first = selected_series[SYMBOLS[0]]
    nav = next(
        float(item["portfolio_nav_usd"])
        for item in NAV_BANDS
        if item["nav_band"] == nav_band
    )
    per_asset_cap = next(
        float(item["per_asset_cap_usd"])
        for item in NAV_BANDS
        if item["nav_band"] == nav_band
    )

    positions: dict[str, Position | None] = {symbol: None for symbol in SYMBOLS}
    pending: dict[str, PendingAction | None] = {symbol: None for symbol in SYMBOLS}
    cooldown_until: dict[str, int] = {symbol: 0 for symbol in SYMBOLS}
    closed_trades: list[dict[str, Any]] = []
    closed_net_pnl = 0.0
    turnover_usd = 0.0
    equity_by_hour: dict[int, float] = {}
    trade_number = 0
    forced_exit_decision_hour = first.end_ms - 3 * HOUR_MS
    final_execution_hour = first.end_ms - HOUR_MS

    for index, hour in enumerate(first.hours):
        for symbol in SYMBOLS:
            series = selected_series[symbol]
            profile = profile_map[(scenario_code, instrument, symbol, nav_band)]
            action = pending[symbol]
            if action is not None and action.execution_time_ms == hour:
                position = positions[symbol]
                price = series.open_price[index]
                if position is not None and position.direction != action.target_direction:
                    trade_number += 1
                    trade = close_position(
                        position=position,
                        price=price,
                        exit_time_ms=hour,
                        exit_reason=action.reason,
                        profile=profile,
                        trade_number=trade_number,
                    )
                    closed_trades.append(trade)
                    closed_net_pnl += float(trade["net_pnl_usd"])
                    turnover_usd += float(trade["final_notional_usd"])
                    positions[symbol] = None
                    cooldown_until[symbol] = hour + int(variant["cooldown_hours"]) * HOUR_MS
                    position = None

                if action.target_direction != 0:
                    if positions[symbol] is None:
                        if hour >= cooldown_until[symbol]:
                            target = min(action.target_notional_usd, per_asset_cap)
                            if target > 0:
                                quantity = target / price
                                entry_cost = execution_cost_usd(
                                    target, profile.entry_cost_bps
                                )
                                positions[symbol] = Position(
                                    symbol=symbol,
                                    instrument=instrument,
                                    direction=action.target_direction,
                                    entry_time_ms=hour,
                                    entry_price=price,
                                    quantity=quantity,
                                    average_entry_price=price,
                                    initial_notional_usd=target,
                                    current_notional_usd=target,
                                    entry_regime=series.regime_by_hour.get(
                                        hour, "UNCLASSIFIED"
                                    ),
                                    entry_reason=action.reason,
                                    entry_cost_usd=entry_cost,
                                    last_resize_time_ms=hour,
                                )
                                turnover_usd += target
                    elif positions[symbol].direction == action.target_direction:
                        position = positions[symbol]
                        target = min(action.target_notional_usd, per_asset_cap)
                        if position.current_notional_usd > 0:
                            difference = abs(target - position.current_notional_usd)
                            ratio = difference / position.current_notional_usd
                        else:
                            ratio = 1.0
                        if (
                            ratio >= 0.25
                            and hour - position.last_resize_time_ms >= 24 * HOUR_MS
                        ):
                            turnover_usd += resize_position(
                                position=position,
                                price=price,
                                target_notional_usd=target,
                                execution_time_ms=hour,
                                profile=profile,
                            )
                pending[symbol] = None

            position = positions[symbol]
            event = series.funding_by_hour.get(hour)
            if position is not None and instrument == "PERPETUAL" and event is not None:
                actual_time = int(event["actual_time_ms"])
                if position.entry_time_ms < actual_time:
                    current_notional = position.quantity * series.open_price[index]
                    rate = float(event["funding_rate"])
                    position.funding_pnl_usd += funding_cash_flow_usd(
                        position.direction, current_notional, rate
                    )

        if hour == forced_exit_decision_hour:
            for symbol in SYMBOLS:
                pending[symbol] = PendingAction(
                    execution_time_ms=final_execution_hour,
                    target_direction=0,
                    target_notional_usd=0.0,
                    reason="PREDECLARED_END_OF_DEVELOPMENT_EXIT",
                    decision_time_ms=hour + HOUR_MS,
                )
        elif (
            (index + 1) % DECISION_INTERVAL_HOURS == 0
            and hour < forced_exit_decision_hour
        ):
            decision_time = hour + HOUR_MS
            execution_time = decision_time + STRICT_EXECUTION_DELAY_HOURS * HOUR_MS
            if execution_time <= final_execution_hour:
                for symbol in SYMBOLS:
                    if pending[symbol] is not None:
                        continue
                    series = selected_series[symbol]
                    position = positions[symbol]
                    current_direction = position.direction if position is not None else 0
                    target_direction = desired_direction(
                        variant=variant,
                        series=series,
                        index=index,
                        current_direction=current_direction,
                    )
                    if position is not None:
                        minimum_exit_time = (
                            position.entry_time_ms
                            + int(variant["minimum_holding_hours"]) * HOUR_MS
                        )
                        if decision_time < minimum_exit_time and target_direction != current_direction:
                            target_direction = current_direction
                    if target_direction != 0 and decision_time < cooldown_until[symbol]:
                        target_direction = 0
                    notional = (
                        target_notional(series, index, per_asset_cap)
                        if target_direction != 0
                        else 0.0
                    )
                    if notional <= 0:
                        target_direction = 0
                    current_notional = (
                        position.current_notional_usd if position is not None else 0.0
                    )
                    direction_changed = target_direction != current_direction
                    resize_needed = (
                        current_direction != 0
                        and target_direction == current_direction
                        and current_notional > 0
                        and abs(notional - current_notional) / current_notional >= 0.25
                    )
                    if direction_changed or resize_needed:
                        pending[symbol] = PendingAction(
                            execution_time_ms=execution_time,
                            target_direction=target_direction,
                            target_notional_usd=notional,
                            reason=(
                                "SIGNAL_STATE_CHANGE"
                                if direction_changed
                                else "VOLATILITY_TARGET_RESIZE"
                            ),
                            decision_time_ms=decision_time,
                        )

        open_mark = 0.0
        for symbol in SYMBOLS:
            position = positions[symbol]
            if position is None:
                continue
            series = selected_series[symbol]
            profile = profile_map[(scenario_code, instrument, symbol, nav_band)]
            price = series.close_price[index]
            price_pnl = current_position_price_pnl(position, price)
            estimated_exit = execution_cost_usd(
                position.quantity * price, profile.exit_cost_bps
            )
            open_mark += (
                price_pnl
                + position.funding_pnl_usd
                - position.entry_cost_usd
                - position.rebalance_cost_usd
                - estimated_exit
            )
        equity_by_hour[hour] = nav + closed_net_pnl + open_mark

    if any(position is not None for position in positions.values()):
        raise RuntimeError("predeclared final exits did not close every position")

    daily_equity = sample_daily_equity(equity_by_hour)
    net_pnl = sum(float(trade["net_pnl_usd"]) for trade in closed_trades)
    net_return_pct = 100.0 * safe_ratio(net_pnl, nav)
    duration_years = max(
        (first.end_ms - first.start_ms) / (365.0 * 24.0 * HOUR_MS),
        1e-9,
    )
    annualized_return_pct = 100.0 * (
        (max(1e-9, 1.0 + net_pnl / nav) ** (1.0 / duration_years)) - 1.0
    )
    drawdown = maximum_drawdown_pct(daily_equity)
    sharpe = annualized_sharpe(daily_equity)
    calmar = safe_ratio(annualized_return_pct, drawdown, 0.0)

    net_by_asset = {
        symbol: sum(
            float(trade["net_pnl_usd"])
            for trade in closed_trades
            if trade["symbol"] == symbol
        )
        for symbol in SYMBOLS
    }
    net_by_quarter: dict[str, float] = defaultdict(float)
    net_by_regime: dict[str, float] = defaultdict(float)
    for trade in closed_trades:
        net_by_quarter[str(trade["quarter"])] += float(trade["net_pnl_usd"])
        net_by_regime[str(trade["entry_regime"])] += float(trade["net_pnl_usd"])

    entry_cost = sum(float(trade["entry_cost_usd"]) for trade in closed_trades)
    rebalance_cost = sum(float(trade["rebalance_cost_usd"]) for trade in closed_trades)
    exit_cost = sum(float(trade["exit_cost_usd"]) for trade in closed_trades)
    total_execution_cost = entry_cost + rebalance_cost + exit_cost
    positive_gross_profit = sum(
        max(0.0, float(trade["gross_pnl_usd"])) for trade in closed_trades
    )
    funding_pnl = sum(float(trade["funding_pnl_usd"]) for trade in closed_trades)

    return {
        "variant_id": str(variant["variant_id"]),
        "family": str(variant["family"]),
        "instrument": instrument,
        "scenario_code": scenario_code,
        "nav_band": nav_band,
        "portfolio_nav_usd": nav,
        "closed_trade_count": len(closed_trades),
        "gross_pnl_usd": sum(float(trade["gross_pnl_usd"]) for trade in closed_trades),
        "net_pnl_usd": net_pnl,
        "net_return_pct": net_return_pct,
        "annualized_return_pct": annualized_return_pct,
        "sharpe_ratio": sharpe,
        "maximum_drawdown_pct": drawdown,
        "calmar_ratio": calmar,
        "turnover_multiple": safe_ratio(turnover_usd, nav),
        "positive_asset_count": sum(value > 0 for value in net_by_asset.values()),
        "maximum_asset_contribution_pct": maximum_positive_contribution_pct(net_by_asset),
        "maximum_quarter_contribution_pct": maximum_positive_contribution_pct(net_by_quarter),
        "maximum_regime_contribution_pct": maximum_positive_contribution_pct(net_by_regime),
        "cost_to_positive_gross_profit_ratio": safe_ratio(
            total_execution_cost, positive_gross_profit, 999.0
        ),
        "funding_pnl_usd": funding_pnl,
        "execution_cost_usd": total_execution_cost,
        "net_pnl_by_asset": dict(net_by_asset),
        "net_pnl_by_quarter": dict(net_by_quarter),
        "net_pnl_by_regime": dict(net_by_regime),
        "daily_equity": daily_equity,
        "trades": closed_trades,
    }


def simulate_buy_and_hold_benchmarks(
    data: Mapping[tuple[str, str], MarketSeries],
    profiles: Mapping[tuple[str, str, str, str], DirectionalCostProfile],
) -> dict[str, Any]:
    nav = 30000.0
    start_index = 336
    final_index = len(data[("BTCUSDT", "SPOT")].hours) - 1

    def one_portfolio(weights: Mapping[str, float]) -> dict[str, float]:
        equity: list[tuple[int, float]] = []
        initial_cost = 0.0
        quantities: dict[str, float] = {}
        for symbol, weight in weights.items():
            series = data[(symbol, "SPOT")]
            notional = nav * weight
            profile = profiles[(CONSERVATIVE_SCENARIO, "SPOT", symbol, PRIMARY_NAV_BAND)]
            initial_cost += execution_cost_usd(notional, profile.entry_cost_bps)
            quantities[symbol] = notional / series.open_price[start_index]
        equity_by_hour: dict[int, float] = {}
        for index in range(start_index, final_index):
            hour = data[("BTCUSDT", "SPOT")].hours[index]
            marked = nav - initial_cost
            for symbol, quantity in quantities.items():
                series = data[(symbol, "SPOT")]
                entry = series.open_price[start_index]
                marked += quantity * (series.close_price[index] - entry)
            equity_by_hour[hour] = marked
        final_hour = data[("BTCUSDT", "SPOT")].hours[final_index]
        final_value = nav - initial_cost
        exit_cost = 0.0
        for symbol, quantity in quantities.items():
            series = data[(symbol, "SPOT")]
            entry = series.open_price[start_index]
            final_price = series.open_price[final_index]
            final_value += quantity * (final_price - entry)
            final_notional = quantity * final_price
            profile = profiles[(CONSERVATIVE_SCENARIO, "SPOT", symbol, PRIMARY_NAV_BAND)]
            exit_cost += execution_cost_usd(final_notional, profile.exit_cost_bps)
        final_value -= exit_cost
        equity_by_hour[final_hour] = final_value
        daily_equity = sample_daily_equity(equity_by_hour)
        net_return = 100.0 * (final_value / nav - 1.0)
        drawdown = maximum_drawdown_pct(daily_equity)
        years = max(
            (daily_equity[-1][0] - daily_equity[0][0]) / (365.0 * 24.0 * HOUR_MS),
            1e-9,
        )
        annualized = 100.0 * ((max(1e-9, final_value / nav) ** (1.0 / years)) - 1.0)
        return {
            "net_return_pct": net_return,
            "maximum_drawdown_pct": drawdown,
            "calmar_ratio": safe_ratio(annualized, drawdown, 0.0),
            "sharpe_ratio": annualized_sharpe(daily_equity),
        }

    return {
        "CASH": {
            "net_return_pct": 0.0,
            "maximum_drawdown_pct": 0.0,
            "calmar_ratio": 0.0,
            "sharpe_ratio": 0.0,
        },
        "BTC_SPOT_BUY_HOLD": one_portfolio({"BTCUSDT": 1.0}),
        "EQUAL_WEIGHT_SPOT_BUY_HOLD": one_portfolio(
            {symbol: 1.0 / 3.0 for symbol in SYMBOLS}
        ),
    }


def calculate_pbo(primary_results: Mapping[str, Mapping[str, Any]]) -> float:
    variant_ids = sorted(primary_results)
    quarters = sorted(
        set().union(
            *(set(result["net_pnl_by_quarter"]) for result in primary_results.values())
        )
    )
    if len(variant_ids) < 2 or len(quarters) < 4:
        return 1.0
    half = len(quarters) // 2
    failures = 0
    combinations = 0
    for in_sample in itertools.combinations(quarters, half):
        inside = set(in_sample)
        outside = [quarter for quarter in quarters if quarter not in inside]
        inside_scores = {
            variant_id: sum(
                float(primary_results[variant_id]["net_pnl_by_quarter"].get(q, 0.0))
                for q in inside
            )
            for variant_id in variant_ids
        }
        selected = max(variant_ids, key=lambda value: (inside_scores[value], value))
        outside_scores = {
            variant_id: sum(
                float(primary_results[variant_id]["net_pnl_by_quarter"].get(q, 0.0))
                for q in outside
            )
            for variant_id in variant_ids
        }
        ranked = sorted(variant_ids, key=lambda value: (outside_scores[value], value))
        percentile = (ranked.index(selected) + 1) / len(ranked)
        failures += int(percentile <= 0.5)
        combinations += 1
    return failures / combinations if combinations else 1.0


def deflated_sharpe_probability(
    daily_equity: Sequence[tuple[int, float]],
    all_sharpes: Sequence[float],
    trial_count: int,
) -> float:
    returns = [
        current / previous - 1.0
        for (_, previous), (_, current) in zip(daily_equity, daily_equity[1:])
        if previous > 0
    ]
    if len(returns) < 3:
        return 0.0
    observed = annualized_sharpe(daily_equity)
    dispersion = statistics.stdev(all_sharpes) if len(all_sharpes) >= 2 else 0.0
    if trial_count <= 1 or dispersion <= 0:
        benchmark = 0.0
    else:
        normal = NormalDist()
        gamma = 0.5772156649015329
        z1 = normal.inv_cdf(1.0 - 1.0 / trial_count)
        z2 = normal.inv_cdf(1.0 - 1.0 / (trial_count * math.e))
        benchmark = dispersion * ((1.0 - gamma) * z1 + gamma * z2)
    mean = statistics.fmean(returns)
    deviation = statistics.stdev(returns)
    if deviation <= 0:
        return 0.0
    skew = statistics.fmean(((value - mean) / deviation) ** 3 for value in returns)
    kurtosis = statistics.fmean(((value - mean) / deviation) ** 4 for value in returns)
    denominator = 1.0 - skew * observed + ((kurtosis - 1.0) / 4.0) * observed**2
    if denominator <= 0:
        return 0.0
    z_score = (observed - benchmark) * math.sqrt(len(returns) - 1) / math.sqrt(denominator)
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
        "gate_status": "PASS" if passed else "FAIL",
        "observed_value": observed,
        "required_value": required,
        "mandatory": mandatory,
        "gate_reason": reason,
    }


def evaluate_candidate_gates(
    variant: Mapping[str, Any],
    primary: Mapping[str, Any],
    micro: Mapping[str, Any],
    neighbor_results: Sequence[Mapping[str, Any]],
    benchmarks: Mapping[str, Mapping[str, float]],
) -> list[dict[str, Any]]:
    positive_neighbors = sum(
        result["net_return_pct"] > 0 and result["sharpe_ratio"] > 0
        for result in neighbor_results
    )
    neighbor_fraction = safe_ratio(positive_neighbors, len(neighbor_results), 0.0)
    candidate_calmar = float(primary["calmar_ratio"])
    best_benchmark_return = max(
        float(benchmarks["BTC_SPOT_BUY_HOLD"]["net_return_pct"]),
        float(benchmarks["EQUAL_WEIGHT_SPOT_BUY_HOLD"]["net_return_pct"]),
    )
    best_benchmark_calmar = max(
        float(benchmarks["BTC_SPOT_BUY_HOLD"]["calmar_ratio"]),
        float(benchmarks["EQUAL_WEIGHT_SPOT_BUY_HOLD"]["calmar_ratio"]),
    )
    benchmark_superiority = (
        float(primary["net_return_pct"]) > best_benchmark_return
        or candidate_calmar > best_benchmark_calmar * 1.05
    )

    return [
        gate(
            "CONSERVATIVE_NET_RETURN_POSITIVE",
            float(primary["net_return_pct"]) > 0.0,
            primary["net_return_pct"],
            "> 0",
            "Primary NAV must be profitable after conservative directional costs.",
        ),
        gate(
            "CONSERVATIVE_SHARPE",
            float(primary["sharpe_ratio"]) >= 0.50,
            primary["sharpe_ratio"],
            ">= 0.50",
            "Development risk-adjusted performance must be positive and material.",
        ),
        gate(
            "MINIMUM_CLOSED_TRADES",
            int(primary["closed_trade_count"]) >= 12,
            primary["closed_trade_count"],
            ">= 12",
            "A minimum closed-trade sample is required before validation.",
        ),
        gate(
            "MAXIMUM_DRAWDOWN",
            float(primary["maximum_drawdown_pct"]) <= 35.0,
            primary["maximum_drawdown_pct"],
            "<= 35%",
            "Development drawdown must remain within the locked ceiling.",
        ),
        gate(
            "POSITIVE_ASSET_BREADTH",
            int(primary["positive_asset_count"]) >= 2,
            primary["positive_asset_count"],
            ">= 2",
            "At least two assets must contribute positive net PnL.",
        ),
        gate(
            "ASSET_CONCENTRATION",
            float(primary["maximum_asset_contribution_pct"]) <= 75.0,
            primary["maximum_asset_contribution_pct"],
            "<= 75%",
            "No single asset may dominate positive PnL.",
        ),
        gate(
            "QUARTER_CONCENTRATION",
            float(primary["maximum_quarter_contribution_pct"]) <= 65.0,
            primary["maximum_quarter_contribution_pct"],
            "<= 65%",
            "No single quarter may dominate positive PnL.",
        ),
        gate(
            "TURNOVER_LIMIT",
            float(primary["turnover_multiple"]) <= 60.0,
            primary["turnover_multiple"],
            "<= 60x NAV",
            "Turnover must remain compatible with a slower directional strategy.",
        ),
        gate(
            "COST_BURDEN",
            float(primary["cost_to_positive_gross_profit_ratio"]) <= 0.80,
            primary["cost_to_positive_gross_profit_ratio"],
            "<= 0.80",
            "Execution costs may not consume most positive gross profit.",
        ),
        gate(
            "PARAMETER_NEIGHBOR_COUNT",
            len(neighbor_results) >= 1,
            len(neighbor_results),
            ">= 1",
            "The selected point must have preregistered parameter neighbors.",
        ),
        gate(
            "PARAMETER_NEIGHBOR_STABILITY",
            neighbor_fraction >= 0.50,
            neighbor_fraction,
            ">= 0.50",
            "At least half of preregistered neighbors must be directionally positive.",
        ),
        gate(
            "MICRO_NAV_SENSITIVITY",
            float(micro["net_return_pct"]) > 0.0,
            micro["net_return_pct"],
            "> 0",
            "The strategy must remain positive at the micro sensitivity notional.",
        ),
        gate(
            "BENCHMARK_SUPERIORITY",
            benchmark_superiority,
            {
                "candidate_return_pct": primary["net_return_pct"],
                "candidate_calmar": candidate_calmar,
                "best_benchmark_return_pct": best_benchmark_return,
                "best_benchmark_calmar": best_benchmark_calmar,
            },
            "higher return or at least 5% higher Calmar",
            "Positive PnL alone is insufficient; relevant passive benchmarks matter.",
        ),
    ]


def choose_candidate(
    variants: Sequence[Mapping[str, Any]],
    results: Mapping[tuple[str, str, str], Mapping[str, Any]],
    benchmarks: Mapping[str, Mapping[str, float]],
) -> tuple[dict[str, Any] | None, dict[str, list[dict[str, Any]]], list[str]]:
    by_id = {str(variant["variant_id"]): variant for variant in variants}
    gates_by_variant: dict[str, list[dict[str, Any]]] = {}
    eligible: list[str] = []
    for variant_id, variant in by_id.items():
        primary = results[(variant_id, CONSERVATIVE_SCENARIO, PRIMARY_NAV_BAND)]
        micro = results[(variant_id, CONSERVATIVE_SCENARIO, "MICRO_3K")]
        neighbor_results = [
            results[(neighbor_id, CONSERVATIVE_SCENARIO, PRIMARY_NAV_BAND)]
            for neighbor_id in variant["neighbor_ids"]
        ]
        gates = evaluate_candidate_gates(
            variant=variant,
            primary=primary,
            micro=micro,
            neighbor_results=neighbor_results,
            benchmarks=benchmarks,
        )
        gates_by_variant[variant_id] = gates
        if all(item["gate_status"] == "PASS" for item in gates if item["mandatory"]):
            eligible.append(variant_id)

    if not eligible:
        return None, gates_by_variant, []

    family_order = {"SPOT_TREND": 1, "PERPETUAL_TREND": 2, "VOLATILITY_BREAKOUT": 3}

    def ranking(variant_id: str) -> tuple[float, float, float, float, float, float, str]:
        variant = by_id[variant_id]
        result = results[(variant_id, CONSERVATIVE_SCENARIO, PRIMARY_NAV_BAND)]
        return (
            float(result["net_return_pct"]),
            float(result["calmar_ratio"]),
            float(result["sharpe_ratio"]),
            -float(result["maximum_drawdown_pct"]),
            -float(result["turnover_multiple"]),
            -float(family_order[str(variant["family"])]),
            variant_id,
        )

    selected_id = max(eligible, key=ranking)
    return deepcopy(dict(by_id[selected_id])), gates_by_variant, sorted(eligible)


def decision_for_selection(
    selected: Mapping[str, Any] | None,
    gates_by_variant: Mapping[str, Sequence[Mapping[str, Any]]],
    results: Mapping[tuple[str, str, str], Mapping[str, Any]],
) -> tuple[str, str, str]:
    if selected is not None:
        family = str(selected["family"])
        if family == "SPOT_TREND":
            return DECISION_SPOT, MISSION91_READY, "MISSION91_FIXED_VALIDATION_AND_ROBUSTNESS_PACK"
        if family == "PERPETUAL_TREND":
            return DECISION_PERPETUAL, MISSION91_READY, "MISSION91_FIXED_VALIDATION_AND_ROBUSTNESS_PACK"
        if family == "VOLATILITY_BREAKOUT":
            return DECISION_BREAKOUT, MISSION91_READY, "MISSION91_FIXED_VALIDATION_AND_ROBUSTNESS_PACK"
        raise RuntimeError(f"unknown selected family: {family}")

    insufficient_gate_names = {
        "MINIMUM_CLOSED_TRADES",
        "PARAMETER_NEIGHBOR_COUNT",
        "PARAMETER_NEIGHBOR_STABILITY",
    }
    for variant_id, gates in gates_by_variant.items():
        primary = results[(variant_id, CONSERVATIVE_SCENARIO, PRIMARY_NAV_BAND)]
        if float(primary["net_return_pct"]) <= 0:
            continue
        failed = {
            str(item["gate_name"])
            for item in gates
            if item["mandatory"] and item["gate_status"] == "FAIL"
        }
        if failed and failed.issubset(insufficient_gate_names):
            return (
                DECISION_CONTINUE,
                MISSION91_PAUSED,
                "DIRECTIONAL_DATA_COLLECTION_AND_REASSESSMENT",
            )
    return (
        DECISION_REJECT,
        MISSION91_NOT_AUTHORIZED,
        "NEW_ECONOMIC_HYPOTHESIS_DISCOVERY",
    )


def build_charter_payload(
    protocol_digest: str,
    decision: str,
    selected: Mapping[str, Any] | None,
    selected_result: Mapping[str, Any] | None,
    mission91_status: str,
    next_workstream: str,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    splits = {str(item["name"]): item for item in contract["research_splits"]}
    return {
        "charter_id": CHARTER_ID,
        "source_protocol_id": PROTOCOL_ID,
        "source_protocol_hash": protocol_digest,
        "source_mission89_decision": "REJECT_AND_ARCHIVE_FUNDING_CARRY",
        "funding_carry_status": "ARCHIVED_AFTER_BASELINE_FALSIFICATION",
        "decision": decision,
        "selected_variant": deepcopy(dict(selected)) if selected is not None else None,
        "selected_development_result": (
            {
                key: selected_result[key]
                for key in (
                    "variant_id",
                    "family",
                    "instrument",
                    "scenario_code",
                    "nav_band",
                    "closed_trade_count",
                    "net_return_pct",
                    "sharpe_ratio",
                    "maximum_drawdown_pct",
                    "calmar_ratio",
                    "turnover_multiple",
                )
            }
            if selected_result is not None
            else None
        ),
        "locked_execution": {
            "decision_interval_hours": DECISION_INTERVAL_HOURS,
            "strict_execution_delay_hours": STRICT_EXECUTION_DELAY_HOURS,
            "same_bar_execution_allowed": False,
            "next_hour_open_only": True,
        },
        "locked_portfolio": {
            "primary_nav_band": PRIMARY_NAV_BAND,
            "maximum_gross_exposure_multiple": 1.0,
            "maximum_asset_fraction": 1.0 / 3.0,
            "volatility_scaled_entry_sizing": True,
            "leverage_escalation_allowed": False,
        },
        "locked_cost_model": {
            "model": "MISSION90_SINGLE_LEG_DIRECTIONAL_ASSUMPTION_MODEL",
            "mandatory_scenario": CONSERVATIVE_SCENARIO,
            "severe_scenario_role": "DIAGNOSTIC_ONLY",
            "historical_order_book_calibrated": False,
            "cost_reduction_after_results_allowed": False,
        },
        "mission91_evaluation": {
            "status": mission91_status,
            "next_workstream": next_workstream,
            "validation_split": deepcopy(splits["validation"]),
            "untouched_holdout_split": deepcopy(splits["untouched_holdout"]),
            "candidate_replacement_allowed": False,
            "parameter_retuning_allowed": False,
            "validation_performance_already_read": False,
            "holdout_performance_already_read": False,
        },
        "forbidden_actions": [
            "LIVE_TRADING",
            "ORDER_SUBMISSION",
            "PRIVATE_KEY_USE",
            "CAPITAL_DEPLOYMENT",
            "MACHINE_LEARNING_RESCUE",
            "POST_SELECTION_PARAMETER_TUNING",
            "FALLBACK_CANDIDATE_AFTER_VALIDATION_FAILURE",
            "FUNDING_CARRY_REOPENING",
        ],
    }


def write_runtime_report(
    path_value: str | Path,
    report_core: Mapping[str, Any],
    created_at: str,
) -> tuple[str, dict[str, Any]]:
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = payload_hash(report_core)
    envelope = {
        "report": deepcopy(dict(report_core)),
        "report_hash_sha256": digest,
        "created_at": created_at,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(envelope, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return digest, envelope


def persist_results(
    conn: sqlite3.Connection,
    *,
    run_label: str,
    created_at: str,
    protocol_envelope: Mapping[str, Any],
    charter_envelope: Mapping[str, Any],
    charter_path: str | Path,
    report_hash: str,
    report_path: str | Path,
    report_envelope: Mapping[str, Any],
    summary: Mapping[str, Any],
    cost_profiles: Mapping[tuple[str, str, str, str], DirectionalCostProfile],
    results: Mapping[tuple[str, str, str], Mapping[str, Any]],
    gates_by_variant: Mapping[str, Sequence[Mapping[str, Any]]],
    selected_result: Mapping[str, Any] | None,
) -> None:
    protocol_digest = str(protocol_envelope["protocol_hash_sha256"])
    charter_digest = str(charter_envelope["charter_hash_sha256"])
    conn.execute(
        """
        INSERT OR REPLACE INTO mission90_protocols (
            protocol_id, protocol_hash, locked_at, protocol_json
        ) VALUES (?, ?, ?, ?)
        """,
        (
            PROTOCOL_ID,
            protocol_digest,
            str(protocol_envelope["locked_at"]),
            canonical_json(protocol_envelope["protocol"]),
        ),
    )

    conn.execute(
        "DELETE FROM mission90_directional_cost_profiles WHERE protocol_hash = ?",
        (protocol_digest,),
    )
    for profile in cost_profiles.values():
        payload = cost_profile_dict(profile)
        conn.execute(
            """
            INSERT INTO mission90_directional_cost_profiles (
                protocol_hash, scenario_code, scenario_rank, instrument,
                symbol, nav_band, nav_rank, portfolio_nav_usd,
                per_asset_cap_usd, entry_cost_bps, exit_cost_bps,
                uncertainty_label, profile_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                protocol_digest,
                profile.scenario_code,
                profile.scenario_rank,
                profile.instrument,
                profile.symbol,
                profile.nav_band,
                profile.nav_rank,
                profile.portfolio_nav_usd,
                profile.per_asset_cap_usd,
                profile.entry_cost_bps,
                profile.exit_cost_bps,
                profile.uncertainty_label,
                canonical_json(payload),
            ),
        )

    for table in (
        "mission90_variant_results",
        "mission90_variant_gates",
        "mission90_selected_trade_ledger",
    ):
        conn.execute(f"DELETE FROM {table} WHERE run_label = ?", (run_label,))
    conn.execute("DELETE FROM mission90_runs WHERE run_label = ?", (run_label,))
    conn.execute("DELETE FROM mission90_reports WHERE run_label = ?", (run_label,))

    for result in results.values():
        persisted = {key: value for key, value in result.items() if key not in {"daily_equity", "trades"}}
        conn.execute(
            """
            INSERT INTO mission90_variant_results (
                run_label, variant_id, family, instrument, scenario_code,
                nav_band, closed_trade_count, net_pnl_usd, net_return_pct,
                annualized_return_pct, sharpe_ratio, maximum_drawdown_pct,
                calmar_ratio, turnover_multiple, positive_asset_count,
                maximum_asset_contribution_pct,
                maximum_quarter_contribution_pct,
                cost_to_positive_gross_profit_ratio, funding_pnl_usd,
                result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_label,
                result["variant_id"],
                result["family"],
                result["instrument"],
                result["scenario_code"],
                result["nav_band"],
                result["closed_trade_count"],
                result["net_pnl_usd"],
                result["net_return_pct"],
                result["annualized_return_pct"],
                result["sharpe_ratio"],
                result["maximum_drawdown_pct"],
                result["calmar_ratio"],
                result["turnover_multiple"],
                result["positive_asset_count"],
                result["maximum_asset_contribution_pct"],
                result["maximum_quarter_contribution_pct"],
                result["cost_to_positive_gross_profit_ratio"],
                result["funding_pnl_usd"],
                canonical_json(persisted),
            ),
        )

    for variant_id, gates in gates_by_variant.items():
        for item in gates:
            conn.execute(
                """
                INSERT INTO mission90_variant_gates (
                    run_label, variant_id, gate_name, gate_status,
                    observed_value, required_value, mandatory, gate_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_label,
                    variant_id,
                    item["gate_name"],
                    item["gate_status"],
                    canonical_json(item["observed_value"]),
                    canonical_json(item["required_value"]),
                    int(bool(item["mandatory"])),
                    item["gate_reason"],
                ),
            )

    if selected_result is not None:
        for trade in selected_result["trades"]:
            conn.execute(
                """
                INSERT INTO mission90_selected_trade_ledger (
                    run_label, trade_id, variant_id, symbol, instrument,
                    direction, entry_time_ms, exit_time_ms, entry_price,
                    exit_price, price_pnl_usd, funding_pnl_usd,
                    entry_cost_usd, rebalance_cost_usd, exit_cost_usd,
                    gross_pnl_usd, net_pnl_usd, trade_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_label,
                    trade["trade_id"],
                    selected_result["variant_id"],
                    trade["symbol"],
                    trade["instrument"],
                    trade["direction"],
                    trade["entry_time_ms"],
                    trade["exit_time_ms"],
                    trade["entry_price"],
                    trade["exit_price"],
                    trade["price_pnl_usd"],
                    trade["funding_pnl_usd"],
                    trade["entry_cost_usd"],
                    trade["rebalance_cost_usd"],
                    trade["exit_cost_usd"],
                    trade["gross_pnl_usd"],
                    trade["net_pnl_usd"],
                    canonical_json(trade),
                ),
            )

    conn.execute(
        """
        INSERT OR REPLACE INTO mission90_strategy_charters (
            charter_id, run_label, charter_hash, created_at, charter_path,
            charter_json, decision
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            CHARTER_ID,
            run_label,
            charter_digest,
            created_at,
            str(charter_path),
            canonical_json(charter_envelope),
            summary["decision"],
        ),
    )

    conn.execute(
        """
        INSERT INTO mission90_reports (
            run_label, report_hash, report_path, created_at, report_json
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
        INSERT INTO mission90_runs (
            run_label, protocol_id, protocol_hash, charter_id, charter_hash,
            source_mission89_protocol_hash, source_mission89_report_hash,
            created_at, mission90_status, decision, selected_variant_id,
            selected_family, development_variant_count, evaluation_count,
            eligible_candidate_count, development_rows_read,
            validation_rows_read, holdout_rows_read,
            maximum_timestamp_read_ms, validation_start_ms, pbo,
            selected_deflated_sharpe_probability, mission91_status,
            next_workstream, live_trading, live_order_sent,
            capital_deployment, profitability_claimed, report_hash,
            summary_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_label,
            PROTOCOL_ID,
            protocol_digest,
            CHARTER_ID,
            charter_digest,
            EXPECTED_SOURCE_MISSION89_PROTOCOL_HASH,
            EXPECTED_SOURCE_MISSION89_REPORT_HASH,
            created_at,
            MISSION90_STATUS,
            summary["decision"],
            summary["selected_variant_id"],
            summary["selected_family"],
            summary["development_variant_count"],
            summary["evaluation_count"],
            summary["eligible_candidate_count"],
            summary["development_rows_read"],
            summary["validation_rows_read"],
            summary["holdout_rows_read"],
            summary["maximum_timestamp_read_ms"],
            summary["validation_start_ms"],
            summary["pbo"],
            summary["selected_deflated_sharpe_probability"],
            summary["mission91_status"],
            summary["next_workstream"],
            LIVE_TRADING,
            LIVE_ORDER_SENT,
            CAPITAL_DEPLOYMENT,
            0,
            report_hash,
            canonical_json(summary),
        ),
    )
    conn.commit()


def run_tournament(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    source_contract_path: str | Path = DEFAULT_SOURCE_CONTRACT_PATH,
    protocol_path: str | Path = DEFAULT_PROTOCOL_PATH,
    charter_path: str | Path = DEFAULT_CHARTER_PATH,
    report_path: str | Path = DEFAULT_REPORT_PATH,
    run_label: str = "mission90-local-check",
    created_at: str | None = None,
) -> dict[str, Any]:
    created_at = created_at or utc_now()
    contract = load_authoritative_contract(source_contract_path)
    ensure_schema(db_path)
    protocol_envelope = lock_json_envelope(
        path_value=protocol_path,
        payload_key="protocol",
        payload=EVALUATION_PROTOCOL,
        status="LOCKED_BEFORE_MISSION90_DEVELOPMENT_RESULT_EVALUATION",
        locked_at=created_at,
    )
    protocol_digest = str(protocol_envelope["protocol_hash_sha256"])

    with sqlite3.connect(Path(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        validate_source_mission89(conn)
        data, data_audit = load_development_data(conn, contract)
        cost_profiles = build_directional_cost_profiles(contract)
        benchmarks = simulate_buy_and_hold_benchmarks(data, cost_profiles)

        results: dict[tuple[str, str, str], dict[str, Any]] = {}
        for variant in VARIANTS:
            for scenario in COST_SCENARIOS:
                for band in NAV_BANDS:
                    result = simulate_variant(
                        data=data,
                        variant=variant,
                        profile_map=cost_profiles,
                        scenario_code=str(scenario["scenario_code"]),
                        nav_band=str(band["nav_band"]),
                    )
                    results[(
                        str(variant["variant_id"]),
                        str(scenario["scenario_code"]),
                        str(band["nav_band"]),
                    )] = result

        primary_conservative = {
            str(variant["variant_id"]): results[(
                str(variant["variant_id"]),
                CONSERVATIVE_SCENARIO,
                PRIMARY_NAV_BAND,
            )]
            for variant in VARIANTS
        }
        pbo = calculate_pbo(primary_conservative)
        all_sharpes = [
            float(result["sharpe_ratio"])
            for result in primary_conservative.values()
        ]
        selected, gates_by_variant, eligible_ids = choose_candidate(
            variants=VARIANTS,
            results=results,
            benchmarks=benchmarks,
        )
        decision, mission91_status, next_workstream = decision_for_selection(
            selected=selected,
            gates_by_variant=gates_by_variant,
            results=results,
        )
        if decision not in VALID_DECISIONS:
            raise RuntimeError("invalid Mission 90 decision")

        selected_result = None
        selected_dsr = 0.0
        if selected is not None:
            selected_result = results[(
                str(selected["variant_id"]),
                CONSERVATIVE_SCENARIO,
                PRIMARY_NAV_BAND,
            )]
            selected_dsr = deflated_sharpe_probability(
                selected_result["daily_equity"],
                all_sharpes,
                len(VARIANTS),
            )

        charter_payload = build_charter_payload(
            protocol_digest=protocol_digest,
            decision=decision,
            selected=selected,
            selected_result=selected_result,
            mission91_status=mission91_status,
            next_workstream=next_workstream,
            contract=contract,
        )
        charter_envelope = lock_json_envelope(
            path_value=charter_path,
            payload_key="charter",
            payload=charter_payload,
            status=(
                "LOCKED_FOR_MISSION91_FIXED_VALIDATION"
                if selected is not None
                else "LOCKED_NO_MISSION91_CANDIDATE"
            ),
            locked_at=created_at,
        )

        compact_results = []
        for key in sorted(results):
            result = results[key]
            compact_results.append(
                {
                    field: result[field]
                    for field in (
                        "variant_id",
                        "family",
                        "instrument",
                        "scenario_code",
                        "nav_band",
                        "closed_trade_count",
                        "net_pnl_usd",
                        "net_return_pct",
                        "annualized_return_pct",
                        "sharpe_ratio",
                        "maximum_drawdown_pct",
                        "calmar_ratio",
                        "turnover_multiple",
                        "positive_asset_count",
                        "maximum_asset_contribution_pct",
                        "maximum_quarter_contribution_pct",
                        "cost_to_positive_gross_profit_ratio",
                        "funding_pnl_usd",
                    )
                }
            )

        report_core = {
            "run_label": run_label,
            "protocol_id": PROTOCOL_ID,
            "protocol_hash": protocol_digest,
            "charter_id": CHARTER_ID,
            "charter_hash": charter_envelope["charter_hash_sha256"],
            "source_mission89_decision": "REJECT_AND_ARCHIVE_FUNDING_CARRY",
            "decision": decision,
            "selected_variant": deepcopy(dict(selected)) if selected is not None else None,
            "eligible_candidate_ids": eligible_ids,
            "benchmarks": benchmarks,
            "pbo": pbo,
            "selected_deflated_sharpe_probability": selected_dsr,
            "data_audit": data_audit,
            "directional_cost_profiles": [
                cost_profile_dict(profile)
                for _, profile in sorted(cost_profiles.items())
            ],
            "variant_results": compact_results,
            "candidate_gates": gates_by_variant,
            "research_boundary": {
                "development_performance_evaluated": True,
                "validation_performance_evaluated": False,
                "holdout_performance_evaluated": False,
                "live_trading": LIVE_TRADING,
                "live_order_sent": LIVE_ORDER_SENT,
                "capital_deployment": CAPITAL_DEPLOYMENT,
                "profitability_claimed": False,
            },
        }
        report_digest, report_envelope = write_runtime_report(
            path_value=report_path,
            report_core=report_core,
            created_at=created_at,
        )

        summary = {
            "run_label": run_label,
            "protocol_id": PROTOCOL_ID,
            "protocol_hash": protocol_digest,
            "charter_id": CHARTER_ID,
            "charter_hash": charter_envelope["charter_hash_sha256"],
            "report_hash": report_digest,
            "mission90_status": MISSION90_STATUS,
            "decision": decision,
            "selected_variant_id": (
                str(selected["variant_id"]) if selected is not None else None
            ),
            "selected_family": (
                str(selected["family"]) if selected is not None else None
            ),
            "development_variant_count": len(VARIANTS),
            "evaluation_count": len(results),
            "eligible_candidate_count": len(eligible_ids),
            "development_rows_read": data_audit["development_rows_read"],
            "validation_rows_read": 0,
            "holdout_rows_read": 0,
            "maximum_timestamp_read_ms": data_audit["maximum_timestamp_read_ms"],
            "validation_start_ms": data_audit["validation_start_ms"],
            "pbo": pbo,
            "selected_deflated_sharpe_probability": selected_dsr,
            "mission91_status": mission91_status,
            "next_workstream": next_workstream,
            "live_trading": LIVE_TRADING,
            "live_order_sent": LIVE_ORDER_SENT,
            "capital_deployment": CAPITAL_DEPLOYMENT,
            "profitability_claimed": 0,
            "report_path": str(report_path),
            "protocol_path": str(protocol_path),
            "charter_path": str(charter_path),
        }

        persist_results(
            conn,
            run_label=run_label,
            created_at=created_at,
            protocol_envelope=protocol_envelope,
            charter_envelope=charter_envelope,
            charter_path=charter_path,
            report_hash=report_digest,
            report_path=report_path,
            report_envelope=report_envelope,
            summary=summary,
            cost_profiles=cost_profiles,
            results=results,
            gates_by_variant=gates_by_variant,
            selected_result=selected_result,
        )

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mission 90 directional strategy tournament and charter lock"
    )
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument(
        "--source-contract-path", default=str(DEFAULT_SOURCE_CONTRACT_PATH)
    )
    parser.add_argument("--protocol-path", default=str(DEFAULT_PROTOCOL_PATH))
    parser.add_argument("--charter-path", default=str(DEFAULT_CHARTER_PATH))
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--run-label", default="mission90-local-check")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    summary = run_tournament(
        db_path=args.db_path,
        source_contract_path=args.source_contract_path,
        protocol_path=args.protocol_path,
        charter_path=args.charter_path,
        report_path=args.report_path,
        run_label=args.run_label,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Mission 82: Paper Execution Agent.

This module converts Mission 81 autonomous paper-only observe signals into
paper execution records.

Boundary:
- paper execution records may be created
- live trading remains disabled
- capital deployment remains blocked
- model training remains disabled
- exchange execution remains disabled
- private keys are not used
- no live orders are sent
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE_RUNS_TABLE = "ai_autonomous_paper_signal_runs"
SOURCE_SIGNALS_TABLE = "ai_autonomous_paper_signals"
SOURCE_CHECKS_TABLE = "ai_autonomous_paper_signal_checks"

RUNS_TABLE = "ai_paper_execution_agent_runs"
EXECUTIONS_TABLE = "ai_paper_execution_records"
CHECKS_TABLE = "ai_paper_execution_agent_checks"
REPORTS_TABLE = "ai_paper_execution_agent_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

SOURCE_ENGINE_STATE_READY = "AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_READY_PAPER_ONLY"
SOURCE_ENGINE_DECISION_READY = "AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_APPROVED_FOR_PAPER_EXECUTION_AGENT"
SOURCE_VERDICT_READY = "AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_READY_SHADOW_ONLY"

PAPER_EXECUTION_SCOPE = "PAPER_EXECUTION_AGENT_PAPER_ONLY"
PAPER_EXECUTION_MODE = "PAPER_EXECUTION_RECORD_ONLY_NO_EXCHANGE_ORDER"
PAPER_EXECUTION_STATUS_READY = "AI_PAPER_EXECUTION_RECORDED_PAPER_ONLY"
PAPER_EXECUTION_STATUS_BLOCKED = "AI_PAPER_EXECUTION_BLOCKED"
PAPER_EXECUTION_ACTION = "PAPER_EXECUTION_RECORD_ONLY_NO_ORDER"
PAPER_FILL_STATUS = "NO_FILL_OBSERVE_ONLY"

NO_LIVE_SIGNAL = "NO_LIVE_SIGNAL"
NO_EXECUTION = "NO_EXCHANGE_EXECUTION"
NO_EXCHANGE_ORDER = "NO_EXCHANGE_ORDER"
NO_CAPITAL_DEPLOYMENT = "NO_CAPITAL_DEPLOYMENT"
KEEP_MODEL_TRAINING_DISABLED = "KEEP_MODEL_TRAINING_DISABLED"

CHECK_PASS = "AI_PAPER_EXECUTION_AGENT_CHECK_PASS"
CHECK_FAIL = "AI_PAPER_EXECUTION_AGENT_CHECK_FAIL"

ENGINE_STATE_READY = "AI_PAPER_EXECUTION_AGENT_READY_PAPER_ONLY"
ENGINE_STATE_UNSTABLE = "AI_PAPER_EXECUTION_AGENT_UNSTABLE"
ENGINE_STATE_BLOCKED = "AI_PAPER_EXECUTION_AGENT_BLOCKED"
ENGINE_STATE_MISSING = "AI_PAPER_EXECUTION_AGENT_MISSING"

ENGINE_DECISION_READY = "AI_PAPER_EXECUTION_AGENT_APPROVED_FOR_SELF_LEARNING_FEEDBACK_LOOP"
ENGINE_DECISION_UNSTABLE = "AI_PAPER_EXECUTION_AGENT_REVIEW_REQUIRED"
ENGINE_DECISION_BLOCK_SAFETY = "AI_PAPER_EXECUTION_AGENT_BLOCKED_BY_SAFETY_POLICY"
ENGINE_DECISION_REJECT_MISSING = "AI_PAPER_EXECUTION_AGENT_REJECTED_MISSING_SIGNALS"

VERDICT_READY = "AI_PAPER_EXECUTION_AGENT_READY_SHADOW_ONLY"
VERDICT_UNSTABLE = "AI_PAPER_EXECUTION_AGENT_UNSTABLE_SHADOW_ONLY"
VERDICT_BLOCKED = "AI_PAPER_EXECUTION_AGENT_BLOCKED_SHADOW_ONLY"
VERDICT_MISSING = "AI_PAPER_EXECUTION_AGENT_MISSING_EVIDENCE"

ACTION_READY = "HAND_OFF_PAPER_EXECUTIONS_TO_SELF_LEARNING_FEEDBACK_LOOP"
ACTION_REVIEW_UNSTABLE = "REVIEW_PAPER_EXECUTION_AGENT_EVIDENCE"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_PAPER_EXECUTION_AGENT_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_AUTONOMOUS_PAPER_SIGNAL_ENGINE"

NEXT_READY = "Mission 83 Self-Learning Feedback Loop"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_execution_run_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission82-paper-execution-agent-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission82-paper-execution-agent-report-{stamp}-{uuid.uuid4().hex[:8]}"


def safe_float(value: Any) -> float:
    try:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return 0.0
        return number
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def round8(value: float) -> float:
    return round(float(value), 8)


def row_get(row: sqlite3.Row | dict[str, Any] | None, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        if key in row.keys():
            return row[key]
    except Exception:
        pass
    return default


def parse_labels(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return ["mission81-final-check"]

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    labels: list[str] = []

    for item in raw_items:
        label = str(item).strip()
        if not label:
            continue
        if any(ch.isspace() for ch in label):
            raise ValueError(f"Invalid signal run label: {label}")
        if label not in labels:
            labels.append(label)

    if not labels:
        raise ValueError("At least one signal run label is required")

    return labels


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not table_exists(conn, table_name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def order_clause(conn: sqlite3.Connection, table_name: str, fallback_column: str) -> str:
    cols = table_columns(conn, table_name)
    if "created_at" in cols and fallback_column in cols:
        return f"created_at ASC, {fallback_column} ASC"
    if fallback_column in cols:
        return f"{fallback_column} ASC"
    return "rowid ASC"


def ensure_schema(db_path: str | Path) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_paper_execution_agent_runs (
                execution_run_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_signal_run_label TEXT NOT NULL,
                source_policy_run_label TEXT,
                source_recommendation_run_label TEXT,
                source_governance_review_label TEXT,
                source_evaluation_label TEXT,
                source_guard_review_label TEXT,
                source_collection_label TEXT,
                source_registry_label TEXT,
                source_build_label TEXT,
                source_schedule_label TEXT,
                source_learning_run_label TEXT,
                source_multi_cycle_track_label TEXT,
                source_session_label TEXT,
                source_portfolio_label TEXT,
                paper_execution_scope TEXT NOT NULL,
                paper_execution_mode TEXT NOT NULL,
                paper_execution_count INTEGER NOT NULL,
                recorded_execution_count INTEGER NOT NULL,
                blocked_execution_count INTEGER NOT NULL,
                paper_only_execution_count INTEGER NOT NULL,
                no_live_signal_count INTEGER NOT NULL,
                no_exchange_order_count INTEGER NOT NULL,
                no_capital_deployment_count INTEGER NOT NULL,
                no_model_training_count INTEGER NOT NULL,
                zero_quantity_execution_count INTEGER NOT NULL,
                zero_notional_execution_count INTEGER NOT NULL,
                source_paper_signal_count INTEGER NOT NULL,
                source_ready_signal_count INTEGER NOT NULL,
                source_blocked_signal_count INTEGER NOT NULL,
                source_observe_only_signal_count INTEGER NOT NULL,
                source_no_live_signal_count INTEGER NOT NULL,
                source_no_execution_count INTEGER NOT NULL,
                source_no_capital_deployment_count INTEGER NOT NULL,
                source_training_disabled_count INTEGER NOT NULL,
                source_signal_check_count INTEGER NOT NULL,
                source_pass_check_count INTEGER NOT NULL,
                source_fail_check_count INTEGER NOT NULL,
                execution_check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                leakage_breach_count INTEGER NOT NULL,
                training_eligible_count INTEGER NOT NULL,
                training_locked_count INTEGER NOT NULL,
                baseline_accuracy_pct TEXT NOT NULL,
                average_label_confidence TEXT NOT NULL,
                average_net_paper_outcome_bps TEXT NOT NULL,
                engine_state TEXT NOT NULL,
                engine_decision TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                next_mission TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_paper_execution_records (
                paper_execution_id TEXT PRIMARY KEY,
                execution_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_signal_run_label TEXT NOT NULL,
                source_paper_signal_id TEXT,
                source_paper_signal_code TEXT,
                source_paper_signal_title TEXT,
                execution_rank INTEGER NOT NULL,
                paper_execution_scope TEXT NOT NULL,
                paper_execution_mode TEXT NOT NULL,
                paper_execution_status TEXT NOT NULL,
                paper_execution_action TEXT NOT NULL,
                paper_execution_side TEXT NOT NULL,
                paper_fill_status TEXT NOT NULL,
                requested_quantity TEXT NOT NULL,
                filled_quantity TEXT NOT NULL,
                paper_fill_price TEXT NOT NULL,
                paper_notional_value TEXT NOT NULL,
                paper_fee_value TEXT NOT NULL,
                paper_slippage_value TEXT NOT NULL,
                model_training_action TEXT NOT NULL,
                live_signal_action TEXT NOT NULL,
                exchange_order_action TEXT NOT NULL,
                capital_action TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_paper_execution_agent_checks (
                check_id TEXT PRIMARY KEY,
                execution_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_signal_run_label TEXT NOT NULL,
                check_category TEXT NOT NULL,
                check_name TEXT NOT NULL,
                check_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                threshold_value TEXT NOT NULL,
                check_reason TEXT NOT NULL,
                paper_execution_scope TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_paper_execution_agent_reports (
                report_label TEXT PRIMARY KEY,
                execution_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_signal_run_label TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                report_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL
            )
            """
        )

        conn.commit()


def safety_problem(row: sqlite3.Row | dict[str, Any] | None) -> bool:
    if row is None:
        return False
    return (
        str(row_get(row, "live_trading", LIVE_TRADING_STATUS)) != LIVE_TRADING_STATUS
        or safe_int(row_get(row, "live_order_sent", LIVE_ORDER_SENT_VALUE)) != LIVE_ORDER_SENT_VALUE
        or str(row_get(row, "capital_deployment", CAPITAL_DEPLOYMENT_STATUS)) != CAPITAL_DEPLOYMENT_STATUS
    )


def load_signal_run(conn: sqlite3.Connection, label: str) -> sqlite3.Row | None:
    if not table_exists(conn, SOURCE_RUNS_TABLE):
        return None
    return conn.execute(
        "SELECT * FROM ai_autonomous_paper_signal_runs WHERE signal_run_label = ?",
        (label,),
    ).fetchone()


def load_paper_signals(conn: sqlite3.Connection, label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, SOURCE_SIGNALS_TABLE):
        return []
    order_by = order_clause(conn, SOURCE_SIGNALS_TABLE, "signal_rank")
    return conn.execute(
        f"SELECT * FROM ai_autonomous_paper_signals WHERE signal_run_label = ? ORDER BY {order_by}",
        (label,),
    ).fetchall()


def load_signal_checks(conn: sqlite3.Connection, label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, SOURCE_CHECKS_TABLE):
        return []
    order_by = order_clause(conn, SOURCE_CHECKS_TABLE, "check_id")
    return conn.execute(
        f"SELECT * FROM ai_autonomous_paper_signal_checks WHERE signal_run_label = ? ORDER BY {order_by}",
        (label,),
    ).fetchall()


def base_metadata(role: str) -> dict[str, Any]:
    return {
        "paper_execution_role": role,
        "paper_execution_scope": PAPER_EXECUTION_SCOPE,
        "paper_only": True,
        "model_training_enabled": False,
        "live_signal_generation_enabled": False,
        "exchange_order_enabled": False,
        "execution_role": "PAPER_RECORD_ONLY",
        "private_keys_used": False,
        "orders_sent": False,
        "paid_api_used": False,
        "real_capital_used": False,
        "autonomous_trading_enabled": False,
        "automatic_strategy_reweighting_enabled": False,
        "not_profitability_claim": True,
    }


def source_signal_is_ready(source_run: sqlite3.Row | None) -> bool:
    if source_run is None:
        return False
    return (
        row_get(source_run, "engine_state", "") == SOURCE_ENGINE_STATE_READY
        and row_get(source_run, "engine_decision", "") == SOURCE_ENGINE_DECISION_READY
        and row_get(source_run, "global_verdict", "") == SOURCE_VERDICT_READY
    )


def build_paper_executions(
    execution_run_label: str,
    created_at: str,
    source_signal_label: str,
    source_run: sqlite3.Row | None,
    paper_signals: list[sqlite3.Row],
) -> list[dict[str, Any]]:
    if source_run is None:
        return []

    if not source_signal_is_ready(source_run):
        return []

    records: list[dict[str, Any]] = []

    for index, signal in enumerate(paper_signals, start=1):
        status = PAPER_EXECUTION_STATUS_READY
        if row_get(signal, "paper_signal_status", "") != "AI_AUTONOMOUS_PAPER_SIGNAL_READY_PAPER_ONLY":
            status = PAPER_EXECUTION_STATUS_BLOCKED

        records.append(
            {
                "paper_execution_id": f"{execution_run_label}-execution-{index}".replace(" ", "_"),
                "execution_run_label": execution_run_label,
                "created_at": created_at,
                "source_signal_run_label": source_signal_label,
                "source_paper_signal_id": row_get(signal, "paper_signal_id", f"{source_signal_label}-signal-{index}"),
                "source_paper_signal_code": row_get(signal, "paper_signal_code", f"PAPER_SIGNAL_{index}"),
                "source_paper_signal_title": row_get(signal, "paper_signal_title", f"Paper signal {index}"),
                "execution_rank": index,
                "paper_execution_scope": PAPER_EXECUTION_SCOPE,
                "paper_execution_mode": PAPER_EXECUTION_MODE,
                "paper_execution_status": status,
                "paper_execution_action": PAPER_EXECUTION_ACTION,
                "paper_execution_side": row_get(signal, "paper_signal_side", "NO_TRADE"),
                "paper_fill_status": PAPER_FILL_STATUS,
                "requested_quantity": "0.0",
                "filled_quantity": "0.0",
                "paper_fill_price": "0.0",
                "paper_notional_value": "0.0",
                "paper_fee_value": "0.0",
                "paper_slippage_value": "0.0",
                "model_training_action": KEEP_MODEL_TRAINING_DISABLED,
                "live_signal_action": NO_LIVE_SIGNAL,
                "exchange_order_action": NO_EXCHANGE_ORDER,
                "capital_action": NO_CAPITAL_DEPLOYMENT,
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT_VALUE,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "metadata": base_metadata("PAPER_EXECUTION_RECORD_ONLY"),
            }
        )

    return records


def make_check(
    execution_run_label: str,
    created_at: str,
    source_signal_label: str,
    category: str,
    name: str,
    passed: bool,
    observed: Any,
    threshold: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{execution_run_label}-{category}-{name}".replace(" ", "_"),
        "execution_run_label": execution_run_label,
        "created_at": created_at,
        "source_signal_run_label": source_signal_label,
        "check_category": category,
        "check_name": name,
        "check_status": CHECK_PASS if passed else CHECK_FAIL,
        "observed_value": str(observed),
        "threshold_value": str(threshold),
        "check_reason": reason,
        "paper_execution_scope": PAPER_EXECUTION_SCOPE,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": base_metadata("PAPER_EXECUTION_AGENT_CHECK"),
    }


def build_missing_checks(execution_run_label: str, created_at: str, source_signal_label: str) -> list[dict[str, Any]]:
    return [
        make_check(
            execution_run_label,
            created_at,
            source_signal_label,
            "availability",
            "source signal run exists",
            False,
            "missing",
            "present",
            "Source Mission 81 signal run is missing.",
        )
    ]


def build_execution_checks(
    execution_run_label: str,
    created_at: str,
    source_signal_label: str,
    source_run: sqlite3.Row,
    source_signals: list[sqlite3.Row],
    source_checks: list[sqlite3.Row],
    executions: list[dict[str, Any]],
    min_executions: int,
) -> list[dict[str, Any]]:
    execution_count = len(executions)
    recorded_count = sum(1 for record in executions if record["paper_execution_status"] == PAPER_EXECUTION_STATUS_READY)
    blocked_count = sum(1 for record in executions if record["paper_execution_status"] == PAPER_EXECUTION_STATUS_BLOCKED)
    paper_only_count = sum(1 for record in executions if record["paper_execution_scope"] == PAPER_EXECUTION_SCOPE)
    no_live_signal_count = sum(1 for record in executions if record["live_signal_action"] == NO_LIVE_SIGNAL)
    no_exchange_order_count = sum(1 for record in executions if record["exchange_order_action"] == NO_EXCHANGE_ORDER)
    no_capital_count = sum(1 for record in executions if record["capital_action"] == NO_CAPITAL_DEPLOYMENT)
    no_training_count = sum(1 for record in executions if record["model_training_action"] == KEEP_MODEL_TRAINING_DISABLED)
    zero_quantity_count = sum(1 for record in executions if safe_float(record["filled_quantity"]) == 0.0)
    zero_notional_count = sum(1 for record in executions if safe_float(record["paper_notional_value"]) == 0.0)

    source_ready = source_signal_is_ready(source_run)
    source_fail_checks = safe_int(row_get(source_run, "fail_check_count", 0))
    safety_count = safe_int(row_get(source_run, "safety_breach_count", 0))
    safety_count += sum(1 for row in [source_run, *source_signals, *source_checks] if safety_problem(row))
    leakage_count = safe_int(row_get(source_run, "leakage_breach_count", 0))
    training_eligible_count = safe_int(row_get(source_run, "training_eligible_count", 0))

    return [
        make_check(execution_run_label, created_at, source_signal_label, "availability", "source signal run exists", True, "present", "present", "Source signal run exists."),
        make_check(execution_run_label, created_at, source_signal_label, "source", "source paper signal engine ready", source_ready, f"state={row_get(source_run, 'engine_state', '')}, decision={row_get(source_run, 'engine_decision', '')}, verdict={row_get(source_run, 'global_verdict', '')}", "ready paper-only signal engine", "Source paper signal engine must be ready."),
        make_check(execution_run_label, created_at, source_signal_label, "source", "source failed checks", source_fail_checks == 0, source_fail_checks, 0, "Source signal failed checks must remain zero."),
        make_check(execution_run_label, created_at, source_signal_label, "safety", "safety breach count", safety_count == 0, safety_count, 0, "Safety breach count must be zero."),
        make_check(execution_run_label, created_at, source_signal_label, "leakage", "leakage breach count", leakage_count == 0, leakage_count, 0, "Leakage breach count must be zero."),
        make_check(execution_run_label, created_at, source_signal_label, "executions", "paper execution count", execution_count >= min_executions, execution_count, f">= {min_executions}", "Paper execution agent must record the minimum execution set."),
        make_check(execution_run_label, created_at, source_signal_label, "executions", "recorded paper executions", recorded_count == execution_count and execution_count > 0, recorded_count, execution_count, "Every paper execution must be recorded as paper-only."),
        make_check(execution_run_label, created_at, source_signal_label, "executions", "blocked paper executions", blocked_count == 0, blocked_count, 0, "No paper execution record should be blocked in the ready path."),
        make_check(execution_run_label, created_at, source_signal_label, "paper_only", "paper only executions", paper_only_count == execution_count and execution_count > 0, paper_only_count, execution_count, "Every execution record must be paper-only."),
        make_check(execution_run_label, created_at, source_signal_label, "live_signal", "no live signals", no_live_signal_count == execution_count and execution_count > 0, no_live_signal_count, execution_count, "Execution records must not generate live signals."),
        make_check(execution_run_label, created_at, source_signal_label, "orders", "no exchange orders", no_exchange_order_count == execution_count and execution_count > 0, no_exchange_order_count, execution_count, "Execution records must not send exchange orders."),
        make_check(execution_run_label, created_at, source_signal_label, "capital", "no capital deployment", no_capital_count == execution_count and execution_count > 0, no_capital_count, execution_count, "Execution records must not deploy capital."),
        make_check(execution_run_label, created_at, source_signal_label, "training_lock", "model training remains disabled", training_eligible_count == 0 and no_training_count == execution_count and execution_count > 0, f"eligible={training_eligible_count}, disabled_executions={no_training_count}", f"eligible=0, disabled_executions={execution_count}", "Paper execution must not unlock model training."),
        make_check(execution_run_label, created_at, source_signal_label, "quantity", "zero filled quantity", zero_quantity_count == execution_count and execution_count > 0, zero_quantity_count, execution_count, "Mission 82 records observe-only no-order executions, so filled quantity must be zero."),
        make_check(execution_run_label, created_at, source_signal_label, "notional", "zero notional value", zero_notional_count == execution_count and execution_count > 0, zero_notional_count, execution_count, "Mission 82 records observe-only no-order executions, so notional value must be zero."),
        make_check(execution_run_label, created_at, source_signal_label, "live_trading", "live trading disabled", str(row_get(source_run, "live_trading", "")) == LIVE_TRADING_STATUS, row_get(source_run, "live_trading", ""), LIVE_TRADING_STATUS, "Live trading must remain disabled."),
        make_check(execution_run_label, created_at, source_signal_label, "capital_deployment", "capital deployment blocked", str(row_get(source_run, "capital_deployment", "")) == CAPITAL_DEPLOYMENT_STATUS, row_get(source_run, "capital_deployment", ""), CAPITAL_DEPLOYMENT_STATUS, "Capital deployment must remain blocked."),
        make_check(execution_run_label, created_at, source_signal_label, "profitability", "no profitability claim", True, "paper execution records are observe-only", "no profitability claim", "Paper execution records are not profitability evidence."),
    ]


def decide_engine_outcome(
    source_run: sqlite3.Row | None,
    checks: list[dict[str, Any]],
) -> tuple[str, str, str, str, str, str]:
    if source_run is None:
        return (
            ENGINE_DECISION_REJECT_MISSING,
            VERDICT_MISSING,
            ACTION_REFRESH,
            "Mission 81 Autonomous Paper Signal Engine",
            ENGINE_STATE_MISSING,
            "Source autonomous paper signal evidence is missing.",
        )

    failed = [check for check in checks if check["check_status"] == CHECK_FAIL]

    if any(check["check_category"] == "safety" for check in failed):
        return (
            ENGINE_DECISION_BLOCK_SAFETY,
            VERDICT_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 82 safety remediation",
            ENGINE_STATE_BLOCKED,
            "Safety invariant failed during paper execution record generation.",
        )

    if failed:
        return (
            ENGINE_DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 81 Autonomous Paper Signal Engine",
            ENGINE_STATE_UNSTABLE,
            "Paper execution agent failed one or more checks.",
        )

    return (
        ENGINE_DECISION_READY,
        VERDICT_READY,
        ACTION_READY,
        NEXT_READY,
        ENGINE_STATE_READY,
        "Paper execution agent recorded paper-only no-order executions. No live trading, capital deployment, model training, or exchange execution is approved.",
    )


def build_summary(
    db_path: str | Path,
    execution_run_label: str,
    report_label: str,
    created_at: str,
    source_signal_label: str,
    source_run: sqlite3.Row | None,
    executions: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    decision: str,
    verdict: str,
    action: str,
    next_mission: str,
    state: str,
    reason: str,
) -> dict[str, Any]:
    execution_count = len(executions)

    return {
        "execution_run_label": execution_run_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_signal_run_label": source_signal_label,
        "source_policy_run_label": row_get(source_run, "source_policy_run_label", None),
        "source_recommendation_run_label": row_get(source_run, "source_recommendation_run_label", None),
        "source_governance_review_label": row_get(source_run, "source_governance_review_label", None),
        "source_evaluation_label": row_get(source_run, "source_evaluation_label", None),
        "source_guard_review_label": row_get(source_run, "source_guard_review_label", None),
        "source_collection_label": row_get(source_run, "source_collection_label", None),
        "source_registry_label": row_get(source_run, "source_registry_label", None),
        "source_build_label": row_get(source_run, "source_build_label", None),
        "source_schedule_label": row_get(source_run, "source_schedule_label", None),
        "source_learning_run_label": row_get(source_run, "source_learning_run_label", None),
        "source_multi_cycle_track_label": row_get(source_run, "source_multi_cycle_track_label", None),
        "source_session_label": row_get(source_run, "source_session_label", None),
        "source_portfolio_label": row_get(source_run, "source_portfolio_label", None),
        "paper_execution_scope": PAPER_EXECUTION_SCOPE,
        "paper_execution_mode": PAPER_EXECUTION_MODE,
        "paper_execution_count": execution_count,
        "recorded_execution_count": sum(1 for record in executions if record["paper_execution_status"] == PAPER_EXECUTION_STATUS_READY),
        "blocked_execution_count": sum(1 for record in executions if record["paper_execution_status"] == PAPER_EXECUTION_STATUS_BLOCKED),
        "paper_only_execution_count": sum(1 for record in executions if record["paper_execution_scope"] == PAPER_EXECUTION_SCOPE),
        "no_live_signal_count": sum(1 for record in executions if record["live_signal_action"] == NO_LIVE_SIGNAL),
        "no_exchange_order_count": sum(1 for record in executions if record["exchange_order_action"] == NO_EXCHANGE_ORDER),
        "no_capital_deployment_count": sum(1 for record in executions if record["capital_action"] == NO_CAPITAL_DEPLOYMENT),
        "no_model_training_count": sum(1 for record in executions if record["model_training_action"] == KEEP_MODEL_TRAINING_DISABLED),
        "zero_quantity_execution_count": sum(1 for record in executions if safe_float(record["filled_quantity"]) == 0.0),
        "zero_notional_execution_count": sum(1 for record in executions if safe_float(record["paper_notional_value"]) == 0.0),
        "source_paper_signal_count": safe_int(row_get(source_run, "paper_signal_count", 0)),
        "source_ready_signal_count": safe_int(row_get(source_run, "ready_signal_count", 0)),
        "source_blocked_signal_count": safe_int(row_get(source_run, "blocked_signal_count", 0)),
        "source_observe_only_signal_count": safe_int(row_get(source_run, "observe_only_signal_count", 0)),
        "source_no_live_signal_count": safe_int(row_get(source_run, "no_live_signal_count", 0)),
        "source_no_execution_count": safe_int(row_get(source_run, "no_execution_count", 0)),
        "source_no_capital_deployment_count": safe_int(row_get(source_run, "no_capital_deployment_count", 0)),
        "source_training_disabled_count": safe_int(row_get(source_run, "training_disabled_count", 0)),
        "source_signal_check_count": safe_int(row_get(source_run, "signal_check_count", 0)),
        "source_pass_check_count": safe_int(row_get(source_run, "pass_check_count", 0)),
        "source_fail_check_count": safe_int(row_get(source_run, "fail_check_count", 0)),
        "execution_check_count": len(checks),
        "pass_check_count": sum(1 for check in checks if check["check_status"] == CHECK_PASS),
        "fail_check_count": sum(1 for check in checks if check["check_status"] == CHECK_FAIL),
        "safety_breach_count": safe_int(row_get(source_run, "safety_breach_count", 0)),
        "leakage_breach_count": safe_int(row_get(source_run, "leakage_breach_count", 0)),
        "training_eligible_count": safe_int(row_get(source_run, "training_eligible_count", 0)),
        "training_locked_count": safe_int(row_get(source_run, "training_locked_count", 0)),
        "baseline_accuracy_pct": round8(safe_float(row_get(source_run, "baseline_accuracy_pct", 0.0))),
        "average_label_confidence": round8(safe_float(row_get(source_run, "average_label_confidence", 0.0))),
        "average_net_paper_outcome_bps": round8(safe_float(row_get(source_run, "average_net_paper_outcome_bps", 0.0))),
        "paper_executions": executions,
        "execution_checks": checks,
        "engine_state": state,
        "engine_decision": decision,
        "global_verdict": verdict,
        "recommended_action": action,
        "next_mission": next_mission,
        "decision_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    execution_lines = [
        f"- #{record['execution_rank']} {record['source_paper_signal_code']}: action={record['paper_execution_action']}, side={record['paper_execution_side']}, fill={record['paper_fill_status']}, status={record['paper_execution_status']}"
        for record in summary["paper_executions"]
    ]

    check_lines = [
        f"- {check['check_category']} / {check['check_name']}: status={check['check_status']}, observed={check['observed_value']}, threshold={check['threshold_value']}"
        for check in summary["execution_checks"]
    ]

    return f"""# DeltaGrid Mission 82 Paper Execution Agent Report

Report label: {summary['report_label']}
Execution run label: {summary['execution_run_label']}
Created at: {summary['created_at']}
Source signal run label: {summary['source_signal_run_label']}
Source policy run label: {summary['source_policy_run_label']}
Source recommendation run label: {summary['source_recommendation_run_label']}
Source governance review label: {summary['source_governance_review_label']}
Source evaluation label: {summary['source_evaluation_label']}
Source guard review label: {summary['source_guard_review_label']}
Source collection label: {summary['source_collection_label']}
Source registry label: {summary['source_registry_label']}
Source build label: {summary['source_build_label']}
Source schedule label: {summary['source_schedule_label']}
Source learning run label: {summary['source_learning_run_label']}
Source multi-cycle track label: {summary['source_multi_cycle_track_label']}
Source session label: {summary['source_session_label']}
Source portfolio label: {summary['source_portfolio_label']}

## Paper Execution Summary

Paper execution scope: {summary['paper_execution_scope']}
Paper execution mode: {summary['paper_execution_mode']}

Paper execution count: {summary['paper_execution_count']}
Recorded execution count: {summary['recorded_execution_count']}
Blocked execution count: {summary['blocked_execution_count']}
Paper-only execution count: {summary['paper_only_execution_count']}
No live signal count: {summary['no_live_signal_count']}
No exchange order count: {summary['no_exchange_order_count']}
No capital deployment count: {summary['no_capital_deployment_count']}
No model training count: {summary['no_model_training_count']}
Zero quantity execution count: {summary['zero_quantity_execution_count']}
Zero notional execution count: {summary['zero_notional_execution_count']}

Source paper signal count: {summary['source_paper_signal_count']}
Source ready signal count: {summary['source_ready_signal_count']}
Source blocked signal count: {summary['source_blocked_signal_count']}
Source observe-only signal count: {summary['source_observe_only_signal_count']}
Source no live signal count: {summary['source_no_live_signal_count']}
Source no execution count: {summary['source_no_execution_count']}
Source no capital deployment count: {summary['source_no_capital_deployment_count']}
Source training disabled count: {summary['source_training_disabled_count']}

Execution check count: {summary['execution_check_count']}
Pass check count: {summary['pass_check_count']}
Fail check count: {summary['fail_check_count']}
Safety breach count: {summary['safety_breach_count']}
Leakage breach count: {summary['leakage_breach_count']}
Training eligible count: {summary['training_eligible_count']}
Training locked count: {summary['training_locked_count']}

Baseline accuracy pct: {summary['baseline_accuracy_pct']}
Average label confidence: {summary['average_label_confidence']}
Average net paper outcome bps: {summary['average_net_paper_outcome_bps']}

## Paper Execution Records

{chr(10).join(execution_lines) if execution_lines else "- None"}

## Checks

{chr(10).join(check_lines) if check_lines else "- None"}

## Decision

Engine state: {summary['engine_state']}
Engine decision: {summary['engine_decision']}
Global verdict: {summary['global_verdict']}
Recommended action: {summary['recommended_action']}
Decision reason: {summary['decision_reason']}
Next mission: {summary['next_mission']}

## Safety Statement

Live trading remains disabled.
Capital deployment remains blocked.
No private keys were read.
No signatures were produced.
No exchange orders were sent.
No real capital was used.
No paid APIs were used.

This agent creates paper execution records only.
It does not train a model.
It does not create live trading signals.
It does not perform exchange execution.
It does not deploy capital.
It does not perform autonomous live trading.

Paper execution records are not profitability evidence.
"""


def insert_row(conn: sqlite3.Connection, table_name: str, row: dict[str, Any], columns: list[str]) -> None:
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT OR REPLACE INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})",
        [row[column] for column in columns],
    )


def persist_execution_run(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for table in (EXECUTIONS_TABLE, CHECKS_TABLE, RUNS_TABLE):
            conn.execute(f"DELETE FROM {table} WHERE execution_run_label = ?", (summary["execution_run_label"],))

        conn.execute(
            "DELETE FROM ai_paper_execution_agent_reports WHERE execution_run_label = ? OR report_label = ?",
            (summary["execution_run_label"], summary["report_label"]),
        )

        for record in summary["paper_executions"]:
            stored = dict(record)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                EXECUTIONS_TABLE,
                stored,
                [
                    "paper_execution_id", "execution_run_label", "created_at",
                    "source_signal_run_label", "source_paper_signal_id",
                    "source_paper_signal_code", "source_paper_signal_title",
                    "execution_rank", "paper_execution_scope",
                    "paper_execution_mode", "paper_execution_status",
                    "paper_execution_action", "paper_execution_side",
                    "paper_fill_status", "requested_quantity", "filled_quantity",
                    "paper_fill_price", "paper_notional_value", "paper_fee_value",
                    "paper_slippage_value", "model_training_action",
                    "live_signal_action", "exchange_order_action", "capital_action",
                    "live_trading", "live_order_sent", "capital_deployment",
                    "metadata_json",
                ],
            )

        for check in summary["execution_checks"]:
            stored = dict(check)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                CHECKS_TABLE,
                stored,
                [
                    "check_id", "execution_run_label", "created_at",
                    "source_signal_run_label", "check_category", "check_name",
                    "check_status", "observed_value", "threshold_value",
                    "check_reason", "paper_execution_scope", "live_trading",
                    "live_order_sent", "capital_deployment", "metadata_json",
                ],
            )

        run_row = {
            **{key: summary[key] for key in [
                "execution_run_label", "report_label", "created_at",
                "source_signal_run_label", "source_policy_run_label",
                "source_recommendation_run_label", "source_governance_review_label",
                "source_evaluation_label", "source_guard_review_label",
                "source_collection_label", "source_registry_label",
                "source_build_label", "source_schedule_label",
                "source_learning_run_label", "source_multi_cycle_track_label",
                "source_session_label", "source_portfolio_label",
                "paper_execution_scope", "paper_execution_mode",
                "paper_execution_count", "recorded_execution_count",
                "blocked_execution_count", "paper_only_execution_count",
                "no_live_signal_count", "no_exchange_order_count",
                "no_capital_deployment_count", "no_model_training_count",
                "zero_quantity_execution_count", "zero_notional_execution_count",
                "source_paper_signal_count", "source_ready_signal_count",
                "source_blocked_signal_count", "source_observe_only_signal_count",
                "source_no_live_signal_count", "source_no_execution_count",
                "source_no_capital_deployment_count", "source_training_disabled_count",
                "source_signal_check_count", "source_pass_check_count",
                "source_fail_check_count", "execution_check_count",
                "pass_check_count", "fail_check_count", "safety_breach_count",
                "leakage_breach_count", "training_eligible_count",
                "training_locked_count", "baseline_accuracy_pct",
                "average_label_confidence", "average_net_paper_outcome_bps",
                "engine_state", "engine_decision", "global_verdict",
                "recommended_action", "next_mission", "live_trading",
                "live_order_sent", "capital_deployment",
            ]},
            "summary_json": json.dumps(summary, sort_keys=True),
            "markdown_report": markdown_report,
        }

        insert_row(
            conn,
            RUNS_TABLE,
            run_row,
            [
                "execution_run_label", "report_label", "created_at",
                "source_signal_run_label", "source_policy_run_label",
                "source_recommendation_run_label", "source_governance_review_label",
                "source_evaluation_label", "source_guard_review_label",
                "source_collection_label", "source_registry_label",
                "source_build_label", "source_schedule_label",
                "source_learning_run_label", "source_multi_cycle_track_label",
                "source_session_label", "source_portfolio_label",
                "paper_execution_scope", "paper_execution_mode",
                "paper_execution_count", "recorded_execution_count",
                "blocked_execution_count", "paper_only_execution_count",
                "no_live_signal_count", "no_exchange_order_count",
                "no_capital_deployment_count", "no_model_training_count",
                "zero_quantity_execution_count", "zero_notional_execution_count",
                "source_paper_signal_count", "source_ready_signal_count",
                "source_blocked_signal_count", "source_observe_only_signal_count",
                "source_no_live_signal_count", "source_no_execution_count",
                "source_no_capital_deployment_count", "source_training_disabled_count",
                "source_signal_check_count", "source_pass_check_count",
                "source_fail_check_count", "execution_check_count",
                "pass_check_count", "fail_check_count", "safety_breach_count",
                "leakage_breach_count", "training_eligible_count",
                "training_locked_count", "baseline_accuracy_pct",
                "average_label_confidence", "average_net_paper_outcome_bps",
                "engine_state", "engine_decision", "global_verdict",
                "recommended_action", "next_mission", "live_trading",
                "live_order_sent", "capital_deployment", "summary_json",
                "markdown_report",
            ],
        )

        report_row = {
            "report_label": summary["report_label"],
            "execution_run_label": summary["execution_run_label"],
            "created_at": summary["created_at"],
            "source_signal_run_label": summary["source_signal_run_label"],
            "global_verdict": summary["global_verdict"],
            "recommended_action": summary["recommended_action"],
            "report_json": json.dumps(summary, sort_keys=True),
            "markdown_report": markdown_report,
            "live_trading": LIVE_TRADING_STATUS,
            "live_order_sent": LIVE_ORDER_SENT_VALUE,
            "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        }

        insert_row(
            conn,
            REPORTS_TABLE,
            report_row,
            [
                "report_label", "execution_run_label", "created_at",
                "source_signal_run_label", "global_verdict",
                "recommended_action", "report_json", "markdown_report",
                "live_trading", "live_order_sent", "capital_deployment",
            ],
        )

        conn.commit()


def run_paper_execution_agent(
    db_path: str | Path = "offchain/deltagrid.db",
    execution_run_label: str | None = None,
    report_label: str | None = None,
    signal_run_label: str = "mission81-final-check",
    min_executions: int = 5,
) -> dict[str, Any]:
    if min_executions <= 0:
        raise ValueError("min_executions must be positive")

    db = Path(db_path)
    run_label = execution_run_label or new_execution_run_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    source_signal_label = parse_labels(signal_run_label)[0]

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        source_run = load_signal_run(conn, source_signal_label)
        source_signals = load_paper_signals(conn, source_signal_label)
        source_checks = load_signal_checks(conn, source_signal_label)

    executions = build_paper_executions(
        execution_run_label=run_label,
        created_at=created_at,
        source_signal_label=source_signal_label,
        source_run=source_run,
        paper_signals=source_signals,
    )

    if source_run is None:
        execution_checks = build_missing_checks(run_label, created_at, source_signal_label)
    else:
        execution_checks = build_execution_checks(
            execution_run_label=run_label,
            created_at=created_at,
            source_signal_label=source_signal_label,
            source_run=source_run,
            source_signals=source_signals,
            source_checks=source_checks,
            executions=executions,
            min_executions=min_executions,
        )

    decision, verdict, action, next_mission, state, reason = decide_engine_outcome(
        source_run=source_run,
        checks=execution_checks,
    )

    summary = build_summary(
        db_path=db,
        execution_run_label=run_label,
        report_label=report,
        created_at=created_at,
        source_signal_label=source_signal_label,
        source_run=source_run,
        executions=executions,
        checks=execution_checks,
        decision=decision,
        verdict=verdict,
        action=action,
        next_mission=next_mission,
        state=state,
        reason=reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_execution_run(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid paper execution agent.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--execution-run-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--signal-run-label", default="mission81-final-check")
    parser.add_argument("--min-executions", type=int, default=5)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_paper_execution_agent(
        db_path=args.db,
        execution_run_label=args.execution_run_label,
        report_label=args.report_label,
        signal_run_label=args.signal_run_label,
        min_executions=args.min_executions,
    )

    print(result["markdown_report"] if args.markdown else json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

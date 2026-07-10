"""
Mission 83: Self-Learning Feedback Loop.

This module converts Mission 82 paper execution records into self-learning
feedback records.

Boundary:
- feedback records may be created
- no model training happens in Mission 83
- no strategy reweighting happens in Mission 83
- live trading remains disabled
- capital deployment remains blocked
- exchange execution remains disabled
- private keys are not used
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


SOURCE_RUNS_TABLE = "ai_paper_execution_agent_runs"
SOURCE_EXECUTIONS_TABLE = "ai_paper_execution_records"
SOURCE_CHECKS_TABLE = "ai_paper_execution_agent_checks"

RUNS_TABLE = "ai_self_learning_feedback_runs"
ITEMS_TABLE = "ai_self_learning_feedback_items"
CHECKS_TABLE = "ai_self_learning_feedback_checks"
REPORTS_TABLE = "ai_self_learning_feedback_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

SOURCE_ENGINE_STATE_READY = "AI_PAPER_EXECUTION_AGENT_READY_PAPER_ONLY"
SOURCE_ENGINE_DECISION_READY = "AI_PAPER_EXECUTION_AGENT_APPROVED_FOR_SELF_LEARNING_FEEDBACK_LOOP"
SOURCE_VERDICT_READY = "AI_PAPER_EXECUTION_AGENT_READY_SHADOW_ONLY"

FEEDBACK_SCOPE = "SELF_LEARNING_FEEDBACK_LOOP_PAPER_ONLY"
FEEDBACK_MODE = "FEEDBACK_RECORD_ONLY_NO_MODEL_TRAINING"
FEEDBACK_STATUS_READY = "AI_SELF_LEARNING_FEEDBACK_RECORDED_PAPER_ONLY"
FEEDBACK_STATUS_BLOCKED = "AI_SELF_LEARNING_FEEDBACK_BLOCKED"

FEEDBACK_ACTION = "RECORD_FEEDBACK_ONLY"
FEEDBACK_OUTCOME_CLASS = "OBSERVE_ONLY_NO_TRADE_OUTCOME"
FEEDBACK_LEARNING_SIGNAL = "PAPER_EVIDENCE_COLLECTION_REQUIRED"
KEEP_MODEL_TRAINING_DISABLED = "KEEP_MODEL_TRAINING_DISABLED"
NO_STRATEGY_REWEIGHTING = "NO_STRATEGY_REWEIGHTING"
NO_LIVE_SIGNAL = "NO_LIVE_SIGNAL"
NO_EXCHANGE_ORDER = "NO_EXCHANGE_ORDER"
NO_CAPITAL_DEPLOYMENT = "NO_CAPITAL_DEPLOYMENT"

CHECK_PASS = "AI_SELF_LEARNING_FEEDBACK_CHECK_PASS"
CHECK_FAIL = "AI_SELF_LEARNING_FEEDBACK_CHECK_FAIL"

ENGINE_STATE_READY = "AI_SELF_LEARNING_FEEDBACK_LOOP_READY_PAPER_ONLY"
ENGINE_STATE_UNSTABLE = "AI_SELF_LEARNING_FEEDBACK_LOOP_UNSTABLE"
ENGINE_STATE_BLOCKED = "AI_SELF_LEARNING_FEEDBACK_LOOP_BLOCKED"
ENGINE_STATE_MISSING = "AI_SELF_LEARNING_FEEDBACK_LOOP_MISSING"

ENGINE_DECISION_READY = "AI_SELF_LEARNING_FEEDBACK_LOOP_APPROVED_FOR_OFFLINE_MODEL_TRAINING_HARNESS"
ENGINE_DECISION_UNSTABLE = "AI_SELF_LEARNING_FEEDBACK_LOOP_REVIEW_REQUIRED"
ENGINE_DECISION_BLOCK_SAFETY = "AI_SELF_LEARNING_FEEDBACK_LOOP_BLOCKED_BY_SAFETY_POLICY"
ENGINE_DECISION_REJECT_MISSING = "AI_SELF_LEARNING_FEEDBACK_LOOP_REJECTED_MISSING_EXECUTIONS"

VERDICT_READY = "AI_SELF_LEARNING_FEEDBACK_LOOP_READY_SHADOW_ONLY"
VERDICT_UNSTABLE = "AI_SELF_LEARNING_FEEDBACK_LOOP_UNSTABLE_SHADOW_ONLY"
VERDICT_BLOCKED = "AI_SELF_LEARNING_FEEDBACK_LOOP_BLOCKED_SHADOW_ONLY"
VERDICT_MISSING = "AI_SELF_LEARNING_FEEDBACK_LOOP_MISSING_EVIDENCE"

ACTION_READY = "HAND_OFF_FEEDBACK_TO_OFFLINE_MODEL_TRAINING_HARNESS"
ACTION_REVIEW_UNSTABLE = "REVIEW_SELF_LEARNING_FEEDBACK_EVIDENCE"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_SELF_LEARNING_FEEDBACK_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_PAPER_EXECUTION_AGENT"

NEXT_READY = "Mission 84 Offline Model Training Harness"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_feedback_run_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission83-self-learning-feedback-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission83-self-learning-feedback-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
        return ["mission82-final-check"]

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    labels: list[str] = []

    for item in raw_items:
        label = str(item).strip()
        if not label:
            continue
        if any(ch.isspace() for ch in label):
            raise ValueError(f"Invalid execution run label: {label}")
        if label not in labels:
            labels.append(label)

    if not labels:
        raise ValueError("At least one execution run label is required")

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
            CREATE TABLE IF NOT EXISTS ai_self_learning_feedback_runs (
                feedback_run_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_execution_run_label TEXT NOT NULL,
                source_signal_run_label TEXT,
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
                feedback_scope TEXT NOT NULL,
                feedback_mode TEXT NOT NULL,
                feedback_item_count INTEGER NOT NULL,
                recorded_feedback_count INTEGER NOT NULL,
                blocked_feedback_count INTEGER NOT NULL,
                feedback_only_count INTEGER NOT NULL,
                no_model_training_count INTEGER NOT NULL,
                no_strategy_reweighting_count INTEGER NOT NULL,
                no_live_signal_count INTEGER NOT NULL,
                no_exchange_order_count INTEGER NOT NULL,
                no_capital_deployment_count INTEGER NOT NULL,
                no_profitability_claim_count INTEGER NOT NULL,
                source_paper_execution_count INTEGER NOT NULL,
                source_recorded_execution_count INTEGER NOT NULL,
                source_blocked_execution_count INTEGER NOT NULL,
                source_paper_only_execution_count INTEGER NOT NULL,
                source_no_live_signal_count INTEGER NOT NULL,
                source_no_exchange_order_count INTEGER NOT NULL,
                source_no_capital_deployment_count INTEGER NOT NULL,
                source_no_model_training_count INTEGER NOT NULL,
                source_zero_quantity_execution_count INTEGER NOT NULL,
                source_zero_notional_execution_count INTEGER NOT NULL,
                source_execution_check_count INTEGER NOT NULL,
                source_pass_check_count INTEGER NOT NULL,
                source_fail_check_count INTEGER NOT NULL,
                feedback_check_count INTEGER NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_self_learning_feedback_items (
                feedback_item_id TEXT PRIMARY KEY,
                feedback_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_execution_run_label TEXT NOT NULL,
                source_paper_execution_id TEXT,
                source_paper_signal_code TEXT,
                feedback_rank INTEGER NOT NULL,
                feedback_scope TEXT NOT NULL,
                feedback_mode TEXT NOT NULL,
                feedback_status TEXT NOT NULL,
                feedback_action TEXT NOT NULL,
                feedback_outcome_class TEXT NOT NULL,
                feedback_learning_signal TEXT NOT NULL,
                paper_outcome_quality TEXT NOT NULL,
                model_training_action TEXT NOT NULL,
                strategy_reweighting_action TEXT NOT NULL,
                live_signal_action TEXT NOT NULL,
                exchange_order_action TEXT NOT NULL,
                capital_action TEXT NOT NULL,
                not_profitability_claim INTEGER NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_self_learning_feedback_checks (
                check_id TEXT PRIMARY KEY,
                feedback_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_execution_run_label TEXT NOT NULL,
                check_category TEXT NOT NULL,
                check_name TEXT NOT NULL,
                check_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                threshold_value TEXT NOT NULL,
                check_reason TEXT NOT NULL,
                feedback_scope TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_self_learning_feedback_reports (
                report_label TEXT PRIMARY KEY,
                feedback_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_execution_run_label TEXT NOT NULL,
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


def load_execution_run(conn: sqlite3.Connection, label: str) -> sqlite3.Row | None:
    if not table_exists(conn, SOURCE_RUNS_TABLE):
        return None
    return conn.execute(
        "SELECT * FROM ai_paper_execution_agent_runs WHERE execution_run_label = ?",
        (label,),
    ).fetchone()


def load_execution_records(conn: sqlite3.Connection, label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, SOURCE_EXECUTIONS_TABLE):
        return []
    order_by = order_clause(conn, SOURCE_EXECUTIONS_TABLE, "execution_rank")
    return conn.execute(
        f"SELECT * FROM ai_paper_execution_records WHERE execution_run_label = ? ORDER BY {order_by}",
        (label,),
    ).fetchall()


def load_execution_checks(conn: sqlite3.Connection, label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, SOURCE_CHECKS_TABLE):
        return []
    order_by = order_clause(conn, SOURCE_CHECKS_TABLE, "check_id")
    return conn.execute(
        f"SELECT * FROM ai_paper_execution_agent_checks WHERE execution_run_label = ? ORDER BY {order_by}",
        (label,),
    ).fetchall()


def base_metadata(role: str) -> dict[str, Any]:
    return {
        "feedback_role": role,
        "feedback_scope": FEEDBACK_SCOPE,
        "paper_only": True,
        "model_training_enabled": False,
        "strategy_reweighting_enabled": False,
        "live_signal_generation_enabled": False,
        "exchange_order_enabled": False,
        "execution_role": "FEEDBACK_RECORD_ONLY",
        "private_keys_used": False,
        "orders_sent": False,
        "paid_api_used": False,
        "real_capital_used": False,
        "autonomous_trading_enabled": False,
        "automatic_strategy_reweighting_enabled": False,
        "not_profitability_claim": True,
    }


def source_execution_is_ready(source_run: sqlite3.Row | None) -> bool:
    if source_run is None:
        return False
    return (
        row_get(source_run, "engine_state", "") == SOURCE_ENGINE_STATE_READY
        and row_get(source_run, "engine_decision", "") == SOURCE_ENGINE_DECISION_READY
        and row_get(source_run, "global_verdict", "") == SOURCE_VERDICT_READY
    )


def execution_record_safe(record: sqlite3.Row | dict[str, Any]) -> bool:
    return (
        str(row_get(record, "paper_execution_status", "")) == "AI_PAPER_EXECUTION_RECORDED_PAPER_ONLY"
        and str(row_get(record, "exchange_order_action", "")) == "NO_EXCHANGE_ORDER"
        and str(row_get(record, "capital_action", "")) == "NO_CAPITAL_DEPLOYMENT"
        and str(row_get(record, "live_signal_action", "")) == "NO_LIVE_SIGNAL"
        and safe_float(row_get(record, "filled_quantity", 0.0)) == 0.0
        and safe_float(row_get(record, "paper_notional_value", 0.0)) == 0.0
    )


def build_feedback_items(
    feedback_run_label: str,
    created_at: str,
    source_execution_label: str,
    source_run: sqlite3.Row | None,
    execution_records: list[sqlite3.Row],
) -> list[dict[str, Any]]:
    if source_run is None:
        return []

    if not source_execution_is_ready(source_run):
        return []

    items: list[dict[str, Any]] = []

    for index, record in enumerate(execution_records, start=1):
        status = FEEDBACK_STATUS_READY if execution_record_safe(record) else FEEDBACK_STATUS_BLOCKED

        items.append(
            {
                "feedback_item_id": f"{feedback_run_label}-feedback-{index}".replace(" ", "_"),
                "feedback_run_label": feedback_run_label,
                "created_at": created_at,
                "source_execution_run_label": source_execution_label,
                "source_paper_execution_id": row_get(record, "paper_execution_id", f"{source_execution_label}-execution-{index}"),
                "source_paper_signal_code": row_get(record, "source_paper_signal_code", f"PAPER_SIGNAL_{index}"),
                "feedback_rank": index,
                "feedback_scope": FEEDBACK_SCOPE,
                "feedback_mode": FEEDBACK_MODE,
                "feedback_status": status,
                "feedback_action": FEEDBACK_ACTION,
                "feedback_outcome_class": FEEDBACK_OUTCOME_CLASS,
                "feedback_learning_signal": FEEDBACK_LEARNING_SIGNAL,
                "paper_outcome_quality": "INSUFFICIENT_FOR_TRAINING",
                "model_training_action": KEEP_MODEL_TRAINING_DISABLED,
                "strategy_reweighting_action": NO_STRATEGY_REWEIGHTING,
                "live_signal_action": NO_LIVE_SIGNAL,
                "exchange_order_action": NO_EXCHANGE_ORDER,
                "capital_action": NO_CAPITAL_DEPLOYMENT,
                "not_profitability_claim": 1,
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT_VALUE,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "metadata": base_metadata("SELF_LEARNING_FEEDBACK_RECORD_ONLY"),
            }
        )

    return items


def make_check(
    feedback_run_label: str,
    created_at: str,
    source_execution_label: str,
    category: str,
    name: str,
    passed: bool,
    observed: Any,
    threshold: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{feedback_run_label}-{category}-{name}".replace(" ", "_"),
        "feedback_run_label": feedback_run_label,
        "created_at": created_at,
        "source_execution_run_label": source_execution_label,
        "check_category": category,
        "check_name": name,
        "check_status": CHECK_PASS if passed else CHECK_FAIL,
        "observed_value": str(observed),
        "threshold_value": str(threshold),
        "check_reason": reason,
        "feedback_scope": FEEDBACK_SCOPE,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": base_metadata("SELF_LEARNING_FEEDBACK_CHECK"),
    }


def build_missing_checks(feedback_run_label: str, created_at: str, source_execution_label: str) -> list[dict[str, Any]]:
    return [
        make_check(
            feedback_run_label,
            created_at,
            source_execution_label,
            "availability",
            "source execution run exists",
            False,
            "missing",
            "present",
            "Source Mission 82 execution run is missing.",
        )
    ]


def build_feedback_checks(
    feedback_run_label: str,
    created_at: str,
    source_execution_label: str,
    source_run: sqlite3.Row,
    execution_records: list[sqlite3.Row],
    source_checks: list[sqlite3.Row],
    feedback_items: list[dict[str, Any]],
    min_feedback_items: int,
) -> list[dict[str, Any]]:
    feedback_count = len(feedback_items)
    recorded_feedback_count = sum(1 for item in feedback_items if item["feedback_status"] == FEEDBACK_STATUS_READY)
    blocked_feedback_count = sum(1 for item in feedback_items if item["feedback_status"] == FEEDBACK_STATUS_BLOCKED)
    feedback_only_count = sum(1 for item in feedback_items if item["feedback_action"] == FEEDBACK_ACTION)
    no_model_training_count = sum(1 for item in feedback_items if item["model_training_action"] == KEEP_MODEL_TRAINING_DISABLED)
    no_strategy_reweighting_count = sum(1 for item in feedback_items if item["strategy_reweighting_action"] == NO_STRATEGY_REWEIGHTING)
    no_live_signal_count = sum(1 for item in feedback_items if item["live_signal_action"] == NO_LIVE_SIGNAL)
    no_exchange_order_count = sum(1 for item in feedback_items if item["exchange_order_action"] == NO_EXCHANGE_ORDER)
    no_capital_count = sum(1 for item in feedback_items if item["capital_action"] == NO_CAPITAL_DEPLOYMENT)
    no_profitability_claim_count = sum(1 for item in feedback_items if safe_int(item["not_profitability_claim"]) == 1)

    source_ready = source_execution_is_ready(source_run)
    source_fail_checks = safe_int(row_get(source_run, "fail_check_count", 0))
    safety_count = safe_int(row_get(source_run, "safety_breach_count", 0))
    safety_count += sum(1 for row in [source_run, *execution_records, *source_checks] if safety_problem(row))
    leakage_count = safe_int(row_get(source_run, "leakage_breach_count", 0))
    training_eligible_count = safe_int(row_get(source_run, "training_eligible_count", 0))
    source_zero_quantity_count = safe_int(row_get(source_run, "zero_quantity_execution_count", 0))
    source_zero_notional_count = safe_int(row_get(source_run, "zero_notional_execution_count", 0))
    source_execution_count = safe_int(row_get(source_run, "paper_execution_count", len(execution_records)))

    actual_zero_quantity_count = sum(1 for record in execution_records if safe_float(row_get(record, "filled_quantity", 0.0)) == 0.0)
    actual_zero_notional_count = sum(1 for record in execution_records if safe_float(row_get(record, "paper_notional_value", 0.0)) == 0.0)

    return [
        make_check(feedback_run_label, created_at, source_execution_label, "availability", "source execution run exists", True, "present", "present", "Source execution run exists."),
        make_check(feedback_run_label, created_at, source_execution_label, "source", "source paper execution agent ready", source_ready, f"state={row_get(source_run, 'engine_state', '')}, decision={row_get(source_run, 'engine_decision', '')}, verdict={row_get(source_run, 'global_verdict', '')}", "ready paper-only execution agent", "Source paper execution agent must be ready."),
        make_check(feedback_run_label, created_at, source_execution_label, "source", "source failed checks", source_fail_checks == 0, source_fail_checks, 0, "Source execution failed checks must remain zero."),
        make_check(feedback_run_label, created_at, source_execution_label, "safety", "safety breach count", safety_count == 0, safety_count, 0, "Safety breach count must be zero."),
        make_check(feedback_run_label, created_at, source_execution_label, "leakage", "leakage breach count", leakage_count == 0, leakage_count, 0, "Leakage breach count must be zero."),
        make_check(feedback_run_label, created_at, source_execution_label, "feedback", "feedback item count", feedback_count >= min_feedback_items, feedback_count, f">= {min_feedback_items}", "Feedback loop must record the minimum feedback set."),
        make_check(feedback_run_label, created_at, source_execution_label, "feedback", "recorded feedback items", recorded_feedback_count == feedback_count and feedback_count > 0, recorded_feedback_count, feedback_count, "Every feedback item must be safely recorded."),
        make_check(feedback_run_label, created_at, source_execution_label, "feedback", "blocked feedback items", blocked_feedback_count == 0, blocked_feedback_count, 0, "No feedback item should be blocked in the ready path."),
        make_check(feedback_run_label, created_at, source_execution_label, "feedback_only", "feedback only actions", feedback_only_count == feedback_count and feedback_count > 0, feedback_only_count, feedback_count, "Mission 83 must only record feedback."),
        make_check(feedback_run_label, created_at, source_execution_label, "training_lock", "no model training", training_eligible_count == 0 and no_model_training_count == feedback_count and feedback_count > 0, f"eligible={training_eligible_count}, disabled_feedback={no_model_training_count}", f"eligible=0, disabled_feedback={feedback_count}", "Mission 83 must not train a model."),
        make_check(feedback_run_label, created_at, source_execution_label, "strategy", "no strategy reweighting", no_strategy_reweighting_count == feedback_count and feedback_count > 0, no_strategy_reweighting_count, feedback_count, "Mission 83 must not reweight strategies."),
        make_check(feedback_run_label, created_at, source_execution_label, "live_signal", "no live signals", no_live_signal_count == feedback_count and feedback_count > 0, no_live_signal_count, feedback_count, "Feedback records must not generate live signals."),
        make_check(feedback_run_label, created_at, source_execution_label, "orders", "no exchange orders", no_exchange_order_count == feedback_count and feedback_count > 0, no_exchange_order_count, feedback_count, "Feedback records must not send exchange orders."),
        make_check(feedback_run_label, created_at, source_execution_label, "capital", "no capital deployment", no_capital_count == feedback_count and feedback_count > 0, no_capital_count, feedback_count, "Feedback records must not deploy capital."),
        make_check(feedback_run_label, created_at, source_execution_label, "source_quantity", "source zero quantity", source_zero_quantity_count == source_execution_count and actual_zero_quantity_count == len(execution_records) and source_execution_count > 0, f"source={source_zero_quantity_count}, actual={actual_zero_quantity_count}, executions={source_execution_count}", f"source={source_execution_count}, actual={len(execution_records)}", "Source paper executions must remain zero-quantity."),
        make_check(feedback_run_label, created_at, source_execution_label, "source_notional", "source zero notional", source_zero_notional_count == source_execution_count and actual_zero_notional_count == len(execution_records) and source_execution_count > 0, f"source={source_zero_notional_count}, actual={actual_zero_notional_count}, executions={source_execution_count}", f"source={source_execution_count}, actual={len(execution_records)}", "Source paper executions must remain zero-notional."),
        make_check(feedback_run_label, created_at, source_execution_label, "live_trading", "live trading disabled", str(row_get(source_run, "live_trading", "")) == LIVE_TRADING_STATUS, row_get(source_run, "live_trading", ""), LIVE_TRADING_STATUS, "Live trading must remain disabled."),
        make_check(feedback_run_label, created_at, source_execution_label, "capital_deployment", "capital deployment blocked", str(row_get(source_run, "capital_deployment", "")) == CAPITAL_DEPLOYMENT_STATUS, row_get(source_run, "capital_deployment", ""), CAPITAL_DEPLOYMENT_STATUS, "Capital deployment must remain blocked."),
        make_check(feedback_run_label, created_at, source_execution_label, "profitability", "no profitability claim", no_profitability_claim_count == feedback_count and feedback_count > 0, no_profitability_claim_count, feedback_count, "Feedback records are not profitability evidence."),
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
            "Mission 82 Paper Execution Agent",
            ENGINE_STATE_MISSING,
            "Source paper execution evidence is missing.",
        )

    failed = [check for check in checks if check["check_status"] == CHECK_FAIL]

    if any(check["check_category"] == "safety" for check in failed):
        return (
            ENGINE_DECISION_BLOCK_SAFETY,
            VERDICT_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 83 safety remediation",
            ENGINE_STATE_BLOCKED,
            "Safety invariant failed during self-learning feedback generation.",
        )

    if failed:
        return (
            ENGINE_DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 82 Paper Execution Agent",
            ENGINE_STATE_UNSTABLE,
            "Self-learning feedback loop failed one or more checks.",
        )

    return (
        ENGINE_DECISION_READY,
        VERDICT_READY,
        ACTION_READY,
        NEXT_READY,
        ENGINE_STATE_READY,
        "Self-learning feedback loop recorded paper-only feedback. No model training, strategy reweighting, live trading, capital deployment, or exchange execution is approved.",
    )


def build_summary(
    db_path: str | Path,
    feedback_run_label: str,
    report_label: str,
    created_at: str,
    source_execution_label: str,
    source_run: sqlite3.Row | None,
    feedback_items: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    decision: str,
    verdict: str,
    action: str,
    next_mission: str,
    state: str,
    reason: str,
) -> dict[str, Any]:
    feedback_count = len(feedback_items)

    return {
        "feedback_run_label": feedback_run_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_execution_run_label": source_execution_label,
        "source_signal_run_label": row_get(source_run, "source_signal_run_label", None),
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
        "feedback_scope": FEEDBACK_SCOPE,
        "feedback_mode": FEEDBACK_MODE,
        "feedback_item_count": feedback_count,
        "recorded_feedback_count": sum(1 for item in feedback_items if item["feedback_status"] == FEEDBACK_STATUS_READY),
        "blocked_feedback_count": sum(1 for item in feedback_items if item["feedback_status"] == FEEDBACK_STATUS_BLOCKED),
        "feedback_only_count": sum(1 for item in feedback_items if item["feedback_action"] == FEEDBACK_ACTION),
        "no_model_training_count": sum(1 for item in feedback_items if item["model_training_action"] == KEEP_MODEL_TRAINING_DISABLED),
        "no_strategy_reweighting_count": sum(1 for item in feedback_items if item["strategy_reweighting_action"] == NO_STRATEGY_REWEIGHTING),
        "no_live_signal_count": sum(1 for item in feedback_items if item["live_signal_action"] == NO_LIVE_SIGNAL),
        "no_exchange_order_count": sum(1 for item in feedback_items if item["exchange_order_action"] == NO_EXCHANGE_ORDER),
        "no_capital_deployment_count": sum(1 for item in feedback_items if item["capital_action"] == NO_CAPITAL_DEPLOYMENT),
        "no_profitability_claim_count": sum(1 for item in feedback_items if safe_int(item["not_profitability_claim"]) == 1),
        "source_paper_execution_count": safe_int(row_get(source_run, "paper_execution_count", 0)),
        "source_recorded_execution_count": safe_int(row_get(source_run, "recorded_execution_count", 0)),
        "source_blocked_execution_count": safe_int(row_get(source_run, "blocked_execution_count", 0)),
        "source_paper_only_execution_count": safe_int(row_get(source_run, "paper_only_execution_count", 0)),
        "source_no_live_signal_count": safe_int(row_get(source_run, "no_live_signal_count", 0)),
        "source_no_exchange_order_count": safe_int(row_get(source_run, "no_exchange_order_count", 0)),
        "source_no_capital_deployment_count": safe_int(row_get(source_run, "no_capital_deployment_count", 0)),
        "source_no_model_training_count": safe_int(row_get(source_run, "no_model_training_count", 0)),
        "source_zero_quantity_execution_count": safe_int(row_get(source_run, "zero_quantity_execution_count", 0)),
        "source_zero_notional_execution_count": safe_int(row_get(source_run, "zero_notional_execution_count", 0)),
        "source_execution_check_count": safe_int(row_get(source_run, "execution_check_count", 0)),
        "source_pass_check_count": safe_int(row_get(source_run, "pass_check_count", 0)),
        "source_fail_check_count": safe_int(row_get(source_run, "fail_check_count", 0)),
        "feedback_check_count": len(checks),
        "pass_check_count": sum(1 for check in checks if check["check_status"] == CHECK_PASS),
        "fail_check_count": sum(1 for check in checks if check["check_status"] == CHECK_FAIL),
        "safety_breach_count": safe_int(row_get(source_run, "safety_breach_count", 0)),
        "leakage_breach_count": safe_int(row_get(source_run, "leakage_breach_count", 0)),
        "training_eligible_count": safe_int(row_get(source_run, "training_eligible_count", 0)),
        "training_locked_count": safe_int(row_get(source_run, "training_locked_count", 0)),
        "baseline_accuracy_pct": round8(safe_float(row_get(source_run, "baseline_accuracy_pct", 0.0))),
        "average_label_confidence": round8(safe_float(row_get(source_run, "average_label_confidence", 0.0))),
        "average_net_paper_outcome_bps": round8(safe_float(row_get(source_run, "average_net_paper_outcome_bps", 0.0))),
        "feedback_items": feedback_items,
        "feedback_checks": checks,
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
    feedback_lines = [
        f"- #{item['feedback_rank']} {item['source_paper_signal_code']}: action={item['feedback_action']}, outcome={item['feedback_outcome_class']}, status={item['feedback_status']}"
        for item in summary["feedback_items"]
    ]

    check_lines = [
        f"- {check['check_category']} / {check['check_name']}: status={check['check_status']}, observed={check['observed_value']}, threshold={check['threshold_value']}"
        for check in summary["feedback_checks"]
    ]

    return f"""# DeltaGrid Mission 83 Self-Learning Feedback Loop Report

Report label: {summary['report_label']}
Feedback run label: {summary['feedback_run_label']}
Created at: {summary['created_at']}
Source execution run label: {summary['source_execution_run_label']}
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

## Feedback Summary

Feedback scope: {summary['feedback_scope']}
Feedback mode: {summary['feedback_mode']}

Feedback item count: {summary['feedback_item_count']}
Recorded feedback count: {summary['recorded_feedback_count']}
Blocked feedback count: {summary['blocked_feedback_count']}
Feedback-only count: {summary['feedback_only_count']}
No model training count: {summary['no_model_training_count']}
No strategy reweighting count: {summary['no_strategy_reweighting_count']}
No live signal count: {summary['no_live_signal_count']}
No exchange order count: {summary['no_exchange_order_count']}
No capital deployment count: {summary['no_capital_deployment_count']}
No profitability claim count: {summary['no_profitability_claim_count']}

Source paper execution count: {summary['source_paper_execution_count']}
Source recorded execution count: {summary['source_recorded_execution_count']}
Source blocked execution count: {summary['source_blocked_execution_count']}
Source paper-only execution count: {summary['source_paper_only_execution_count']}
Source no live signal count: {summary['source_no_live_signal_count']}
Source no exchange order count: {summary['source_no_exchange_order_count']}
Source no capital deployment count: {summary['source_no_capital_deployment_count']}
Source no model training count: {summary['source_no_model_training_count']}
Source zero quantity execution count: {summary['source_zero_quantity_execution_count']}
Source zero notional execution count: {summary['source_zero_notional_execution_count']}

Feedback check count: {summary['feedback_check_count']}
Pass check count: {summary['pass_check_count']}
Fail check count: {summary['fail_check_count']}
Safety breach count: {summary['safety_breach_count']}
Leakage breach count: {summary['leakage_breach_count']}
Training eligible count: {summary['training_eligible_count']}
Training locked count: {summary['training_locked_count']}

Baseline accuracy pct: {summary['baseline_accuracy_pct']}
Average label confidence: {summary['average_label_confidence']}
Average net paper outcome bps: {summary['average_net_paper_outcome_bps']}

## Feedback Records

{chr(10).join(feedback_lines) if feedback_lines else "- None"}

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

This loop creates feedback records only.
It does not train a model.
It does not reweight strategies.
It does not create live trading signals.
It does not perform exchange execution.
It does not deploy capital.
It does not perform autonomous live trading.

Feedback records are not profitability evidence.
"""


def insert_row(conn: sqlite3.Connection, table_name: str, row: dict[str, Any], columns: list[str]) -> None:
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT OR REPLACE INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})",
        [row[column] for column in columns],
    )


def persist_feedback_run(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for table in (ITEMS_TABLE, CHECKS_TABLE, RUNS_TABLE):
            conn.execute(f"DELETE FROM {table} WHERE feedback_run_label = ?", (summary["feedback_run_label"],))

        conn.execute(
            "DELETE FROM ai_self_learning_feedback_reports WHERE feedback_run_label = ? OR report_label = ?",
            (summary["feedback_run_label"], summary["report_label"]),
        )

        for item in summary["feedback_items"]:
            stored = dict(item)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                ITEMS_TABLE,
                stored,
                [
                    "feedback_item_id", "feedback_run_label", "created_at",
                    "source_execution_run_label", "source_paper_execution_id",
                    "source_paper_signal_code", "feedback_rank", "feedback_scope",
                    "feedback_mode", "feedback_status", "feedback_action",
                    "feedback_outcome_class", "feedback_learning_signal",
                    "paper_outcome_quality", "model_training_action",
                    "strategy_reweighting_action", "live_signal_action",
                    "exchange_order_action", "capital_action",
                    "not_profitability_claim", "live_trading", "live_order_sent",
                    "capital_deployment", "metadata_json",
                ],
            )

        for check in summary["feedback_checks"]:
            stored = dict(check)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                CHECKS_TABLE,
                stored,
                [
                    "check_id", "feedback_run_label", "created_at",
                    "source_execution_run_label", "check_category", "check_name",
                    "check_status", "observed_value", "threshold_value",
                    "check_reason", "feedback_scope", "live_trading",
                    "live_order_sent", "capital_deployment", "metadata_json",
                ],
            )

        run_row = {
            **{key: summary[key] for key in [
                "feedback_run_label", "report_label", "created_at",
                "source_execution_run_label", "source_signal_run_label",
                "source_policy_run_label", "source_recommendation_run_label",
                "source_governance_review_label", "source_evaluation_label",
                "source_guard_review_label", "source_collection_label",
                "source_registry_label", "source_build_label",
                "source_schedule_label", "source_learning_run_label",
                "source_multi_cycle_track_label", "source_session_label",
                "source_portfolio_label", "feedback_scope", "feedback_mode",
                "feedback_item_count", "recorded_feedback_count",
                "blocked_feedback_count", "feedback_only_count",
                "no_model_training_count", "no_strategy_reweighting_count",
                "no_live_signal_count", "no_exchange_order_count",
                "no_capital_deployment_count", "no_profitability_claim_count",
                "source_paper_execution_count", "source_recorded_execution_count",
                "source_blocked_execution_count", "source_paper_only_execution_count",
                "source_no_live_signal_count", "source_no_exchange_order_count",
                "source_no_capital_deployment_count", "source_no_model_training_count",
                "source_zero_quantity_execution_count", "source_zero_notional_execution_count",
                "source_execution_check_count", "source_pass_check_count",
                "source_fail_check_count", "feedback_check_count",
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
                "feedback_run_label", "report_label", "created_at",
                "source_execution_run_label", "source_signal_run_label",
                "source_policy_run_label", "source_recommendation_run_label",
                "source_governance_review_label", "source_evaluation_label",
                "source_guard_review_label", "source_collection_label",
                "source_registry_label", "source_build_label",
                "source_schedule_label", "source_learning_run_label",
                "source_multi_cycle_track_label", "source_session_label",
                "source_portfolio_label", "feedback_scope", "feedback_mode",
                "feedback_item_count", "recorded_feedback_count",
                "blocked_feedback_count", "feedback_only_count",
                "no_model_training_count", "no_strategy_reweighting_count",
                "no_live_signal_count", "no_exchange_order_count",
                "no_capital_deployment_count", "no_profitability_claim_count",
                "source_paper_execution_count", "source_recorded_execution_count",
                "source_blocked_execution_count", "source_paper_only_execution_count",
                "source_no_live_signal_count", "source_no_exchange_order_count",
                "source_no_capital_deployment_count", "source_no_model_training_count",
                "source_zero_quantity_execution_count", "source_zero_notional_execution_count",
                "source_execution_check_count", "source_pass_check_count",
                "source_fail_check_count", "feedback_check_count",
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
            "feedback_run_label": summary["feedback_run_label"],
            "created_at": summary["created_at"],
            "source_execution_run_label": summary["source_execution_run_label"],
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
                "report_label", "feedback_run_label", "created_at",
                "source_execution_run_label", "global_verdict",
                "recommended_action", "report_json", "markdown_report",
                "live_trading", "live_order_sent", "capital_deployment",
            ],
        )

        conn.commit()


def run_self_learning_feedback_loop(
    db_path: str | Path = "offchain/deltagrid.db",
    feedback_run_label: str | None = None,
    report_label: str | None = None,
    execution_run_label: str = "mission82-final-check",
    min_feedback_items: int = 5,
) -> dict[str, Any]:
    if min_feedback_items <= 0:
        raise ValueError("min_feedback_items must be positive")

    db = Path(db_path)
    run_label = feedback_run_label or new_feedback_run_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    source_execution_label = parse_labels(execution_run_label)[0]

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        source_run = load_execution_run(conn, source_execution_label)
        execution_records = load_execution_records(conn, source_execution_label)
        source_checks = load_execution_checks(conn, source_execution_label)

    feedback_items = build_feedback_items(
        feedback_run_label=run_label,
        created_at=created_at,
        source_execution_label=source_execution_label,
        source_run=source_run,
        execution_records=execution_records,
    )

    if source_run is None:
        feedback_checks = build_missing_checks(run_label, created_at, source_execution_label)
    else:
        feedback_checks = build_feedback_checks(
            feedback_run_label=run_label,
            created_at=created_at,
            source_execution_label=source_execution_label,
            source_run=source_run,
            execution_records=execution_records,
            source_checks=source_checks,
            feedback_items=feedback_items,
            min_feedback_items=min_feedback_items,
        )

    decision, verdict, action, next_mission, state, reason = decide_engine_outcome(
        source_run=source_run,
        checks=feedback_checks,
    )

    summary = build_summary(
        db_path=db,
        feedback_run_label=run_label,
        report_label=report,
        created_at=created_at,
        source_execution_label=source_execution_label,
        source_run=source_run,
        feedback_items=feedback_items,
        checks=feedback_checks,
        decision=decision,
        verdict=verdict,
        action=action,
        next_mission=next_mission,
        state=state,
        reason=reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_feedback_run(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid self-learning feedback loop.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--feedback-run-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--execution-run-label", default="mission82-final-check")
    parser.add_argument("--min-feedback-items", type=int, default=5)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_self_learning_feedback_loop(
        db_path=args.db,
        feedback_run_label=args.feedback_run_label,
        report_label=args.report_label,
        execution_run_label=args.execution_run_label,
        min_feedback_items=args.min_feedback_items,
    )

    print(result["markdown_report"] if args.markdown else json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

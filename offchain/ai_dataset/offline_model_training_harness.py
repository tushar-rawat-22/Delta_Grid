"""
Mission 84: Offline Model Training Harness.

This module creates the offline model training harness layer after Mission 83.

Boundary:
- training candidate records may be created
- actual training remains blocked until feedback quality is sufficient
- no model artifacts are created in the locked path
- no model deployment happens
- no strategy reweighting happens
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


SOURCE_RUNS_TABLE = "ai_self_learning_feedback_runs"
SOURCE_ITEMS_TABLE = "ai_self_learning_feedback_items"
SOURCE_CHECKS_TABLE = "ai_self_learning_feedback_checks"

RUNS_TABLE = "ai_offline_model_training_harness_runs"
CANDIDATES_TABLE = "ai_offline_model_training_candidates"
CHECKS_TABLE = "ai_offline_model_training_checks"
REPORTS_TABLE = "ai_offline_model_training_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

SOURCE_ENGINE_STATE_READY = "AI_SELF_LEARNING_FEEDBACK_LOOP_READY_PAPER_ONLY"
SOURCE_ENGINE_DECISION_READY = "AI_SELF_LEARNING_FEEDBACK_LOOP_APPROVED_FOR_OFFLINE_MODEL_TRAINING_HARNESS"
SOURCE_VERDICT_READY = "AI_SELF_LEARNING_FEEDBACK_LOOP_READY_SHADOW_ONLY"

TRAINING_SCOPE = "OFFLINE_MODEL_TRAINING_HARNESS_LOCAL_ONLY"
TRAINING_MODE = "OFFLINE_TRAINING_HARNESS_NO_MODEL_ARTIFACT_NO_DEPLOYMENT"

CANDIDATE_STATUS_BLOCKED = "AI_OFFLINE_TRAINING_CANDIDATE_BLOCKED_DATA_INSUFFICIENT"
CANDIDATE_STATUS_READY = "AI_OFFLINE_TRAINING_CANDIDATE_READY_FOR_FUTURE_OFFLINE_TRAINING"
CANDIDATE_ACTION = "RECORD_TRAINING_CANDIDATE_ONLY"
MODEL_TRAINING_ACTION_BLOCKED = "OFFLINE_MODEL_TRAINING_NOT_RUN_DATA_INSUFFICIENT"
MODEL_ARTIFACT_ACTION_NONE = "NO_MODEL_ARTIFACT_CREATED"
MODEL_DEPLOYMENT_ACTION_NONE = "NO_MODEL_DEPLOYMENT"
NO_STRATEGY_REWEIGHTING = "NO_STRATEGY_REWEIGHTING"
NO_LIVE_SIGNAL = "NO_LIVE_SIGNAL"
NO_EXCHANGE_ORDER = "NO_EXCHANGE_ORDER"
NO_CAPITAL_DEPLOYMENT = "NO_CAPITAL_DEPLOYMENT"
NO_PROFITABILITY_CLAIM = "NO_PROFITABILITY_CLAIM"

CHECK_PASS = "AI_OFFLINE_MODEL_TRAINING_HARNESS_CHECK_PASS"
CHECK_FAIL = "AI_OFFLINE_MODEL_TRAINING_HARNESS_CHECK_FAIL"

ENGINE_STATE_READY = "AI_OFFLINE_MODEL_TRAINING_HARNESS_READY_LOCAL_ONLY"
ENGINE_STATE_UNSTABLE = "AI_OFFLINE_MODEL_TRAINING_HARNESS_UNSTABLE"
ENGINE_STATE_BLOCKED = "AI_OFFLINE_MODEL_TRAINING_HARNESS_BLOCKED"
ENGINE_STATE_MISSING = "AI_OFFLINE_MODEL_TRAINING_HARNESS_MISSING"

ENGINE_DECISION_READY = "AI_OFFLINE_MODEL_TRAINING_HARNESS_APPROVED_FOR_MODEL_PROMOTION_ENGINE_REVIEW"
ENGINE_DECISION_UNSTABLE = "AI_OFFLINE_MODEL_TRAINING_HARNESS_REVIEW_REQUIRED"
ENGINE_DECISION_BLOCK_SAFETY = "AI_OFFLINE_MODEL_TRAINING_HARNESS_BLOCKED_BY_SAFETY_POLICY"
ENGINE_DECISION_REJECT_MISSING = "AI_OFFLINE_MODEL_TRAINING_HARNESS_REJECTED_MISSING_FEEDBACK"

VERDICT_READY = "AI_OFFLINE_MODEL_TRAINING_HARNESS_READY_SHADOW_ONLY"
VERDICT_UNSTABLE = "AI_OFFLINE_MODEL_TRAINING_HARNESS_UNSTABLE_SHADOW_ONLY"
VERDICT_BLOCKED = "AI_OFFLINE_MODEL_TRAINING_HARNESS_BLOCKED_SHADOW_ONLY"
VERDICT_MISSING = "AI_OFFLINE_MODEL_TRAINING_HARNESS_MISSING_EVIDENCE"

ACTION_READY = "HAND_OFF_OFFLINE_TRAINING_HARNESS_TO_MODEL_PROMOTION_ENGINE"
ACTION_REVIEW_UNSTABLE = "REVIEW_OFFLINE_MODEL_TRAINING_HARNESS_EVIDENCE"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_OFFLINE_MODEL_TRAINING_HARNESS_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_SELF_LEARNING_FEEDBACK_LOOP"

NEXT_READY = "Mission 85 Model Promotion Engine"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_training_run_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission84-offline-training-harness-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission84-offline-training-harness-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
        return ["mission83-final-check"]

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    labels: list[str] = []

    for item in raw_items:
        label = str(item).strip()
        if not label:
            continue
        if any(ch.isspace() for ch in label):
            raise ValueError(f"Invalid feedback run label: {label}")
        if label not in labels:
            labels.append(label)

    if not labels:
        raise ValueError("At least one feedback run label is required")

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
            CREATE TABLE IF NOT EXISTS ai_offline_model_training_harness_runs (
                training_run_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_feedback_run_label TEXT NOT NULL,
                source_execution_run_label TEXT,
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
                training_scope TEXT NOT NULL,
                training_mode TEXT NOT NULL,
                training_candidate_count INTEGER NOT NULL,
                training_ready_candidate_count INTEGER NOT NULL,
                training_blocked_candidate_count INTEGER NOT NULL,
                actual_model_training_count INTEGER NOT NULL,
                model_artifact_count INTEGER NOT NULL,
                no_model_deployment_count INTEGER NOT NULL,
                no_live_deployment_count INTEGER NOT NULL,
                no_strategy_reweighting_count INTEGER NOT NULL,
                no_live_signal_count INTEGER NOT NULL,
                no_exchange_order_count INTEGER NOT NULL,
                no_capital_deployment_count INTEGER NOT NULL,
                no_profitability_claim_count INTEGER NOT NULL,
                source_feedback_item_count INTEGER NOT NULL,
                source_recorded_feedback_count INTEGER NOT NULL,
                source_blocked_feedback_count INTEGER NOT NULL,
                source_feedback_only_count INTEGER NOT NULL,
                source_no_model_training_count INTEGER NOT NULL,
                source_no_strategy_reweighting_count INTEGER NOT NULL,
                source_no_live_signal_count INTEGER NOT NULL,
                source_no_exchange_order_count INTEGER NOT NULL,
                source_no_capital_deployment_count INTEGER NOT NULL,
                source_no_profitability_claim_count INTEGER NOT NULL,
                source_feedback_check_count INTEGER NOT NULL,
                source_pass_check_count INTEGER NOT NULL,
                source_fail_check_count INTEGER NOT NULL,
                training_check_count INTEGER NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_offline_model_training_candidates (
                training_candidate_id TEXT PRIMARY KEY,
                training_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_feedback_run_label TEXT NOT NULL,
                source_feedback_item_id TEXT,
                source_paper_signal_code TEXT,
                candidate_rank INTEGER NOT NULL,
                training_scope TEXT NOT NULL,
                training_mode TEXT NOT NULL,
                candidate_status TEXT NOT NULL,
                candidate_action TEXT NOT NULL,
                dataset_readiness TEXT NOT NULL,
                target_label_quality TEXT NOT NULL,
                model_family TEXT NOT NULL,
                model_training_action TEXT NOT NULL,
                model_artifact_action TEXT NOT NULL,
                model_deployment_action TEXT NOT NULL,
                live_deployment_action TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_offline_model_training_checks (
                check_id TEXT PRIMARY KEY,
                training_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_feedback_run_label TEXT NOT NULL,
                check_category TEXT NOT NULL,
                check_name TEXT NOT NULL,
                check_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                threshold_value TEXT NOT NULL,
                check_reason TEXT NOT NULL,
                training_scope TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_offline_model_training_reports (
                report_label TEXT PRIMARY KEY,
                training_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_feedback_run_label TEXT NOT NULL,
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


def load_feedback_run(conn: sqlite3.Connection, label: str) -> sqlite3.Row | None:
    if not table_exists(conn, SOURCE_RUNS_TABLE):
        return None
    return conn.execute(
        "SELECT * FROM ai_self_learning_feedback_runs WHERE feedback_run_label = ?",
        (label,),
    ).fetchone()


def load_feedback_items(conn: sqlite3.Connection, label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, SOURCE_ITEMS_TABLE):
        return []
    order_by = order_clause(conn, SOURCE_ITEMS_TABLE, "feedback_rank")
    return conn.execute(
        f"SELECT * FROM ai_self_learning_feedback_items WHERE feedback_run_label = ? ORDER BY {order_by}",
        (label,),
    ).fetchall()


def load_feedback_checks(conn: sqlite3.Connection, label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, SOURCE_CHECKS_TABLE):
        return []
    order_by = order_clause(conn, SOURCE_CHECKS_TABLE, "check_id")
    return conn.execute(
        f"SELECT * FROM ai_self_learning_feedback_checks WHERE feedback_run_label = ? ORDER BY {order_by}",
        (label,),
    ).fetchall()


def base_metadata(role: str) -> dict[str, Any]:
    return {
        "training_role": role,
        "training_scope": TRAINING_SCOPE,
        "offline_only": True,
        "paper_only": True,
        "actual_model_training_enabled": False,
        "model_artifact_created": False,
        "model_deployment_enabled": False,
        "live_deployment_enabled": False,
        "strategy_reweighting_enabled": False,
        "live_signal_generation_enabled": False,
        "exchange_order_enabled": False,
        "private_keys_used": False,
        "orders_sent": False,
        "paid_api_used": False,
        "real_capital_used": False,
        "autonomous_trading_enabled": False,
        "automatic_strategy_reweighting_enabled": False,
        "not_profitability_claim": True,
    }


def source_feedback_is_ready(source_run: sqlite3.Row | None) -> bool:
    if source_run is None:
        return False
    return (
        row_get(source_run, "engine_state", "") == SOURCE_ENGINE_STATE_READY
        and row_get(source_run, "engine_decision", "") == SOURCE_ENGINE_DECISION_READY
        and row_get(source_run, "global_verdict", "") == SOURCE_VERDICT_READY
    )


def feedback_item_is_safe(item: sqlite3.Row | dict[str, Any]) -> bool:
    return (
        str(row_get(item, "feedback_status", "")) == "AI_SELF_LEARNING_FEEDBACK_RECORDED_PAPER_ONLY"
        and str(row_get(item, "model_training_action", "")) == "KEEP_MODEL_TRAINING_DISABLED"
        and str(row_get(item, "strategy_reweighting_action", "")) == "NO_STRATEGY_REWEIGHTING"
        and str(row_get(item, "live_signal_action", "")) == "NO_LIVE_SIGNAL"
        and str(row_get(item, "exchange_order_action", "")) == "NO_EXCHANGE_ORDER"
        and str(row_get(item, "capital_action", "")) == "NO_CAPITAL_DEPLOYMENT"
        and safe_int(row_get(item, "not_profitability_claim", 0)) == 1
    )


def item_training_quality(item: sqlite3.Row | dict[str, Any]) -> str:
    return str(row_get(item, "paper_outcome_quality", "INSUFFICIENT_FOR_TRAINING"))


def item_ready_for_actual_training(item: sqlite3.Row | dict[str, Any]) -> bool:
    return feedback_item_is_safe(item) and item_training_quality(item) == "SUFFICIENT_FOR_OFFLINE_TRAINING"


def build_training_candidates(
    training_run_label: str,
    created_at: str,
    source_feedback_label: str,
    source_run: sqlite3.Row | None,
    feedback_items: list[sqlite3.Row],
) -> list[dict[str, Any]]:
    if source_run is None:
        return []

    if not source_feedback_is_ready(source_run):
        return []

    candidates: list[dict[str, Any]] = []

    for index, item in enumerate(feedback_items, start=1):
        ready_for_training = item_ready_for_actual_training(item)
        status = CANDIDATE_STATUS_READY if ready_for_training else CANDIDATE_STATUS_BLOCKED
        quality = item_training_quality(item)

        candidates.append(
            {
                "training_candidate_id": f"{training_run_label}-candidate-{index}".replace(" ", "_"),
                "training_run_label": training_run_label,
                "created_at": created_at,
                "source_feedback_run_label": source_feedback_label,
                "source_feedback_item_id": row_get(item, "feedback_item_id", f"{source_feedback_label}-feedback-{index}"),
                "source_paper_signal_code": row_get(item, "source_paper_signal_code", f"PAPER_SIGNAL_{index}"),
                "candidate_rank": index,
                "training_scope": TRAINING_SCOPE,
                "training_mode": TRAINING_MODE,
                "candidate_status": status,
                "candidate_action": CANDIDATE_ACTION,
                "dataset_readiness": "BLOCKED_DATA_INSUFFICIENT" if not ready_for_training else "READY_FOR_FUTURE_OFFLINE_TRAINING",
                "target_label_quality": quality,
                "model_family": "LOCAL_BASELINE_CLASSIFIER_PLACEHOLDER",
                "model_training_action": MODEL_TRAINING_ACTION_BLOCKED,
                "model_artifact_action": MODEL_ARTIFACT_ACTION_NONE,
                "model_deployment_action": MODEL_DEPLOYMENT_ACTION_NONE,
                "live_deployment_action": MODEL_DEPLOYMENT_ACTION_NONE,
                "strategy_reweighting_action": NO_STRATEGY_REWEIGHTING,
                "live_signal_action": NO_LIVE_SIGNAL,
                "exchange_order_action": NO_EXCHANGE_ORDER,
                "capital_action": NO_CAPITAL_DEPLOYMENT,
                "not_profitability_claim": 1,
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT_VALUE,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "metadata": base_metadata("OFFLINE_MODEL_TRAINING_CANDIDATE_RECORD_ONLY"),
            }
        )

    return candidates


def make_check(
    training_run_label: str,
    created_at: str,
    source_feedback_label: str,
    category: str,
    name: str,
    passed: bool,
    observed: Any,
    threshold: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{training_run_label}-{category}-{name}".replace(" ", "_"),
        "training_run_label": training_run_label,
        "created_at": created_at,
        "source_feedback_run_label": source_feedback_label,
        "check_category": category,
        "check_name": name,
        "check_status": CHECK_PASS if passed else CHECK_FAIL,
        "observed_value": str(observed),
        "threshold_value": str(threshold),
        "check_reason": reason,
        "training_scope": TRAINING_SCOPE,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": base_metadata("OFFLINE_MODEL_TRAINING_HARNESS_CHECK"),
    }


def build_missing_checks(training_run_label: str, created_at: str, source_feedback_label: str) -> list[dict[str, Any]]:
    return [
        make_check(
            training_run_label,
            created_at,
            source_feedback_label,
            "availability",
            "source feedback run exists",
            False,
            "missing",
            "present",
            "Source Mission 83 feedback run is missing.",
        )
    ]


def build_training_checks(
    training_run_label: str,
    created_at: str,
    source_feedback_label: str,
    source_run: sqlite3.Row,
    feedback_items: list[sqlite3.Row],
    source_checks: list[sqlite3.Row],
    candidates: list[dict[str, Any]],
    min_candidates: int,
) -> list[dict[str, Any]]:
    candidate_count = len(candidates)
    ready_candidate_count = sum(1 for candidate in candidates if candidate["candidate_status"] == CANDIDATE_STATUS_READY)
    blocked_candidate_count = sum(1 for candidate in candidates if candidate["candidate_status"] == CANDIDATE_STATUS_BLOCKED)
    actual_training_count = sum(1 for candidate in candidates if candidate["model_training_action"] != MODEL_TRAINING_ACTION_BLOCKED)
    artifact_count = sum(1 for candidate in candidates if candidate["model_artifact_action"] != MODEL_ARTIFACT_ACTION_NONE)
    no_model_deployment_count = sum(1 for candidate in candidates if candidate["model_deployment_action"] == MODEL_DEPLOYMENT_ACTION_NONE)
    no_live_deployment_count = sum(1 for candidate in candidates if candidate["live_deployment_action"] == MODEL_DEPLOYMENT_ACTION_NONE)
    no_strategy_reweighting_count = sum(1 for candidate in candidates if candidate["strategy_reweighting_action"] == NO_STRATEGY_REWEIGHTING)
    no_live_signal_count = sum(1 for candidate in candidates if candidate["live_signal_action"] == NO_LIVE_SIGNAL)
    no_exchange_order_count = sum(1 for candidate in candidates if candidate["exchange_order_action"] == NO_EXCHANGE_ORDER)
    no_capital_count = sum(1 for candidate in candidates if candidate["capital_action"] == NO_CAPITAL_DEPLOYMENT)
    no_profitability_claim_count = sum(1 for candidate in candidates if safe_int(candidate["not_profitability_claim"]) == 1)

    source_ready = source_feedback_is_ready(source_run)
    source_fail_checks = safe_int(row_get(source_run, "fail_check_count", 0))
    safety_count = safe_int(row_get(source_run, "safety_breach_count", 0))
    safety_count += sum(1 for row in [source_run, *feedback_items, *source_checks] if safety_problem(row))
    leakage_count = safe_int(row_get(source_run, "leakage_breach_count", 0))
    source_feedback_count = safe_int(row_get(source_run, "feedback_item_count", len(feedback_items)))
    source_no_training_count = safe_int(row_get(source_run, "no_model_training_count", 0))
    source_no_reweight_count = safe_int(row_get(source_run, "no_strategy_reweighting_count", 0))
    source_no_live_signal_count = safe_int(row_get(source_run, "no_live_signal_count", 0))
    source_no_exchange_order_count = safe_int(row_get(source_run, "no_exchange_order_count", 0))
    source_no_capital_count = safe_int(row_get(source_run, "no_capital_deployment_count", 0))
    source_no_profitability_count = safe_int(row_get(source_run, "no_profitability_claim_count", 0))

    return [
        make_check(training_run_label, created_at, source_feedback_label, "availability", "source feedback run exists", True, "present", "present", "Source feedback run exists."),
        make_check(training_run_label, created_at, source_feedback_label, "source", "source feedback loop ready", source_ready, f"state={row_get(source_run, 'engine_state', '')}, decision={row_get(source_run, 'engine_decision', '')}, verdict={row_get(source_run, 'global_verdict', '')}", "ready paper-only feedback loop", "Source feedback loop must be ready."),
        make_check(training_run_label, created_at, source_feedback_label, "source", "source failed checks", source_fail_checks == 0, source_fail_checks, 0, "Source feedback failed checks must remain zero."),
        make_check(training_run_label, created_at, source_feedback_label, "safety", "safety breach count", safety_count == 0, safety_count, 0, "Safety breach count must be zero."),
        make_check(training_run_label, created_at, source_feedback_label, "leakage", "leakage breach count", leakage_count == 0, leakage_count, 0, "Leakage breach count must be zero."),
        make_check(training_run_label, created_at, source_feedback_label, "candidates", "training candidate count", candidate_count >= min_candidates, candidate_count, f">= {min_candidates}", "Training harness must record the minimum candidate set."),
        make_check(training_run_label, created_at, source_feedback_label, "candidates", "blocked training candidates", blocked_candidate_count == candidate_count and candidate_count > 0, blocked_candidate_count, candidate_count, "Current feedback is insufficient, so all candidates must remain blocked from actual training."),
        make_check(training_run_label, created_at, source_feedback_label, "candidates", "ready training candidates", ready_candidate_count == 0, ready_candidate_count, 0, "No candidate should be ready for actual model fitting yet."),
        make_check(training_run_label, created_at, source_feedback_label, "training_lock", "actual model training count", actual_training_count == 0, actual_training_count, 0, "Mission 84 harness must not run actual training on insufficient data."),
        make_check(training_run_label, created_at, source_feedback_label, "artifacts", "model artifact count", artifact_count == 0, artifact_count, 0, "Mission 84 must not create model artifacts in the locked path."),
        make_check(training_run_label, created_at, source_feedback_label, "deployment", "no model deployment", no_model_deployment_count == candidate_count and candidate_count > 0, no_model_deployment_count, candidate_count, "Mission 84 must not deploy models."),
        make_check(training_run_label, created_at, source_feedback_label, "deployment", "no live deployment", no_live_deployment_count == candidate_count and candidate_count > 0, no_live_deployment_count, candidate_count, "Mission 84 must not deploy live systems."),
        make_check(training_run_label, created_at, source_feedback_label, "strategy", "no strategy reweighting", no_strategy_reweighting_count == candidate_count and candidate_count > 0, no_strategy_reweighting_count, candidate_count, "Mission 84 must not reweight strategies."),
        make_check(training_run_label, created_at, source_feedback_label, "live_signal", "no live signals", no_live_signal_count == candidate_count and candidate_count > 0, no_live_signal_count, candidate_count, "Training candidates must not generate live signals."),
        make_check(training_run_label, created_at, source_feedback_label, "orders", "no exchange orders", no_exchange_order_count == candidate_count and candidate_count > 0, no_exchange_order_count, candidate_count, "Training candidates must not send exchange orders."),
        make_check(training_run_label, created_at, source_feedback_label, "capital", "no capital deployment", no_capital_count == candidate_count and candidate_count > 0, no_capital_count, candidate_count, "Training candidates must not deploy capital."),
        make_check(training_run_label, created_at, source_feedback_label, "source_training", "source no model training", source_no_training_count == source_feedback_count and source_feedback_count > 0, source_no_training_count, source_feedback_count, "Source feedback records must have no model training."),
        make_check(training_run_label, created_at, source_feedback_label, "source_strategy", "source no strategy reweighting", source_no_reweight_count == source_feedback_count and source_feedback_count > 0, source_no_reweight_count, source_feedback_count, "Source feedback records must have no strategy reweighting."),
        make_check(training_run_label, created_at, source_feedback_label, "source_safety", "source no live signals orders capital", source_no_live_signal_count == source_feedback_count and source_no_exchange_order_count == source_feedback_count and source_no_capital_count == source_feedback_count and source_feedback_count > 0, f"signals={source_no_live_signal_count}, orders={source_no_exchange_order_count}, capital={source_no_capital_count}", f"all={source_feedback_count}", "Source feedback records must not signal live, order, or deploy capital."),
        make_check(training_run_label, created_at, source_feedback_label, "live_trading", "live trading disabled", str(row_get(source_run, "live_trading", "")) == LIVE_TRADING_STATUS, row_get(source_run, "live_trading", ""), LIVE_TRADING_STATUS, "Live trading must remain disabled."),
        make_check(training_run_label, created_at, source_feedback_label, "capital_deployment", "capital deployment blocked", str(row_get(source_run, "capital_deployment", "")) == CAPITAL_DEPLOYMENT_STATUS, row_get(source_run, "capital_deployment", ""), CAPITAL_DEPLOYMENT_STATUS, "Capital deployment must remain blocked."),
        make_check(training_run_label, created_at, source_feedback_label, "profitability", "no profitability claim", no_profitability_claim_count == candidate_count and source_no_profitability_count == source_feedback_count and candidate_count > 0, f"candidates={no_profitability_claim_count}, source={source_no_profitability_count}", f"candidates={candidate_count}, source={source_feedback_count}", "Training harness records are not profitability evidence."),
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
            "Mission 83 Self-Learning Feedback Loop",
            ENGINE_STATE_MISSING,
            "Source feedback evidence is missing.",
        )

    failed = [check for check in checks if check["check_status"] == CHECK_FAIL]

    if any(check["check_category"] == "safety" for check in failed):
        return (
            ENGINE_DECISION_BLOCK_SAFETY,
            VERDICT_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 84 safety remediation",
            ENGINE_STATE_BLOCKED,
            "Safety invariant failed during offline training harness generation.",
        )

    if failed:
        return (
            ENGINE_DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 83 Self-Learning Feedback Loop",
            ENGINE_STATE_UNSTABLE,
            "Offline model training harness failed one or more checks.",
        )

    return (
        ENGINE_DECISION_READY,
        VERDICT_READY,
        ACTION_READY,
        NEXT_READY,
        ENGINE_STATE_READY,
        "Offline model training harness recorded locked training candidates. Actual model training, model artifact creation, model deployment, strategy reweighting, live trading, capital deployment, and exchange execution remain blocked.",
    )


def build_summary(
    db_path: str | Path,
    training_run_label: str,
    report_label: str,
    created_at: str,
    source_feedback_label: str,
    source_run: sqlite3.Row | None,
    candidates: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    decision: str,
    verdict: str,
    action: str,
    next_mission: str,
    state: str,
    reason: str,
) -> dict[str, Any]:
    candidate_count = len(candidates)

    return {
        "training_run_label": training_run_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_feedback_run_label": source_feedback_label,
        "source_execution_run_label": row_get(source_run, "source_execution_run_label", None),
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
        "training_scope": TRAINING_SCOPE,
        "training_mode": TRAINING_MODE,
        "training_candidate_count": candidate_count,
        "training_ready_candidate_count": sum(1 for candidate in candidates if candidate["candidate_status"] == CANDIDATE_STATUS_READY),
        "training_blocked_candidate_count": sum(1 for candidate in candidates if candidate["candidate_status"] == CANDIDATE_STATUS_BLOCKED),
        "actual_model_training_count": sum(1 for candidate in candidates if candidate["model_training_action"] != MODEL_TRAINING_ACTION_BLOCKED),
        "model_artifact_count": sum(1 for candidate in candidates if candidate["model_artifact_action"] != MODEL_ARTIFACT_ACTION_NONE),
        "no_model_deployment_count": sum(1 for candidate in candidates if candidate["model_deployment_action"] == MODEL_DEPLOYMENT_ACTION_NONE),
        "no_live_deployment_count": sum(1 for candidate in candidates if candidate["live_deployment_action"] == MODEL_DEPLOYMENT_ACTION_NONE),
        "no_strategy_reweighting_count": sum(1 for candidate in candidates if candidate["strategy_reweighting_action"] == NO_STRATEGY_REWEIGHTING),
        "no_live_signal_count": sum(1 for candidate in candidates if candidate["live_signal_action"] == NO_LIVE_SIGNAL),
        "no_exchange_order_count": sum(1 for candidate in candidates if candidate["exchange_order_action"] == NO_EXCHANGE_ORDER),
        "no_capital_deployment_count": sum(1 for candidate in candidates if candidate["capital_action"] == NO_CAPITAL_DEPLOYMENT),
        "no_profitability_claim_count": sum(1 for candidate in candidates if safe_int(candidate["not_profitability_claim"]) == 1),
        "source_feedback_item_count": safe_int(row_get(source_run, "feedback_item_count", 0)),
        "source_recorded_feedback_count": safe_int(row_get(source_run, "recorded_feedback_count", 0)),
        "source_blocked_feedback_count": safe_int(row_get(source_run, "blocked_feedback_count", 0)),
        "source_feedback_only_count": safe_int(row_get(source_run, "feedback_only_count", 0)),
        "source_no_model_training_count": safe_int(row_get(source_run, "no_model_training_count", 0)),
        "source_no_strategy_reweighting_count": safe_int(row_get(source_run, "no_strategy_reweighting_count", 0)),
        "source_no_live_signal_count": safe_int(row_get(source_run, "no_live_signal_count", 0)),
        "source_no_exchange_order_count": safe_int(row_get(source_run, "no_exchange_order_count", 0)),
        "source_no_capital_deployment_count": safe_int(row_get(source_run, "no_capital_deployment_count", 0)),
        "source_no_profitability_claim_count": safe_int(row_get(source_run, "no_profitability_claim_count", 0)),
        "source_feedback_check_count": safe_int(row_get(source_run, "feedback_check_count", 0)),
        "source_pass_check_count": safe_int(row_get(source_run, "pass_check_count", 0)),
        "source_fail_check_count": safe_int(row_get(source_run, "fail_check_count", 0)),
        "training_check_count": len(checks),
        "pass_check_count": sum(1 for check in checks if check["check_status"] == CHECK_PASS),
        "fail_check_count": sum(1 for check in checks if check["check_status"] == CHECK_FAIL),
        "safety_breach_count": safe_int(row_get(source_run, "safety_breach_count", 0)),
        "leakage_breach_count": safe_int(row_get(source_run, "leakage_breach_count", 0)),
        "training_eligible_count": safe_int(row_get(source_run, "training_eligible_count", 0)),
        "training_locked_count": safe_int(row_get(source_run, "training_locked_count", 0)),
        "baseline_accuracy_pct": round8(safe_float(row_get(source_run, "baseline_accuracy_pct", 0.0))),
        "average_label_confidence": round8(safe_float(row_get(source_run, "average_label_confidence", 0.0))),
        "average_net_paper_outcome_bps": round8(safe_float(row_get(source_run, "average_net_paper_outcome_bps", 0.0))),
        "training_candidates": candidates,
        "training_checks": checks,
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
    candidate_lines = [
        f"- #{candidate['candidate_rank']} {candidate['source_paper_signal_code']}: status={candidate['candidate_status']}, action={candidate['candidate_action']}, training={candidate['model_training_action']}, artifact={candidate['model_artifact_action']}"
        for candidate in summary["training_candidates"]
    ]

    check_lines = [
        f"- {check['check_category']} / {check['check_name']}: status={check['check_status']}, observed={check['observed_value']}, threshold={check['threshold_value']}"
        for check in summary["training_checks"]
    ]

    return f"""# DeltaGrid Mission 84 Offline Model Training Harness Report

Report label: {summary['report_label']}
Training run label: {summary['training_run_label']}
Created at: {summary['created_at']}
Source feedback run label: {summary['source_feedback_run_label']}
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

## Offline Training Harness Summary

Training scope: {summary['training_scope']}
Training mode: {summary['training_mode']}

Training candidate count: {summary['training_candidate_count']}
Training ready candidate count: {summary['training_ready_candidate_count']}
Training blocked candidate count: {summary['training_blocked_candidate_count']}
Actual model training count: {summary['actual_model_training_count']}
Model artifact count: {summary['model_artifact_count']}
No model deployment count: {summary['no_model_deployment_count']}
No live deployment count: {summary['no_live_deployment_count']}
No strategy reweighting count: {summary['no_strategy_reweighting_count']}
No live signal count: {summary['no_live_signal_count']}
No exchange order count: {summary['no_exchange_order_count']}
No capital deployment count: {summary['no_capital_deployment_count']}
No profitability claim count: {summary['no_profitability_claim_count']}

Source feedback item count: {summary['source_feedback_item_count']}
Source recorded feedback count: {summary['source_recorded_feedback_count']}
Source blocked feedback count: {summary['source_blocked_feedback_count']}
Source feedback-only count: {summary['source_feedback_only_count']}
Source no model training count: {summary['source_no_model_training_count']}
Source no strategy reweighting count: {summary['source_no_strategy_reweighting_count']}
Source no live signal count: {summary['source_no_live_signal_count']}
Source no exchange order count: {summary['source_no_exchange_order_count']}
Source no capital deployment count: {summary['source_no_capital_deployment_count']}
Source no profitability claim count: {summary['source_no_profitability_claim_count']}

Training check count: {summary['training_check_count']}
Pass check count: {summary['pass_check_count']}
Fail check count: {summary['fail_check_count']}
Safety breach count: {summary['safety_breach_count']}
Leakage breach count: {summary['leakage_breach_count']}
Training eligible count: {summary['training_eligible_count']}
Training locked count: {summary['training_locked_count']}

Baseline accuracy pct: {summary['baseline_accuracy_pct']}
Average label confidence: {summary['average_label_confidence']}
Average net paper outcome bps: {summary['average_net_paper_outcome_bps']}

## Training Candidate Records

{chr(10).join(candidate_lines) if candidate_lines else "- None"}

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

This harness creates offline training candidate records only.
It does not run actual model training on insufficient data.
It does not create model artifacts.
It does not deploy models.
It does not reweight strategies.
It does not create live trading signals.
It does not perform exchange execution.
It does not deploy capital.
It does not perform autonomous live trading.

Training harness records are not profitability evidence.
"""


def insert_row(conn: sqlite3.Connection, table_name: str, row: dict[str, Any], columns: list[str]) -> None:
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT OR REPLACE INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})",
        [row[column] for column in columns],
    )


def persist_training_run(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for table in (CANDIDATES_TABLE, CHECKS_TABLE, RUNS_TABLE):
            conn.execute(f"DELETE FROM {table} WHERE training_run_label = ?", (summary["training_run_label"],))

        conn.execute(
            "DELETE FROM ai_offline_model_training_reports WHERE training_run_label = ? OR report_label = ?",
            (summary["training_run_label"], summary["report_label"]),
        )

        for candidate in summary["training_candidates"]:
            stored = dict(candidate)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                CANDIDATES_TABLE,
                stored,
                [
                    "training_candidate_id", "training_run_label", "created_at",
                    "source_feedback_run_label", "source_feedback_item_id",
                    "source_paper_signal_code", "candidate_rank", "training_scope",
                    "training_mode", "candidate_status", "candidate_action",
                    "dataset_readiness", "target_label_quality", "model_family",
                    "model_training_action", "model_artifact_action",
                    "model_deployment_action", "live_deployment_action",
                    "strategy_reweighting_action", "live_signal_action",
                    "exchange_order_action", "capital_action",
                    "not_profitability_claim", "live_trading", "live_order_sent",
                    "capital_deployment", "metadata_json",
                ],
            )

        for check in summary["training_checks"]:
            stored = dict(check)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                CHECKS_TABLE,
                stored,
                [
                    "check_id", "training_run_label", "created_at",
                    "source_feedback_run_label", "check_category", "check_name",
                    "check_status", "observed_value", "threshold_value",
                    "check_reason", "training_scope", "live_trading",
                    "live_order_sent", "capital_deployment", "metadata_json",
                ],
            )

        run_row = {
            **{key: summary[key] for key in [
                "training_run_label", "report_label", "created_at",
                "source_feedback_run_label", "source_execution_run_label",
                "source_signal_run_label", "source_policy_run_label",
                "source_recommendation_run_label", "source_governance_review_label",
                "source_evaluation_label", "source_guard_review_label",
                "source_collection_label", "source_registry_label",
                "source_build_label", "source_schedule_label",
                "source_learning_run_label", "source_multi_cycle_track_label",
                "source_session_label", "source_portfolio_label",
                "training_scope", "training_mode", "training_candidate_count",
                "training_ready_candidate_count", "training_blocked_candidate_count",
                "actual_model_training_count", "model_artifact_count",
                "no_model_deployment_count", "no_live_deployment_count",
                "no_strategy_reweighting_count", "no_live_signal_count",
                "no_exchange_order_count", "no_capital_deployment_count",
                "no_profitability_claim_count", "source_feedback_item_count",
                "source_recorded_feedback_count", "source_blocked_feedback_count",
                "source_feedback_only_count", "source_no_model_training_count",
                "source_no_strategy_reweighting_count", "source_no_live_signal_count",
                "source_no_exchange_order_count", "source_no_capital_deployment_count",
                "source_no_profitability_claim_count", "source_feedback_check_count",
                "source_pass_check_count", "source_fail_check_count",
                "training_check_count", "pass_check_count", "fail_check_count",
                "safety_breach_count", "leakage_breach_count",
                "training_eligible_count", "training_locked_count",
                "baseline_accuracy_pct", "average_label_confidence",
                "average_net_paper_outcome_bps", "engine_state",
                "engine_decision", "global_verdict", "recommended_action",
                "next_mission", "live_trading", "live_order_sent",
                "capital_deployment",
            ]},
            "summary_json": json.dumps(summary, sort_keys=True),
            "markdown_report": markdown_report,
        }

        insert_row(
            conn,
            RUNS_TABLE,
            run_row,
            [
                "training_run_label", "report_label", "created_at",
                "source_feedback_run_label", "source_execution_run_label",
                "source_signal_run_label", "source_policy_run_label",
                "source_recommendation_run_label", "source_governance_review_label",
                "source_evaluation_label", "source_guard_review_label",
                "source_collection_label", "source_registry_label",
                "source_build_label", "source_schedule_label",
                "source_learning_run_label", "source_multi_cycle_track_label",
                "source_session_label", "source_portfolio_label",
                "training_scope", "training_mode", "training_candidate_count",
                "training_ready_candidate_count", "training_blocked_candidate_count",
                "actual_model_training_count", "model_artifact_count",
                "no_model_deployment_count", "no_live_deployment_count",
                "no_strategy_reweighting_count", "no_live_signal_count",
                "no_exchange_order_count", "no_capital_deployment_count",
                "no_profitability_claim_count", "source_feedback_item_count",
                "source_recorded_feedback_count", "source_blocked_feedback_count",
                "source_feedback_only_count", "source_no_model_training_count",
                "source_no_strategy_reweighting_count", "source_no_live_signal_count",
                "source_no_exchange_order_count", "source_no_capital_deployment_count",
                "source_no_profitability_claim_count", "source_feedback_check_count",
                "source_pass_check_count", "source_fail_check_count",
                "training_check_count", "pass_check_count", "fail_check_count",
                "safety_breach_count", "leakage_breach_count",
                "training_eligible_count", "training_locked_count",
                "baseline_accuracy_pct", "average_label_confidence",
                "average_net_paper_outcome_bps", "engine_state",
                "engine_decision", "global_verdict", "recommended_action",
                "next_mission", "live_trading", "live_order_sent",
                "capital_deployment", "summary_json", "markdown_report",
            ],
        )

        report_row = {
            "report_label": summary["report_label"],
            "training_run_label": summary["training_run_label"],
            "created_at": summary["created_at"],
            "source_feedback_run_label": summary["source_feedback_run_label"],
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
                "report_label", "training_run_label", "created_at",
                "source_feedback_run_label", "global_verdict",
                "recommended_action", "report_json", "markdown_report",
                "live_trading", "live_order_sent", "capital_deployment",
            ],
        )

        conn.commit()


def run_offline_model_training_harness(
    db_path: str | Path = "offchain/deltagrid.db",
    training_run_label: str | None = None,
    report_label: str | None = None,
    feedback_run_label: str = "mission83-final-check",
    min_training_candidates: int = 5,
) -> dict[str, Any]:
    if min_training_candidates <= 0:
        raise ValueError("min_training_candidates must be positive")

    db = Path(db_path)
    run_label = training_run_label or new_training_run_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    source_feedback_label = parse_labels(feedback_run_label)[0]

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        source_run = load_feedback_run(conn, source_feedback_label)
        feedback_items = load_feedback_items(conn, source_feedback_label)
        source_checks = load_feedback_checks(conn, source_feedback_label)

    candidates = build_training_candidates(
        training_run_label=run_label,
        created_at=created_at,
        source_feedback_label=source_feedback_label,
        source_run=source_run,
        feedback_items=feedback_items,
    )

    if source_run is None:
        training_checks = build_missing_checks(run_label, created_at, source_feedback_label)
    else:
        training_checks = build_training_checks(
            training_run_label=run_label,
            created_at=created_at,
            source_feedback_label=source_feedback_label,
            source_run=source_run,
            feedback_items=feedback_items,
            source_checks=source_checks,
            candidates=candidates,
            min_candidates=min_training_candidates,
        )

    decision, verdict, action, next_mission, state, reason = decide_engine_outcome(
        source_run=source_run,
        checks=training_checks,
    )

    summary = build_summary(
        db_path=db,
        training_run_label=run_label,
        report_label=report,
        created_at=created_at,
        source_feedback_label=source_feedback_label,
        source_run=source_run,
        candidates=candidates,
        checks=training_checks,
        decision=decision,
        verdict=verdict,
        action=action,
        next_mission=next_mission,
        state=state,
        reason=reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_training_run(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid offline model training harness.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--training-run-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--feedback-run-label", default="mission83-final-check")
    parser.add_argument("--min-training-candidates", type=int, default=5)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_offline_model_training_harness(
        db_path=args.db,
        training_run_label=args.training_run_label,
        report_label=args.report_label,
        feedback_run_label=args.feedback_run_label,
        min_training_candidates=args.min_training_candidates,
    )

    print(result["markdown_report"] if args.markdown else json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

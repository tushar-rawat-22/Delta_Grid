"""
Mission 77: AI Offline Evaluation Harness.

This module evaluates finalized paper-only labels after Mission 76 approval.

Important boundary:
- This is offline evaluation only.
- This does not train a model.
- This does not unlock training.
- This does not create live signals.
- This does not trade.
- This does not adjust strategy weights.

It reads:
- ai_label_quality_leakage_guard_reviews
- ai_label_quality_leakage_guard_checks
- ai_label_quality_leakage_guard_findings
- ai_paper_outcome_final_labels

It writes:
- ai_offline_evaluation_runs
- ai_offline_evaluation_cases
- ai_offline_evaluation_metrics
- ai_offline_evaluation_checks
- ai_offline_evaluation_reports
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


GUARD_REVIEWS_TABLE = "ai_label_quality_leakage_guard_reviews"
GUARD_CHECKS_TABLE = "ai_label_quality_leakage_guard_checks"
GUARD_FINDINGS_TABLE = "ai_label_quality_leakage_guard_findings"
FINAL_LABELS_TABLE = "ai_paper_outcome_final_labels"

RUNS_TABLE = "ai_offline_evaluation_runs"
CASES_TABLE = "ai_offline_evaluation_cases"
METRICS_TABLE = "ai_offline_evaluation_metrics"
CHECKS_TABLE = "ai_offline_evaluation_checks"
REPORTS_TABLE = "ai_offline_evaluation_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

GUARD_DECISION_READY = "AI_LABEL_QUALITY_LEAKAGE_GUARD_APPROVED_FOR_OFFLINE_EVALUATION"
GUARD_VERDICT_READY = "AI_LABEL_QUALITY_LEAKAGE_GUARD_READY_SHADOW_ONLY"
GUARD_STATE_READY = "AI_LABEL_QUALITY_LEAKAGE_GUARD_READY"

OUTCOME_POSITIVE = "AI_PAPER_OUTCOME_LABEL_POSITIVE_AFTER_COST"
OUTCOME_NEUTRAL = "AI_PAPER_OUTCOME_LABEL_COST_DRAG_NEUTRAL"
OUTCOME_NEGATIVE = "AI_PAPER_OUTCOME_LABEL_NEGATIVE_AFTER_COST"

TARGET_POSITIVE = "AI_TARGET_LABEL_POSITIVE_AFTER_COST"
TARGET_NEUTRAL = "AI_TARGET_LABEL_COST_DRAG_NEUTRAL_EARLY"
TARGET_NEGATIVE = "AI_TARGET_LABEL_NEGATIVE_AFTER_COST"

ALLOWED_TARGET_LABELS = {TARGET_POSITIVE, TARGET_NEUTRAL, TARGET_NEGATIVE}

FINDING_STATUS_BREACH = "AI_LABEL_LEAKAGE_FINDING_BREACH"

EVALUATION_MODE = "DETERMINISTIC_BASELINE_OFFLINE_EVALUATION_NO_MODEL_TRAINING"
BASELINE_NAME = "COST_DRAG_NEUTRAL_BASELINE"
CASE_STATUS = "AI_OFFLINE_EVALUATION_CASE_EVALUATED_NO_TRAINING"
METRIC_STATUS = "AI_OFFLINE_EVALUATION_METRIC_RECORDED_NO_TRAINING"

CHECK_PASS = "AI_OFFLINE_EVALUATION_CHECK_PASS"
CHECK_FAIL = "AI_OFFLINE_EVALUATION_CHECK_FAIL"

EVALUATION_STATE_READY = "AI_OFFLINE_EVALUATION_HARNESS_READY"
EVALUATION_STATE_UNSTABLE = "AI_OFFLINE_EVALUATION_HARNESS_UNSTABLE"
EVALUATION_STATE_BLOCKED = "AI_OFFLINE_EVALUATION_HARNESS_BLOCKED"
EVALUATION_STATE_MISSING = "AI_OFFLINE_EVALUATION_HARNESS_MISSING"

DECISION_READY = "AI_OFFLINE_EVALUATION_APPROVED_FOR_GOVERNANCE_REVIEW"
DECISION_UNSTABLE = "AI_OFFLINE_EVALUATION_UNSTABLE_REVIEW_REQUIRED"
DECISION_BLOCK_SAFETY = "AI_OFFLINE_EVALUATION_BLOCKED_BY_SAFETY_POLICY"
DECISION_REJECT_MISSING = "AI_OFFLINE_EVALUATION_REJECTED_MISSING_EVIDENCE"

VERDICT_READY = "AI_OFFLINE_EVALUATION_READY_SHADOW_ONLY"
VERDICT_UNSTABLE = "AI_OFFLINE_EVALUATION_UNSTABLE_SHADOW_ONLY"
VERDICT_BLOCKED = "AI_OFFLINE_EVALUATION_BLOCKED_SHADOW_ONLY"
VERDICT_MISSING = "AI_OFFLINE_EVALUATION_MISSING_EVIDENCE"

ACTION_READY = "HAND_OFF_OFFLINE_EVALUATION_TO_GOVERNANCE_REVIEW"
ACTION_REVIEW_UNSTABLE = "REVIEW_OFFLINE_EVALUATION_BEFORE_GOVERNANCE"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_OFFLINE_EVALUATION_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_AI_LABEL_QUALITY_LEAKAGE_GUARD"

NEXT_READY = "Mission 78 AI Offline Evaluation Governance Board"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_evaluation_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission77-ai-offline-evaluation-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission77-ai-offline-evaluation-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
        return default
    except (AttributeError, IndexError, KeyError):
        try:
            return row[key]
        except (IndexError, KeyError, TypeError):
            return default


def parse_labels(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return ["mission76-final-check"]

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    labels: list[str] = []

    for item in raw_items:
        label = str(item).strip()

        if not label:
            continue

        if any(ch.isspace() for ch in label):
            raise ValueError(f"Invalid label quality guard review label: {label}")

        if label not in labels:
            labels.append(label)

    if not labels:
        raise ValueError("At least one label quality guard review label is required")

    return labels


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name = ?
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def ensure_schema(db_path: str | Path) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_offline_evaluation_runs (
                evaluation_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_guard_review_label TEXT NOT NULL,
                source_collection_label TEXT,
                source_registry_label TEXT,
                source_build_label TEXT,
                source_schedule_label TEXT,
                source_guard_review_label_upstream TEXT,
                source_learning_run_label TEXT,
                source_multi_cycle_track_label TEXT,
                source_session_label TEXT,
                source_portfolio_label TEXT,
                final_label_count INTEGER NOT NULL,
                evaluation_case_count INTEGER NOT NULL,
                metric_count INTEGER NOT NULL,
                correct_prediction_count INTEGER NOT NULL,
                incorrect_prediction_count INTEGER NOT NULL,
                baseline_accuracy_pct TEXT NOT NULL,
                neutral_prediction_count INTEGER NOT NULL,
                positive_actual_count INTEGER NOT NULL,
                neutral_actual_count INTEGER NOT NULL,
                negative_actual_count INTEGER NOT NULL,
                training_eligible_count INTEGER NOT NULL,
                training_locked_count INTEGER NOT NULL,
                leakage_breach_count INTEGER NOT NULL,
                offline_evaluation_candidate_count INTEGER NOT NULL,
                evaluation_check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                average_label_confidence TEXT NOT NULL,
                average_net_paper_outcome_bps TEXT NOT NULL,
                worst_net_paper_outcome_bps TEXT NOT NULL,
                best_net_paper_outcome_bps TEXT NOT NULL,
                evaluation_mode TEXT NOT NULL,
                baseline_name TEXT NOT NULL,
                evaluation_state TEXT NOT NULL,
                evaluation_decision TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_offline_evaluation_cases (
                evaluation_case_id TEXT PRIMARY KEY,
                evaluation_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_guard_review_label TEXT NOT NULL,
                source_final_label_id TEXT NOT NULL,
                source_collection_label TEXT,
                source_collection_record_id TEXT,
                source_feature_record_id TEXT,
                source_training_entry_id TEXT,
                actual_outcome_label TEXT NOT NULL,
                actual_target_label TEXT NOT NULL,
                baseline_prediction_label TEXT NOT NULL,
                prediction_correct INTEGER NOT NULL,
                label_confidence TEXT NOT NULL,
                net_paper_outcome_bps TEXT NOT NULL,
                training_eligible INTEGER NOT NULL,
                offline_evaluation_candidate INTEGER NOT NULL,
                evaluation_mode TEXT NOT NULL,
                baseline_name TEXT NOT NULL,
                case_status TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_offline_evaluation_metrics (
                metric_id TEXT PRIMARY KEY,
                evaluation_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_guard_review_label TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value TEXT NOT NULL,
                metric_status TEXT NOT NULL,
                metric_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_offline_evaluation_checks (
                check_id TEXT PRIMARY KEY,
                evaluation_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_guard_review_label TEXT NOT NULL,
                check_category TEXT NOT NULL,
                check_name TEXT NOT NULL,
                check_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                threshold_value TEXT NOT NULL,
                check_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_offline_evaluation_reports (
                report_label TEXT PRIMARY KEY,
                evaluation_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_guard_review_label TEXT NOT NULL,
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


def load_guard_review(conn: sqlite3.Connection, review_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, GUARD_REVIEWS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM ai_label_quality_leakage_guard_reviews
        WHERE review_label = ?
        """,
        (review_label,),
    ).fetchone()


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not table_exists(conn, table_name):
        return set()

    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def load_guard_checks(conn: sqlite3.Connection, review_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, GUARD_CHECKS_TABLE):
        return []

    columns = table_columns(conn, GUARD_CHECKS_TABLE)
    order_by = "created_at ASC, check_id ASC" if "created_at" in columns else "check_id ASC"

    return conn.execute(
        f"""
        SELECT *
        FROM ai_label_quality_leakage_guard_checks
        WHERE review_label = ?
        ORDER BY {order_by}
        """,
        (review_label,),
    ).fetchall()


def load_guard_findings(conn: sqlite3.Connection, review_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, GUARD_FINDINGS_TABLE):
        return []

    columns = table_columns(conn, GUARD_FINDINGS_TABLE)
    order_by = "created_at ASC, finding_id ASC" if "created_at" in columns else "finding_id ASC"

    return conn.execute(
        f"""
        SELECT *
        FROM ai_label_quality_leakage_guard_findings
        WHERE review_label = ?
        ORDER BY {order_by}
        """,
        (review_label,),
    ).fetchall()


def load_final_labels(conn: sqlite3.Connection, collection_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, FINAL_LABELS_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM ai_paper_outcome_final_labels
        WHERE collection_label = ?
        ORDER BY final_label_id ASC
        """,
        (collection_label,),
    ).fetchall()


def actual_bucket_counts(labels: list[sqlite3.Row]) -> tuple[int, int, int]:
    positive = sum(1 for row in labels if row_get(row, "target_label", "") == TARGET_POSITIVE)
    neutral = sum(1 for row in labels if row_get(row, "target_label", "") == TARGET_NEUTRAL)
    negative = sum(1 for row in labels if row_get(row, "target_label", "") == TARGET_NEGATIVE)
    return positive, neutral, negative


def build_evaluation_cases(
    evaluation_label: str,
    created_at: str,
    guard_review_label: str,
    labels: list[sqlite3.Row],
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    for index, label in enumerate(labels, start=1):
        final_label_id = str(row_get(label, "final_label_id", f"final-label-{index}"))
        actual_target = str(row_get(label, "target_label", ""))
        baseline_prediction = TARGET_NEUTRAL
        prediction_correct = 1 if actual_target == baseline_prediction else 0

        cases.append(
            {
                "evaluation_case_id": f"{evaluation_label}-{final_label_id}-case".replace(" ", "_"),
                "evaluation_label": evaluation_label,
                "created_at": created_at,
                "source_guard_review_label": guard_review_label,
                "source_final_label_id": final_label_id,
                "source_collection_label": row_get(label, "collection_label", None),
                "source_collection_record_id": row_get(label, "source_collection_record_id", None),
                "source_feature_record_id": row_get(label, "source_feature_record_id", None),
                "source_training_entry_id": row_get(label, "source_training_entry_id", None),
                "actual_outcome_label": str(row_get(label, "outcome_label", "")),
                "actual_target_label": actual_target,
                "baseline_prediction_label": baseline_prediction,
                "prediction_correct": prediction_correct,
                "label_confidence": round8(safe_float(row_get(label, "label_confidence", 0.0))),
                "net_paper_outcome_bps": round8(safe_float(row_get(label, "net_paper_outcome_bps", 0.0))),
                "training_eligible": safe_int(row_get(label, "training_eligible", 0)),
                "offline_evaluation_candidate": safe_int(row_get(label, "offline_evaluation_candidate", 0)),
                "evaluation_mode": EVALUATION_MODE,
                "baseline_name": BASELINE_NAME,
                "case_status": CASE_STATUS,
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT_VALUE,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "metadata": {
                    "offline_evaluation_role": "DETERMINISTIC_BASELINE_CASE_ONLY",
                    "baseline_prediction_only": True,
                    "model_training_enabled": False,
                    "execution_role": "NONE",
                    "private_keys_used": False,
                    "orders_sent": False,
                    "paid_api_used": False,
                    "real_capital_used": False,
                    "autonomous_trading_enabled": False,
                    "automatic_strategy_reweighting_enabled": False,
                    "not_profitability_claim": True,
                },
            }
        )

    return cases


def metric_row(
    evaluation_label: str,
    created_at: str,
    guard_review_label: str,
    name: str,
    value: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "metric_id": f"{evaluation_label}-{name}".replace(" ", "_"),
        "evaluation_label": evaluation_label,
        "created_at": created_at,
        "source_guard_review_label": guard_review_label,
        "metric_name": name,
        "metric_value": str(value),
        "metric_status": METRIC_STATUS,
        "metric_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "offline_evaluation_role": "METRIC_RECORD_ONLY",
            "model_training_enabled": False,
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
            "autonomous_trading_enabled": False,
            "automatic_strategy_reweighting_enabled": False,
        },
    }


def average(values: list[float]) -> float:
    return round8(sum(values) / len(values)) if values else 0.0


def build_metrics(
    evaluation_label: str,
    created_at: str,
    guard_review_label: str,
    cases: list[dict[str, Any]],
    labels: list[sqlite3.Row],
) -> list[dict[str, Any]]:
    case_count = len(cases)
    correct = sum(case["prediction_correct"] for case in cases)
    incorrect = case_count - correct
    accuracy = round8((correct / case_count) * 100.0) if case_count else 0.0
    neutral_predictions = sum(1 for case in cases if case["baseline_prediction_label"] == TARGET_NEUTRAL)
    positive_actual, neutral_actual, negative_actual = actual_bucket_counts(labels)
    confidences = [safe_float(case["label_confidence"]) for case in cases]
    net_bps = [safe_float(case["net_paper_outcome_bps"]) for case in cases]

    return [
        metric_row(evaluation_label, created_at, guard_review_label, "case_count", case_count, "Total offline evaluation cases."),
        metric_row(evaluation_label, created_at, guard_review_label, "correct_prediction_count", correct, "Baseline label agreement count."),
        metric_row(evaluation_label, created_at, guard_review_label, "incorrect_prediction_count", incorrect, "Baseline label disagreement count."),
        metric_row(evaluation_label, created_at, guard_review_label, "baseline_accuracy_pct", accuracy, "Deterministic baseline label-agreement percentage, not profitability."),
        metric_row(evaluation_label, created_at, guard_review_label, "neutral_prediction_count", neutral_predictions, "Count of neutral baseline predictions."),
        metric_row(evaluation_label, created_at, guard_review_label, "positive_actual_count", positive_actual, "Actual positive target labels."),
        metric_row(evaluation_label, created_at, guard_review_label, "neutral_actual_count", neutral_actual, "Actual neutral target labels."),
        metric_row(evaluation_label, created_at, guard_review_label, "negative_actual_count", negative_actual, "Actual negative target labels."),
        metric_row(evaluation_label, created_at, guard_review_label, "average_label_confidence", average(confidences), "Average finalized-label confidence."),
        metric_row(evaluation_label, created_at, guard_review_label, "average_net_paper_outcome_bps", average(net_bps), "Average local paper outcome bps."),
    ]


def offline_check(
    evaluation_label: str,
    created_at: str,
    guard_review_label: str,
    category: str,
    name: str,
    status: str,
    observed: Any,
    threshold: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{evaluation_label}-{category}-{name}".replace(" ", "_"),
        "evaluation_label": evaluation_label,
        "created_at": created_at,
        "source_guard_review_label": guard_review_label,
        "check_category": category,
        "check_name": name,
        "check_status": status,
        "observed_value": str(observed),
        "threshold_value": str(threshold),
        "check_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "offline_evaluation_role": "CHECK_RECORD_ONLY",
            "model_training_enabled": False,
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
            "autonomous_trading_enabled": False,
            "automatic_strategy_reweighting_enabled": False,
        },
    }


def build_missing_checks(evaluation_label: str, created_at: str, guard_review_label: str) -> list[dict[str, Any]]:
    return [
        offline_check(
            evaluation_label,
            created_at,
            guard_review_label,
            "availability",
            "label quality guard review exists",
            CHECK_FAIL,
            "missing",
            "ai_label_quality_leakage_guard_reviews record",
            "No label quality guard review exists for this label.",
        )
    ]


def build_quality_checks(
    evaluation_label: str,
    created_at: str,
    guard_review_label: str,
    guard_review: sqlite3.Row,
    labels: list[sqlite3.Row],
    guard_checks: list[sqlite3.Row],
    guard_findings: list[sqlite3.Row],
    cases: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    min_cases: int,
    min_label_confidence: float,
) -> list[dict[str, Any]]:
    safety_count = safe_int(row_get(guard_review, "safety_breach_count", 0))
    safety_count += sum(1 for row in [guard_review, *labels, *guard_checks, *guard_findings] if safety_problem(row))

    label_count = len(labels)
    case_count = len(cases)
    metric_count = len(metrics)
    source_fail_count = safe_int(row_get(guard_review, "fail_check_count", 0))
    leakage_breach_count = safe_int(row_get(guard_review, "leakage_breach_count", 0))
    leakage_breach_count += sum(1 for finding in guard_findings if row_get(finding, "finding_status", "") == FINDING_STATUS_BREACH)

    training_eligible_count = sum(1 for label in labels if safe_int(row_get(label, "training_eligible", 0)) != 0)
    training_locked_count = sum(1 for label in labels if safe_int(row_get(label, "training_eligible", 0)) == 0)
    offline_candidate_count = sum(1 for label in labels if safe_int(row_get(label, "offline_evaluation_candidate", 0)) == 1)
    low_confidence_count = sum(1 for label in labels if safe_float(row_get(label, "label_confidence", 0.0)) < min_label_confidence)
    invalid_target_count = sum(1 for label in labels if row_get(label, "target_label", "") not in ALLOWED_TARGET_LABELS)
    correct = sum(case["prediction_correct"] for case in cases)

    return [
        offline_check(evaluation_label, created_at, guard_review_label, "availability", "label quality guard review exists", CHECK_PASS, "present", "present", "Label quality guard review exists."),
        offline_check(evaluation_label, created_at, guard_review_label, "safety", "safety breach count", CHECK_PASS if safety_count == 0 else CHECK_FAIL, safety_count, 0, "Offline evaluation requires zero safety breaches."),
        offline_check(evaluation_label, created_at, guard_review_label, "guard", "guard decision approved", CHECK_PASS if row_get(guard_review, "guard_decision", "") == GUARD_DECISION_READY else CHECK_FAIL, row_get(guard_review, "guard_decision", ""), GUARD_DECISION_READY, "Guard must approve labels for offline evaluation."),
        offline_check(evaluation_label, created_at, guard_review_label, "guard", "guard verdict ready", CHECK_PASS if row_get(guard_review, "global_verdict", "") == GUARD_VERDICT_READY else CHECK_FAIL, row_get(guard_review, "global_verdict", ""), GUARD_VERDICT_READY, "Guard verdict must be ready and shadow-only."),
        offline_check(evaluation_label, created_at, guard_review_label, "guard", "guard state ready", CHECK_PASS if row_get(guard_review, "guard_state", "") == GUARD_STATE_READY else CHECK_FAIL, row_get(guard_review, "guard_state", ""), GUARD_STATE_READY, "Guard state must be ready."),
        offline_check(evaluation_label, created_at, guard_review_label, "guard", "source guard failed checks", CHECK_PASS if source_fail_count == 0 else CHECK_FAIL, source_fail_count, 0, "Guard failed checks must remain zero."),
        offline_check(evaluation_label, created_at, guard_review_label, "leakage", "leakage breach count", CHECK_PASS if leakage_breach_count == 0 else CHECK_FAIL, leakage_breach_count, 0, "Offline evaluation cannot proceed with leakage breaches."),
        offline_check(evaluation_label, created_at, guard_review_label, "coverage", "final label count", CHECK_PASS if label_count >= min_cases else CHECK_FAIL, label_count, f">= {min_cases}", "Enough final labels must exist for offline evaluation."),
        offline_check(evaluation_label, created_at, guard_review_label, "coverage", "evaluation case count", CHECK_PASS if case_count == label_count and case_count >= min_cases else CHECK_FAIL, case_count, f"== {label_count} and >= {min_cases}", "Every final label must produce one evaluation case."),
        offline_check(evaluation_label, created_at, guard_review_label, "metrics", "metric count", CHECK_PASS if metric_count >= 10 else CHECK_FAIL, metric_count, ">= 10", "Offline evaluation must produce the core metric set."),
        offline_check(evaluation_label, created_at, guard_review_label, "labels", "allowed target labels", CHECK_PASS if invalid_target_count == 0 else CHECK_FAIL, invalid_target_count, 0, "All labels must use allowed target classes."),
        offline_check(evaluation_label, created_at, guard_review_label, "labels", "label confidence floor", CHECK_PASS if low_confidence_count == 0 else CHECK_FAIL, low_confidence_count, 0, f"All label confidences must be >= {min_label_confidence}."),
        offline_check(evaluation_label, created_at, guard_review_label, "training_lock", "training remains locked", CHECK_PASS if training_eligible_count == 0 and training_locked_count == label_count and label_count > 0 else CHECK_FAIL, f"eligible={training_eligible_count}, locked={training_locked_count}", f"eligible=0, locked={label_count}", "Offline evaluation must not unlock training."),
        offline_check(evaluation_label, created_at, guard_review_label, "offline_eval", "offline evaluation candidates", CHECK_PASS if offline_candidate_count == label_count and label_count > 0 else CHECK_FAIL, offline_candidate_count, label_count, "Every final label must be an offline-evaluation candidate."),
        offline_check(evaluation_label, created_at, guard_review_label, "baseline", "baseline predictions recorded", CHECK_PASS if correct >= 0 and case_count > 0 else CHECK_FAIL, f"correct={correct}, cases={case_count}", "cases > 0", "Baseline predictions must be recorded for analysis only."),
        offline_check(evaluation_label, created_at, guard_review_label, "model_training", "model training remains disabled", CHECK_PASS, "disabled", "disabled", "This harness does not train a model."),
    ]


def decide_evaluation_outcome(
    guard_review: sqlite3.Row | None,
    checks: list[dict[str, Any]],
) -> tuple[str, str, str, str, str, str]:
    if guard_review is None:
        return (
            DECISION_REJECT_MISSING,
            VERDICT_MISSING,
            ACTION_REFRESH,
            "Mission 76 AI Label Quality and Leakage Guard",
            EVALUATION_STATE_MISSING,
            "Label quality guard evidence is missing.",
        )

    failed = [check for check in checks if check["check_status"] == CHECK_FAIL]

    if any(check["check_category"] == "safety" for check in failed):
        return (
            DECISION_BLOCK_SAFETY,
            VERDICT_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 77 safety remediation",
            EVALUATION_STATE_BLOCKED,
            "Safety invariant failed during offline evaluation.",
        )

    if failed:
        return (
            DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 76 AI Label Quality and Leakage Guard",
            EVALUATION_STATE_UNSTABLE,
            "Offline evaluation failed one or more readiness checks.",
        )

    return (
        DECISION_READY,
        VERDICT_READY,
        ACTION_READY,
        NEXT_READY,
        EVALUATION_STATE_READY,
        "Offline evaluation completed. Results are governance-review evidence only; no model training or trading is approved.",
    )


def metric_value(metrics: list[dict[str, Any]], name: str) -> float:
    for metric in metrics:
        if metric["metric_name"] == name:
            return safe_float(metric["metric_value"])
    return 0.0


def build_summary(
    db_path: str | Path,
    evaluation_label: str,
    report_label: str,
    created_at: str,
    guard_review_label: str,
    guard_review: sqlite3.Row | None,
    labels: list[sqlite3.Row],
    cases: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    decision: str,
    verdict: str,
    action: str,
    next_mission: str,
    state: str,
    reason: str,
) -> dict[str, Any]:
    pass_count = sum(1 for check in checks if check["check_status"] == CHECK_PASS)
    fail_count = sum(1 for check in checks if check["check_status"] == CHECK_FAIL)
    correct = sum(case["prediction_correct"] for case in cases)
    case_count = len(cases)
    incorrect = case_count - correct
    positive_actual, neutral_actual, negative_actual = actual_bucket_counts(labels)
    training_eligible_count = sum(1 for label in labels if safe_int(row_get(label, "training_eligible", 0)) != 0)
    training_locked_count = sum(1 for label in labels if safe_int(row_get(label, "training_eligible", 0)) == 0)
    offline_candidate_count = sum(1 for label in labels if safe_int(row_get(label, "offline_evaluation_candidate", 0)) == 1)

    return {
        "evaluation_label": evaluation_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_guard_review_label": guard_review_label,
        "source_collection_label": row_get(guard_review, "source_collection_label", None),
        "source_registry_label": row_get(guard_review, "source_registry_label", None),
        "source_build_label": row_get(guard_review, "source_build_label", None),
        "source_schedule_label": row_get(guard_review, "source_schedule_label", None),
        "source_guard_review_label_upstream": row_get(guard_review, "source_guard_review_label", None),
        "source_learning_run_label": row_get(guard_review, "source_learning_run_label", None),
        "source_multi_cycle_track_label": row_get(guard_review, "source_multi_cycle_track_label", None),
        "source_session_label": row_get(guard_review, "source_session_label", None),
        "source_portfolio_label": row_get(guard_review, "source_portfolio_label", None),
        "final_label_count": len(labels),
        "evaluation_case_count": case_count,
        "metric_count": len(metrics),
        "correct_prediction_count": correct,
        "incorrect_prediction_count": incorrect,
        "baseline_accuracy_pct": round8((correct / case_count) * 100.0) if case_count else 0.0,
        "neutral_prediction_count": sum(1 for case in cases if case["baseline_prediction_label"] == TARGET_NEUTRAL),
        "positive_actual_count": positive_actual,
        "neutral_actual_count": neutral_actual,
        "negative_actual_count": negative_actual,
        "training_eligible_count": training_eligible_count,
        "training_locked_count": training_locked_count,
        "leakage_breach_count": safe_int(row_get(guard_review, "leakage_breach_count", 0)),
        "offline_evaluation_candidate_count": offline_candidate_count,
        "evaluation_check_count": len(checks),
        "pass_check_count": pass_count,
        "fail_check_count": fail_count,
        "safety_breach_count": safe_int(row_get(guard_review, "safety_breach_count", 0)),
        "average_label_confidence": round8(safe_float(row_get(guard_review, "average_label_confidence", metric_value(metrics, "average_label_confidence")))),
        "average_net_paper_outcome_bps": round8(safe_float(row_get(guard_review, "average_net_paper_outcome_bps", metric_value(metrics, "average_net_paper_outcome_bps")))),
        "worst_net_paper_outcome_bps": round8(safe_float(row_get(guard_review, "worst_net_paper_outcome_bps", 0.0))),
        "best_net_paper_outcome_bps": round8(safe_float(row_get(guard_review, "best_net_paper_outcome_bps", 0.0))),
        "evaluation_mode": EVALUATION_MODE,
        "baseline_name": BASELINE_NAME,
        "evaluation_cases": cases,
        "evaluation_metrics": metrics,
        "evaluation_checks": checks,
        "evaluation_state": state,
        "evaluation_decision": decision,
        "global_verdict": verdict,
        "recommended_action": action,
        "next_mission": next_mission,
        "decision_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    case_lines = [
        f"- actual={case['actual_target_label']}, baseline={case['baseline_prediction_label']}, correct={case['prediction_correct']}, net_bps={case['net_paper_outcome_bps']}"
        for case in summary["evaluation_cases"]
    ]

    metric_lines = [
        f"- {metric['metric_name']}: {metric['metric_value']}"
        for metric in summary["evaluation_metrics"]
    ]

    check_lines = [
        f"- {check['check_category']} / {check['check_name']}: status={check['check_status']}, observed={check['observed_value']}, threshold={check['threshold_value']}"
        for check in summary["evaluation_checks"]
    ]

    return f"""# DeltaGrid Mission 77 AI Offline Evaluation Harness Report

Report label: {summary['report_label']}
Evaluation label: {summary['evaluation_label']}
Created at: {summary['created_at']}
Source guard review label: {summary['source_guard_review_label']}
Source collection label: {summary['source_collection_label']}
Source registry label: {summary['source_registry_label']}
Source build label: {summary['source_build_label']}
Source schedule label: {summary['source_schedule_label']}
Source learning run label: {summary['source_learning_run_label']}
Source multi-cycle track label: {summary['source_multi_cycle_track_label']}
Source session label: {summary['source_session_label']}
Source portfolio label: {summary['source_portfolio_label']}

## Offline Evaluation Summary

Evaluation mode: {summary['evaluation_mode']}
Baseline name: {summary['baseline_name']}
Final label count: {summary['final_label_count']}
Evaluation case count: {summary['evaluation_case_count']}
Metric count: {summary['metric_count']}
Correct prediction count: {summary['correct_prediction_count']}
Incorrect prediction count: {summary['incorrect_prediction_count']}
Baseline accuracy pct: {summary['baseline_accuracy_pct']}
Neutral prediction count: {summary['neutral_prediction_count']}
Positive actual count: {summary['positive_actual_count']}
Neutral actual count: {summary['neutral_actual_count']}
Negative actual count: {summary['negative_actual_count']}

Training eligible count: {summary['training_eligible_count']}
Training locked count: {summary['training_locked_count']}
Leakage breach count: {summary['leakage_breach_count']}
Offline evaluation candidate count: {summary['offline_evaluation_candidate_count']}

Average label confidence: {summary['average_label_confidence']}
Average net paper outcome bps: {summary['average_net_paper_outcome_bps']}
Worst net paper outcome bps: {summary['worst_net_paper_outcome_bps']}
Best net paper outcome bps: {summary['best_net_paper_outcome_bps']}

Evaluation check count: {summary['evaluation_check_count']}
Pass check count: {summary['pass_check_count']}
Fail check count: {summary['fail_check_count']}
Safety breach count: {summary['safety_breach_count']}

## Evaluation Cases

{chr(10).join(case_lines) if case_lines else "- None"}

## Metrics

{chr(10).join(metric_lines) if metric_lines else "- None"}

## Checks

{chr(10).join(check_lines) if check_lines else "- None"}

## Decision

Evaluation state: {summary['evaluation_state']}
Evaluation decision: {summary['evaluation_decision']}
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

This harness does not train a model.
This harness does not create live trading signals.
This harness does not perform autonomous trading.
This harness does not adjust strategy weights automatically.

Baseline accuracy here is offline label agreement only.
It is not profitability evidence.
"""


def insert_row(conn: sqlite3.Connection, table_name: str, row: dict[str, Any], columns: list[str]) -> None:
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    values = [row[column] for column in columns]
    conn.execute(f"INSERT OR REPLACE INTO {table_name} ({column_sql}) VALUES ({placeholders})", values)


def persist_evaluation(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for case in summary["evaluation_cases"]:
            stored = dict(case)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                CASES_TABLE,
                stored,
                [
                    "evaluation_case_id", "evaluation_label", "created_at",
                    "source_guard_review_label", "source_final_label_id",
                    "source_collection_label", "source_collection_record_id",
                    "source_feature_record_id", "source_training_entry_id",
                    "actual_outcome_label", "actual_target_label",
                    "baseline_prediction_label", "prediction_correct",
                    "label_confidence", "net_paper_outcome_bps",
                    "training_eligible", "offline_evaluation_candidate",
                    "evaluation_mode", "baseline_name", "case_status",
                    "live_trading", "live_order_sent", "capital_deployment",
                    "metadata_json",
                ],
            )

        for metric in summary["evaluation_metrics"]:
            stored_metric = dict(metric)
            stored_metric["metadata_json"] = json.dumps(stored_metric.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                METRICS_TABLE,
                stored_metric,
                [
                    "metric_id", "evaluation_label", "created_at",
                    "source_guard_review_label", "metric_name", "metric_value",
                    "metric_status", "metric_reason", "live_trading",
                    "live_order_sent", "capital_deployment", "metadata_json",
                ],
            )

        for check in summary["evaluation_checks"]:
            stored_check = dict(check)
            stored_check["metadata_json"] = json.dumps(stored_check.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                CHECKS_TABLE,
                stored_check,
                [
                    "check_id", "evaluation_label", "created_at",
                    "source_guard_review_label", "check_category", "check_name",
                    "check_status", "observed_value", "threshold_value",
                    "check_reason", "live_trading", "live_order_sent",
                    "capital_deployment", "metadata_json",
                ],
            )

        run_row = {
            "evaluation_label": summary["evaluation_label"],
            "report_label": summary["report_label"],
            "created_at": summary["created_at"],
            "source_guard_review_label": summary["source_guard_review_label"],
            "source_collection_label": summary["source_collection_label"],
            "source_registry_label": summary["source_registry_label"],
            "source_build_label": summary["source_build_label"],
            "source_schedule_label": summary["source_schedule_label"],
            "source_guard_review_label_upstream": summary["source_guard_review_label_upstream"],
            "source_learning_run_label": summary["source_learning_run_label"],
            "source_multi_cycle_track_label": summary["source_multi_cycle_track_label"],
            "source_session_label": summary["source_session_label"],
            "source_portfolio_label": summary["source_portfolio_label"],
            "final_label_count": summary["final_label_count"],
            "evaluation_case_count": summary["evaluation_case_count"],
            "metric_count": summary["metric_count"],
            "correct_prediction_count": summary["correct_prediction_count"],
            "incorrect_prediction_count": summary["incorrect_prediction_count"],
            "baseline_accuracy_pct": str(summary["baseline_accuracy_pct"]),
            "neutral_prediction_count": summary["neutral_prediction_count"],
            "positive_actual_count": summary["positive_actual_count"],
            "neutral_actual_count": summary["neutral_actual_count"],
            "negative_actual_count": summary["negative_actual_count"],
            "training_eligible_count": summary["training_eligible_count"],
            "training_locked_count": summary["training_locked_count"],
            "leakage_breach_count": summary["leakage_breach_count"],
            "offline_evaluation_candidate_count": summary["offline_evaluation_candidate_count"],
            "evaluation_check_count": summary["evaluation_check_count"],
            "pass_check_count": summary["pass_check_count"],
            "fail_check_count": summary["fail_check_count"],
            "safety_breach_count": summary["safety_breach_count"],
            "average_label_confidence": str(summary["average_label_confidence"]),
            "average_net_paper_outcome_bps": str(summary["average_net_paper_outcome_bps"]),
            "worst_net_paper_outcome_bps": str(summary["worst_net_paper_outcome_bps"]),
            "best_net_paper_outcome_bps": str(summary["best_net_paper_outcome_bps"]),
            "evaluation_mode": summary["evaluation_mode"],
            "baseline_name": summary["baseline_name"],
            "evaluation_state": summary["evaluation_state"],
            "evaluation_decision": summary["evaluation_decision"],
            "global_verdict": summary["global_verdict"],
            "recommended_action": summary["recommended_action"],
            "next_mission": summary["next_mission"],
            "live_trading": summary["live_trading"],
            "live_order_sent": summary["live_order_sent"],
            "capital_deployment": summary["capital_deployment"],
            "summary_json": json.dumps(summary, sort_keys=True),
            "markdown_report": markdown_report,
        }

        insert_row(
            conn,
            RUNS_TABLE,
            run_row,
            [
                "evaluation_label", "report_label", "created_at",
                "source_guard_review_label", "source_collection_label",
                "source_registry_label", "source_build_label", "source_schedule_label",
                "source_guard_review_label_upstream", "source_learning_run_label",
                "source_multi_cycle_track_label", "source_session_label",
                "source_portfolio_label", "final_label_count",
                "evaluation_case_count", "metric_count", "correct_prediction_count",
                "incorrect_prediction_count", "baseline_accuracy_pct",
                "neutral_prediction_count", "positive_actual_count",
                "neutral_actual_count", "negative_actual_count",
                "training_eligible_count", "training_locked_count",
                "leakage_breach_count", "offline_evaluation_candidate_count",
                "evaluation_check_count", "pass_check_count", "fail_check_count",
                "safety_breach_count", "average_label_confidence",
                "average_net_paper_outcome_bps", "worst_net_paper_outcome_bps",
                "best_net_paper_outcome_bps", "evaluation_mode", "baseline_name",
                "evaluation_state", "evaluation_decision", "global_verdict",
                "recommended_action", "next_mission", "live_trading",
                "live_order_sent", "capital_deployment", "summary_json",
                "markdown_report",
            ],
        )

        report_row = {
            "report_label": summary["report_label"],
            "evaluation_label": summary["evaluation_label"],
            "created_at": summary["created_at"],
            "source_guard_review_label": summary["source_guard_review_label"],
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
                "report_label", "evaluation_label", "created_at",
                "source_guard_review_label", "global_verdict",
                "recommended_action", "report_json", "markdown_report",
                "live_trading", "live_order_sent", "capital_deployment",
            ],
        )

        conn.commit()


def run_ai_offline_evaluation_harness(
    db_path: str | Path = "offchain/deltagrid.db",
    evaluation_label: str | None = None,
    report_label: str | None = None,
    guard_review_label: str = "mission76-final-check",
    min_cases: int = 4,
    min_label_confidence: float = 0.60,
) -> dict[str, Any]:
    if min_cases <= 0:
        raise ValueError("min_cases must be positive")

    if min_label_confidence < 0 or min_label_confidence > 1:
        raise ValueError("min_label_confidence must be between 0 and 1")

    db = Path(db_path)
    evaluation = evaluation_label or new_evaluation_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    source_guard_review_label = parse_labels(guard_review_label)[0]

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        guard_review = load_guard_review(conn, source_guard_review_label)
        guard_checks = load_guard_checks(conn, source_guard_review_label)
        guard_findings = load_guard_findings(conn, source_guard_review_label)

        if guard_review is None:
            labels: list[sqlite3.Row] = []
        else:
            labels = load_final_labels(conn, str(row_get(guard_review, "source_collection_label", "")))

    if guard_review is None:
        cases: list[dict[str, Any]] = []
        metrics: list[dict[str, Any]] = []
        checks = build_missing_checks(evaluation, created_at, source_guard_review_label)
    else:
        cases = build_evaluation_cases(evaluation, created_at, source_guard_review_label, labels)
        metrics = build_metrics(evaluation, created_at, source_guard_review_label, cases, labels)
        checks = build_quality_checks(
            evaluation_label=evaluation,
            created_at=created_at,
            guard_review_label=source_guard_review_label,
            guard_review=guard_review,
            labels=labels,
            guard_checks=guard_checks,
            guard_findings=guard_findings,
            cases=cases,
            metrics=metrics,
            min_cases=min_cases,
            min_label_confidence=min_label_confidence,
        )

    decision, verdict, action, next_mission, state, reason = decide_evaluation_outcome(guard_review, checks)

    summary = build_summary(
        db_path=db,
        evaluation_label=evaluation,
        report_label=report,
        created_at=created_at,
        guard_review_label=source_guard_review_label,
        guard_review=guard_review,
        labels=labels,
        cases=cases,
        metrics=metrics,
        checks=checks,
        decision=decision,
        verdict=verdict,
        action=action,
        next_mission=next_mission,
        state=state,
        reason=reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_evaluation(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid AI offline evaluation harness.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--evaluation-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--guard-review-label", default="mission76-final-check")
    parser.add_argument("--min-cases", type=int, default=4)
    parser.add_argument("--min-label-confidence", type=float, default=0.60)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_ai_offline_evaluation_harness(
        db_path=args.db,
        evaluation_label=args.evaluation_label,
        report_label=args.report_label,
        guard_review_label=args.guard_review_label,
        min_cases=args.min_cases,
        min_label_confidence=args.min_label_confidence,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

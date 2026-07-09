"""
Mission 76: AI Label Quality and Leakage Guard.

This module validates finalized paper outcome labels before offline evaluation.

It reads:
- ai_paper_outcome_collection_runs
- ai_paper_outcome_collection_records
- ai_paper_outcome_final_labels
- ai_paper_outcome_collection_checks

It writes:
- ai_label_quality_leakage_guard_reviews
- ai_label_quality_leakage_guard_checks
- ai_label_quality_leakage_guard_findings
- ai_label_quality_leakage_guard_reports

It never:
- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital
- trains a model
- performs autonomous strategy reweighting
- runs autonomous execution
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


COLLECTION_RUNS_TABLE = "ai_paper_outcome_collection_runs"
COLLECTION_RECORDS_TABLE = "ai_paper_outcome_collection_records"
FINAL_LABELS_TABLE = "ai_paper_outcome_final_labels"
COLLECTION_CHECKS_TABLE = "ai_paper_outcome_collection_checks"

REVIEWS_TABLE = "ai_label_quality_leakage_guard_reviews"
CHECKS_TABLE = "ai_label_quality_leakage_guard_checks"
FINDINGS_TABLE = "ai_label_quality_leakage_guard_findings"
REPORTS_TABLE = "ai_label_quality_leakage_guard_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

COLLECTION_DECISION_READY = "AI_PAPER_OUTCOME_COLLECTION_APPROVED_FOR_LABEL_QUALITY_REVIEW"
COLLECTION_VERDICT_READY = "AI_PAPER_OUTCOME_COLLECTION_READY_SHADOW_ONLY"
COLLECTION_STATE_READY = "AI_PAPER_OUTCOME_COLLECTION_LABELS_FINALIZED_TRAINING_LOCKED"

OUTCOME_POSITIVE = "AI_PAPER_OUTCOME_LABEL_POSITIVE_AFTER_COST"
OUTCOME_NEUTRAL = "AI_PAPER_OUTCOME_LABEL_COST_DRAG_NEUTRAL"
OUTCOME_NEGATIVE = "AI_PAPER_OUTCOME_LABEL_NEGATIVE_AFTER_COST"
ALLOWED_OUTCOME_LABELS = {OUTCOME_POSITIVE, OUTCOME_NEUTRAL, OUTCOME_NEGATIVE}

TARGET_POSITIVE = "AI_TARGET_LABEL_POSITIVE_AFTER_COST"
TARGET_NEUTRAL = "AI_TARGET_LABEL_COST_DRAG_NEUTRAL_EARLY"
TARGET_NEGATIVE = "AI_TARGET_LABEL_NEGATIVE_AFTER_COST"
ALLOWED_TARGET_LABELS = {TARGET_POSITIVE, TARGET_NEUTRAL, TARGET_NEGATIVE}

PENDING_OUTCOME = "AI_OUTCOME_DATASET_LABEL_PENDING_PAPER_OBSERVATION"
PENDING_TARGET = "AI_OUTCOME_TARGET_PENDING_COLLECTION"

CHECK_PASS = "AI_LABEL_QUALITY_LEAKAGE_CHECK_PASS"
CHECK_FAIL = "AI_LABEL_QUALITY_LEAKAGE_CHECK_FAIL"

FINDING_STATUS_CLEAR = "AI_LABEL_LEAKAGE_FINDING_CLEAR"
FINDING_STATUS_BREACH = "AI_LABEL_LEAKAGE_FINDING_BREACH"
FINDING_TYPE_NONE = "NO_LABEL_LEAKAGE_DETECTED"
FINDING_TYPE_FORBIDDEN_FIELD = "FORBIDDEN_LABEL_LEAKAGE_FIELD_DETECTED"

GUARD_STATE_READY = "AI_LABEL_QUALITY_LEAKAGE_GUARD_READY"
GUARD_STATE_UNSTABLE = "AI_LABEL_QUALITY_LEAKAGE_GUARD_UNSTABLE"
GUARD_STATE_BLOCKED = "AI_LABEL_QUALITY_LEAKAGE_GUARD_BLOCKED"
GUARD_STATE_MISSING = "AI_LABEL_QUALITY_LEAKAGE_GUARD_MISSING"

DECISION_READY = "AI_LABEL_QUALITY_LEAKAGE_GUARD_APPROVED_FOR_OFFLINE_EVALUATION"
DECISION_UNSTABLE = "AI_LABEL_QUALITY_LEAKAGE_GUARD_UNSTABLE_REVIEW_REQUIRED"
DECISION_BLOCK_SAFETY = "AI_LABEL_QUALITY_LEAKAGE_GUARD_BLOCKED_BY_SAFETY_POLICY"
DECISION_REJECT_MISSING = "AI_LABEL_QUALITY_LEAKAGE_GUARD_REJECTED_MISSING_EVIDENCE"

VERDICT_READY = "AI_LABEL_QUALITY_LEAKAGE_GUARD_READY_SHADOW_ONLY"
VERDICT_UNSTABLE = "AI_LABEL_QUALITY_LEAKAGE_GUARD_UNSTABLE_SHADOW_ONLY"
VERDICT_BLOCKED = "AI_LABEL_QUALITY_LEAKAGE_GUARD_BLOCKED_SHADOW_ONLY"
VERDICT_MISSING = "AI_LABEL_QUALITY_LEAKAGE_GUARD_MISSING_EVIDENCE"

ACTION_READY = "HAND_OFF_LABELS_TO_OFFLINE_EVALUATION_HARNESS"
ACTION_REVIEW_UNSTABLE = "REVIEW_LABEL_QUALITY_BEFORE_OFFLINE_EVALUATION"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_LABEL_QUALITY_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_AI_PAPER_OUTCOME_COLLECTION_LABELS"

NEXT_READY = "Mission 77 AI Offline Evaluation Harness"

FORBIDDEN_LEAKAGE_TERMS = (
    "future_price",
    "future_return",
    "realized_pnl",
    "realized_profit",
    "live_fill",
    "exchange_order_id",
    "private_key",
    "api_secret",
    "wallet",
    "signature",
    "post_trade",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_review_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission76-ai-label-quality-guard-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission76-ai-label-quality-guard-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
        return ["mission75-final-check"]

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    labels: list[str] = []

    for item in raw_items:
        label = str(item).strip()
        if not label:
            continue
        if any(ch.isspace() for ch in label):
            raise ValueError(f"Invalid paper outcome collection label: {label}")
        if label not in labels:
            labels.append(label)

    if not labels:
        raise ValueError("At least one paper outcome collection label is required")

    return labels


def parse_json(value: Any, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if fallback is None:
        fallback = {}
    if isinstance(value, dict):
        return value
    if not value:
        return dict(fallback)
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return dict(fallback)
    return parsed if isinstance(parsed, dict) else dict(fallback)


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
            CREATE TABLE IF NOT EXISTS ai_label_quality_leakage_guard_reviews (
                review_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_collection_label TEXT NOT NULL,
                source_registry_label TEXT,
                source_build_label TEXT,
                source_schedule_label TEXT,
                source_guard_review_label TEXT,
                source_learning_run_label TEXT,
                source_multi_cycle_track_label TEXT,
                source_session_label TEXT,
                source_portfolio_label TEXT,
                collection_record_count INTEGER NOT NULL,
                final_label_count INTEGER NOT NULL,
                allowed_label_count INTEGER NOT NULL,
                invalid_label_count INTEGER NOT NULL,
                pending_label_count INTEGER NOT NULL,
                low_confidence_label_count INTEGER NOT NULL,
                training_eligible_count INTEGER NOT NULL,
                training_locked_count INTEGER NOT NULL,
                offline_evaluation_candidate_count INTEGER NOT NULL,
                lineage_complete_count INTEGER NOT NULL,
                leakage_finding_count INTEGER NOT NULL,
                leakage_breach_count INTEGER NOT NULL,
                quality_check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                min_label_confidence TEXT NOT NULL,
                average_label_confidence TEXT NOT NULL,
                average_net_paper_outcome_bps TEXT NOT NULL,
                worst_net_paper_outcome_bps TEXT NOT NULL,
                best_net_paper_outcome_bps TEXT NOT NULL,
                guard_state TEXT NOT NULL,
                guard_decision TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_label_quality_leakage_guard_checks (
                check_id TEXT PRIMARY KEY,
                review_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_collection_label TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_label_quality_leakage_guard_findings (
                finding_id TEXT PRIMARY KEY,
                review_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_collection_label TEXT NOT NULL,
                source_final_label_id TEXT,
                finding_type TEXT NOT NULL,
                finding_status TEXT NOT NULL,
                inspected_field TEXT NOT NULL,
                inspected_value TEXT NOT NULL,
                finding_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_label_quality_leakage_guard_reports (
                report_label TEXT PRIMARY KEY,
                review_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_collection_label TEXT NOT NULL,
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


def load_collection_run(conn: sqlite3.Connection, collection_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, COLLECTION_RUNS_TABLE):
        return None
    return conn.execute(
        """
        SELECT *
        FROM ai_paper_outcome_collection_runs
        WHERE collection_label = ?
        """,
        (collection_label,),
    ).fetchone()


def load_collection_records(conn: sqlite3.Connection, collection_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, COLLECTION_RECORDS_TABLE):
        return []
    return conn.execute(
        """
        SELECT *
        FROM ai_paper_outcome_collection_records
        WHERE collection_label = ?
        ORDER BY planned_cycle_index ASC, planned_symbol ASC, collection_record_id ASC
        """,
        (collection_label,),
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


def load_collection_checks(conn: sqlite3.Connection, collection_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, COLLECTION_CHECKS_TABLE):
        return []
    return conn.execute(
        """
        SELECT *
        FROM ai_paper_outcome_collection_checks
        WHERE collection_label = ?
        ORDER BY created_at ASC, check_id ASC
        """,
        (collection_label,),
    ).fetchall()


def row_lineage_complete(row: sqlite3.Row | dict[str, Any]) -> bool:
    required = (
        "source_collection_record_id",
        "source_feature_record_id",
        "source_training_entry_id",
    )
    return all(row_get(row, field, None) not in (None, "") for field in required)


def label_allowed(label: sqlite3.Row | dict[str, Any]) -> bool:
    return (
        str(row_get(label, "outcome_label", "")) in ALLOWED_OUTCOME_LABELS
        and str(row_get(label, "target_label", "")) in ALLOWED_TARGET_LABELS
    )


def label_pending(label: sqlite3.Row | dict[str, Any]) -> bool:
    return (
        str(row_get(label, "outcome_label", "")) == PENDING_OUTCOME
        or str(row_get(label, "target_label", "")) == PENDING_TARGET
    )


SAFE_FALSE_METADATA_KEYS = {
    "private_keys_used",
    "orders_sent",
    "paid_api_used",
    "real_capital_used",
    "model_training_enabled",
    "autonomous_trading_enabled",
    "automatic_strategy_reweighting_enabled",
}


def inspect_for_leakage(value: Any, path: str = "") -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []

    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).lower()
            child_path = f"{path}.{key_text}" if path else key_text

            if key_text in SAFE_FALSE_METADATA_KEYS and child is False:
                continue

            for term in FORBIDDEN_LEAKAGE_TERMS:
                if term == key_text or key_text.startswith(f"{term}_"):
                    hits.append((term, f"{child_path}={str(child)[:200]}"))

            hits.extend(inspect_for_leakage(child, child_path))

        return hits

    if isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            hits.extend(inspect_for_leakage(child, child_path))

        return hits

    text = str(value).lower()

    for term in FORBIDDEN_LEAKAGE_TERMS:
        if term in text:
            hits.append((term, f"{path}={text[:220]}"))

    return hits


def leakage_finding(
    review_label: str,
    created_at: str,
    collection_label: str,
    final_label_id: str | None,
    finding_type: str,
    finding_status: str,
    field: str,
    value: str,
    reason: str,
) -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:8] if finding_status == FINDING_STATUS_BREACH else "clear"
    return {
        "finding_id": f"{review_label}-{finding_type}-{suffix}".replace(" ", "_"),
        "review_label": review_label,
        "created_at": created_at,
        "source_collection_label": collection_label,
        "source_final_label_id": final_label_id,
        "finding_type": finding_type,
        "finding_status": finding_status,
        "inspected_field": field,
        "inspected_value": value,
        "finding_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "label_guard_role": "LEAKAGE_FINDING_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
            "model_training_enabled": False,
            "autonomous_trading_enabled": False,
            "automatic_strategy_reweighting_enabled": False,
        },
    }


def build_leakage_findings(
    review_label: str,
    created_at: str,
    collection_label: str,
    collection_records: list[sqlite3.Row],
    final_labels: list[sqlite3.Row],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for label in final_labels:
        label_id = str(row_get(label, "final_label_id", ""))
        metadata = parse_json(row_get(label, "metadata_json", "{}"))
        inspected = {
            "outcome_label": row_get(label, "outcome_label", ""),
            "target_label": row_get(label, "target_label", ""),
            "metadata_json": metadata,
        }

        for field, value in inspected.items():
            for term, snippet in inspect_for_leakage(value):
                findings.append(
                    leakage_finding(
                        review_label,
                        created_at,
                        collection_label,
                        label_id,
                        FINDING_TYPE_FORBIDDEN_FIELD,
                        FINDING_STATUS_BREACH,
                        field,
                        snippet,
                        f"Forbidden leakage term detected: {term}",
                    )
                )

    for record in collection_records:
        metadata = parse_json(row_get(record, "metadata_json", "{}"))
        record_id = str(row_get(record, "collection_record_id", ""))
        for term, snippet in inspect_for_leakage(metadata):
            findings.append(
                leakage_finding(
                    review_label,
                    created_at,
                    collection_label,
                    record_id,
                    FINDING_TYPE_FORBIDDEN_FIELD,
                    FINDING_STATUS_BREACH,
                    "collection_record_metadata",
                    snippet,
                    f"Forbidden leakage term detected: {term}",
                )
            )

    if not findings:
        findings.append(
            leakage_finding(
                review_label,
                created_at,
                collection_label,
                None,
                FINDING_TYPE_NONE,
                FINDING_STATUS_CLEAR,
                "all_labels_and_metadata",
                "clear",
                "No label leakage terms were detected.",
            )
        )

    return findings


def guard_check(
    review_label: str,
    created_at: str,
    collection_label: str,
    category: str,
    name: str,
    status: str,
    observed: Any,
    threshold: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{review_label}-{category}-{name}".replace(" ", "_"),
        "review_label": review_label,
        "created_at": created_at,
        "source_collection_label": collection_label,
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
            "label_guard_role": "LABEL_QUALITY_LEAKAGE_CHECK_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
            "model_training_enabled": False,
            "autonomous_trading_enabled": False,
            "automatic_strategy_reweighting_enabled": False,
        },
    }


def build_missing_checks(review_label: str, created_at: str, collection_label: str) -> list[dict[str, Any]]:
    return [
        guard_check(
            review_label,
            created_at,
            collection_label,
            "availability",
            "paper outcome collection exists",
            CHECK_FAIL,
            "missing",
            "ai_paper_outcome_collection_runs record",
            "No paper outcome collection run exists for this label.",
        )
    ]


def build_quality_checks(
    review_label: str,
    created_at: str,
    collection_label: str,
    collection_run: sqlite3.Row,
    collection_records: list[sqlite3.Row],
    final_labels: list[sqlite3.Row],
    collection_checks: list[sqlite3.Row],
    findings: list[dict[str, Any]],
    min_records: int,
    min_label_confidence: float,
) -> list[dict[str, Any]]:
    final_count = len(final_labels)
    record_count = len(collection_records)
    source_fail_count = safe_int(row_get(collection_run, "fail_check_count", 0))
    source_safety_count = safe_int(row_get(collection_run, "safety_breach_count", 0))
    safety_count = source_safety_count + sum(1 for row in [collection_run, *collection_records, *final_labels, *collection_checks] if safety_problem(row))

    allowed_count = sum(1 for label in final_labels if label_allowed(label))
    pending_count = sum(1 for label in final_labels if label_pending(label))
    low_confidence_count = sum(1 for label in final_labels if safe_float(row_get(label, "label_confidence", 0.0)) < min_label_confidence)
    training_eligible_count = sum(1 for label in final_labels if safe_int(row_get(label, "training_eligible", 0)) != 0)
    training_locked_count = sum(1 for label in final_labels if safe_int(row_get(label, "training_eligible", 0)) == 0)
    offline_candidate_count = sum(1 for label in final_labels if safe_int(row_get(label, "offline_evaluation_candidate", 0)) == 1)
    lineage_count = sum(1 for label in final_labels if row_lineage_complete(label))
    leakage_breach_count = sum(1 for finding in findings if finding["finding_status"] == FINDING_STATUS_BREACH)

    return [
        guard_check(review_label, created_at, collection_label, "availability", "paper outcome collection exists", CHECK_PASS, "present", "present", "Paper outcome collection run exists."),
        guard_check(review_label, created_at, collection_label, "safety", "safety breach count", CHECK_PASS if safety_count == 0 else CHECK_FAIL, safety_count, 0, "Label quality guard requires zero safety breaches."),
        guard_check(review_label, created_at, collection_label, "collection", "collection decision ready", CHECK_PASS if row_get(collection_run, "collection_decision", "") == COLLECTION_DECISION_READY else CHECK_FAIL, row_get(collection_run, "collection_decision", ""), COLLECTION_DECISION_READY, "Collection decision must be approved for label quality review."),
        guard_check(review_label, created_at, collection_label, "collection", "collection verdict ready", CHECK_PASS if row_get(collection_run, "global_verdict", "") == COLLECTION_VERDICT_READY else CHECK_FAIL, row_get(collection_run, "global_verdict", ""), COLLECTION_VERDICT_READY, "Collection verdict must be ready and shadow-only."),
        guard_check(review_label, created_at, collection_label, "collection", "collection state finalized locked", CHECK_PASS if row_get(collection_run, "collection_state", "") == COLLECTION_STATE_READY else CHECK_FAIL, row_get(collection_run, "collection_state", ""), COLLECTION_STATE_READY, "Collection state must show finalized labels with training locked."),
        guard_check(review_label, created_at, collection_label, "collection", "source collection failed checks", CHECK_PASS if source_fail_count == 0 else CHECK_FAIL, source_fail_count, 0, "Source collection failed checks must remain zero."),
        guard_check(review_label, created_at, collection_label, "coverage", "collection record count", CHECK_PASS if record_count >= min_records else CHECK_FAIL, record_count, f">= {min_records}", "Enough collection records must exist."),
        guard_check(review_label, created_at, collection_label, "coverage", "final label count", CHECK_PASS if final_count == record_count and final_count >= min_records else CHECK_FAIL, final_count, f"== {record_count} and >= {min_records}", "Every collection record must have one final label."),
        guard_check(review_label, created_at, collection_label, "labels", "allowed outcome labels", CHECK_PASS if allowed_count == final_count and final_count > 0 else CHECK_FAIL, allowed_count, final_count, "All final labels must use allowed outcome and target label values."),
        guard_check(review_label, created_at, collection_label, "labels", "no pending labels", CHECK_PASS if pending_count == 0 else CHECK_FAIL, pending_count, 0, "Final labels must not be pending placeholders."),
        guard_check(review_label, created_at, collection_label, "labels", "label confidence floor", CHECK_PASS if low_confidence_count == 0 else CHECK_FAIL, low_confidence_count, 0, f"All label confidences must be >= {min_label_confidence}."),
        guard_check(review_label, created_at, collection_label, "training_lock", "training remains locked", CHECK_PASS if training_eligible_count == 0 and training_locked_count == final_count and final_count > 0 else CHECK_FAIL, f"eligible={training_eligible_count}, locked={training_locked_count}", f"eligible=0, locked={final_count}", "Training must remain locked after label quality review."),
        guard_check(review_label, created_at, collection_label, "offline_eval", "offline evaluation candidates", CHECK_PASS if offline_candidate_count == final_count and final_count > 0 else CHECK_FAIL, offline_candidate_count, final_count, "Final labels should be offline-evaluation candidates only."),
        guard_check(review_label, created_at, collection_label, "lineage", "final label lineage completeness", CHECK_PASS if lineage_count == final_count and final_count > 0 else CHECK_FAIL, lineage_count, final_count, "Every final label must preserve collection, feature, and training-entry lineage."),
        guard_check(review_label, created_at, collection_label, "leakage", "label leakage breach count", CHECK_PASS if leakage_breach_count == 0 else CHECK_FAIL, leakage_breach_count, 0, "No forbidden leakage fields may be present."),
        guard_check(review_label, created_at, collection_label, "model_training", "model training remains disabled", CHECK_PASS, "disabled", "disabled", "This guard does not train a model."),
    ]


def decide_guard_outcome(
    collection_run: sqlite3.Row | None,
    checks: list[dict[str, Any]],
) -> tuple[str, str, str, str, str, str]:
    if collection_run is None:
        return (
            DECISION_REJECT_MISSING,
            VERDICT_MISSING,
            ACTION_REFRESH,
            "Mission 75 AI Paper Outcome Collection and Label Finalizer",
            GUARD_STATE_MISSING,
            "Paper outcome collection evidence is missing.",
        )

    failed = [check for check in checks if check["check_status"] == CHECK_FAIL]

    if any(check["check_category"] == "safety" for check in failed):
        return (
            DECISION_BLOCK_SAFETY,
            VERDICT_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 76 safety remediation",
            GUARD_STATE_BLOCKED,
            "Safety invariant failed during label quality and leakage guarding.",
        )

    if failed:
        return (
            DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 75 AI Paper Outcome Collection and Label Finalizer",
            GUARD_STATE_UNSTABLE,
            "Label quality or leakage guard failed one or more checks.",
        )

    return (
        DECISION_READY,
        VERDICT_READY,
        ACTION_READY,
        NEXT_READY,
        GUARD_STATE_READY,
        "Final labels passed quality and leakage guard. Offline evaluation may proceed; training and live trading remain locked.",
    )


def confidence_average(final_labels: list[sqlite3.Row]) -> float:
    values = [safe_float(row_get(label, "label_confidence", 0.0)) for label in final_labels]
    return round8(sum(values) / len(values)) if values else 0.0


def build_summary(
    db_path: str | Path,
    review_label: str,
    report_label: str,
    created_at: str,
    collection_label: str,
    collection_run: sqlite3.Row | None,
    collection_records: list[sqlite3.Row],
    final_labels: list[sqlite3.Row],
    checks: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    min_label_confidence: float,
    decision: str,
    verdict: str,
    action: str,
    next_mission: str,
    state: str,
    reason: str,
) -> dict[str, Any]:
    pass_count = sum(1 for check in checks if check["check_status"] == CHECK_PASS)
    fail_count = sum(1 for check in checks if check["check_status"] == CHECK_FAIL)
    allowed_count = sum(1 for label in final_labels if label_allowed(label))
    pending_count = sum(1 for label in final_labels if label_pending(label))
    low_confidence_count = sum(1 for label in final_labels if safe_float(row_get(label, "label_confidence", 0.0)) < min_label_confidence)
    training_eligible_count = sum(1 for label in final_labels if safe_int(row_get(label, "training_eligible", 0)) != 0)
    training_locked_count = sum(1 for label in final_labels if safe_int(row_get(label, "training_eligible", 0)) == 0)
    offline_candidate_count = sum(1 for label in final_labels if safe_int(row_get(label, "offline_evaluation_candidate", 0)) == 1)
    lineage_count = sum(1 for label in final_labels if row_lineage_complete(label))
    leakage_breach_count = sum(1 for finding in findings if finding["finding_status"] == FINDING_STATUS_BREACH)

    return {
        "review_label": review_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_collection_label": collection_label,
        "source_registry_label": row_get(collection_run, "source_registry_label", None),
        "source_build_label": row_get(collection_run, "source_build_label", None),
        "source_schedule_label": row_get(collection_run, "source_schedule_label", None),
        "source_guard_review_label": row_get(collection_run, "source_guard_review_label", None),
        "source_learning_run_label": row_get(collection_run, "source_learning_run_label", None),
        "source_multi_cycle_track_label": row_get(collection_run, "source_multi_cycle_track_label", None),
        "source_session_label": row_get(collection_run, "source_session_label", None),
        "source_portfolio_label": row_get(collection_run, "source_portfolio_label", None),
        "collection_record_count": len(collection_records),
        "final_label_count": len(final_labels),
        "allowed_label_count": allowed_count,
        "invalid_label_count": len(final_labels) - allowed_count,
        "pending_label_count": pending_count,
        "low_confidence_label_count": low_confidence_count,
        "training_eligible_count": training_eligible_count,
        "training_locked_count": training_locked_count,
        "offline_evaluation_candidate_count": offline_candidate_count,
        "lineage_complete_count": lineage_count,
        "leakage_finding_count": len(findings),
        "leakage_breach_count": leakage_breach_count,
        "quality_check_count": len(checks),
        "pass_check_count": pass_count,
        "fail_check_count": fail_count,
        "safety_breach_count": safe_int(row_get(collection_run, "safety_breach_count", 0)),
        "min_label_confidence": round8(min_label_confidence),
        "average_label_confidence": confidence_average(final_labels),
        "average_net_paper_outcome_bps": round8(safe_float(row_get(collection_run, "average_net_paper_outcome_bps", 0.0))),
        "worst_net_paper_outcome_bps": round8(safe_float(row_get(collection_run, "worst_net_paper_outcome_bps", 0.0))),
        "best_net_paper_outcome_bps": round8(safe_float(row_get(collection_run, "best_net_paper_outcome_bps", 0.0))),
        "guard_checks": checks,
        "leakage_findings": findings,
        "guard_state": state,
        "guard_decision": decision,
        "global_verdict": verdict,
        "recommended_action": action,
        "next_mission": next_mission,
        "decision_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    check_lines = [
        f"- {check['check_category']} / {check['check_name']}: status={check['check_status']}, observed={check['observed_value']}, threshold={check['threshold_value']}"
        for check in summary["guard_checks"]
    ]

    finding_lines = [
        f"- {finding['finding_type']}: status={finding['finding_status']}, field={finding['inspected_field']}, reason={finding['finding_reason']}"
        for finding in summary["leakage_findings"]
    ]

    return f"""# DeltaGrid Mission 76 AI Label Quality and Leakage Guard Report

Report label: {summary['report_label']}
Review label: {summary['review_label']}
Created at: {summary['created_at']}
Source collection label: {summary['source_collection_label']}
Source registry label: {summary['source_registry_label']}
Source build label: {summary['source_build_label']}
Source schedule label: {summary['source_schedule_label']}
Source guard review label: {summary['source_guard_review_label']}
Source learning run label: {summary['source_learning_run_label']}
Source multi-cycle track label: {summary['source_multi_cycle_track_label']}
Source session label: {summary['source_session_label']}
Source portfolio label: {summary['source_portfolio_label']}

## Label Quality Summary

Collection record count: {summary['collection_record_count']}
Final label count: {summary['final_label_count']}
Allowed label count: {summary['allowed_label_count']}
Invalid label count: {summary['invalid_label_count']}
Pending label count: {summary['pending_label_count']}
Low confidence label count: {summary['low_confidence_label_count']}
Training eligible count: {summary['training_eligible_count']}
Training locked count: {summary['training_locked_count']}
Offline evaluation candidate count: {summary['offline_evaluation_candidate_count']}
Lineage complete count: {summary['lineage_complete_count']}

Minimum label confidence: {summary['min_label_confidence']}
Average label confidence: {summary['average_label_confidence']}
Average net paper outcome bps: {summary['average_net_paper_outcome_bps']}
Worst net paper outcome bps: {summary['worst_net_paper_outcome_bps']}
Best net paper outcome bps: {summary['best_net_paper_outcome_bps']}

Leakage finding count: {summary['leakage_finding_count']}
Leakage breach count: {summary['leakage_breach_count']}
Quality check count: {summary['quality_check_count']}
Pass check count: {summary['pass_check_count']}
Fail check count: {summary['fail_check_count']}
Safety breach count: {summary['safety_breach_count']}

## Checks

{chr(10).join(check_lines) if check_lines else "- None"}

## Leakage Findings

{chr(10).join(finding_lines) if finding_lines else "- None"}

## Decision

Guard state: {summary['guard_state']}
Guard decision: {summary['guard_decision']}
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

This guard does not train a model.
Training remains locked.
Labels are offline-evaluation candidates only.
This guard does not perform autonomous trading.
This guard does not adjust strategy weights automatically.
"""


def insert_row(conn: sqlite3.Connection, table_name: str, row: dict[str, Any], columns: list[str]) -> None:
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    values = [row[column] for column in columns]
    conn.execute(f"INSERT OR REPLACE INTO {table_name} ({column_sql}) VALUES ({placeholders})", values)


def persist_review(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for check in summary["guard_checks"]:
            stored = dict(check)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                CHECKS_TABLE,
                stored,
                [
                    "check_id", "review_label", "created_at", "source_collection_label",
                    "check_category", "check_name", "check_status", "observed_value",
                    "threshold_value", "check_reason", "live_trading", "live_order_sent",
                    "capital_deployment", "metadata_json",
                ],
            )

        for finding in summary["leakage_findings"]:
            stored_finding = dict(finding)
            stored_finding["metadata_json"] = json.dumps(stored_finding.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                FINDINGS_TABLE,
                stored_finding,
                [
                    "finding_id", "review_label", "created_at", "source_collection_label",
                    "source_final_label_id", "finding_type", "finding_status",
                    "inspected_field", "inspected_value", "finding_reason",
                    "live_trading", "live_order_sent", "capital_deployment", "metadata_json",
                ],
            )

        review_row = {
            "review_label": summary["review_label"],
            "report_label": summary["report_label"],
            "created_at": summary["created_at"],
            "source_collection_label": summary["source_collection_label"],
            "source_registry_label": summary["source_registry_label"],
            "source_build_label": summary["source_build_label"],
            "source_schedule_label": summary["source_schedule_label"],
            "source_guard_review_label": summary["source_guard_review_label"],
            "source_learning_run_label": summary["source_learning_run_label"],
            "source_multi_cycle_track_label": summary["source_multi_cycle_track_label"],
            "source_session_label": summary["source_session_label"],
            "source_portfolio_label": summary["source_portfolio_label"],
            "collection_record_count": summary["collection_record_count"],
            "final_label_count": summary["final_label_count"],
            "allowed_label_count": summary["allowed_label_count"],
            "invalid_label_count": summary["invalid_label_count"],
            "pending_label_count": summary["pending_label_count"],
            "low_confidence_label_count": summary["low_confidence_label_count"],
            "training_eligible_count": summary["training_eligible_count"],
            "training_locked_count": summary["training_locked_count"],
            "offline_evaluation_candidate_count": summary["offline_evaluation_candidate_count"],
            "lineage_complete_count": summary["lineage_complete_count"],
            "leakage_finding_count": summary["leakage_finding_count"],
            "leakage_breach_count": summary["leakage_breach_count"],
            "quality_check_count": summary["quality_check_count"],
            "pass_check_count": summary["pass_check_count"],
            "fail_check_count": summary["fail_check_count"],
            "safety_breach_count": summary["safety_breach_count"],
            "min_label_confidence": str(summary["min_label_confidence"]),
            "average_label_confidence": str(summary["average_label_confidence"]),
            "average_net_paper_outcome_bps": str(summary["average_net_paper_outcome_bps"]),
            "worst_net_paper_outcome_bps": str(summary["worst_net_paper_outcome_bps"]),
            "best_net_paper_outcome_bps": str(summary["best_net_paper_outcome_bps"]),
            "guard_state": summary["guard_state"],
            "guard_decision": summary["guard_decision"],
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
            REVIEWS_TABLE,
            review_row,
            [
                "review_label", "report_label", "created_at", "source_collection_label",
                "source_registry_label", "source_build_label", "source_schedule_label",
                "source_guard_review_label", "source_learning_run_label", "source_multi_cycle_track_label",
                "source_session_label", "source_portfolio_label", "collection_record_count",
                "final_label_count", "allowed_label_count", "invalid_label_count",
                "pending_label_count", "low_confidence_label_count", "training_eligible_count",
                "training_locked_count", "offline_evaluation_candidate_count", "lineage_complete_count",
                "leakage_finding_count", "leakage_breach_count", "quality_check_count",
                "pass_check_count", "fail_check_count", "safety_breach_count",
                "min_label_confidence", "average_label_confidence", "average_net_paper_outcome_bps",
                "worst_net_paper_outcome_bps", "best_net_paper_outcome_bps",
                "guard_state", "guard_decision", "global_verdict", "recommended_action",
                "next_mission", "live_trading", "live_order_sent", "capital_deployment",
                "summary_json", "markdown_report",
            ],
        )

        report_row = {
            "report_label": summary["report_label"],
            "review_label": summary["review_label"],
            "created_at": summary["created_at"],
            "source_collection_label": summary["source_collection_label"],
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
                "report_label", "review_label", "created_at", "source_collection_label",
                "global_verdict", "recommended_action", "report_json", "markdown_report",
                "live_trading", "live_order_sent", "capital_deployment",
            ],
        )

        conn.commit()


def run_ai_label_quality_leakage_guard(
    db_path: str | Path = "offchain/deltagrid.db",
    review_label: str | None = None,
    report_label: str | None = None,
    collection_label: str = "mission75-final-check",
    min_records: int = 4,
    min_label_confidence: float = 0.60,
) -> dict[str, Any]:
    if min_records <= 0:
        raise ValueError("min_records must be positive")
    if min_label_confidence < 0 or min_label_confidence > 1:
        raise ValueError("min_label_confidence must be between 0 and 1")

    db = Path(db_path)
    review = review_label or new_review_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    source_collection_label = parse_labels(collection_label)[0]

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        collection_run = load_collection_run(conn, source_collection_label)
        collection_records = load_collection_records(conn, source_collection_label)
        final_labels = load_final_labels(conn, source_collection_label)
        collection_checks = load_collection_checks(conn, source_collection_label)

    if collection_run is None:
        findings: list[dict[str, Any]] = []
        checks = build_missing_checks(review, created_at, source_collection_label)
    else:
        findings = build_leakage_findings(review, created_at, source_collection_label, collection_records, final_labels)
        checks = build_quality_checks(
            review_label=review,
            created_at=created_at,
            collection_label=source_collection_label,
            collection_run=collection_run,
            collection_records=collection_records,
            final_labels=final_labels,
            collection_checks=collection_checks,
            findings=findings,
            min_records=min_records,
            min_label_confidence=min_label_confidence,
        )

    decision, verdict, action, next_mission, state, reason = decide_guard_outcome(collection_run, checks)

    summary = build_summary(
        db_path=db,
        review_label=review,
        report_label=report,
        created_at=created_at,
        collection_label=source_collection_label,
        collection_run=collection_run,
        collection_records=collection_records,
        final_labels=final_labels,
        checks=checks,
        findings=findings,
        min_label_confidence=min_label_confidence,
        decision=decision,
        verdict=verdict,
        action=action,
        next_mission=next_mission,
        state=state,
        reason=reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_review(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid AI label quality and leakage guard.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--review-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--collection-label", default="mission75-final-check")
    parser.add_argument("--min-records", type=int, default=4)
    parser.add_argument("--min-label-confidence", type=float, default=0.60)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_ai_label_quality_leakage_guard(
        db_path=args.db,
        review_label=args.review_label,
        report_label=args.report_label,
        collection_label=args.collection_label,
        min_records=args.min_records,
        min_label_confidence=args.min_label_confidence,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

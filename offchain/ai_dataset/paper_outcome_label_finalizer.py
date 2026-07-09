"""
Mission 75: AI Paper Outcome Collection and Label Finalizer.

This module collects local deterministic paper-only outcomes from Mission 74
feature-store records and finalizes paper outcome labels.

Important boundary:
- This does not use live market execution.
- This does not train a model.
- This does not unlock autonomous trading.
- Training remains locked after labels are finalized.
- Finalized labels become offline-evaluation candidates only.

It reads:
- ai_feature_store_training_registries
- ai_feature_store_feature_records
- ai_training_dataset_registry_entries
- ai_feature_store_training_registry_checks

It writes:
- ai_paper_outcome_collection_runs
- ai_paper_outcome_collection_records
- ai_paper_outcome_final_labels
- ai_paper_outcome_collection_checks
- ai_paper_outcome_collection_reports
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


REGISTRIES_TABLE = "ai_feature_store_training_registries"
FEATURE_RECORDS_TABLE = "ai_feature_store_feature_records"
TRAINING_ENTRIES_TABLE = "ai_training_dataset_registry_entries"
REGISTRY_CHECKS_TABLE = "ai_feature_store_training_registry_checks"

RUNS_TABLE = "ai_paper_outcome_collection_runs"
COLLECTION_RECORDS_TABLE = "ai_paper_outcome_collection_records"
FINAL_LABELS_TABLE = "ai_paper_outcome_final_labels"
COLLECTION_CHECKS_TABLE = "ai_paper_outcome_collection_checks"
REPORTS_TABLE = "ai_paper_outcome_collection_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

REGISTRY_DECISION_READY_LOCKED = "AI_FEATURE_STORE_REGISTRY_APPROVED_TRAINING_LOCKED"
REGISTRY_VERDICT_READY = "AI_FEATURE_STORE_TRAINING_REGISTRY_READY_SHADOW_ONLY"
REGISTRY_STATE_READY_LOCKED = "AI_FEATURE_STORE_REGISTRY_READY_TRAINING_LOCKED"

PENDING_OUTCOME_LABEL = "AI_OUTCOME_DATASET_LABEL_PENDING_PAPER_OBSERVATION"
PENDING_TARGET_LABEL = "AI_OUTCOME_TARGET_PENDING_COLLECTION"

COLLECTION_MODE = "LOCAL_DETERMINISTIC_PAPER_OUTCOME_LABEL_FINALIZATION"
COLLECTION_RECORD_STATUS = "AI_PAPER_OUTCOME_COLLECTION_RECORD_FINALIZED"
FINAL_LABEL_STATUS = "AI_PAPER_OUTCOME_FINAL_LABEL_READY_TRAINING_LOCKED"

OUTCOME_POSITIVE = "AI_PAPER_OUTCOME_LABEL_POSITIVE_AFTER_COST"
OUTCOME_NEUTRAL = "AI_PAPER_OUTCOME_LABEL_COST_DRAG_NEUTRAL"
OUTCOME_NEGATIVE = "AI_PAPER_OUTCOME_LABEL_NEGATIVE_AFTER_COST"

TARGET_POSITIVE = "AI_TARGET_LABEL_POSITIVE_AFTER_COST"
TARGET_NEUTRAL = "AI_TARGET_LABEL_COST_DRAG_NEUTRAL_EARLY"
TARGET_NEGATIVE = "AI_TARGET_LABEL_NEGATIVE_AFTER_COST"

TRAINING_LOCKED = 0
OFFLINE_EVAL_CANDIDATE = 1

CHECK_PASS = "AI_PAPER_OUTCOME_COLLECTION_CHECK_PASS"
CHECK_FAIL = "AI_PAPER_OUTCOME_COLLECTION_CHECK_FAIL"

COLLECTION_STATE_READY_LOCKED = "AI_PAPER_OUTCOME_COLLECTION_LABELS_FINALIZED_TRAINING_LOCKED"
COLLECTION_STATE_UNSTABLE = "AI_PAPER_OUTCOME_COLLECTION_UNSTABLE"
COLLECTION_STATE_BLOCKED = "AI_PAPER_OUTCOME_COLLECTION_BLOCKED"
COLLECTION_STATE_MISSING = "AI_PAPER_OUTCOME_COLLECTION_MISSING"

DECISION_READY_LOCKED = "AI_PAPER_OUTCOME_COLLECTION_APPROVED_FOR_LABEL_QUALITY_REVIEW"
DECISION_UNSTABLE = "AI_PAPER_OUTCOME_COLLECTION_UNSTABLE_REVIEW_REQUIRED"
DECISION_BLOCK_SAFETY = "AI_PAPER_OUTCOME_COLLECTION_BLOCKED_BY_SAFETY_POLICY"
DECISION_REJECT_MISSING = "AI_PAPER_OUTCOME_COLLECTION_REJECTED_MISSING_EVIDENCE"

VERDICT_READY = "AI_PAPER_OUTCOME_COLLECTION_READY_SHADOW_ONLY"
VERDICT_UNSTABLE = "AI_PAPER_OUTCOME_COLLECTION_UNSTABLE_SHADOW_ONLY"
VERDICT_BLOCKED = "AI_PAPER_OUTCOME_COLLECTION_BLOCKED_SHADOW_ONLY"
VERDICT_MISSING = "AI_PAPER_OUTCOME_COLLECTION_MISSING_EVIDENCE"

ACTION_READY_LOCKED = "HAND_OFF_FINALIZED_LABELS_TO_LABEL_QUALITY_GUARD"
ACTION_REVIEW_UNSTABLE = "REVIEW_PAPER_OUTCOME_COLLECTION_BEFORE_LABEL_HANDOFF"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_PAPER_OUTCOME_COLLECTION_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_AI_FEATURE_STORE_TRAINING_REGISTRY"

NEXT_READY = "Mission 76 AI Label Quality and Leakage Guard"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_collection_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission75-ai-paper-outcome-collection-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission75-ai-paper-outcome-collection-report-{stamp}-{uuid.uuid4().hex[:8]}"


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


def parse_labels(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return ["mission74-final-check"]

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    labels: list[str] = []

    for item in raw_items:
        label = str(item).strip()

        if not label:
            continue

        if any(ch.isspace() for ch in label):
            raise ValueError(f"Invalid feature-store registry label: {label}")

        if label not in labels:
            labels.append(label)

    if not labels:
        raise ValueError("At least one feature-store registry label is required")

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
            CREATE TABLE IF NOT EXISTS ai_paper_outcome_collection_runs (
                collection_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_registry_label TEXT NOT NULL,
                source_build_label TEXT,
                source_schedule_label TEXT,
                source_guard_review_label TEXT,
                source_learning_run_label TEXT,
                source_multi_cycle_track_label TEXT,
                source_session_label TEXT,
                source_portfolio_label TEXT,
                feature_record_count INTEGER NOT NULL,
                training_registry_entry_count INTEGER NOT NULL,
                collection_record_count INTEGER NOT NULL,
                final_label_count INTEGER NOT NULL,
                pending_before_count INTEGER NOT NULL,
                finalized_label_count INTEGER NOT NULL,
                training_eligible_count INTEGER NOT NULL,
                training_locked_count INTEGER NOT NULL,
                offline_evaluation_candidate_count INTEGER NOT NULL,
                lineage_complete_count INTEGER NOT NULL,
                collection_check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                average_net_paper_outcome_bps TEXT NOT NULL,
                worst_net_paper_outcome_bps TEXT NOT NULL,
                best_net_paper_outcome_bps TEXT NOT NULL,
                average_fee_drag_bps TEXT NOT NULL,
                collection_mode TEXT NOT NULL,
                collection_state TEXT NOT NULL,
                collection_decision TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_paper_outcome_collection_records (
                collection_record_id TEXT PRIMARY KEY,
                collection_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_registry_label TEXT NOT NULL,
                source_feature_record_id TEXT NOT NULL,
                source_training_entry_id TEXT,
                source_dataset_row_id TEXT,
                planned_symbol TEXT NOT NULL,
                planned_cycle_index INTEGER NOT NULL,
                gross_paper_outcome_bps TEXT NOT NULL,
                fee_drag_bps TEXT NOT NULL,
                net_paper_outcome_bps TEXT NOT NULL,
                outcome_label TEXT NOT NULL,
                target_label TEXT NOT NULL,
                label_confidence TEXT NOT NULL,
                training_eligible INTEGER NOT NULL,
                offline_evaluation_candidate INTEGER NOT NULL,
                collection_mode TEXT NOT NULL,
                collection_record_status TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_paper_outcome_final_labels (
                final_label_id TEXT PRIMARY KEY,
                collection_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_collection_record_id TEXT NOT NULL,
                source_feature_record_id TEXT NOT NULL,
                source_training_entry_id TEXT,
                outcome_label TEXT NOT NULL,
                target_label TEXT NOT NULL,
                net_paper_outcome_bps TEXT NOT NULL,
                label_confidence TEXT NOT NULL,
                final_label_status TEXT NOT NULL,
                training_eligible INTEGER NOT NULL,
                offline_evaluation_candidate INTEGER NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_paper_outcome_collection_checks (
                check_id TEXT PRIMARY KEY,
                collection_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_registry_label TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_paper_outcome_collection_reports (
                report_label TEXT PRIMARY KEY,
                collection_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_registry_label TEXT NOT NULL,
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


def load_registry(conn: sqlite3.Connection, registry_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, REGISTRIES_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM ai_feature_store_training_registries
        WHERE registry_label = ?
        """,
        (registry_label,),
    ).fetchone()


def load_feature_records(conn: sqlite3.Connection, registry_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, FEATURE_RECORDS_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM ai_feature_store_feature_records
        WHERE registry_label = ?
        ORDER BY planned_cycle_index ASC, planned_symbol ASC, feature_record_id ASC
        """,
        (registry_label,),
    ).fetchall()


def load_training_entries(conn: sqlite3.Connection, registry_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, TRAINING_ENTRIES_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM ai_training_dataset_registry_entries
        WHERE registry_label = ?
        ORDER BY training_entry_id ASC
        """,
        (registry_label,),
    ).fetchall()


def load_registry_checks(conn: sqlite3.Connection, registry_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, REGISTRY_CHECKS_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM ai_feature_store_training_registry_checks
        WHERE registry_label = ?
        ORDER BY created_at ASC, check_id ASC
        """,
        (registry_label,),
    ).fetchall()


def training_entry_by_feature_id(training_entries: list[sqlite3.Row]) -> dict[str, sqlite3.Row]:
    return {
        str(row_get(entry, "source_feature_record_id", "")): entry
        for entry in training_entries
        if str(row_get(entry, "source_feature_record_id", ""))
    }


def classify_outcome(net_bps: float, positive_threshold_bps: float, loss_threshold_bps: float) -> tuple[str, str, float]:
    if net_bps >= positive_threshold_bps:
        return OUTCOME_POSITIVE, TARGET_POSITIVE, 0.70

    if net_bps <= -abs(loss_threshold_bps):
        return OUTCOME_NEGATIVE, TARGET_NEGATIVE, 0.70

    return OUTCOME_NEUTRAL, TARGET_NEUTRAL, 0.65


def lineage_complete(record: sqlite3.Row | dict[str, Any]) -> bool:
    required = (
        "source_build_label",
        "source_dataset_row_id",
        "source_schedule_label",
        "source_guard_review_label",
        "source_learning_run_label",
        "source_multi_cycle_track_label",
        "source_session_label",
        "source_portfolio_label",
    )

    return all(row_get(record, field, None) not in (None, "") for field in required)


def collection_lineage_complete(record: dict[str, Any]) -> bool:
    required = (
        "source_registry_label",
        "source_feature_record_id",
        "source_training_entry_id",
        "source_dataset_row_id",
        "planned_symbol",
    )

    return all(record.get(field) not in (None, "") for field in required)


def collection_check(
    collection_label: str,
    created_at: str,
    registry_label: str,
    category: str,
    name: str,
    status: str,
    observed_value: Any,
    threshold_value: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{collection_label}-{category}-{name}".replace(" ", "_"),
        "collection_label": collection_label,
        "created_at": created_at,
        "source_registry_label": registry_label,
        "check_category": category,
        "check_name": name,
        "check_status": status,
        "observed_value": str(observed_value),
        "threshold_value": str(threshold_value),
        "check_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "paper_outcome_role": "PAPER_OUTCOME_COLLECTION_CHECK_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
            "autonomous_trading_enabled": False,
            "automatic_strategy_reweighting_enabled": False,
            "model_training_enabled": False,
        },
    }


def build_missing_checks(collection_label: str, created_at: str, registry_label: str) -> list[dict[str, Any]]:
    return [
        collection_check(
            collection_label,
            created_at,
            registry_label,
            "availability",
            "feature store registry exists",
            CHECK_FAIL,
            "missing",
            "ai_feature_store_training_registries record",
            "No AI feature store training registry exists for this label.",
        )
    ]


def build_collection_records(
    collection_label: str,
    created_at: str,
    registry_label: str,
    feature_records: list[sqlite3.Row],
    training_entries: list[sqlite3.Row],
    gross_outcome_bps: float,
    fee_drag_bps: float,
    positive_threshold_bps: float,
    loss_threshold_bps: float,
) -> list[dict[str, Any]]:
    entries_by_feature = training_entry_by_feature_id(training_entries)
    records: list[dict[str, Any]] = []

    for feature in feature_records:
        feature_id = str(row_get(feature, "feature_record_id", ""))
        training_entry = entries_by_feature.get(feature_id)
        net_bps = round8(gross_outcome_bps - fee_drag_bps)
        outcome_label, target_label, confidence = classify_outcome(net_bps, positive_threshold_bps, loss_threshold_bps)

        records.append(
            {
                "collection_record_id": f"{collection_label}-{feature_id}-collection".replace(" ", "_"),
                "collection_label": collection_label,
                "created_at": created_at,
                "source_registry_label": registry_label,
                "source_feature_record_id": feature_id,
                "source_training_entry_id": row_get(training_entry, "training_entry_id", None),
                "source_dataset_row_id": row_get(feature, "source_dataset_row_id", None),
                "planned_symbol": str(row_get(feature, "planned_symbol", "")),
                "planned_cycle_index": safe_int(row_get(feature, "planned_cycle_index", 0)),
                "gross_paper_outcome_bps": round8(gross_outcome_bps),
                "fee_drag_bps": round8(fee_drag_bps),
                "net_paper_outcome_bps": net_bps,
                "outcome_label": outcome_label,
                "target_label": target_label,
                "label_confidence": round8(confidence),
                "training_eligible": TRAINING_LOCKED,
                "offline_evaluation_candidate": OFFLINE_EVAL_CANDIDATE,
                "collection_mode": COLLECTION_MODE,
                "collection_record_status": COLLECTION_RECORD_STATUS,
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT_VALUE,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "metadata": {
                    "paper_outcome_role": "LOCAL_DETERMINISTIC_PAPER_LABEL_ONLY",
                    "execution_role": "NONE",
                    "private_keys_used": False,
                    "orders_sent": False,
                    "paid_api_used": False,
                    "real_capital_used": False,
                    "autonomous_trading_enabled": False,
                    "automatic_strategy_reweighting_enabled": False,
                    "model_training_enabled": False,
                    "training_locked_after_labeling": True,
                    "not_profitability_claim": True,
                },
            }
        )

    return records


def build_final_labels(
    collection_label: str,
    created_at: str,
    collection_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []

    for record in collection_records:
        labels.append(
            {
                "final_label_id": f"{record['collection_record_id']}-final-label",
                "collection_label": collection_label,
                "created_at": created_at,
                "source_collection_record_id": record["collection_record_id"],
                "source_feature_record_id": record["source_feature_record_id"],
                "source_training_entry_id": record["source_training_entry_id"],
                "outcome_label": record["outcome_label"],
                "target_label": record["target_label"],
                "net_paper_outcome_bps": record["net_paper_outcome_bps"],
                "label_confidence": record["label_confidence"],
                "final_label_status": FINAL_LABEL_STATUS,
                "training_eligible": TRAINING_LOCKED,
                "offline_evaluation_candidate": OFFLINE_EVAL_CANDIDATE,
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT_VALUE,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "metadata": {
                    "paper_outcome_role": "FINAL_LABEL_RECORD_ONLY",
                    "execution_role": "NONE",
                    "private_keys_used": False,
                    "orders_sent": False,
                    "paid_api_used": False,
                    "real_capital_used": False,
                    "autonomous_trading_enabled": False,
                    "automatic_strategy_reweighting_enabled": False,
                    "model_training_enabled": False,
                    "training_locked_after_labeling": True,
                    "offline_evaluation_candidate": True,
                },
            }
        )

    return labels


def build_quality_checks(
    collection_label: str,
    created_at: str,
    registry_label: str,
    registry: sqlite3.Row,
    feature_records: list[sqlite3.Row],
    training_entries: list[sqlite3.Row],
    registry_checks: list[sqlite3.Row],
    collection_records: list[dict[str, Any]],
    final_labels: list[dict[str, Any]],
    min_records: int,
) -> list[dict[str, Any]]:
    safety_count = safe_int(row_get(registry, "safety_breach_count", 0))
    safety_count += sum(1 for row in [registry, *feature_records, *training_entries, *registry_checks] if safety_problem(row))

    feature_count = len(feature_records)
    training_entry_count = len(training_entries)
    collection_count = len(collection_records)
    final_label_count = len(final_labels)
    pending_before = sum(1 for record in feature_records if row_get(record, "outcome_label", "") == PENDING_OUTCOME_LABEL)
    finalized_non_pending = sum(1 for label in final_labels if label["outcome_label"] != PENDING_OUTCOME_LABEL)
    training_locked = sum(1 for label in final_labels if label["training_eligible"] == TRAINING_LOCKED)
    offline_candidates = sum(1 for label in final_labels if label["offline_evaluation_candidate"] == OFFLINE_EVAL_CANDIDATE)
    lineage_count = sum(1 for record in collection_records if collection_lineage_complete(record))
    source_fail_count = safe_int(row_get(registry, "fail_check_count", 0))

    return [
        collection_check(collection_label, created_at, registry_label, "availability", "feature store registry exists", CHECK_PASS, "present", "present", "Feature-store registry exists."),
        collection_check(collection_label, created_at, registry_label, "safety", "safety breach count", CHECK_PASS if safety_count == 0 else CHECK_FAIL, safety_count, 0, "Paper outcome collection requires zero live-trading, order-transmission, and capital-deployment breaches."),
        collection_check(collection_label, created_at, registry_label, "registry", "registry decision ready locked", CHECK_PASS if row_get(registry, "registry_decision", "") == REGISTRY_DECISION_READY_LOCKED else CHECK_FAIL, row_get(registry, "registry_decision", ""), REGISTRY_DECISION_READY_LOCKED, "Outcome collection requires a ready but training-locked feature-store registry."),
        collection_check(collection_label, created_at, registry_label, "registry", "registry verdict ready", CHECK_PASS if row_get(registry, "global_verdict", "") == REGISTRY_VERDICT_READY else CHECK_FAIL, row_get(registry, "global_verdict", ""), REGISTRY_VERDICT_READY, "Outcome collection requires a ready shadow-only registry verdict."),
        collection_check(collection_label, created_at, registry_label, "registry", "registry state ready locked", CHECK_PASS if row_get(registry, "registry_state", "") == REGISTRY_STATE_READY_LOCKED else CHECK_FAIL, row_get(registry, "registry_state", ""), REGISTRY_STATE_READY_LOCKED, "Registry state must be ready with training locked."),
        collection_check(collection_label, created_at, registry_label, "registry", "source registry failed checks", CHECK_PASS if source_fail_count == 0 else CHECK_FAIL, source_fail_count, 0, "Source registry failed checks must remain zero."),
        collection_check(collection_label, created_at, registry_label, "coverage", "feature record count", CHECK_PASS if feature_count >= min_records else CHECK_FAIL, feature_count, f">= {min_records}", "Enough feature records must exist for paper outcome collection."),
        collection_check(collection_label, created_at, registry_label, "coverage", "training registry entry count", CHECK_PASS if training_entry_count == feature_count and feature_count > 0 else CHECK_FAIL, training_entry_count, feature_count, "Each feature record should have one training registry entry."),
        collection_check(collection_label, created_at, registry_label, "labels", "pending labels before collection", CHECK_PASS if pending_before == feature_count and feature_count > 0 else CHECK_FAIL, pending_before, feature_count, "All feature records should enter collection with pending outcome labels."),
        collection_check(collection_label, created_at, registry_label, "collection", "collection record count", CHECK_PASS if collection_count == feature_count and collection_count >= min_records else CHECK_FAIL, collection_count, f"== {feature_count} and >= {min_records}", "Every feature record must produce one paper outcome collection record."),
        collection_check(collection_label, created_at, registry_label, "labels", "final label count", CHECK_PASS if final_label_count == collection_count and final_label_count > 0 else CHECK_FAIL, final_label_count, collection_count, "Every collection record must produce one final label."),
        collection_check(collection_label, created_at, registry_label, "labels", "final labels no longer pending", CHECK_PASS if finalized_non_pending == final_label_count and final_label_count > 0 else CHECK_FAIL, finalized_non_pending, final_label_count, "Final labels must no longer be pending placeholders."),
        collection_check(collection_label, created_at, registry_label, "training_lock", "training remains locked", CHECK_PASS if training_locked == final_label_count and final_label_count > 0 else CHECK_FAIL, training_locked, final_label_count, "Training must remain locked after label finalization."),
        collection_check(collection_label, created_at, registry_label, "offline_eval", "offline evaluation candidates", CHECK_PASS if offline_candidates == final_label_count and final_label_count > 0 else CHECK_FAIL, offline_candidates, final_label_count, "Final labels may become offline-evaluation candidates only."),
        collection_check(collection_label, created_at, registry_label, "lineage", "collection lineage completeness", CHECK_PASS if lineage_count == collection_count and collection_count > 0 else CHECK_FAIL, lineage_count, collection_count, "Every collection record must preserve feature-store and training-entry lineage."),
        collection_check(collection_label, created_at, registry_label, "mode", "collection mode local deterministic", CHECK_PASS, COLLECTION_MODE, COLLECTION_MODE, "Outcome collection mode is local deterministic paper-only label finalization."),
    ]


def decide_collection_outcome(
    registry: sqlite3.Row | None,
    checks: list[dict[str, Any]],
) -> tuple[str, str, str, str, str, str]:
    if registry is None:
        return (
            DECISION_REJECT_MISSING,
            VERDICT_MISSING,
            ACTION_REFRESH,
            "Mission 74 AI Feature Store and Training Dataset Registry",
            COLLECTION_STATE_MISSING,
            "Feature-store registry evidence is missing.",
        )

    failed = [check for check in checks if check["check_status"] == CHECK_FAIL]

    if any(check["check_category"] == "safety" for check in failed):
        return (
            DECISION_BLOCK_SAFETY,
            VERDICT_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 75 safety remediation",
            COLLECTION_STATE_BLOCKED,
            "Safety invariant failed during paper outcome collection and label finalization.",
        )

    if failed:
        return (
            DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 74 AI Feature Store and Training Dataset Registry",
            COLLECTION_STATE_UNSTABLE,
            "Paper outcome collection or label finalization failed one or more checks.",
        )

    return (
        DECISION_READY_LOCKED,
        VERDICT_READY,
        ACTION_READY_LOCKED,
        NEXT_READY,
        COLLECTION_STATE_READY_LOCKED,
        "Paper outcome labels are finalized for quality review. Training and live trading remain locked.",
    )


def bps_metrics(collection_records: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    nets = [safe_float(record["net_paper_outcome_bps"]) for record in collection_records]
    fees = [safe_float(record["fee_drag_bps"]) for record in collection_records]

    average_net = round8(sum(nets) / len(nets)) if nets else 0.0
    worst_net = round8(min(nets)) if nets else 0.0
    best_net = round8(max(nets)) if nets else 0.0
    average_fee = round8(sum(fees) / len(fees)) if fees else 0.0

    return average_net, worst_net, best_net, average_fee


def build_summary(
    db_path: str | Path,
    collection_label: str,
    report_label: str,
    created_at: str,
    registry_label: str,
    registry: sqlite3.Row | None,
    feature_records: list[sqlite3.Row],
    training_entries: list[sqlite3.Row],
    collection_records: list[dict[str, Any]],
    final_labels: list[dict[str, Any]],
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
    pending_before = sum(1 for record in feature_records if row_get(record, "outcome_label", "") == PENDING_OUTCOME_LABEL)
    finalized = sum(1 for label in final_labels if label["outcome_label"] != PENDING_OUTCOME_LABEL)
    training_locked = sum(1 for label in final_labels if label["training_eligible"] == TRAINING_LOCKED)
    training_eligible = sum(1 for label in final_labels if label["training_eligible"] != TRAINING_LOCKED)
    offline_candidates = sum(1 for label in final_labels if label["offline_evaluation_candidate"] == OFFLINE_EVAL_CANDIDATE)
    lineage_count = sum(1 for record in collection_records if collection_lineage_complete(record))
    average_net, worst_net, best_net, average_fee = bps_metrics(collection_records)

    return {
        "collection_label": collection_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_registry_label": registry_label,
        "source_build_label": row_get(registry, "source_build_label", None),
        "source_schedule_label": row_get(registry, "source_schedule_label", None),
        "source_guard_review_label": row_get(registry, "source_guard_review_label", None),
        "source_learning_run_label": row_get(registry, "source_learning_run_label", None),
        "source_multi_cycle_track_label": row_get(registry, "source_multi_cycle_track_label", None),
        "source_session_label": row_get(registry, "source_session_label", None),
        "source_portfolio_label": row_get(registry, "source_portfolio_label", None),
        "feature_record_count": len(feature_records),
        "training_registry_entry_count": len(training_entries),
        "collection_record_count": len(collection_records),
        "final_label_count": len(final_labels),
        "pending_before_count": pending_before,
        "finalized_label_count": finalized,
        "training_eligible_count": training_eligible,
        "training_locked_count": training_locked,
        "offline_evaluation_candidate_count": offline_candidates,
        "lineage_complete_count": lineage_count,
        "collection_check_count": len(checks),
        "pass_check_count": pass_count,
        "fail_check_count": fail_count,
        "safety_breach_count": safe_int(row_get(registry, "safety_breach_count", 0)),
        "average_net_paper_outcome_bps": average_net,
        "worst_net_paper_outcome_bps": worst_net,
        "best_net_paper_outcome_bps": best_net,
        "average_fee_drag_bps": average_fee,
        "collection_mode": COLLECTION_MODE,
        "collection_records": collection_records,
        "final_labels": final_labels,
        "collection_checks": checks,
        "collection_state": state,
        "collection_decision": decision,
        "global_verdict": verdict,
        "recommended_action": action,
        "next_mission": next_mission,
        "decision_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    record_lines = []
    for record in summary["collection_records"]:
        record_lines.append(
            "- "
            + f"symbol={record['planned_symbol']}, "
            + f"cycle={record['planned_cycle_index']}, "
            + f"net_bps={record['net_paper_outcome_bps']}, "
            + f"label={record['outcome_label']}, "
            + f"training_eligible={record['training_eligible']}"
        )

    check_lines = []
    for check in summary["collection_checks"]:
        check_lines.append(
            "- "
            + f"{check['check_category']} / {check['check_name']}: "
            + f"status={check['check_status']}, "
            + f"observed={check['observed_value']}, "
            + f"threshold={check['threshold_value']}"
        )

    records_markdown = "\n".join(record_lines) or "- None"
    checks_markdown = "\n".join(check_lines) or "- None"

    return f"""# DeltaGrid Mission 75 AI Paper Outcome Collection and Label Finalizer Report

Report label: {summary['report_label']}
Collection label: {summary['collection_label']}
Created at: {summary['created_at']}
Source registry label: {summary['source_registry_label']}
Source build label: {summary['source_build_label']}
Source schedule label: {summary['source_schedule_label']}
Source guard review label: {summary['source_guard_review_label']}
Source learning run label: {summary['source_learning_run_label']}
Source multi-cycle track label: {summary['source_multi_cycle_track_label']}
Source session label: {summary['source_session_label']}
Source portfolio label: {summary['source_portfolio_label']}

## Collection Summary

Feature record count: {summary['feature_record_count']}
Training registry entry count: {summary['training_registry_entry_count']}
Collection record count: {summary['collection_record_count']}
Final label count: {summary['final_label_count']}
Pending before count: {summary['pending_before_count']}
Finalized label count: {summary['finalized_label_count']}
Training eligible count: {summary['training_eligible_count']}
Training locked count: {summary['training_locked_count']}
Offline evaluation candidate count: {summary['offline_evaluation_candidate_count']}
Lineage complete count: {summary['lineage_complete_count']}

Average net paper outcome bps: {summary['average_net_paper_outcome_bps']}
Worst net paper outcome bps: {summary['worst_net_paper_outcome_bps']}
Best net paper outcome bps: {summary['best_net_paper_outcome_bps']}
Average fee drag bps: {summary['average_fee_drag_bps']}
Collection mode: {summary['collection_mode']}

Collection check count: {summary['collection_check_count']}
Pass check count: {summary['pass_check_count']}
Fail check count: {summary['fail_check_count']}
Safety breach count: {summary['safety_breach_count']}

## Collection Records

{records_markdown}

## Checks

{checks_markdown}

## Decision

Collection state: {summary['collection_state']}
Collection decision: {summary['collection_decision']}
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

This finalizer does not train a model.
Training remains locked after label finalization.
Labels are offline-evaluation candidates only.
This finalizer does not perform autonomous trading.
This finalizer does not adjust strategy weights automatically.
"""


def insert_row(conn: sqlite3.Connection, table_name: str, row: dict[str, Any], columns: list[str]) -> None:
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    values = [row[column] for column in columns]

    conn.execute(
        f"""
        INSERT OR REPLACE INTO {table_name} (
            {column_sql}
        )
        VALUES ({placeholders})
        """,
        values,
    )


def persist_collection(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for record in summary["collection_records"]:
            stored = dict(record)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                COLLECTION_RECORDS_TABLE,
                stored,
                [
                    "collection_record_id",
                    "collection_label",
                    "created_at",
                    "source_registry_label",
                    "source_feature_record_id",
                    "source_training_entry_id",
                    "source_dataset_row_id",
                    "planned_symbol",
                    "planned_cycle_index",
                    "gross_paper_outcome_bps",
                    "fee_drag_bps",
                    "net_paper_outcome_bps",
                    "outcome_label",
                    "target_label",
                    "label_confidence",
                    "training_eligible",
                    "offline_evaluation_candidate",
                    "collection_mode",
                    "collection_record_status",
                    "live_trading",
                    "live_order_sent",
                    "capital_deployment",
                    "metadata_json",
                ],
            )

        for label in summary["final_labels"]:
            stored_label = dict(label)
            stored_label["metadata_json"] = json.dumps(stored_label.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                FINAL_LABELS_TABLE,
                stored_label,
                [
                    "final_label_id",
                    "collection_label",
                    "created_at",
                    "source_collection_record_id",
                    "source_feature_record_id",
                    "source_training_entry_id",
                    "outcome_label",
                    "target_label",
                    "net_paper_outcome_bps",
                    "label_confidence",
                    "final_label_status",
                    "training_eligible",
                    "offline_evaluation_candidate",
                    "live_trading",
                    "live_order_sent",
                    "capital_deployment",
                    "metadata_json",
                ],
            )

        for check in summary["collection_checks"]:
            stored_check = dict(check)
            stored_check["metadata_json"] = json.dumps(stored_check.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                COLLECTION_CHECKS_TABLE,
                stored_check,
                [
                    "check_id",
                    "collection_label",
                    "created_at",
                    "source_registry_label",
                    "check_category",
                    "check_name",
                    "check_status",
                    "observed_value",
                    "threshold_value",
                    "check_reason",
                    "live_trading",
                    "live_order_sent",
                    "capital_deployment",
                    "metadata_json",
                ],
            )

        run_row = {
            "collection_label": summary["collection_label"],
            "report_label": summary["report_label"],
            "created_at": summary["created_at"],
            "source_registry_label": summary["source_registry_label"],
            "source_build_label": summary["source_build_label"],
            "source_schedule_label": summary["source_schedule_label"],
            "source_guard_review_label": summary["source_guard_review_label"],
            "source_learning_run_label": summary["source_learning_run_label"],
            "source_multi_cycle_track_label": summary["source_multi_cycle_track_label"],
            "source_session_label": summary["source_session_label"],
            "source_portfolio_label": summary["source_portfolio_label"],
            "feature_record_count": summary["feature_record_count"],
            "training_registry_entry_count": summary["training_registry_entry_count"],
            "collection_record_count": summary["collection_record_count"],
            "final_label_count": summary["final_label_count"],
            "pending_before_count": summary["pending_before_count"],
            "finalized_label_count": summary["finalized_label_count"],
            "training_eligible_count": summary["training_eligible_count"],
            "training_locked_count": summary["training_locked_count"],
            "offline_evaluation_candidate_count": summary["offline_evaluation_candidate_count"],
            "lineage_complete_count": summary["lineage_complete_count"],
            "collection_check_count": summary["collection_check_count"],
            "pass_check_count": summary["pass_check_count"],
            "fail_check_count": summary["fail_check_count"],
            "safety_breach_count": summary["safety_breach_count"],
            "average_net_paper_outcome_bps": str(summary["average_net_paper_outcome_bps"]),
            "worst_net_paper_outcome_bps": str(summary["worst_net_paper_outcome_bps"]),
            "best_net_paper_outcome_bps": str(summary["best_net_paper_outcome_bps"]),
            "average_fee_drag_bps": str(summary["average_fee_drag_bps"]),
            "collection_mode": summary["collection_mode"],
            "collection_state": summary["collection_state"],
            "collection_decision": summary["collection_decision"],
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
                "collection_label",
                "report_label",
                "created_at",
                "source_registry_label",
                "source_build_label",
                "source_schedule_label",
                "source_guard_review_label",
                "source_learning_run_label",
                "source_multi_cycle_track_label",
                "source_session_label",
                "source_portfolio_label",
                "feature_record_count",
                "training_registry_entry_count",
                "collection_record_count",
                "final_label_count",
                "pending_before_count",
                "finalized_label_count",
                "training_eligible_count",
                "training_locked_count",
                "offline_evaluation_candidate_count",
                "lineage_complete_count",
                "collection_check_count",
                "pass_check_count",
                "fail_check_count",
                "safety_breach_count",
                "average_net_paper_outcome_bps",
                "worst_net_paper_outcome_bps",
                "best_net_paper_outcome_bps",
                "average_fee_drag_bps",
                "collection_mode",
                "collection_state",
                "collection_decision",
                "global_verdict",
                "recommended_action",
                "next_mission",
                "live_trading",
                "live_order_sent",
                "capital_deployment",
                "summary_json",
                "markdown_report",
            ],
        )

        report_row = {
            "report_label": summary["report_label"],
            "collection_label": summary["collection_label"],
            "created_at": summary["created_at"],
            "source_registry_label": summary["source_registry_label"],
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
                "report_label",
                "collection_label",
                "created_at",
                "source_registry_label",
                "global_verdict",
                "recommended_action",
                "report_json",
                "markdown_report",
                "live_trading",
                "live_order_sent",
                "capital_deployment",
            ],
        )

        conn.commit()


def run_ai_paper_outcome_label_finalizer(
    db_path: str | Path = "offchain/deltagrid.db",
    collection_label: str | None = None,
    report_label: str | None = None,
    registry_label: str = "mission74-final-check",
    min_records: int = 4,
    gross_outcome_bps: float = 0.0,
    fee_drag_bps: float = 2.0,
    positive_threshold_bps: float = 5.0,
    loss_threshold_bps: float = 10.0,
) -> dict[str, Any]:
    if min_records <= 0:
        raise ValueError("min_records must be positive")

    if fee_drag_bps < 0:
        raise ValueError("fee_drag_bps cannot be negative")

    if positive_threshold_bps < 0:
        raise ValueError("positive_threshold_bps cannot be negative")

    if loss_threshold_bps < 0:
        raise ValueError("loss_threshold_bps cannot be negative")

    db = Path(db_path)
    collection = collection_label or new_collection_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    source_registry_label = parse_labels(registry_label)[0]

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        registry = load_registry(conn, source_registry_label)
        feature_records = load_feature_records(conn, source_registry_label)
        training_entries = load_training_entries(conn, source_registry_label)
        registry_checks = load_registry_checks(conn, source_registry_label)

    if registry is None:
        collection_records: list[dict[str, Any]] = []
        final_labels: list[dict[str, Any]] = []
        checks = build_missing_checks(collection, created_at, source_registry_label)
    else:
        collection_records = build_collection_records(
            collection_label=collection,
            created_at=created_at,
            registry_label=source_registry_label,
            feature_records=feature_records,
            training_entries=training_entries,
            gross_outcome_bps=gross_outcome_bps,
            fee_drag_bps=fee_drag_bps,
            positive_threshold_bps=positive_threshold_bps,
            loss_threshold_bps=loss_threshold_bps,
        )
        final_labels = build_final_labels(collection, created_at, collection_records)
        checks = build_quality_checks(
            collection_label=collection,
            created_at=created_at,
            registry_label=source_registry_label,
            registry=registry,
            feature_records=feature_records,
            training_entries=training_entries,
            registry_checks=registry_checks,
            collection_records=collection_records,
            final_labels=final_labels,
            min_records=min_records,
        )

    decision, verdict, action, next_mission, state, reason = decide_collection_outcome(registry, checks)

    summary = build_summary(
        db_path=db,
        collection_label=collection,
        report_label=report,
        created_at=created_at,
        registry_label=source_registry_label,
        registry=registry,
        feature_records=feature_records,
        training_entries=training_entries,
        collection_records=collection_records,
        final_labels=final_labels,
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

    persist_collection(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid AI paper outcome collection and label finalizer.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--collection-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--registry-label", default="mission74-final-check")
    parser.add_argument("--min-records", type=int, default=4)
    parser.add_argument("--gross-outcome-bps", type=float, default=0.0)
    parser.add_argument("--fee-drag-bps", type=float, default=2.0)
    parser.add_argument("--positive-threshold-bps", type=float, default=5.0)
    parser.add_argument("--loss-threshold-bps", type=float, default=10.0)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_ai_paper_outcome_label_finalizer(
        db_path=args.db,
        collection_label=args.collection_label,
        report_label=args.report_label,
        registry_label=args.registry_label,
        min_records=args.min_records,
        gross_outcome_bps=args.gross_outcome_bps,
        fee_drag_bps=args.fee_drag_bps,
        positive_threshold_bps=args.positive_threshold_bps,
        loss_threshold_bps=args.loss_threshold_bps,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

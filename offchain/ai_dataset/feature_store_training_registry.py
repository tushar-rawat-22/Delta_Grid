"""
Mission 74: AI Feature Store and Training Dataset Registry.

This module registers Mission 73 paper-only outcome dataset rows into a local
feature store and creates training dataset registry entries.

Important boundary:
- Rows remain training-locked while outcome labels are pending.
- No model training happens here.
- No autonomous strategy reweighting happens here.
- No trading or execution happens here.

It reads:
- ai_outcome_dataset_builds
- ai_outcome_dataset_rows
- ai_outcome_dataset_quality_checks
- ai_outcome_dataset_handoffs

It writes:
- ai_feature_store_training_registries
- ai_feature_store_feature_records
- ai_training_dataset_registry_entries
- ai_feature_store_training_registry_checks
- ai_feature_store_training_registry_reports
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


BUILDS_TABLE = "ai_outcome_dataset_builds"
ROWS_TABLE = "ai_outcome_dataset_rows"
QUALITY_CHECKS_TABLE = "ai_outcome_dataset_quality_checks"
HANDOFFS_TABLE = "ai_outcome_dataset_handoffs"

REGISTRIES_TABLE = "ai_feature_store_training_registries"
FEATURE_RECORDS_TABLE = "ai_feature_store_feature_records"
TRAINING_ENTRIES_TABLE = "ai_training_dataset_registry_entries"
REGISTRY_CHECKS_TABLE = "ai_feature_store_training_registry_checks"
REPORTS_TABLE = "ai_feature_store_training_registry_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

BUILD_DECISION_READY = "AI_OUTCOME_DATASET_BUILD_APPROVED_FOR_FEATURE_STORE_HANDOFF"
BUILD_VERDICT_READY = "AI_OUTCOME_DATASET_BUILD_READY_SHADOW_ONLY"
BUILD_STATE_READY = "AI_OUTCOME_DATASET_BUILD_READY"
HANDOFF_STATUS_READY = "AI_OUTCOME_DATASET_HANDOFF_READY_FOR_FEATURE_STORE"

OUTCOME_LABEL_PENDING = "AI_OUTCOME_DATASET_LABEL_PENDING_PAPER_OBSERVATION"
TARGET_LABEL_PENDING = "AI_OUTCOME_TARGET_PENDING_COLLECTION"

FEATURE_NAMESPACE = "paper_outcome_feature_store"
FEATURE_VERSION = "v1"
FEATURE_RECORD_STATUS = "AI_FEATURE_STORE_RECORD_REGISTERED_PENDING_OUTCOME"
TRAINING_ENTRY_STATUS_LOCKED = "AI_TRAINING_DATASET_ENTRY_LOCKED_PENDING_OUTCOME"

CHECK_PASS = "AI_FEATURE_STORE_REGISTRY_CHECK_PASS"
CHECK_FAIL = "AI_FEATURE_STORE_REGISTRY_CHECK_FAIL"

REGISTRY_STATE_READY_LOCKED = "AI_FEATURE_STORE_REGISTRY_READY_TRAINING_LOCKED"
REGISTRY_STATE_UNSTABLE = "AI_FEATURE_STORE_REGISTRY_UNSTABLE"
REGISTRY_STATE_BLOCKED = "AI_FEATURE_STORE_REGISTRY_BLOCKED"
REGISTRY_STATE_MISSING = "AI_FEATURE_STORE_REGISTRY_MISSING"

DECISION_READY_LOCKED = "AI_FEATURE_STORE_REGISTRY_APPROVED_TRAINING_LOCKED"
DECISION_UNSTABLE = "AI_FEATURE_STORE_REGISTRY_UNSTABLE_REVIEW_REQUIRED"
DECISION_BLOCK_SAFETY = "AI_FEATURE_STORE_REGISTRY_BLOCKED_BY_SAFETY_POLICY"
DECISION_REJECT_MISSING = "AI_FEATURE_STORE_REGISTRY_REJECTED_MISSING_EVIDENCE"

VERDICT_READY = "AI_FEATURE_STORE_TRAINING_REGISTRY_READY_SHADOW_ONLY"
VERDICT_UNSTABLE = "AI_FEATURE_STORE_TRAINING_REGISTRY_UNSTABLE_SHADOW_ONLY"
VERDICT_BLOCKED = "AI_FEATURE_STORE_TRAINING_REGISTRY_BLOCKED_SHADOW_ONLY"
VERDICT_MISSING = "AI_FEATURE_STORE_TRAINING_REGISTRY_MISSING_EVIDENCE"

ACTION_READY_LOCKED = "CONTINUE_PAPER_OUTCOME_COLLECTION_BEFORE_TRAINING_DATASET_ACTIVATION"
ACTION_REVIEW_UNSTABLE = "REVIEW_FEATURE_STORE_REGISTRY_BEFORE_OUTCOME_COLLECTION"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_FEATURE_STORE_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_AI_OUTCOME_DATASET_BUILD"

NEXT_READY = "Mission 75 AI Paper Outcome Collection and Label Finalizer"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_registry_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission74-ai-feature-store-registry-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission74-ai-feature-store-registry-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
        return ["mission73-final-check"]

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    labels: list[str] = []

    for item in raw_items:
        label = str(item).strip()

        if not label:
            continue

        if any(ch.isspace() for ch in label):
            raise ValueError(f"Invalid AI outcome dataset build label: {label}")

        if label not in labels:
            labels.append(label)

    if not labels:
        raise ValueError("At least one AI outcome dataset build label is required")

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
            CREATE TABLE IF NOT EXISTS ai_feature_store_training_registries (
                registry_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_build_label TEXT NOT NULL,
                source_schedule_label TEXT,
                source_guard_review_label TEXT,
                source_learning_run_label TEXT,
                source_multi_cycle_track_label TEXT,
                source_session_label TEXT,
                source_portfolio_label TEXT,
                dataset_row_count INTEGER NOT NULL,
                feature_record_count INTEGER NOT NULL,
                training_registry_entry_count INTEGER NOT NULL,
                pending_outcome_count INTEGER NOT NULL,
                training_eligible_count INTEGER NOT NULL,
                training_locked_count INTEGER NOT NULL,
                lineage_complete_count INTEGER NOT NULL,
                feature_snapshot_complete_count INTEGER NOT NULL,
                registry_check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                learning_score TEXT NOT NULL,
                max_feature_drift TEXT NOT NULL,
                feature_namespace TEXT NOT NULL,
                feature_version TEXT NOT NULL,
                registry_state TEXT NOT NULL,
                registry_decision TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_feature_store_feature_records (
                feature_record_id TEXT PRIMARY KEY,
                registry_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_build_label TEXT NOT NULL,
                source_dataset_row_id TEXT NOT NULL,
                source_schedule_label TEXT,
                source_guard_review_label TEXT,
                source_learning_run_label TEXT,
                source_multi_cycle_track_label TEXT,
                source_session_label TEXT,
                source_portfolio_label TEXT,
                feature_namespace TEXT NOT NULL,
                feature_version TEXT NOT NULL,
                planned_symbol TEXT NOT NULL,
                planned_cycle_index INTEGER NOT NULL,
                feature_snapshot_json TEXT NOT NULL,
                outcome_label TEXT NOT NULL,
                target_label TEXT NOT NULL,
                training_eligible INTEGER NOT NULL,
                feature_record_status TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_training_dataset_registry_entries (
                training_entry_id TEXT PRIMARY KEY,
                registry_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_feature_record_id TEXT NOT NULL,
                source_dataset_row_id TEXT NOT NULL,
                source_build_label TEXT NOT NULL,
                training_entry_status TEXT NOT NULL,
                training_eligible INTEGER NOT NULL,
                outcome_label TEXT NOT NULL,
                target_label TEXT NOT NULL,
                exclusion_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_feature_store_training_registry_checks (
                check_id TEXT PRIMARY KEY,
                registry_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_build_label TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_feature_store_training_registry_reports (
                report_label TEXT PRIMARY KEY,
                registry_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_build_label TEXT NOT NULL,
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


def load_build(conn: sqlite3.Connection, build_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, BUILDS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM ai_outcome_dataset_builds
        WHERE build_label = ?
        """,
        (build_label,),
    ).fetchone()


def load_dataset_rows(conn: sqlite3.Connection, build_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, ROWS_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM ai_outcome_dataset_rows
        WHERE build_label = ?
        ORDER BY row_index ASC, dataset_row_id ASC
        """,
        (build_label,),
    ).fetchall()


def load_quality_checks(conn: sqlite3.Connection, build_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, QUALITY_CHECKS_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM ai_outcome_dataset_quality_checks
        WHERE build_label = ?
        ORDER BY created_at ASC, check_id ASC
        """,
        (build_label,),
    ).fetchall()


def load_handoffs(conn: sqlite3.Connection, build_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, HANDOFFS_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM ai_outcome_dataset_handoffs
        WHERE build_label = ?
        ORDER BY created_at ASC, handoff_id ASC
        """,
        (build_label,),
    ).fetchall()


def primary_handoff(handoffs: list[sqlite3.Row]) -> sqlite3.Row | None:
    for handoff in handoffs:
        if row_get(handoff, "handoff_status", "") == HANDOFF_STATUS_READY:
            return handoff

    return handoffs[0] if handoffs else None


def row_lineage_complete(row: sqlite3.Row | dict[str, Any]) -> bool:
    required = (
        "source_schedule_label",
        "source_guard_review_label",
        "source_learning_run_label",
        "source_multi_cycle_track_label",
        "source_session_label",
        "source_portfolio_label",
    )

    return all(row_get(row, field, None) not in (None, "") for field in required)


def feature_record_lineage_complete(record: dict[str, Any]) -> bool:
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

    return all(record.get(field) not in (None, "") for field in required)


def snapshot_complete(row: sqlite3.Row | dict[str, Any]) -> bool:
    snapshot = parse_json(row_get(row, "feature_snapshot_json", "{}"))
    return bool(snapshot) and "learning_score" in snapshot and "max_feature_drift" in snapshot


def registry_check(
    registry_label: str,
    created_at: str,
    build_label: str,
    category: str,
    name: str,
    status: str,
    observed_value: Any,
    threshold_value: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{registry_label}-{category}-{name}".replace(" ", "_"),
        "registry_label": registry_label,
        "created_at": created_at,
        "source_build_label": build_label,
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
            "feature_store_role": "TRAINING_REGISTRY_CHECK_ONLY",
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


def build_missing_checks(registry_label: str, created_at: str, build_label: str) -> list[dict[str, Any]]:
    return [
        registry_check(
            registry_label,
            created_at,
            build_label,
            "availability",
            "outcome dataset build exists",
            CHECK_FAIL,
            "missing",
            "ai_outcome_dataset_builds record",
            "No AI outcome dataset build exists for this label.",
        )
    ]


def build_feature_records(
    registry_label: str,
    created_at: str,
    build: sqlite3.Row,
    rows: list[sqlite3.Row],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for index, row in enumerate(rows, start=1):
        dataset_row_id = str(row_get(row, "dataset_row_id", f"dataset-row-{index}"))
        snapshot = parse_json(row_get(row, "feature_snapshot_json", "{}"))

        records.append(
            {
                "feature_record_id": f"{registry_label}-{dataset_row_id}-feature-record".replace(" ", "_"),
                "registry_label": registry_label,
                "created_at": created_at,
                "source_build_label": str(row_get(build, "build_label", "")),
                "source_dataset_row_id": dataset_row_id,
                "source_schedule_label": row_get(row, "source_schedule_label", row_get(build, "source_schedule_label", None)),
                "source_guard_review_label": row_get(row, "source_guard_review_label", row_get(build, "source_guard_review_label", None)),
                "source_learning_run_label": row_get(row, "source_learning_run_label", row_get(build, "source_learning_run_label", None)),
                "source_multi_cycle_track_label": row_get(row, "source_multi_cycle_track_label", row_get(build, "source_multi_cycle_track_label", None)),
                "source_session_label": row_get(row, "source_session_label", row_get(build, "source_session_label", None)),
                "source_portfolio_label": row_get(row, "source_portfolio_label", row_get(build, "source_portfolio_label", None)),
                "feature_namespace": FEATURE_NAMESPACE,
                "feature_version": FEATURE_VERSION,
                "planned_symbol": str(row_get(row, "planned_symbol", "")),
                "planned_cycle_index": safe_int(row_get(row, "planned_cycle_index", 0)),
                "feature_snapshot": snapshot,
                "outcome_label": str(row_get(row, "outcome_label", OUTCOME_LABEL_PENDING)),
                "target_label": str(row_get(row, "target_label", TARGET_LABEL_PENDING)),
                "training_eligible": safe_int(row_get(row, "training_eligible", 0)),
                "feature_record_status": FEATURE_RECORD_STATUS,
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT_VALUE,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "metadata": {
                    "feature_store_role": "PAPER_FEATURE_RECORD_ONLY",
                    "execution_role": "NONE",
                    "private_keys_used": False,
                    "orders_sent": False,
                    "paid_api_used": False,
                    "real_capital_used": False,
                    "autonomous_trading_enabled": False,
                    "automatic_strategy_reweighting_enabled": False,
                    "model_training_enabled": False,
                    "training_locked_pending_outcome": True,
                },
            }
        )

    return records


def build_training_entries(
    registry_label: str,
    created_at: str,
    feature_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    for record in feature_records:
        entries.append(
            {
                "training_entry_id": f"{record['feature_record_id']}-training-registry-entry",
                "registry_label": registry_label,
                "created_at": created_at,
                "source_feature_record_id": record["feature_record_id"],
                "source_dataset_row_id": record["source_dataset_row_id"],
                "source_build_label": record["source_build_label"],
                "training_entry_status": TRAINING_ENTRY_STATUS_LOCKED,
                "training_eligible": 0,
                "outcome_label": record["outcome_label"],
                "target_label": record["target_label"],
                "exclusion_reason": "Outcome label is pending paper observation; training remains locked.",
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT_VALUE,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "metadata": {
                    "feature_store_role": "TRAINING_DATASET_REGISTRY_ENTRY_ONLY",
                    "execution_role": "NONE",
                    "private_keys_used": False,
                    "orders_sent": False,
                    "paid_api_used": False,
                    "real_capital_used": False,
                    "autonomous_trading_enabled": False,
                    "automatic_strategy_reweighting_enabled": False,
                    "model_training_enabled": False,
                    "training_locked_pending_outcome": True,
                },
            }
        )

    return entries


def build_quality_checks(
    registry_label: str,
    created_at: str,
    build_label: str,
    build: sqlite3.Row,
    rows: list[sqlite3.Row],
    quality_checks: list[sqlite3.Row],
    handoffs: list[sqlite3.Row],
    feature_records: list[dict[str, Any]],
    training_entries: list[dict[str, Any]],
    min_feature_records: int,
) -> list[dict[str, Any]]:
    handoff = primary_handoff(handoffs)

    safety_count = safe_int(row_get(build, "safety_breach_count", 0))
    safety_count += sum(1 for row in [build, *rows, *quality_checks, *handoffs] if safety_problem(row))

    dataset_row_count = len(rows)
    feature_record_count = len(feature_records)
    training_entry_count = len(training_entries)
    pending_outcomes = sum(1 for record in feature_records if record["outcome_label"] == OUTCOME_LABEL_PENDING)
    training_locked = sum(1 for entry in training_entries if entry["training_eligible"] == 0)
    training_eligible = sum(1 for entry in training_entries if entry["training_eligible"] != 0)
    lineage_complete = sum(1 for record in feature_records if feature_record_lineage_complete(record))
    snapshot_complete_count = sum(1 for row in rows if snapshot_complete(row))
    source_fail_count = safe_int(row_get(build, "fail_check_count", 0))

    return [
        registry_check(
            registry_label,
            created_at,
            build_label,
            "availability",
            "outcome dataset build exists",
            CHECK_PASS,
            "present",
            "present",
            "AI outcome dataset build exists.",
        ),
        registry_check(
            registry_label,
            created_at,
            build_label,
            "safety",
            "safety breach count",
            CHECK_PASS if safety_count == 0 else CHECK_FAIL,
            safety_count,
            0,
            "Feature store registry requires zero live-trading, order-transmission, and capital-deployment breaches.",
        ),
        registry_check(
            registry_label,
            created_at,
            build_label,
            "build",
            "build decision ready",
            CHECK_PASS if row_get(build, "build_decision", "") == BUILD_DECISION_READY else CHECK_FAIL,
            row_get(build, "build_decision", ""),
            BUILD_DECISION_READY,
            "Feature-store registration requires an approved outcome dataset build decision.",
        ),
        registry_check(
            registry_label,
            created_at,
            build_label,
            "build",
            "build verdict ready",
            CHECK_PASS if row_get(build, "global_verdict", "") == BUILD_VERDICT_READY else CHECK_FAIL,
            row_get(build, "global_verdict", ""),
            BUILD_VERDICT_READY,
            "Feature-store registration requires a ready shadow-only build verdict.",
        ),
        registry_check(
            registry_label,
            created_at,
            build_label,
            "build",
            "build state ready",
            CHECK_PASS if row_get(build, "build_state", "") == BUILD_STATE_READY else CHECK_FAIL,
            row_get(build, "build_state", ""),
            BUILD_STATE_READY,
            "Feature-store registration requires the source build state to be ready.",
        ),
        registry_check(
            registry_label,
            created_at,
            build_label,
            "handoff",
            "feature store handoff ready",
            CHECK_PASS if row_get(handoff, "handoff_status", "") == HANDOFF_STATUS_READY else CHECK_FAIL,
            row_get(handoff, "handoff_status", "missing"),
            HANDOFF_STATUS_READY,
            "Mission 73 must provide a feature-store handoff.",
        ),
        registry_check(
            registry_label,
            created_at,
            build_label,
            "build",
            "source build failed checks",
            CHECK_PASS if source_fail_count == 0 else CHECK_FAIL,
            source_fail_count,
            0,
            "Source outcome dataset build failed checks must remain zero.",
        ),
        registry_check(
            registry_label,
            created_at,
            build_label,
            "coverage",
            "dataset row count",
            CHECK_PASS if dataset_row_count >= min_feature_records else CHECK_FAIL,
            dataset_row_count,
            f">= {min_feature_records}",
            "Feature-store registry needs enough source dataset rows.",
        ),
        registry_check(
            registry_label,
            created_at,
            build_label,
            "feature_store",
            "feature record count",
            CHECK_PASS if feature_record_count == dataset_row_count and feature_record_count >= min_feature_records else CHECK_FAIL,
            feature_record_count,
            f"== {dataset_row_count} and >= {min_feature_records}",
            "Every dataset row must become one feature-store record.",
        ),
        registry_check(
            registry_label,
            created_at,
            build_label,
            "training_registry",
            "training entry count",
            CHECK_PASS if training_entry_count == feature_record_count and training_entry_count > 0 else CHECK_FAIL,
            training_entry_count,
            feature_record_count,
            "Every feature-store record must get one training dataset registry entry.",
        ),
        registry_check(
            registry_label,
            created_at,
            build_label,
            "labels",
            "pending outcome labels",
            CHECK_PASS if pending_outcomes == feature_record_count and feature_record_count > 0 else CHECK_FAIL,
            pending_outcomes,
            feature_record_count,
            "All records must remain pending until paper outcomes are collected.",
        ),
        registry_check(
            registry_label,
            created_at,
            build_label,
            "training_lock",
            "training eligibility locked",
            CHECK_PASS if training_locked == training_entry_count and training_eligible == 0 and training_entry_count > 0 else CHECK_FAIL,
            f"locked={training_locked}, eligible={training_eligible}",
            f"locked={training_entry_count}, eligible=0",
            "Training must remain locked while outcome labels are pending.",
        ),
        registry_check(
            registry_label,
            created_at,
            build_label,
            "lineage",
            "feature record lineage completeness",
            CHECK_PASS if lineage_complete == feature_record_count and feature_record_count > 0 else CHECK_FAIL,
            lineage_complete,
            feature_record_count,
            "Every feature-store record must preserve source lineage.",
        ),
        registry_check(
            registry_label,
            created_at,
            build_label,
            "features",
            "feature snapshot completeness",
            CHECK_PASS if snapshot_complete_count == dataset_row_count and dataset_row_count > 0 else CHECK_FAIL,
            snapshot_complete_count,
            dataset_row_count,
            "Every source row must include a complete feature snapshot.",
        ),
        registry_check(
            registry_label,
            created_at,
            build_label,
            "namespace",
            "feature namespace version",
            CHECK_PASS,
            f"{FEATURE_NAMESPACE}:{FEATURE_VERSION}",
            f"{FEATURE_NAMESPACE}:{FEATURE_VERSION}",
            "Feature namespace and version are assigned for feature-store registration.",
        ),
    ]


def decide_registry_outcome(
    build: sqlite3.Row | None,
    checks: list[dict[str, Any]],
) -> tuple[str, str, str, str, str, str]:
    if build is None:
        return (
            DECISION_REJECT_MISSING,
            VERDICT_MISSING,
            ACTION_REFRESH,
            "Mission 73 AI Outcome Dataset Builder Pack",
            REGISTRY_STATE_MISSING,
            "AI outcome dataset build evidence is missing.",
        )

    failed = [check for check in checks if check["check_status"] == CHECK_FAIL]

    if any(check["check_category"] == "safety" for check in failed):
        return (
            DECISION_BLOCK_SAFETY,
            VERDICT_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 74 safety remediation",
            REGISTRY_STATE_BLOCKED,
            "Safety invariant failed during feature-store and training dataset registry.",
        )

    if failed:
        return (
            DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 73 AI Outcome Dataset Builder Pack",
            REGISTRY_STATE_UNSTABLE,
            "Feature-store or training dataset registry failed one or more checks.",
        )

    return (
        DECISION_READY_LOCKED,
        VERDICT_READY,
        ACTION_READY_LOCKED,
        NEXT_READY,
        REGISTRY_STATE_READY_LOCKED,
        "Feature store registry is ready, but training remains locked until paper outcomes are collected.",
    )


def build_summary(
    db_path: str | Path,
    registry_label: str,
    report_label: str,
    created_at: str,
    build_label: str,
    build: sqlite3.Row | None,
    feature_records: list[dict[str, Any]],
    training_entries: list[dict[str, Any]],
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
    pending_count = sum(1 for record in feature_records if record["outcome_label"] == OUTCOME_LABEL_PENDING)
    training_eligible_count = sum(1 for entry in training_entries if entry["training_eligible"] != 0)
    training_locked_count = sum(1 for entry in training_entries if entry["training_eligible"] == 0)
    lineage_count = sum(1 for record in feature_records if feature_record_lineage_complete(record))
    snapshot_count = sum(1 for record in feature_records if bool(record["feature_snapshot"]))

    safety_breach_count = safe_int(row_get(build, "safety_breach_count", 0))

    return {
        "registry_label": registry_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_build_label": build_label,
        "source_schedule_label": row_get(build, "source_schedule_label", None),
        "source_guard_review_label": row_get(build, "source_guard_review_label", None),
        "source_learning_run_label": row_get(build, "source_learning_run_label", None),
        "source_multi_cycle_track_label": row_get(build, "source_multi_cycle_track_label", None),
        "source_session_label": row_get(build, "source_session_label", None),
        "source_portfolio_label": row_get(build, "source_portfolio_label", None),
        "dataset_row_count": safe_int(row_get(build, "dataset_row_count", len(feature_records))),
        "feature_record_count": len(feature_records),
        "training_registry_entry_count": len(training_entries),
        "pending_outcome_count": pending_count,
        "training_eligible_count": training_eligible_count,
        "training_locked_count": training_locked_count,
        "lineage_complete_count": lineage_count,
        "feature_snapshot_complete_count": snapshot_count,
        "registry_check_count": len(checks),
        "pass_check_count": pass_count,
        "fail_check_count": fail_count,
        "safety_breach_count": safety_breach_count,
        "learning_score": round8(safe_float(row_get(build, "learning_score", 0.0))),
        "max_feature_drift": round8(safe_float(row_get(build, "max_feature_drift", 0.0))),
        "feature_namespace": FEATURE_NAMESPACE,
        "feature_version": FEATURE_VERSION,
        "feature_records": feature_records,
        "training_registry_entries": training_entries,
        "registry_checks": checks,
        "registry_state": state,
        "registry_decision": decision,
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
    for record in summary["feature_records"]:
        record_lines.append(
            "- "
            + f"symbol={record['planned_symbol']}, "
            + f"cycle={record['planned_cycle_index']}, "
            + f"status={record['feature_record_status']}, "
            + f"training_eligible={record['training_eligible']}"
        )

    entry_lines = []
    for entry in summary["training_registry_entries"]:
        entry_lines.append(
            "- "
            + f"entry={entry['training_entry_id']}, "
            + f"status={entry['training_entry_status']}, "
            + f"eligible={entry['training_eligible']}"
        )

    check_lines = []
    for check in summary["registry_checks"]:
        check_lines.append(
            "- "
            + f"{check['check_category']} / {check['check_name']}: "
            + f"status={check['check_status']}, "
            + f"observed={check['observed_value']}, "
            + f"threshold={check['threshold_value']}"
        )

    records_markdown = "\n".join(record_lines) or "- None"
    entries_markdown = "\n".join(entry_lines) or "- None"
    checks_markdown = "\n".join(check_lines) or "- None"

    return f"""# DeltaGrid Mission 74 AI Feature Store and Training Dataset Registry Report

Report label: {summary['report_label']}
Registry label: {summary['registry_label']}
Created at: {summary['created_at']}
Source build label: {summary['source_build_label']}
Source schedule label: {summary['source_schedule_label']}
Source guard review label: {summary['source_guard_review_label']}
Source learning run label: {summary['source_learning_run_label']}
Source multi-cycle track label: {summary['source_multi_cycle_track_label']}
Source session label: {summary['source_session_label']}
Source portfolio label: {summary['source_portfolio_label']}

## Registry Summary

Feature namespace: {summary['feature_namespace']}
Feature version: {summary['feature_version']}
Dataset row count: {summary['dataset_row_count']}
Feature record count: {summary['feature_record_count']}
Training registry entry count: {summary['training_registry_entry_count']}
Pending outcome count: {summary['pending_outcome_count']}
Training eligible count: {summary['training_eligible_count']}
Training locked count: {summary['training_locked_count']}
Lineage complete count: {summary['lineage_complete_count']}
Feature snapshot complete count: {summary['feature_snapshot_complete_count']}

Learning score: {summary['learning_score']}
Max feature drift: {summary['max_feature_drift']}

Registry check count: {summary['registry_check_count']}
Pass check count: {summary['pass_check_count']}
Fail check count: {summary['fail_check_count']}
Safety breach count: {summary['safety_breach_count']}

## Feature Records

{records_markdown}

## Training Dataset Registry Entries

{entries_markdown}

## Checks

{checks_markdown}

## Decision

Registry state: {summary['registry_state']}
Registry decision: {summary['registry_decision']}
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

This registry does not train a model.
Training remains locked until paper outcomes are collected.
This registry does not perform autonomous trading.
This registry does not adjust strategy weights automatically.
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


def persist_registry(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for record in summary["feature_records"]:
            stored = dict(record)
            stored["feature_snapshot_json"] = json.dumps(stored.pop("feature_snapshot"), sort_keys=True)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                FEATURE_RECORDS_TABLE,
                stored,
                [
                    "feature_record_id",
                    "registry_label",
                    "created_at",
                    "source_build_label",
                    "source_dataset_row_id",
                    "source_schedule_label",
                    "source_guard_review_label",
                    "source_learning_run_label",
                    "source_multi_cycle_track_label",
                    "source_session_label",
                    "source_portfolio_label",
                    "feature_namespace",
                    "feature_version",
                    "planned_symbol",
                    "planned_cycle_index",
                    "feature_snapshot_json",
                    "outcome_label",
                    "target_label",
                    "training_eligible",
                    "feature_record_status",
                    "live_trading",
                    "live_order_sent",
                    "capital_deployment",
                    "metadata_json",
                ],
            )

        for entry in summary["training_registry_entries"]:
            stored_entry = dict(entry)
            stored_entry["metadata_json"] = json.dumps(stored_entry.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                TRAINING_ENTRIES_TABLE,
                stored_entry,
                [
                    "training_entry_id",
                    "registry_label",
                    "created_at",
                    "source_feature_record_id",
                    "source_dataset_row_id",
                    "source_build_label",
                    "training_entry_status",
                    "training_eligible",
                    "outcome_label",
                    "target_label",
                    "exclusion_reason",
                    "live_trading",
                    "live_order_sent",
                    "capital_deployment",
                    "metadata_json",
                ],
            )

        for check in summary["registry_checks"]:
            stored_check = dict(check)
            stored_check["metadata_json"] = json.dumps(stored_check.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                REGISTRY_CHECKS_TABLE,
                stored_check,
                [
                    "check_id",
                    "registry_label",
                    "created_at",
                    "source_build_label",
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

        registry_row = {
            "registry_label": summary["registry_label"],
            "report_label": summary["report_label"],
            "created_at": summary["created_at"],
            "source_build_label": summary["source_build_label"],
            "source_schedule_label": summary["source_schedule_label"],
            "source_guard_review_label": summary["source_guard_review_label"],
            "source_learning_run_label": summary["source_learning_run_label"],
            "source_multi_cycle_track_label": summary["source_multi_cycle_track_label"],
            "source_session_label": summary["source_session_label"],
            "source_portfolio_label": summary["source_portfolio_label"],
            "dataset_row_count": summary["dataset_row_count"],
            "feature_record_count": summary["feature_record_count"],
            "training_registry_entry_count": summary["training_registry_entry_count"],
            "pending_outcome_count": summary["pending_outcome_count"],
            "training_eligible_count": summary["training_eligible_count"],
            "training_locked_count": summary["training_locked_count"],
            "lineage_complete_count": summary["lineage_complete_count"],
            "feature_snapshot_complete_count": summary["feature_snapshot_complete_count"],
            "registry_check_count": summary["registry_check_count"],
            "pass_check_count": summary["pass_check_count"],
            "fail_check_count": summary["fail_check_count"],
            "safety_breach_count": summary["safety_breach_count"],
            "learning_score": str(summary["learning_score"]),
            "max_feature_drift": str(summary["max_feature_drift"]),
            "feature_namespace": summary["feature_namespace"],
            "feature_version": summary["feature_version"],
            "registry_state": summary["registry_state"],
            "registry_decision": summary["registry_decision"],
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
            REGISTRIES_TABLE,
            registry_row,
            [
                "registry_label",
                "report_label",
                "created_at",
                "source_build_label",
                "source_schedule_label",
                "source_guard_review_label",
                "source_learning_run_label",
                "source_multi_cycle_track_label",
                "source_session_label",
                "source_portfolio_label",
                "dataset_row_count",
                "feature_record_count",
                "training_registry_entry_count",
                "pending_outcome_count",
                "training_eligible_count",
                "training_locked_count",
                "lineage_complete_count",
                "feature_snapshot_complete_count",
                "registry_check_count",
                "pass_check_count",
                "fail_check_count",
                "safety_breach_count",
                "learning_score",
                "max_feature_drift",
                "feature_namespace",
                "feature_version",
                "registry_state",
                "registry_decision",
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
            "registry_label": summary["registry_label"],
            "created_at": summary["created_at"],
            "source_build_label": summary["source_build_label"],
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
                "registry_label",
                "created_at",
                "source_build_label",
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


def run_ai_feature_store_training_registry(
    db_path: str | Path = "offchain/deltagrid.db",
    registry_label: str | None = None,
    report_label: str | None = None,
    build_label: str = "mission73-final-check",
    min_feature_records: int = 4,
) -> dict[str, Any]:
    if min_feature_records <= 0:
        raise ValueError("min_feature_records must be positive")

    db = Path(db_path)
    registry = registry_label or new_registry_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    source_build_label = parse_labels(build_label)[0]

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        build = load_build(conn, source_build_label)
        rows = load_dataset_rows(conn, source_build_label)
        quality_checks = load_quality_checks(conn, source_build_label)
        handoffs = load_handoffs(conn, source_build_label)

    if build is None:
        feature_records: list[dict[str, Any]] = []
        training_entries: list[dict[str, Any]] = []
        checks = build_missing_checks(registry, created_at, source_build_label)
    else:
        feature_records = build_feature_records(registry, created_at, build, rows)
        training_entries = build_training_entries(registry, created_at, feature_records)
        checks = build_quality_checks(
            registry_label=registry,
            created_at=created_at,
            build_label=source_build_label,
            build=build,
            rows=rows,
            quality_checks=quality_checks,
            handoffs=handoffs,
            feature_records=feature_records,
            training_entries=training_entries,
            min_feature_records=min_feature_records,
        )

    decision, verdict, action, next_mission, state, reason = decide_registry_outcome(build, checks)

    summary = build_summary(
        db_path=db,
        registry_label=registry,
        report_label=report,
        created_at=created_at,
        build_label=source_build_label,
        build=build,
        feature_records=feature_records,
        training_entries=training_entries,
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

    persist_registry(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid AI feature store and training dataset registry.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--registry-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--build-label", default="mission73-final-check")
    parser.add_argument("--min-feature-records", type=int, default=4)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_ai_feature_store_training_registry(
        db_path=args.db,
        registry_label=args.registry_label,
        report_label=args.report_label,
        build_label=args.build_label,
        min_feature_records=args.min_feature_records,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

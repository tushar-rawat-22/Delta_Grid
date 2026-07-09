"""
Mission 73: AI Outcome Dataset Builder Pack.

This module builds paper-only AI outcome dataset rows from the approved
Mission 72 AI paper dataset expansion schedule.

It reads:
- ai_paper_dataset_expansion_schedules
- ai_paper_dataset_expansion_schedule_items
- ai_paper_dataset_expansion_checks

It writes:
- ai_outcome_dataset_builds
- ai_outcome_dataset_rows
- ai_outcome_dataset_quality_checks
- ai_outcome_dataset_handoffs
- ai_outcome_dataset_reports

It is a paper dataset construction layer only.

It never:
- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital
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


SCHEDULES_TABLE = "ai_paper_dataset_expansion_schedules"
ITEMS_TABLE = "ai_paper_dataset_expansion_schedule_items"
EXPANSION_CHECKS_TABLE = "ai_paper_dataset_expansion_checks"

BUILDS_TABLE = "ai_outcome_dataset_builds"
ROWS_TABLE = "ai_outcome_dataset_rows"
QUALITY_CHECKS_TABLE = "ai_outcome_dataset_quality_checks"
HANDOFFS_TABLE = "ai_outcome_dataset_handoffs"
REPORTS_TABLE = "ai_outcome_dataset_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

SCHEDULE_DECISION_APPROVED = "AI_DATASET_EXPANSION_SCHEDULE_APPROVED_PAPER_ONLY"
SCHEDULE_VERDICT_READY = "AI_DATASET_EXPANSION_SCHEDULE_READY_SHADOW_ONLY"
SCHEDULE_STATE_READY = "AI_DATASET_EXPANSION_SCHEDULE_READY"

ROW_STATUS_READY = "AI_OUTCOME_DATASET_ROW_READY_FOR_PAPER_COLLECTION"
OUTCOME_LABEL_PENDING = "AI_OUTCOME_DATASET_LABEL_PENDING_PAPER_OBSERVATION"
TARGET_LABEL_PENDING = "AI_OUTCOME_TARGET_PENDING_COLLECTION"
TRAINING_ELIGIBLE_FALSE = 0

CHECK_PASS = "AI_OUTCOME_DATASET_CHECK_PASS"
CHECK_FAIL = "AI_OUTCOME_DATASET_CHECK_FAIL"

BUILD_STATE_READY = "AI_OUTCOME_DATASET_BUILD_READY"
BUILD_STATE_UNSTABLE = "AI_OUTCOME_DATASET_BUILD_UNSTABLE"
BUILD_STATE_BLOCKED = "AI_OUTCOME_DATASET_BUILD_BLOCKED"
BUILD_STATE_MISSING = "AI_OUTCOME_DATASET_BUILD_MISSING"

DECISION_READY = "AI_OUTCOME_DATASET_BUILD_APPROVED_FOR_FEATURE_STORE_HANDOFF"
DECISION_UNSTABLE = "AI_OUTCOME_DATASET_BUILD_UNSTABLE_REVIEW_REQUIRED"
DECISION_BLOCK_SAFETY = "AI_OUTCOME_DATASET_BUILD_BLOCKED_BY_SAFETY_POLICY"
DECISION_REJECT_MISSING = "AI_OUTCOME_DATASET_BUILD_REJECTED_MISSING_EVIDENCE"

VERDICT_READY = "AI_OUTCOME_DATASET_BUILD_READY_SHADOW_ONLY"
VERDICT_UNSTABLE = "AI_OUTCOME_DATASET_BUILD_UNSTABLE_SHADOW_ONLY"
VERDICT_BLOCKED = "AI_OUTCOME_DATASET_BUILD_BLOCKED_SHADOW_ONLY"
VERDICT_MISSING = "AI_OUTCOME_DATASET_BUILD_MISSING_EVIDENCE"

ACTION_READY = "HAND_OFF_AI_OUTCOME_DATASET_TO_FEATURE_STORE"
ACTION_REVIEW_UNSTABLE = "REVIEW_AI_OUTCOME_DATASET_BEFORE_FEATURE_STORE_HANDOFF"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_AI_OUTCOME_DATASET_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_AI_PAPER_DATASET_EXPANSION_SCHEDULE"

HANDOFF_STATUS_READY = "AI_OUTCOME_DATASET_HANDOFF_READY_FOR_FEATURE_STORE"
NEXT_READY = "Mission 74 AI Feature Store and Training Dataset Registry"

REQUIRED_ROW_FIELDS = (
    "source_schedule_label",
    "source_schedule_item_id",
    "planned_symbol",
    "planned_cycle_index",
    "outcome_label",
    "target_label",
    "training_eligible",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_build_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission73-ai-outcome-dataset-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission73-ai-outcome-dataset-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
        return ["mission72-final-check"]

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    labels: list[str] = []

    for item in raw_items:
        label = str(item).strip()

        if not label:
            continue

        if any(ch.isspace() for ch in label):
            raise ValueError(f"Invalid dataset expansion schedule label: {label}")

        if label not in labels:
            labels.append(label)

    if not labels:
        raise ValueError("At least one dataset expansion schedule label is required")

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
            CREATE TABLE IF NOT EXISTS ai_outcome_dataset_builds (
                build_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_schedule_label TEXT NOT NULL,
                source_guard_review_label TEXT,
                source_learning_run_label TEXT,
                source_multi_cycle_track_label TEXT,
                source_session_label TEXT,
                source_portfolio_label TEXT,
                planned_cycle_count INTEGER NOT NULL,
                planned_symbol_count INTEGER NOT NULL,
                planned_item_count INTEGER NOT NULL,
                dataset_row_count INTEGER NOT NULL,
                pending_outcome_count INTEGER NOT NULL,
                training_eligible_count INTEGER NOT NULL,
                lineage_complete_count INTEGER NOT NULL,
                quality_check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                learning_score TEXT NOT NULL,
                max_feature_drift TEXT NOT NULL,
                build_state TEXT NOT NULL,
                build_decision TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_outcome_dataset_rows (
                dataset_row_id TEXT PRIMARY KEY,
                build_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_schedule_label TEXT NOT NULL,
                source_schedule_item_id TEXT NOT NULL,
                source_guard_review_label TEXT,
                source_learning_run_label TEXT,
                source_multi_cycle_track_label TEXT,
                source_session_label TEXT,
                source_portfolio_label TEXT,
                row_index INTEGER NOT NULL,
                planned_cycle_index INTEGER NOT NULL,
                planned_symbol TEXT NOT NULL,
                planned_start_at TEXT NOT NULL,
                planned_end_at TEXT NOT NULL,
                outcome_label TEXT NOT NULL,
                target_label TEXT NOT NULL,
                training_eligible INTEGER NOT NULL,
                row_status TEXT NOT NULL,
                feature_snapshot_json TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_outcome_dataset_quality_checks (
                check_id TEXT PRIMARY KEY,
                build_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_schedule_label TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_outcome_dataset_handoffs (
                handoff_id TEXT PRIMARY KEY,
                build_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_schedule_label TEXT NOT NULL,
                target_mission TEXT NOT NULL,
                handoff_status TEXT NOT NULL,
                dataset_row_count INTEGER NOT NULL,
                training_eligible_count INTEGER NOT NULL,
                handoff_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_outcome_dataset_reports (
                report_label TEXT PRIMARY KEY,
                build_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_schedule_label TEXT NOT NULL,
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


def load_schedule(conn: sqlite3.Connection, schedule_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, SCHEDULES_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM ai_paper_dataset_expansion_schedules
        WHERE schedule_label = ?
        """,
        (schedule_label,),
    ).fetchone()


def load_schedule_items(conn: sqlite3.Connection, schedule_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, ITEMS_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM ai_paper_dataset_expansion_schedule_items
        WHERE schedule_label = ?
        ORDER BY planned_cycle_index ASC, item_index ASC
        """,
        (schedule_label,),
    ).fetchall()


def load_expansion_checks(conn: sqlite3.Connection, schedule_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, EXPANSION_CHECKS_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM ai_paper_dataset_expansion_checks
        WHERE schedule_label = ?
        ORDER BY created_at ASC, check_id ASC
        """,
        (schedule_label,),
    ).fetchall()


def build_dataset_rows(
    build_label: str,
    created_at: str,
    schedule: sqlite3.Row,
    items: list[sqlite3.Row],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    feature_snapshot = {
        "learning_score": round8(safe_float(row_get(schedule, "learning_score", 0.0))),
        "max_feature_drift": round8(safe_float(row_get(schedule, "max_feature_drift", 0.0))),
        "current_cycle_count": safe_int(row_get(schedule, "current_cycle_count", 0)),
        "target_total_cycles": safe_int(row_get(schedule, "target_total_cycles", 0)),
        "planned_cycle_count": safe_int(row_get(schedule, "planned_cycle_count", 0)),
        "planned_symbol_count": safe_int(row_get(schedule, "planned_symbol_count", 0)),
    }

    for index, item in enumerate(items, start=1):
        item_id = str(row_get(item, "item_id", f"item-{index}"))
        row_id = f"{build_label}-{item_id}".replace(" ", "_")

        rows.append(
            {
                "dataset_row_id": row_id,
                "build_label": build_label,
                "created_at": created_at,
                "source_schedule_label": str(row_get(schedule, "schedule_label", "")),
                "source_schedule_item_id": item_id,
                "source_guard_review_label": row_get(schedule, "source_guard_review_label", None),
                "source_learning_run_label": row_get(schedule, "source_learning_run_label", None),
                "source_multi_cycle_track_label": row_get(schedule, "source_multi_cycle_track_label", None),
                "source_session_label": row_get(schedule, "source_session_label", None),
                "source_portfolio_label": row_get(schedule, "source_portfolio_label", None),
                "row_index": index,
                "planned_cycle_index": safe_int(row_get(item, "planned_cycle_index", 0)),
                "planned_symbol": str(row_get(item, "planned_symbol", "")),
                "planned_start_at": str(row_get(item, "planned_start_at", "")),
                "planned_end_at": str(row_get(item, "planned_end_at", "")),
                "outcome_label": OUTCOME_LABEL_PENDING,
                "target_label": TARGET_LABEL_PENDING,
                "training_eligible": TRAINING_ELIGIBLE_FALSE,
                "row_status": ROW_STATUS_READY,
                "feature_snapshot": feature_snapshot,
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT_VALUE,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "metadata": {
                    "dataset_builder_role": "PAPER_OUTCOME_DATASET_ROW_ONLY",
                    "execution_role": "NONE",
                    "private_keys_used": False,
                    "orders_sent": False,
                    "paid_api_used": False,
                    "real_capital_used": False,
                    "autonomous_trading_enabled": False,
                    "automatic_strategy_reweighting_enabled": False,
                    "training_eligible": False,
                },
            }
        )

    return rows


def row_has_required_fields(row: dict[str, Any]) -> bool:
    for field in REQUIRED_ROW_FIELDS:
        if row.get(field) is None:
            return False

        if isinstance(row.get(field), str) and not row.get(field):
            return False

    return True


def lineage_complete(row: dict[str, Any]) -> bool:
    required = (
        "source_schedule_label",
        "source_schedule_item_id",
        "source_guard_review_label",
        "source_learning_run_label",
        "source_multi_cycle_track_label",
        "source_session_label",
        "source_portfolio_label",
    )

    return all(row.get(field) not in (None, "") for field in required)


def dataset_check(
    build_label: str,
    created_at: str,
    schedule_label: str,
    category: str,
    name: str,
    status: str,
    observed_value: Any,
    threshold_value: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{build_label}-{category}-{name}".replace(" ", "_"),
        "build_label": build_label,
        "created_at": created_at,
        "source_schedule_label": schedule_label,
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
            "dataset_builder_role": "PAPER_OUTCOME_DATASET_QUALITY_CHECK_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
            "autonomous_trading_enabled": False,
            "automatic_strategy_reweighting_enabled": False,
        },
    }


def build_missing_checks(build_label: str, created_at: str, schedule_label: str) -> list[dict[str, Any]]:
    return [
        dataset_check(
            build_label,
            created_at,
            schedule_label,
            "availability",
            "dataset expansion schedule exists",
            CHECK_FAIL,
            "missing",
            "ai_paper_dataset_expansion_schedules record",
            "No AI paper dataset expansion schedule exists for this label.",
        )
    ]


def build_quality_checks(
    build_label: str,
    created_at: str,
    schedule_label: str,
    schedule: sqlite3.Row,
    items: list[sqlite3.Row],
    expansion_checks: list[sqlite3.Row],
    rows: list[dict[str, Any]],
    min_dataset_rows: int,
    min_planned_cycles: int,
    min_symbols: int,
) -> list[dict[str, Any]]:
    row_count = len(rows)
    planned_item_count = safe_int(row_get(schedule, "planned_item_count", 0))
    planned_cycle_count = safe_int(row_get(schedule, "planned_cycle_count", 0))
    planned_symbol_count = safe_int(row_get(schedule, "planned_symbol_count", 0))
    schedule_fail_count = safe_int(row_get(schedule, "fail_check_count", 0))
    safety_breach_count = safe_int(row_get(schedule, "safety_breach_count", 0))
    safety_breach_count += sum(1 for row in [schedule, *items, *expansion_checks] if safety_problem(row))

    required_rows_ok = sum(1 for row in rows if row_has_required_fields(row))
    pending_outcomes = sum(1 for row in rows if row["outcome_label"] == OUTCOME_LABEL_PENDING)
    training_disabled = sum(1 for row in rows if safe_int(row["training_eligible"]) == TRAINING_ELIGIBLE_FALSE)
    lineage_complete_count = sum(1 for row in rows if lineage_complete(row))

    return [
        dataset_check(
            build_label,
            created_at,
            schedule_label,
            "availability",
            "dataset expansion schedule exists",
            CHECK_PASS,
            "present",
            "present",
            "AI paper dataset expansion schedule exists.",
        ),
        dataset_check(
            build_label,
            created_at,
            schedule_label,
            "safety",
            "safety breach count",
            CHECK_PASS if safety_breach_count == 0 else CHECK_FAIL,
            safety_breach_count,
            0,
            "Outcome dataset building requires zero live-trading, order-transmission, and capital-deployment breaches.",
        ),
        dataset_check(
            build_label,
            created_at,
            schedule_label,
            "schedule",
            "schedule decision approved",
            CHECK_PASS if row_get(schedule, "schedule_decision", "") == SCHEDULE_DECISION_APPROVED else CHECK_FAIL,
            row_get(schedule, "schedule_decision", ""),
            SCHEDULE_DECISION_APPROVED,
            "Outcome dataset building requires an approved paper-only schedule decision.",
        ),
        dataset_check(
            build_label,
            created_at,
            schedule_label,
            "schedule",
            "schedule verdict ready",
            CHECK_PASS if row_get(schedule, "global_verdict", "") == SCHEDULE_VERDICT_READY else CHECK_FAIL,
            row_get(schedule, "global_verdict", ""),
            SCHEDULE_VERDICT_READY,
            "Outcome dataset building requires a ready shadow-only schedule verdict.",
        ),
        dataset_check(
            build_label,
            created_at,
            schedule_label,
            "schedule",
            "schedule state ready",
            CHECK_PASS if row_get(schedule, "schedule_state", "") == SCHEDULE_STATE_READY else CHECK_FAIL,
            row_get(schedule, "schedule_state", ""),
            SCHEDULE_STATE_READY,
            "Outcome dataset building requires the schedule state to be ready.",
        ),
        dataset_check(
            build_label,
            created_at,
            schedule_label,
            "schedule",
            "schedule failed checks",
            CHECK_PASS if schedule_fail_count == 0 else CHECK_FAIL,
            schedule_fail_count,
            0,
            "Schedule failed checks must remain zero before building the dataset.",
        ),
        dataset_check(
            build_label,
            created_at,
            schedule_label,
            "coverage",
            "planned item count",
            CHECK_PASS if planned_item_count >= min_dataset_rows else CHECK_FAIL,
            planned_item_count,
            f">= {min_dataset_rows}",
            "The source schedule must contain enough planned paper dataset items.",
        ),
        dataset_check(
            build_label,
            created_at,
            schedule_label,
            "coverage",
            "planned cycle count",
            CHECK_PASS if planned_cycle_count >= min_planned_cycles else CHECK_FAIL,
            planned_cycle_count,
            f">= {min_planned_cycles}",
            "The source schedule must cover enough planned paper cycles.",
        ),
        dataset_check(
            build_label,
            created_at,
            schedule_label,
            "coverage",
            "planned symbol count",
            CHECK_PASS if planned_symbol_count >= min_symbols else CHECK_FAIL,
            planned_symbol_count,
            f">= {min_symbols}",
            "The source schedule must cover enough planned symbols.",
        ),
        dataset_check(
            build_label,
            created_at,
            schedule_label,
            "dataset",
            "dataset row count",
            CHECK_PASS if row_count == planned_item_count and row_count >= min_dataset_rows else CHECK_FAIL,
            row_count,
            f"== {planned_item_count} and >= {min_dataset_rows}",
            "Dataset row count must match planned schedule item count.",
        ),
        dataset_check(
            build_label,
            created_at,
            schedule_label,
            "dataset",
            "required row fields",
            CHECK_PASS if required_rows_ok == row_count and row_count > 0 else CHECK_FAIL,
            required_rows_ok,
            row_count,
            "Every dataset row must contain all required fields.",
        ),
        dataset_check(
            build_label,
            created_at,
            schedule_label,
            "dataset",
            "pending outcome labels",
            CHECK_PASS if pending_outcomes == row_count and row_count > 0 else CHECK_FAIL,
            pending_outcomes,
            row_count,
            "All new outcome dataset rows should be pending paper observation.",
        ),
        dataset_check(
            build_label,
            created_at,
            schedule_label,
            "dataset",
            "training eligibility disabled",
            CHECK_PASS if training_disabled == row_count and row_count > 0 else CHECK_FAIL,
            training_disabled,
            row_count,
            "Rows built from scheduled paper items are not training-eligible until outcomes are collected.",
        ),
        dataset_check(
            build_label,
            created_at,
            schedule_label,
            "lineage",
            "source lineage completeness",
            CHECK_PASS if lineage_complete_count == row_count and row_count > 0 else CHECK_FAIL,
            lineage_complete_count,
            row_count,
            "Every row must preserve schedule, guard, learning, multi-cycle, session, and portfolio lineage.",
        ),
    ]


def decide_outcome(schedule: sqlite3.Row | None, checks: list[dict[str, Any]]) -> tuple[str, str, str, str, str, str]:
    if schedule is None:
        return (
            DECISION_REJECT_MISSING,
            VERDICT_MISSING,
            ACTION_REFRESH,
            "Mission 72 AI Paper Dataset Expansion Scheduler",
            BUILD_STATE_MISSING,
            "AI paper dataset expansion schedule evidence is missing.",
        )

    failed = [check for check in checks if check["check_status"] == CHECK_FAIL]

    if any(check["check_category"] == "safety" for check in failed):
        return (
            DECISION_BLOCK_SAFETY,
            VERDICT_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 73 safety remediation",
            BUILD_STATE_BLOCKED,
            "Safety invariant failed during AI outcome dataset building.",
        )

    if failed:
        return (
            DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 72 AI Paper Dataset Expansion Scheduler",
            BUILD_STATE_UNSTABLE,
            "AI outcome dataset build failed one or more quality checks.",
        )

    return (
        DECISION_READY,
        VERDICT_READY,
        ACTION_READY,
        NEXT_READY,
        BUILD_STATE_READY,
        "AI outcome dataset build is ready for feature store handoff. No autonomous trading is approved.",
    )


def build_handoff(
    build_label: str,
    created_at: str,
    schedule_label: str,
    row_count: int,
    training_eligible_count: int,
    decision: str,
) -> dict[str, Any]:
    status = HANDOFF_STATUS_READY if decision == DECISION_READY else "AI_OUTCOME_DATASET_HANDOFF_NOT_READY"

    return {
        "handoff_id": f"{build_label}-feature-store-handoff",
        "build_label": build_label,
        "created_at": created_at,
        "source_schedule_label": schedule_label,
        "target_mission": NEXT_READY,
        "handoff_status": status,
        "dataset_row_count": row_count,
        "training_eligible_count": training_eligible_count,
        "handoff_reason": "Dataset rows are pending paper outcomes and ready for feature-store registration handoff.",
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "dataset_builder_role": "FEATURE_STORE_HANDOFF_RECORD_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
            "autonomous_trading_enabled": False,
            "automatic_strategy_reweighting_enabled": False,
        },
    }


def build_summary(
    db_path: str | Path,
    build_label: str,
    report_label: str,
    created_at: str,
    schedule_label: str,
    schedule: sqlite3.Row | None,
    rows: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    handoff: dict[str, Any],
    decision: str,
    verdict: str,
    action: str,
    next_mission: str,
    state: str,
    reason: str,
) -> dict[str, Any]:
    pass_count = sum(1 for check in checks if check["check_status"] == CHECK_PASS)
    fail_count = sum(1 for check in checks if check["check_status"] == CHECK_FAIL)
    pending_count = sum(1 for row in rows if row["outcome_label"] == OUTCOME_LABEL_PENDING)
    training_count = sum(1 for row in rows if safe_int(row["training_eligible"]) != 0)
    lineage_count = sum(1 for row in rows if lineage_complete(row))

    return {
        "build_label": build_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_schedule_label": schedule_label,
        "source_guard_review_label": row_get(schedule, "source_guard_review_label", None),
        "source_learning_run_label": row_get(schedule, "source_learning_run_label", None),
        "source_multi_cycle_track_label": row_get(schedule, "source_multi_cycle_track_label", None),
        "source_session_label": row_get(schedule, "source_session_label", None),
        "source_portfolio_label": row_get(schedule, "source_portfolio_label", None),
        "planned_cycle_count": safe_int(row_get(schedule, "planned_cycle_count", 0)),
        "planned_symbol_count": safe_int(row_get(schedule, "planned_symbol_count", 0)),
        "planned_item_count": safe_int(row_get(schedule, "planned_item_count", 0)),
        "dataset_row_count": len(rows),
        "pending_outcome_count": pending_count,
        "training_eligible_count": training_count,
        "lineage_complete_count": lineage_count,
        "learning_score": round8(safe_float(row_get(schedule, "learning_score", 0.0))),
        "max_feature_drift": round8(safe_float(row_get(schedule, "max_feature_drift", 0.0))),
        "quality_check_count": len(checks),
        "pass_check_count": pass_count,
        "fail_check_count": fail_count,
        "safety_breach_count": safe_int(row_get(schedule, "safety_breach_count", 0)),
        "dataset_rows": rows,
        "quality_checks": checks,
        "handoff": handoff,
        "build_state": state,
        "build_decision": decision,
        "global_verdict": verdict,
        "recommended_action": action,
        "next_mission": next_mission,
        "decision_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    row_lines = []
    for row in summary["dataset_rows"]:
        row_lines.append(
            "- "
            + f"row={row['row_index']}, "
            + f"cycle={row['planned_cycle_index']}, "
            + f"symbol={row['planned_symbol']}, "
            + f"outcome={row['outcome_label']}, "
            + f"training_eligible={row['training_eligible']}"
        )

    check_lines = []
    for check in summary["quality_checks"]:
        check_lines.append(
            "- "
            + f"{check['check_category']} / {check['check_name']}: "
            + f"status={check['check_status']}, "
            + f"observed={check['observed_value']}, "
            + f"threshold={check['threshold_value']}"
        )

    rows_markdown = "\n".join(row_lines) or "- None"
    checks_markdown = "\n".join(check_lines) or "- None"

    return f"""# DeltaGrid Mission 73 AI Outcome Dataset Builder Pack Report

Report label: {summary['report_label']}
Build label: {summary['build_label']}
Created at: {summary['created_at']}
Source schedule label: {summary['source_schedule_label']}
Source guard review label: {summary['source_guard_review_label']}
Source learning run label: {summary['source_learning_run_label']}
Source multi-cycle track label: {summary['source_multi_cycle_track_label']}
Source session label: {summary['source_session_label']}
Source portfolio label: {summary['source_portfolio_label']}

## Dataset Build Summary

Planned cycle count: {summary['planned_cycle_count']}
Planned symbol count: {summary['planned_symbol_count']}
Planned item count: {summary['planned_item_count']}
Dataset row count: {summary['dataset_row_count']}
Pending outcome count: {summary['pending_outcome_count']}
Training eligible count: {summary['training_eligible_count']}
Lineage complete count: {summary['lineage_complete_count']}

Learning score: {summary['learning_score']}
Max feature drift: {summary['max_feature_drift']}

Quality check count: {summary['quality_check_count']}
Pass check count: {summary['pass_check_count']}
Fail check count: {summary['fail_check_count']}
Safety breach count: {summary['safety_breach_count']}

## Dataset Rows

{rows_markdown}

## Quality Checks

{checks_markdown}

## Handoff

Handoff status: {summary['handoff']['handoff_status']}
Target mission: {summary['handoff']['target_mission']}
Handoff reason: {summary['handoff']['handoff_reason']}

## Decision

Build state: {summary['build_state']}
Build decision: {summary['build_decision']}
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

This builder creates paper-only AI outcome dataset rows.
Rows are not training-eligible until paper outcomes are collected.
This builder does not perform autonomous trading.
This builder does not adjust strategy weights automatically.
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


def persist_build(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for row in summary["dataset_rows"]:
            stored = dict(row)
            stored["feature_snapshot_json"] = json.dumps(stored.pop("feature_snapshot"), sort_keys=True)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                ROWS_TABLE,
                stored,
                [
                    "dataset_row_id",
                    "build_label",
                    "created_at",
                    "source_schedule_label",
                    "source_schedule_item_id",
                    "source_guard_review_label",
                    "source_learning_run_label",
                    "source_multi_cycle_track_label",
                    "source_session_label",
                    "source_portfolio_label",
                    "row_index",
                    "planned_cycle_index",
                    "planned_symbol",
                    "planned_start_at",
                    "planned_end_at",
                    "outcome_label",
                    "target_label",
                    "training_eligible",
                    "row_status",
                    "feature_snapshot_json",
                    "live_trading",
                    "live_order_sent",
                    "capital_deployment",
                    "metadata_json",
                ],
            )

        for check in summary["quality_checks"]:
            stored_check = dict(check)
            stored_check["metadata_json"] = json.dumps(stored_check.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                QUALITY_CHECKS_TABLE,
                stored_check,
                [
                    "check_id",
                    "build_label",
                    "created_at",
                    "source_schedule_label",
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

        handoff = dict(summary["handoff"])
        handoff["metadata_json"] = json.dumps(handoff.pop("metadata"), sort_keys=True)
        insert_row(
            conn,
            HANDOFFS_TABLE,
            handoff,
            [
                "handoff_id",
                "build_label",
                "created_at",
                "source_schedule_label",
                "target_mission",
                "handoff_status",
                "dataset_row_count",
                "training_eligible_count",
                "handoff_reason",
                "live_trading",
                "live_order_sent",
                "capital_deployment",
                "metadata_json",
            ],
        )

        build_row = {
            "build_label": summary["build_label"],
            "report_label": summary["report_label"],
            "created_at": summary["created_at"],
            "source_schedule_label": summary["source_schedule_label"],
            "source_guard_review_label": summary["source_guard_review_label"],
            "source_learning_run_label": summary["source_learning_run_label"],
            "source_multi_cycle_track_label": summary["source_multi_cycle_track_label"],
            "source_session_label": summary["source_session_label"],
            "source_portfolio_label": summary["source_portfolio_label"],
            "planned_cycle_count": summary["planned_cycle_count"],
            "planned_symbol_count": summary["planned_symbol_count"],
            "planned_item_count": summary["planned_item_count"],
            "dataset_row_count": summary["dataset_row_count"],
            "pending_outcome_count": summary["pending_outcome_count"],
            "training_eligible_count": summary["training_eligible_count"],
            "lineage_complete_count": summary["lineage_complete_count"],
            "quality_check_count": summary["quality_check_count"],
            "pass_check_count": summary["pass_check_count"],
            "fail_check_count": summary["fail_check_count"],
            "safety_breach_count": summary["safety_breach_count"],
            "learning_score": str(summary["learning_score"]),
            "max_feature_drift": str(summary["max_feature_drift"]),
            "build_state": summary["build_state"],
            "build_decision": summary["build_decision"],
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
            BUILDS_TABLE,
            build_row,
            [
                "build_label",
                "report_label",
                "created_at",
                "source_schedule_label",
                "source_guard_review_label",
                "source_learning_run_label",
                "source_multi_cycle_track_label",
                "source_session_label",
                "source_portfolio_label",
                "planned_cycle_count",
                "planned_symbol_count",
                "planned_item_count",
                "dataset_row_count",
                "pending_outcome_count",
                "training_eligible_count",
                "lineage_complete_count",
                "quality_check_count",
                "pass_check_count",
                "fail_check_count",
                "safety_breach_count",
                "learning_score",
                "max_feature_drift",
                "build_state",
                "build_decision",
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
            "build_label": summary["build_label"],
            "created_at": summary["created_at"],
            "source_schedule_label": summary["source_schedule_label"],
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
                "build_label",
                "created_at",
                "source_schedule_label",
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


def run_ai_outcome_dataset_builder(
    db_path: str | Path = "offchain/deltagrid.db",
    build_label: str | None = None,
    report_label: str | None = None,
    schedule_label: str = "mission72-final-check",
    min_dataset_rows: int = 4,
    min_planned_cycles: int = 2,
    min_symbols: int = 2,
) -> dict[str, Any]:
    if min_dataset_rows <= 0:
        raise ValueError("min_dataset_rows must be positive")

    if min_planned_cycles <= 0:
        raise ValueError("min_planned_cycles must be positive")

    if min_symbols <= 0:
        raise ValueError("min_symbols must be positive")

    db = Path(db_path)
    build = build_label or new_build_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    source_schedule_label = parse_labels(schedule_label)[0]

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        schedule = load_schedule(conn, source_schedule_label)
        items = load_schedule_items(conn, source_schedule_label)
        expansion_checks = load_expansion_checks(conn, source_schedule_label)

    if schedule is None:
        rows: list[dict[str, Any]] = []
        checks = build_missing_checks(build, created_at, source_schedule_label)
    else:
        rows = build_dataset_rows(build, created_at, schedule, items)
        checks = build_quality_checks(
            build_label=build,
            created_at=created_at,
            schedule_label=source_schedule_label,
            schedule=schedule,
            items=items,
            expansion_checks=expansion_checks,
            rows=rows,
            min_dataset_rows=min_dataset_rows,
            min_planned_cycles=min_planned_cycles,
            min_symbols=min_symbols,
        )

    decision, verdict, action, next_mission, state, reason = decide_outcome(schedule, checks)

    handoff = build_handoff(
        build_label=build,
        created_at=created_at,
        schedule_label=source_schedule_label,
        row_count=len(rows),
        training_eligible_count=sum(1 for row in rows if safe_int(row["training_eligible"]) != 0),
        decision=decision,
    )

    summary = build_summary(
        db_path=db,
        build_label=build,
        report_label=report,
        created_at=created_at,
        schedule_label=source_schedule_label,
        schedule=schedule,
        rows=rows,
        checks=checks,
        handoff=handoff,
        decision=decision,
        verdict=verdict,
        action=action,
        next_mission=next_mission,
        state=state,
        reason=reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_build(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid AI outcome dataset builder pack.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--build-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--schedule-label", default="mission72-final-check")
    parser.add_argument("--min-dataset-rows", type=int, default=4)
    parser.add_argument("--min-planned-cycles", type=int, default=2)
    parser.add_argument("--min-symbols", type=int, default=2)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_ai_outcome_dataset_builder(
        db_path=args.db,
        build_label=args.build_label,
        report_label=args.report_label,
        schedule_label=args.schedule_label,
        min_dataset_rows=args.min_dataset_rows,
        min_planned_cycles=args.min_planned_cycles,
        min_symbols=args.min_symbols,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

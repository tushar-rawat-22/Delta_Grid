"""
Mission 72: AI Paper Dataset Expansion Scheduler.

This module creates a controlled paper-only schedule for AI dataset expansion
after the AI Feature Quality and Drift Guard approves expansion.

It reads:
- ai_feature_quality_drift_guard_reviews
- ai_feature_quality_drift_guard_checks
- ai_feature_quality_drift_guard_feature_drifts

It writes:
- ai_paper_dataset_expansion_schedules
- ai_paper_dataset_expansion_schedule_items
- ai_paper_dataset_expansion_checks
- ai_paper_dataset_expansion_reports

It is a paper dataset planning layer only.

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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


GUARD_REVIEWS_TABLE = "ai_feature_quality_drift_guard_reviews"
GUARD_CHECKS_TABLE = "ai_feature_quality_drift_guard_checks"
GUARD_DRIFTS_TABLE = "ai_feature_quality_drift_guard_feature_drifts"

SCHEDULES_TABLE = "ai_paper_dataset_expansion_schedules"
ITEMS_TABLE = "ai_paper_dataset_expansion_schedule_items"
CHECKS_TABLE = "ai_paper_dataset_expansion_checks"
REPORTS_TABLE = "ai_paper_dataset_expansion_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

GUARD_DECISION_APPROVED = "AI_FEATURE_QUALITY_DRIFT_GUARD_APPROVED_FOR_DATASET_EXPANSION"
GUARD_VERDICT_READY = "AI_FEATURE_QUALITY_DRIFT_GUARD_READY_SHADOW_ONLY"
GUARD_STATE_READY = "AI_FEATURE_QUALITY_STATE_READY"
DRIFT_STATUS_WITHIN_LIMIT = "AI_FEATURE_DRIFT_WITHIN_LIMIT"
DRIFT_STATUS_BASELINE_UNAVAILABLE = "AI_FEATURE_DRIFT_BASELINE_UNAVAILABLE"

CHECK_PASS = "AI_DATASET_EXPANSION_CHECK_PASS"
CHECK_FAIL = "AI_DATASET_EXPANSION_CHECK_FAIL"

SCHEDULE_STATE_READY = "AI_DATASET_EXPANSION_SCHEDULE_READY"
SCHEDULE_STATE_UNSTABLE = "AI_DATASET_EXPANSION_SCHEDULE_UNSTABLE"
SCHEDULE_STATE_BLOCKED = "AI_DATASET_EXPANSION_SCHEDULE_BLOCKED"
SCHEDULE_STATE_MISSING = "AI_DATASET_EXPANSION_SCHEDULE_MISSING"

DECISION_READY = "AI_DATASET_EXPANSION_SCHEDULE_APPROVED_PAPER_ONLY"
DECISION_UNSTABLE = "AI_DATASET_EXPANSION_SCHEDULE_UNSTABLE_REVIEW_REQUIRED"
DECISION_BLOCK_SAFETY = "AI_DATASET_EXPANSION_SCHEDULE_BLOCKED_BY_SAFETY_POLICY"
DECISION_REJECT_MISSING = "AI_DATASET_EXPANSION_SCHEDULE_REJECTED_MISSING_EVIDENCE"

VERDICT_READY = "AI_DATASET_EXPANSION_SCHEDULE_READY_SHADOW_ONLY"
VERDICT_UNSTABLE = "AI_DATASET_EXPANSION_SCHEDULE_UNSTABLE_SHADOW_ONLY"
VERDICT_BLOCKED = "AI_DATASET_EXPANSION_SCHEDULE_BLOCKED_SHADOW_ONLY"
VERDICT_MISSING = "AI_DATASET_EXPANSION_SCHEDULE_MISSING_EVIDENCE"

ACTION_READY = "RUN_SCHEDULED_PAPER_DATASET_COLLECTION_ONLY"
ACTION_REVIEW_UNSTABLE = "REVIEW_AI_FEATURE_GUARD_BEFORE_DATASET_EXPANSION"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_DATASET_EXPANSION_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_AI_FEATURE_QUALITY_DRIFT_GUARD_EVIDENCE"

NEXT_READY = "Mission 73 AI Outcome Dataset Builder"

ITEM_STATUS_PLANNED = "AI_DATASET_EXPANSION_ITEM_PLANNED_PAPER_ONLY"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_utc(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc).replace(microsecond=0)

    text = value.strip()

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    parsed = datetime.fromisoformat(text)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def new_schedule_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission72-ai-dataset-expansion-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission72-ai-dataset-expansion-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
        return ["mission71-final-check"]

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    labels: list[str] = []

    for item in raw_items:
        label = str(item).strip()

        if not label:
            continue

        if any(ch.isspace() for ch in label):
            raise ValueError(f"Invalid guard review label: {label}")

        if label not in labels:
            labels.append(label)

    if not labels:
        raise ValueError("At least one guard review label is required")

    return labels


def parse_symbols(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return ["BTCUSDT", "ETHUSDT"]

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    symbols: list[str] = []

    for item in raw_items:
        symbol = str(item).strip().upper()

        if not symbol:
            continue

        if not symbol.endswith("USDT"):
            raise ValueError(f"Only USDT symbols are supported for paper dataset expansion: {symbol}")

        if not symbol.replace("_", "").isalnum():
            raise ValueError(f"Invalid symbol: {symbol}")

        if symbol not in symbols:
            symbols.append(symbol)

    if not symbols:
        raise ValueError("At least one symbol is required")

    return symbols


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
            CREATE TABLE IF NOT EXISTS ai_paper_dataset_expansion_schedules (
                schedule_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_guard_review_label TEXT NOT NULL,
                source_learning_run_label TEXT,
                source_multi_cycle_track_label TEXT,
                source_session_label TEXT,
                source_portfolio_label TEXT,
                planned_cycle_count INTEGER NOT NULL,
                planned_symbol_count INTEGER NOT NULL,
                planned_item_count INTEGER NOT NULL,
                schedule_start_at TEXT NOT NULL,
                schedule_end_at TEXT NOT NULL,
                schedule_interval_hours INTEGER NOT NULL,
                min_required_prior_cycles INTEGER NOT NULL,
                current_cycle_count INTEGER NOT NULL,
                target_total_cycles INTEGER NOT NULL,
                max_feature_drift TEXT NOT NULL,
                learning_score TEXT NOT NULL,
                guard_quality_check_count INTEGER NOT NULL,
                guard_pass_check_count INTEGER NOT NULL,
                guard_fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                expansion_check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                schedule_state TEXT NOT NULL,
                schedule_decision TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_paper_dataset_expansion_schedule_items (
                item_id TEXT PRIMARY KEY,
                schedule_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_guard_review_label TEXT NOT NULL,
                item_index INTEGER NOT NULL,
                planned_cycle_index INTEGER NOT NULL,
                planned_symbol TEXT NOT NULL,
                planned_start_at TEXT NOT NULL,
                planned_end_at TEXT NOT NULL,
                item_status TEXT NOT NULL,
                collection_scope TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_paper_dataset_expansion_checks (
                check_id TEXT PRIMARY KEY,
                schedule_label TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_paper_dataset_expansion_reports (
                report_label TEXT PRIMARY KEY,
                schedule_label TEXT NOT NULL,
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
        FROM ai_feature_quality_drift_guard_reviews
        WHERE review_label = ?
        """,
        (review_label,),
    ).fetchone()


def load_guard_checks(conn: sqlite3.Connection, review_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, GUARD_CHECKS_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM ai_feature_quality_drift_guard_checks
        WHERE review_label = ?
        ORDER BY created_at ASC, check_id ASC
        """,
        (review_label,),
    ).fetchall()


def load_guard_drifts(conn: sqlite3.Connection, review_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, GUARD_DRIFTS_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM ai_feature_quality_drift_guard_feature_drifts
        WHERE review_label = ?
        ORDER BY feature_group ASC, feature_name ASC
        """,
        (review_label,),
    ).fetchall()


def expansion_check(
    schedule_label: str,
    created_at: str,
    guard_review_label: str,
    category: str,
    name: str,
    status: str,
    observed_value: Any,
    threshold_value: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{schedule_label}-{category}-{name}".replace(" ", "_"),
        "schedule_label": schedule_label,
        "created_at": created_at,
        "source_guard_review_label": guard_review_label,
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
            "dataset_expansion_role": "PAPER_DATASET_EXPANSION_CHECK_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
            "autonomous_trading_enabled": False,
            "automatic_strategy_reweighting_enabled": False,
        },
    }


def build_missing_checks(schedule_label: str, created_at: str, guard_review_label: str) -> list[dict[str, Any]]:
    return [
        expansion_check(
            schedule_label,
            created_at,
            guard_review_label,
            "availability",
            "guard review exists",
            CHECK_FAIL,
            "missing",
            "ai_feature_quality_drift_guard_reviews record",
            "No AI feature quality drift guard review exists for this label.",
        )
    ]


def build_schedule_items(
    schedule_label: str,
    created_at: str,
    guard_review_label: str,
    symbols: list[str],
    planned_cycle_count: int,
    schedule_start_at: datetime,
    interval_hours: int,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    item_index = 1

    for cycle_index in range(1, planned_cycle_count + 1):
        cycle_start = schedule_start_at + timedelta(hours=(cycle_index - 1) * interval_hours)
        cycle_end = cycle_start + timedelta(hours=interval_hours)

        for symbol in symbols:
            items.append(
                {
                    "item_id": f"{schedule_label}-cycle-{cycle_index}-{symbol}".replace(" ", "_"),
                    "schedule_label": schedule_label,
                    "created_at": created_at,
                    "source_guard_review_label": guard_review_label,
                    "item_index": item_index,
                    "planned_cycle_index": cycle_index,
                    "planned_symbol": symbol,
                    "planned_start_at": cycle_start.isoformat(),
                    "planned_end_at": cycle_end.isoformat(),
                    "item_status": ITEM_STATUS_PLANNED,
                    "collection_scope": "PAPER_DATASET_COLLECTION_PLAN_ONLY",
                    "live_trading": LIVE_TRADING_STATUS,
                    "live_order_sent": LIVE_ORDER_SENT_VALUE,
                    "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                    "metadata": {
                        "dataset_expansion_role": "PAPER_DATASET_EXPANSION_ITEM_ONLY",
                        "execution_role": "NONE",
                        "private_keys_used": False,
                        "orders_sent": False,
                        "paid_api_used": False,
                        "real_capital_used": False,
                        "autonomous_trading_enabled": False,
                        "automatic_strategy_reweighting_enabled": False,
                    },
                }
            )
            item_index += 1

    return items


def build_metrics(
    guard_review: sqlite3.Row | None,
    guard_checks: list[sqlite3.Row],
    guard_drifts: list[sqlite3.Row],
    planned_cycle_count: int,
    symbols: list[str],
    schedule_start_at: datetime,
    interval_hours: int,
) -> dict[str, Any]:
    if guard_review is None:
        return {
            "source_learning_run_label": None,
            "source_multi_cycle_track_label": None,
            "source_session_label": None,
            "source_portfolio_label": None,
            "planned_cycle_count": planned_cycle_count,
            "planned_symbol_count": len(symbols),
            "planned_item_count": planned_cycle_count * len(symbols),
            "schedule_start_at": schedule_start_at.isoformat(),
            "schedule_end_at": (schedule_start_at + timedelta(hours=planned_cycle_count * interval_hours)).isoformat(),
            "schedule_interval_hours": interval_hours,
            "current_cycle_count": 0,
            "learning_score": 0.0,
            "max_feature_drift": 0.0,
            "guard_quality_check_count": 0,
            "guard_pass_check_count": 0,
            "guard_fail_check_count": 0,
            "safety_breach_count": 0,
            "guard_decision": "",
            "guard_verdict": "",
            "quality_state": "",
            "drift_status": "",
        }

    row_safety = sum(1 for row in [guard_review, *guard_checks, *guard_drifts] if safety_problem(row))
    safety_breach_count = safe_int(row_get(guard_review, "safety_breach_count", 0)) + row_safety

    return {
        "source_learning_run_label": row_get(guard_review, "source_learning_run_label", None),
        "source_multi_cycle_track_label": row_get(guard_review, "source_multi_cycle_track_label", None),
        "source_session_label": row_get(guard_review, "source_session_label", None),
        "source_portfolio_label": row_get(guard_review, "source_portfolio_label", None),
        "planned_cycle_count": planned_cycle_count,
        "planned_symbol_count": len(symbols),
        "planned_item_count": planned_cycle_count * len(symbols),
        "schedule_start_at": schedule_start_at.isoformat(),
        "schedule_end_at": (schedule_start_at + timedelta(hours=planned_cycle_count * interval_hours)).isoformat(),
        "schedule_interval_hours": interval_hours,
        "current_cycle_count": safe_int(row_get(guard_review, "cycle_count", 0)),
        "learning_score": round8(safe_float(row_get(guard_review, "learning_score", 0.0))),
        "max_feature_drift": round8(safe_float(row_get(guard_review, "max_feature_drift", 0.0))),
        "guard_quality_check_count": safe_int(row_get(guard_review, "quality_check_count", len(guard_checks))),
        "guard_pass_check_count": safe_int(row_get(guard_review, "pass_check_count", 0)),
        "guard_fail_check_count": safe_int(row_get(guard_review, "fail_check_count", 0)),
        "safety_breach_count": safety_breach_count,
        "guard_decision": str(row_get(guard_review, "guard_decision", "")),
        "guard_verdict": str(row_get(guard_review, "global_verdict", "")),
        "quality_state": str(row_get(guard_review, "quality_state", "")),
        "drift_status": str(row_get(guard_review, "drift_status", "")),
    }


def build_checks(
    schedule_label: str,
    created_at: str,
    guard_review_label: str,
    guard_review: sqlite3.Row,
    metrics: dict[str, Any],
    planned_cycle_count: int,
    min_planned_cycles: int,
    max_planned_cycles: int,
    min_symbols: int,
    target_total_cycles: int,
    max_allowed_feature_drift: float,
    min_learning_score: float,
) -> list[dict[str, Any]]:
    projected_total_cycles = safe_int(metrics["current_cycle_count"]) + planned_cycle_count

    return [
        expansion_check(
            schedule_label,
            created_at,
            guard_review_label,
            "availability",
            "guard review exists",
            CHECK_PASS,
            "present",
            "present",
            "AI feature quality drift guard review exists.",
        ),
        expansion_check(
            schedule_label,
            created_at,
            guard_review_label,
            "safety",
            "safety breach count",
            CHECK_PASS if safe_int(metrics["safety_breach_count"]) == 0 else CHECK_FAIL,
            metrics["safety_breach_count"],
            0,
            "Dataset expansion requires zero live-trading, order-transmission, and capital-deployment breaches.",
        ),
        expansion_check(
            schedule_label,
            created_at,
            guard_review_label,
            "guard",
            "guard decision approved",
            CHECK_PASS if metrics["guard_decision"] == GUARD_DECISION_APPROVED else CHECK_FAIL,
            metrics["guard_decision"],
            GUARD_DECISION_APPROVED,
            "Dataset expansion requires an approved AI feature quality guard decision.",
        ),
        expansion_check(
            schedule_label,
            created_at,
            guard_review_label,
            "guard",
            "guard verdict ready",
            CHECK_PASS if metrics["guard_verdict"] == GUARD_VERDICT_READY else CHECK_FAIL,
            metrics["guard_verdict"],
            GUARD_VERDICT_READY,
            "Dataset expansion requires a ready shadow-only guard verdict.",
        ),
        expansion_check(
            schedule_label,
            created_at,
            guard_review_label,
            "guard",
            "quality state ready",
            CHECK_PASS if metrics["quality_state"] == GUARD_STATE_READY else CHECK_FAIL,
            metrics["quality_state"],
            GUARD_STATE_READY,
            "Dataset expansion requires feature quality state to be ready.",
        ),
        expansion_check(
            schedule_label,
            created_at,
            guard_review_label,
            "guard",
            "guard failed checks",
            CHECK_PASS if safe_int(metrics["guard_fail_check_count"]) == 0 else CHECK_FAIL,
            metrics["guard_fail_check_count"],
            0,
            "Guard failed checks must remain zero.",
        ),
        expansion_check(
            schedule_label,
            created_at,
            guard_review_label,
            "drift",
            "drift status accepted",
            CHECK_PASS
            if metrics["drift_status"] in {DRIFT_STATUS_WITHIN_LIMIT, DRIFT_STATUS_BASELINE_UNAVAILABLE}
            else CHECK_FAIL,
            metrics["drift_status"],
            f"{DRIFT_STATUS_WITHIN_LIMIT} or {DRIFT_STATUS_BASELINE_UNAVAILABLE}",
            "Feature drift must be within limit or establishing an initial baseline.",
        ),
        expansion_check(
            schedule_label,
            created_at,
            guard_review_label,
            "drift",
            "max feature drift",
            CHECK_PASS if safe_float(metrics["max_feature_drift"]) <= max_allowed_feature_drift else CHECK_FAIL,
            metrics["max_feature_drift"],
            f"<= {max_allowed_feature_drift}",
            "Max feature drift must stay inside the dataset expansion threshold.",
        ),
        expansion_check(
            schedule_label,
            created_at,
            guard_review_label,
            "learning",
            "learning score",
            CHECK_PASS if safe_float(metrics["learning_score"]) >= min_learning_score else CHECK_FAIL,
            metrics["learning_score"],
            f">= {min_learning_score}",
            "Learning score must clear dataset expansion threshold.",
        ),
        expansion_check(
            schedule_label,
            created_at,
            guard_review_label,
            "schedule",
            "planned cycle count lower bound",
            CHECK_PASS if planned_cycle_count >= min_planned_cycles else CHECK_FAIL,
            planned_cycle_count,
            f">= {min_planned_cycles}",
            "The schedule must contain enough planned paper dataset cycles.",
        ),
        expansion_check(
            schedule_label,
            created_at,
            guard_review_label,
            "schedule",
            "planned cycle count upper bound",
            CHECK_PASS if planned_cycle_count <= max_planned_cycles else CHECK_FAIL,
            planned_cycle_count,
            f"<= {max_planned_cycles}",
            "The schedule must not over-expand the dataset too quickly.",
        ),
        expansion_check(
            schedule_label,
            created_at,
            guard_review_label,
            "schedule",
            "planned symbol count",
            CHECK_PASS if safe_int(metrics["planned_symbol_count"]) >= min_symbols else CHECK_FAIL,
            metrics["planned_symbol_count"],
            f">= {min_symbols}",
            "Dataset expansion must cover enough paper symbols.",
        ),
        expansion_check(
            schedule_label,
            created_at,
            guard_review_label,
            "schedule",
            "target total cycles",
            CHECK_PASS if projected_total_cycles >= target_total_cycles else CHECK_FAIL,
            projected_total_cycles,
            f">= {target_total_cycles}",
            "Projected total cycles should reach the next AI dataset sufficiency target.",
        ),
    ]


def decide_schedule_outcome(
    guard_review: sqlite3.Row | None,
    checks: list[dict[str, Any]],
) -> tuple[str, str, str, str, str, str]:
    if guard_review is None:
        return (
            DECISION_REJECT_MISSING,
            VERDICT_MISSING,
            ACTION_REFRESH,
            "Mission 71 AI Feature Quality and Drift Guard",
            SCHEDULE_STATE_MISSING,
            "AI feature quality drift guard evidence is missing.",
        )

    failed = [check for check in checks if check["check_status"] == CHECK_FAIL]

    if any(check["check_category"] == "safety" for check in failed):
        return (
            DECISION_BLOCK_SAFETY,
            VERDICT_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 72 safety remediation",
            SCHEDULE_STATE_BLOCKED,
            "Safety invariant failed during AI paper dataset expansion scheduling.",
        )

    if failed:
        return (
            DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 71 AI Feature Quality and Drift Guard",
            SCHEDULE_STATE_UNSTABLE,
            "AI paper dataset expansion schedule failed one or more readiness checks.",
        )

    return (
        DECISION_READY,
        VERDICT_READY,
        ACTION_READY,
        NEXT_READY,
        SCHEDULE_STATE_READY,
        "AI paper dataset expansion schedule is approved for paper-only collection planning. No autonomous trading is approved.",
    )


def build_summary(
    db_path: str | Path,
    schedule_label: str,
    report_label: str,
    created_at: str,
    guard_review_label: str,
    symbols: list[str],
    metrics: dict[str, Any],
    checks: list[dict[str, Any]],
    items: list[dict[str, Any]],
    decision: str,
    verdict: str,
    action: str,
    next_mission: str,
    state: str,
    reason: str,
    min_required_prior_cycles: int,
    target_total_cycles: int,
) -> dict[str, Any]:
    pass_count = sum(1 for check in checks if check["check_status"] == CHECK_PASS)
    fail_count = sum(1 for check in checks if check["check_status"] == CHECK_FAIL)

    return {
        "schedule_label": schedule_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_guard_review_label": guard_review_label,
        "source_learning_run_label": metrics.get("source_learning_run_label"),
        "source_multi_cycle_track_label": metrics.get("source_multi_cycle_track_label"),
        "source_session_label": metrics.get("source_session_label"),
        "source_portfolio_label": metrics.get("source_portfolio_label"),
        "planned_symbols": symbols,
        "planned_cycle_count": safe_int(metrics.get("planned_cycle_count", 0)),
        "planned_symbol_count": safe_int(metrics.get("planned_symbol_count", 0)),
        "planned_item_count": safe_int(metrics.get("planned_item_count", 0)),
        "schedule_start_at": metrics.get("schedule_start_at"),
        "schedule_end_at": metrics.get("schedule_end_at"),
        "schedule_interval_hours": safe_int(metrics.get("schedule_interval_hours", 0)),
        "min_required_prior_cycles": min_required_prior_cycles,
        "current_cycle_count": safe_int(metrics.get("current_cycle_count", 0)),
        "target_total_cycles": target_total_cycles,
        "max_feature_drift": round8(safe_float(metrics.get("max_feature_drift", 0.0))),
        "learning_score": round8(safe_float(metrics.get("learning_score", 0.0))),
        "guard_quality_check_count": safe_int(metrics.get("guard_quality_check_count", 0)),
        "guard_pass_check_count": safe_int(metrics.get("guard_pass_check_count", 0)),
        "guard_fail_check_count": safe_int(metrics.get("guard_fail_check_count", 0)),
        "safety_breach_count": safe_int(metrics.get("safety_breach_count", 0)),
        "expansion_check_count": len(checks),
        "pass_check_count": pass_count,
        "fail_check_count": fail_count,
        "schedule_items": items,
        "expansion_checks": checks,
        "schedule_state": state,
        "schedule_decision": decision,
        "global_verdict": verdict,
        "recommended_action": action,
        "next_mission": next_mission,
        "decision_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    item_lines = []
    for item in summary["schedule_items"]:
        item_lines.append(
            "- "
            + f"cycle={item['planned_cycle_index']}, "
            + f"symbol={item['planned_symbol']}, "
            + f"start={item['planned_start_at']}, "
            + f"status={item['item_status']}"
        )

    check_lines = []
    for check in summary["expansion_checks"]:
        check_lines.append(
            "- "
            + f"{check['check_category']} / {check['check_name']}: "
            + f"status={check['check_status']}, "
            + f"observed={check['observed_value']}, "
            + f"threshold={check['threshold_value']}"
        )

    items_markdown = "\n".join(item_lines) or "- None"
    checks_markdown = "\n".join(check_lines) or "- None"

    return f"""# DeltaGrid Mission 72 AI Paper Dataset Expansion Scheduler Report

Report label: {summary['report_label']}
Schedule label: {summary['schedule_label']}
Created at: {summary['created_at']}
Source guard review label: {summary['source_guard_review_label']}
Source learning run label: {summary['source_learning_run_label']}
Source multi-cycle track label: {summary['source_multi_cycle_track_label']}
Source session label: {summary['source_session_label']}
Source portfolio label: {summary['source_portfolio_label']}

## Schedule Summary

Planned symbols: {', '.join(summary['planned_symbols'])}
Planned cycle count: {summary['planned_cycle_count']}
Planned symbol count: {summary['planned_symbol_count']}
Planned item count: {summary['planned_item_count']}
Schedule start at: {summary['schedule_start_at']}
Schedule end at: {summary['schedule_end_at']}
Schedule interval hours: {summary['schedule_interval_hours']}

Current cycle count: {summary['current_cycle_count']}
Target total cycles: {summary['target_total_cycles']}
Learning score: {summary['learning_score']}
Max feature drift: {summary['max_feature_drift']}

Guard quality check count: {summary['guard_quality_check_count']}
Guard pass check count: {summary['guard_pass_check_count']}
Guard fail check count: {summary['guard_fail_check_count']}
Safety breach count: {summary['safety_breach_count']}

Expansion check count: {summary['expansion_check_count']}
Pass check count: {summary['pass_check_count']}
Fail check count: {summary['fail_check_count']}

## Planned Items

{items_markdown}

## Checks

{checks_markdown}

## Decision

Schedule state: {summary['schedule_state']}
Schedule decision: {summary['schedule_decision']}
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

This scheduler creates paper dataset collection plans only.
This scheduler does not perform autonomous trading.
This scheduler does not adjust strategy weights automatically.
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


def persist_schedule(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for item in summary["schedule_items"]:
            row = dict(item)
            row["metadata_json"] = json.dumps(row.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                ITEMS_TABLE,
                row,
                [
                    "item_id",
                    "schedule_label",
                    "created_at",
                    "source_guard_review_label",
                    "item_index",
                    "planned_cycle_index",
                    "planned_symbol",
                    "planned_start_at",
                    "planned_end_at",
                    "item_status",
                    "collection_scope",
                    "live_trading",
                    "live_order_sent",
                    "capital_deployment",
                    "metadata_json",
                ],
            )

        for check in summary["expansion_checks"]:
            row = dict(check)
            row["metadata_json"] = json.dumps(row.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                CHECKS_TABLE,
                row,
                [
                    "check_id",
                    "schedule_label",
                    "created_at",
                    "source_guard_review_label",
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

        schedule_row = {
            "schedule_label": summary["schedule_label"],
            "report_label": summary["report_label"],
            "created_at": summary["created_at"],
            "source_guard_review_label": summary["source_guard_review_label"],
            "source_learning_run_label": summary["source_learning_run_label"],
            "source_multi_cycle_track_label": summary["source_multi_cycle_track_label"],
            "source_session_label": summary["source_session_label"],
            "source_portfolio_label": summary["source_portfolio_label"],
            "planned_cycle_count": summary["planned_cycle_count"],
            "planned_symbol_count": summary["planned_symbol_count"],
            "planned_item_count": summary["planned_item_count"],
            "schedule_start_at": summary["schedule_start_at"],
            "schedule_end_at": summary["schedule_end_at"],
            "schedule_interval_hours": summary["schedule_interval_hours"],
            "min_required_prior_cycles": summary["min_required_prior_cycles"],
            "current_cycle_count": summary["current_cycle_count"],
            "target_total_cycles": summary["target_total_cycles"],
            "max_feature_drift": str(summary["max_feature_drift"]),
            "learning_score": str(summary["learning_score"]),
            "guard_quality_check_count": summary["guard_quality_check_count"],
            "guard_pass_check_count": summary["guard_pass_check_count"],
            "guard_fail_check_count": summary["guard_fail_check_count"],
            "safety_breach_count": summary["safety_breach_count"],
            "expansion_check_count": summary["expansion_check_count"],
            "pass_check_count": summary["pass_check_count"],
            "fail_check_count": summary["fail_check_count"],
            "schedule_state": summary["schedule_state"],
            "schedule_decision": summary["schedule_decision"],
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
            SCHEDULES_TABLE,
            schedule_row,
            [
                "schedule_label",
                "report_label",
                "created_at",
                "source_guard_review_label",
                "source_learning_run_label",
                "source_multi_cycle_track_label",
                "source_session_label",
                "source_portfolio_label",
                "planned_cycle_count",
                "planned_symbol_count",
                "planned_item_count",
                "schedule_start_at",
                "schedule_end_at",
                "schedule_interval_hours",
                "min_required_prior_cycles",
                "current_cycle_count",
                "target_total_cycles",
                "max_feature_drift",
                "learning_score",
                "guard_quality_check_count",
                "guard_pass_check_count",
                "guard_fail_check_count",
                "safety_breach_count",
                "expansion_check_count",
                "pass_check_count",
                "fail_check_count",
                "schedule_state",
                "schedule_decision",
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
            "schedule_label": summary["schedule_label"],
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
                "report_label",
                "schedule_label",
                "created_at",
                "source_guard_review_label",
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


def run_ai_paper_dataset_expansion_scheduler(
    db_path: str | Path = "offchain/deltagrid.db",
    schedule_label: str | None = None,
    report_label: str | None = None,
    guard_review_label: str = "mission71-final-check",
    symbols: str | list[str] | tuple[str, ...] | None = None,
    planned_cycle_count: int = 2,
    min_planned_cycles: int = 2,
    max_planned_cycles: int = 6,
    min_symbols: int = 2,
    min_required_prior_cycles: int = 1,
    target_total_cycles: int = 3,
    schedule_interval_hours: int = 24,
    schedule_start_at: str | None = None,
    max_allowed_feature_drift: float = 0.10,
    min_learning_score: float = 70.0,
) -> dict[str, Any]:
    if planned_cycle_count <= 0:
        raise ValueError("planned_cycle_count must be positive")

    if min_planned_cycles <= 0:
        raise ValueError("min_planned_cycles must be positive")

    if max_planned_cycles < min_planned_cycles:
        raise ValueError("max_planned_cycles cannot be below min_planned_cycles")

    if min_symbols <= 0:
        raise ValueError("min_symbols must be positive")

    if min_required_prior_cycles < 0:
        raise ValueError("min_required_prior_cycles cannot be negative")

    if target_total_cycles <= 0:
        raise ValueError("target_total_cycles must be positive")

    if schedule_interval_hours <= 0:
        raise ValueError("schedule_interval_hours must be positive")

    if max_allowed_feature_drift < 0:
        raise ValueError("max_allowed_feature_drift cannot be negative")

    if min_learning_score < 0:
        raise ValueError("min_learning_score cannot be negative")

    db = Path(db_path)
    schedule = schedule_label or new_schedule_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    source_guard_label = parse_labels(guard_review_label)[0]
    parsed_symbols = parse_symbols(symbols)
    start_at = parse_utc(schedule_start_at)

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        guard_review = load_guard_review(conn, source_guard_label)
        guard_checks = load_guard_checks(conn, source_guard_label)
        guard_drifts = load_guard_drifts(conn, source_guard_label)

    metrics = build_metrics(
        guard_review=guard_review,
        guard_checks=guard_checks,
        guard_drifts=guard_drifts,
        planned_cycle_count=planned_cycle_count,
        symbols=parsed_symbols,
        schedule_start_at=start_at,
        interval_hours=schedule_interval_hours,
    )

    items = build_schedule_items(
        schedule_label=schedule,
        created_at=created_at,
        guard_review_label=source_guard_label,
        symbols=parsed_symbols,
        planned_cycle_count=planned_cycle_count,
        schedule_start_at=start_at,
        interval_hours=schedule_interval_hours,
    )

    if guard_review is None:
        checks = build_missing_checks(schedule, created_at, source_guard_label)
    else:
        checks = build_checks(
            schedule_label=schedule,
            created_at=created_at,
            guard_review_label=source_guard_label,
            guard_review=guard_review,
            metrics=metrics,
            planned_cycle_count=planned_cycle_count,
            min_planned_cycles=min_planned_cycles,
            max_planned_cycles=max_planned_cycles,
            min_symbols=min_symbols,
            target_total_cycles=target_total_cycles,
            max_allowed_feature_drift=max_allowed_feature_drift,
            min_learning_score=min_learning_score,
        )

        if safe_int(metrics["current_cycle_count"]) < min_required_prior_cycles:
            checks.append(
                expansion_check(
                    schedule,
                    created_at,
                    source_guard_label,
                    "history",
                    "minimum prior cycle count",
                    CHECK_FAIL,
                    metrics["current_cycle_count"],
                    f">= {min_required_prior_cycles}",
                    "Dataset expansion requires enough prior paper cycles before scheduling.",
                )
            )

    decision, verdict, action, next_mission, state, reason = decide_schedule_outcome(guard_review, checks)

    summary = build_summary(
        db_path=db,
        schedule_label=schedule,
        report_label=report,
        created_at=created_at,
        guard_review_label=source_guard_label,
        symbols=parsed_symbols,
        metrics=metrics,
        checks=checks,
        items=items,
        decision=decision,
        verdict=verdict,
        action=action,
        next_mission=next_mission,
        state=state,
        reason=reason,
        min_required_prior_cycles=min_required_prior_cycles,
        target_total_cycles=target_total_cycles,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_schedule(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid AI paper dataset expansion scheduler.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--schedule-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--guard-review-label", default="mission71-final-check")
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT")
    parser.add_argument("--planned-cycle-count", type=int, default=2)
    parser.add_argument("--min-planned-cycles", type=int, default=2)
    parser.add_argument("--max-planned-cycles", type=int, default=6)
    parser.add_argument("--min-symbols", type=int, default=2)
    parser.add_argument("--min-required-prior-cycles", type=int, default=1)
    parser.add_argument("--target-total-cycles", type=int, default=3)
    parser.add_argument("--schedule-interval-hours", type=int, default=24)
    parser.add_argument("--schedule-start-at", default=None)
    parser.add_argument("--max-allowed-feature-drift", type=float, default=0.10)
    parser.add_argument("--min-learning-score", type=float, default=70.0)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_ai_paper_dataset_expansion_scheduler(
        db_path=args.db,
        schedule_label=args.schedule_label,
        report_label=args.report_label,
        guard_review_label=args.guard_review_label,
        symbols=args.symbols,
        planned_cycle_count=args.planned_cycle_count,
        min_planned_cycles=args.min_planned_cycles,
        max_planned_cycles=args.max_planned_cycles,
        min_symbols=args.min_symbols,
        min_required_prior_cycles=args.min_required_prior_cycles,
        target_total_cycles=args.target_total_cycles,
        schedule_interval_hours=args.schedule_interval_hours,
        schedule_start_at=args.schedule_start_at,
        max_allowed_feature_drift=args.max_allowed_feature_drift,
        min_learning_score=args.min_learning_score,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

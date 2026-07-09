"""
Mission 69: Multi-Cycle Paper Observation Tracker.

This module tracks paper-only observation results across one or more recovery
stability cycles.

It reads:
- paper_recovery_stability_reviews

It writes:
- paper_multi_cycle_observation_tracks
- paper_multi_cycle_observation_cycles
- paper_multi_cycle_observation_checks
- paper_multi_cycle_observation_reports

It is paper-only analytics.

It never:
- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RECOVERY_REVIEWS_TABLE = "paper_recovery_stability_reviews"

TRACKS_TABLE = "paper_multi_cycle_observation_tracks"
CYCLES_TABLE = "paper_multi_cycle_observation_cycles"
CHECKS_TABLE = "paper_multi_cycle_observation_checks"
REPORTS_TABLE = "paper_multi_cycle_observation_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

RECOVERY_DECISION_CONFIRMED = "PAPER_RECOVERY_STABILITY_CONFIRMED_CONTINUE_OBSERVATION"
RECOVERY_VERDICT_CONFIRMED = "PAPER_RECOVERY_STABILITY_CONFIRMED_SHADOW_ONLY"
RECOVERY_STATE_CONFIRMED = "RECOVERY_STABILITY_STATE_CONFIRMED"

CHECK_PASS = "MULTI_CYCLE_CHECK_PASS"
CHECK_FAIL = "MULTI_CYCLE_CHECK_FAIL"

EVENT_CONFIRMED = "MULTI_CYCLE_OBSERVATION_TRACK_CONFIRMED"
EVENT_UNSTABLE = "MULTI_CYCLE_OBSERVATION_TRACK_UNSTABLE"
EVENT_MISSING = "MULTI_CYCLE_OBSERVATION_TRACK_MISSING_EVIDENCE"
EVENT_SAFETY_BLOCK = "MULTI_CYCLE_OBSERVATION_TRACK_SAFETY_BLOCK"

DECISION_CONFIRMED = "MULTI_CYCLE_OBSERVATION_CONFIRMED_CONTINUE_TRACKING"
DECISION_UNSTABLE = "MULTI_CYCLE_OBSERVATION_UNSTABLE_STOP_AND_REVIEW"
DECISION_BLOCK_SAFETY = "MULTI_CYCLE_OBSERVATION_BLOCKED_BY_SAFETY_POLICY"
DECISION_REJECT_MISSING = "MULTI_CYCLE_OBSERVATION_REJECTED_MISSING_EVIDENCE"

VERDICT_CONFIRMED = "MULTI_CYCLE_OBSERVATION_TRACK_READY_SHADOW_ONLY"
VERDICT_UNSTABLE = "MULTI_CYCLE_OBSERVATION_TRACK_UNSTABLE_SHADOW_ONLY"
VERDICT_BLOCKED = "MULTI_CYCLE_OBSERVATION_TRACK_BLOCKED_SHADOW_ONLY"
VERDICT_MISSING = "MULTI_CYCLE_OBSERVATION_TRACK_MISSING_EVIDENCE"

ACTION_CONTINUE = "CONTINUE_MULTI_CYCLE_PAPER_TRACKING_AND_PREPARE_AI_DATASET"
ACTION_REVIEW_UNSTABLE = "STOP_MULTI_CYCLE_TRACKING_AND_REVIEW_STABILITY"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_MULTI_CYCLE_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_RECOVERY_STABILITY_EVIDENCE"

STATE_CONFIRMED = "MULTI_CYCLE_STATE_CONFIRMED"
STATE_UNSTABLE = "MULTI_CYCLE_STATE_UNSTABLE"
STATE_BLOCKED = "MULTI_CYCLE_STATE_BLOCKED"
STATE_MISSING = "MULTI_CYCLE_STATE_MISSING"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_track_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission69-multi-cycle-track-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission69-multi-cycle-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
        return ["mission68-final-check"]

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    labels: list[str] = []

    for item in raw_items:
        label = str(item).strip()

        if not label:
            continue

        if any(ch.isspace() for ch in label):
            raise ValueError(f"Invalid recovery review label: {label}")

        if label not in labels:
            labels.append(label)

    if not labels:
        raise ValueError("At least one recovery review label is required")

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
            CREATE TABLE IF NOT EXISTS paper_multi_cycle_observation_tracks (
                track_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                recovery_review_labels_json TEXT NOT NULL,
                source_session_label TEXT,
                source_portfolio_label TEXT,
                cycle_count INTEGER NOT NULL,
                paper_notional TEXT NOT NULL,
                cumulative_net_paper_pnl TEXT NOT NULL,
                cumulative_net_pnl_bps TEXT NOT NULL,
                average_cycle_net_pnl_bps TEXT NOT NULL,
                worst_cycle_net_pnl_bps TEXT NOT NULL,
                worst_position_loss_bps TEXT NOT NULL,
                average_fee_drag_bps TEXT NOT NULL,
                total_alert_count INTEGER NOT NULL,
                total_triggered_event_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                multi_cycle_state TEXT NOT NULL,
                multi_cycle_decision TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS paper_multi_cycle_observation_cycles (
                cycle_id TEXT PRIMARY KEY,
                track_label TEXT NOT NULL,
                cycle_index INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                source_recovery_review_label TEXT NOT NULL,
                source_kill_switch_review_label TEXT,
                source_performance_run_label TEXT,
                source_capital_review_label TEXT,
                source_session_label TEXT,
                source_portfolio_label TEXT,
                paper_notional TEXT NOT NULL,
                monitored_position_count INTEGER NOT NULL,
                net_paper_pnl TEXT NOT NULL,
                net_paper_pnl_bps TEXT NOT NULL,
                max_position_loss_bps TEXT NOT NULL,
                fee_drag_bps TEXT NOT NULL,
                alert_count INTEGER NOT NULL,
                triggered_event_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                recovery_stability_state TEXT NOT NULL,
                recovery_stability_decision TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_multi_cycle_observation_checks (
                check_id TEXT PRIMARY KEY,
                track_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS paper_multi_cycle_observation_reports (
                report_label TEXT PRIMARY KEY,
                track_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
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


def load_recovery_reviews(conn: sqlite3.Connection, labels: list[str]) -> dict[str, sqlite3.Row]:
    if not table_exists(conn, RECOVERY_REVIEWS_TABLE):
        return {}

    loaded: dict[str, sqlite3.Row] = {}

    for label in labels:
        row = conn.execute(
            """
            SELECT *
            FROM paper_recovery_stability_reviews
            WHERE review_label = ?
            """,
            (label,),
        ).fetchone()

        if row is not None:
            loaded[label] = row

    return loaded


def build_cycle(
    track_label: str,
    created_at: str,
    cycle_index: int,
    label: str,
    row: sqlite3.Row,
) -> dict[str, Any]:
    return {
        "cycle_id": f"{track_label}-cycle-{cycle_index}-{label}".replace(" ", "_"),
        "track_label": track_label,
        "cycle_index": cycle_index,
        "created_at": created_at,
        "source_recovery_review_label": label,
        "source_kill_switch_review_label": row_get(row, "source_kill_switch_review_label", None),
        "source_performance_run_label": row_get(row, "source_performance_run_label", None),
        "source_capital_review_label": row_get(row, "source_capital_review_label", None),
        "source_session_label": row_get(row, "source_session_label", None),
        "source_portfolio_label": row_get(row, "source_portfolio_label", None),
        "paper_notional": round8(safe_float(row_get(row, "paper_notional", 0.0))),
        "monitored_position_count": safe_int(row_get(row, "monitored_position_count", 0)),
        "net_paper_pnl": round8(safe_float(row_get(row, "net_paper_pnl", 0.0))),
        "net_paper_pnl_bps": round8(safe_float(row_get(row, "net_paper_pnl_bps", 0.0))),
        "max_position_loss_bps": round8(safe_float(row_get(row, "max_position_loss_bps", 0.0))),
        "fee_drag_bps": round8(safe_float(row_get(row, "fee_drag_bps", 0.0))),
        "alert_count": safe_int(row_get(row, "alert_count", 0)),
        "triggered_event_count": safe_int(row_get(row, "triggered_event_count", 0)),
        "safety_breach_count": safe_int(row_get(row, "safety_breach_count", 0)),
        "recovery_stability_state": str(row_get(row, "recovery_stability_state", "")),
        "recovery_stability_decision": str(row_get(row, "recovery_stability_decision", "")),
        "global_verdict": str(row_get(row, "global_verdict", "")),
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "multi_cycle_role": "PAPER_MULTI_CYCLE_OBSERVATION_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def build_cycles(
    track_label: str,
    created_at: str,
    requested_labels: list[str],
    loaded_reviews: dict[str, sqlite3.Row],
) -> list[dict[str, Any]]:
    cycles: list[dict[str, Any]] = []

    for index, label in enumerate(requested_labels, start=1):
        row = loaded_reviews.get(label)

        if row is None:
            continue

        cycles.append(
            build_cycle(
                track_label=track_label,
                created_at=created_at,
                cycle_index=index,
                label=label,
                row=row,
            )
        )

    return cycles


def observation_check(
    track_label: str,
    created_at: str,
    category: str,
    name: str,
    status: str,
    observed_value: Any,
    threshold_value: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{track_label}-{category}-{name}".replace(" ", "_"),
        "track_label": track_label,
        "created_at": created_at,
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
            "multi_cycle_role": "PAPER_MULTI_CYCLE_CHECK_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def build_metrics(
    requested_labels: list[str],
    cycles: list[dict[str, Any]],
    loaded_reviews: dict[str, sqlite3.Row],
) -> dict[str, Any]:
    total_paper_notional = round8(sum(safe_float(cycle["paper_notional"]) for cycle in cycles))
    cumulative_net_pnl = round8(sum(safe_float(cycle["net_paper_pnl"]) for cycle in cycles))
    cumulative_net_pnl_bps = round8((cumulative_net_pnl / total_paper_notional) * 10000.0) if total_paper_notional > 0 else 0.0

    cycle_net_bps = [safe_float(cycle["net_paper_pnl_bps"]) for cycle in cycles]
    average_cycle_bps = round8(sum(cycle_net_bps) / len(cycle_net_bps)) if cycle_net_bps else 0.0
    worst_cycle_bps = round8(min(cycle_net_bps)) if cycle_net_bps else 0.0

    position_losses = [safe_float(cycle["max_position_loss_bps"]) for cycle in cycles]
    worst_position_loss = round8(min(position_losses)) if position_losses else 0.0

    fee_drags = [safe_float(cycle["fee_drag_bps"]) for cycle in cycles]
    average_fee_drag = round8(sum(fee_drags) / len(fee_drags)) if fee_drags else 0.0

    total_alert_count = sum(safe_int(cycle["alert_count"]) for cycle in cycles)
    total_triggered_events = sum(safe_int(cycle["triggered_event_count"]) for cycle in cycles)

    row_safety = 0
    for label in requested_labels:
        row_safety += 0 if label in loaded_reviews and not safety_problem(loaded_reviews[label]) else 0

    safety_breach_count = row_safety + sum(safe_int(cycle["safety_breach_count"]) for cycle in cycles)

    source_session_label = cycles[-1]["source_session_label"] if cycles else None
    source_portfolio_label = cycles[-1]["source_portfolio_label"] if cycles else None

    return {
        "requested_cycle_count": len(requested_labels),
        "loaded_cycle_count": len(cycles),
        "missing_cycle_count": len(requested_labels) - len(cycles),
        "paper_notional": total_paper_notional,
        "cumulative_net_paper_pnl": cumulative_net_pnl,
        "cumulative_net_pnl_bps": cumulative_net_pnl_bps,
        "average_cycle_net_pnl_bps": average_cycle_bps,
        "worst_cycle_net_pnl_bps": worst_cycle_bps,
        "worst_position_loss_bps": worst_position_loss,
        "average_fee_drag_bps": average_fee_drag,
        "total_alert_count": total_alert_count,
        "total_triggered_event_count": total_triggered_events,
        "safety_breach_count": safety_breach_count,
        "source_session_label": source_session_label,
        "source_portfolio_label": source_portfolio_label,
    }


def build_checks(
    track_label: str,
    created_at: str,
    requested_labels: list[str],
    cycles: list[dict[str, Any]],
    metrics: dict[str, Any],
    min_cycles: int,
    max_allowed_cumulative_loss_bps: float,
    max_allowed_cycle_loss_bps: float,
    max_allowed_position_loss_bps: float,
    max_allowed_average_fee_drag_bps: float,
    max_allowed_triggered_events: int,
) -> list[dict[str, Any]]:
    missing_count = safe_int(metrics["missing_cycle_count"])
    cycle_count = safe_int(metrics["loaded_cycle_count"])

    confirmed_decisions = sum(
        1 for cycle in cycles if cycle["recovery_stability_decision"] == RECOVERY_DECISION_CONFIRMED
    )
    confirmed_verdicts = sum(
        1 for cycle in cycles if cycle["global_verdict"] == RECOVERY_VERDICT_CONFIRMED
    )
    confirmed_states = sum(
        1 for cycle in cycles if cycle["recovery_stability_state"] == RECOVERY_STATE_CONFIRMED
    )

    return [
        observation_check(
            track_label,
            created_at,
            "availability",
            "recovery reviews loaded",
            CHECK_PASS if missing_count == 0 else CHECK_FAIL,
            f"{cycle_count}/{len(requested_labels)}",
            f"{len(requested_labels)}/{len(requested_labels)}",
            "All requested recovery stability reviews must exist.",
        ),
        observation_check(
            track_label,
            created_at,
            "cycle",
            "minimum cycle count",
            CHECK_PASS if cycle_count >= min_cycles else CHECK_FAIL,
            cycle_count,
            f">= {min_cycles}",
            "Multi-cycle tracking requires the minimum requested cycle count.",
        ),
        observation_check(
            track_label,
            created_at,
            "recovery",
            "confirmed recovery decisions",
            CHECK_PASS if confirmed_decisions == cycle_count and cycle_count > 0 else CHECK_FAIL,
            confirmed_decisions,
            cycle_count,
            "Every tracked cycle must have a confirmed recovery stability decision.",
        ),
        observation_check(
            track_label,
            created_at,
            "recovery",
            "confirmed recovery verdicts",
            CHECK_PASS if confirmed_verdicts == cycle_count and cycle_count > 0 else CHECK_FAIL,
            confirmed_verdicts,
            cycle_count,
            "Every tracked cycle must have a confirmed recovery stability verdict.",
        ),
        observation_check(
            track_label,
            created_at,
            "recovery",
            "confirmed recovery states",
            CHECK_PASS if confirmed_states == cycle_count and cycle_count > 0 else CHECK_FAIL,
            confirmed_states,
            cycle_count,
            "Every tracked cycle must remain in a confirmed recovery stability state.",
        ),
        observation_check(
            track_label,
            created_at,
            "safety",
            "safety breach count",
            CHECK_PASS if safe_int(metrics["safety_breach_count"]) == 0 else CHECK_FAIL,
            metrics["safety_breach_count"],
            0,
            "Multi-cycle tracking requires zero live-trading, order-transmission, and capital-deployment breaches.",
        ),
        observation_check(
            track_label,
            created_at,
            "events",
            "triggered event count",
            CHECK_PASS if safe_int(metrics["total_triggered_event_count"]) <= max_allowed_triggered_events else CHECK_FAIL,
            metrics["total_triggered_event_count"],
            f"<= {max_allowed_triggered_events}",
            "Triggered recovery or kill-switch events must remain inside the multi-cycle threshold.",
        ),
        observation_check(
            track_label,
            created_at,
            "drawdown",
            "cumulative net pnl bps",
            CHECK_PASS if safe_float(metrics["cumulative_net_pnl_bps"]) >= -abs(max_allowed_cumulative_loss_bps) else CHECK_FAIL,
            metrics["cumulative_net_pnl_bps"],
            f">= {-abs(max_allowed_cumulative_loss_bps)}",
            "Cumulative paper PnL bps must remain above the multi-cycle loss threshold.",
        ),
        observation_check(
            track_label,
            created_at,
            "drawdown",
            "worst cycle net pnl bps",
            CHECK_PASS if safe_float(metrics["worst_cycle_net_pnl_bps"]) >= -abs(max_allowed_cycle_loss_bps) else CHECK_FAIL,
            metrics["worst_cycle_net_pnl_bps"],
            f">= {-abs(max_allowed_cycle_loss_bps)}",
            "Worst individual cycle paper PnL bps must remain above the cycle loss threshold.",
        ),
        observation_check(
            track_label,
            created_at,
            "drawdown",
            "worst position loss bps",
            CHECK_PASS if safe_float(metrics["worst_position_loss_bps"]) >= -abs(max_allowed_position_loss_bps) else CHECK_FAIL,
            metrics["worst_position_loss_bps"],
            f">= {-abs(max_allowed_position_loss_bps)}",
            "Worst position loss bps must remain above the multi-cycle position-loss threshold.",
        ),
        observation_check(
            track_label,
            created_at,
            "cost",
            "average fee drag bps",
            CHECK_PASS if safe_float(metrics["average_fee_drag_bps"]) <= max_allowed_average_fee_drag_bps else CHECK_FAIL,
            metrics["average_fee_drag_bps"],
            f"<= {max_allowed_average_fee_drag_bps}",
            "Average fee drag must remain inside the multi-cycle fee threshold.",
        ),
    ]


def decide_outcome(cycles: list[dict[str, Any]], checks: list[dict[str, Any]]) -> tuple[str, str, str, str, str, str]:
    failed = [check for check in checks if check["check_status"] == CHECK_FAIL]

    if not cycles:
        return (
            DECISION_REJECT_MISSING,
            VERDICT_MISSING,
            ACTION_REFRESH,
            "Mission 68 Paper Recovery Stability Monitor",
            STATE_MISSING,
            "No recovery stability cycles were available for multi-cycle tracking.",
        )

    if any(check["check_category"] == "safety" for check in failed):
        return (
            DECISION_BLOCK_SAFETY,
            VERDICT_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 69 safety remediation",
            STATE_BLOCKED,
            "Safety invariant failed during multi-cycle paper observation tracking.",
        )

    if failed:
        return (
            DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 68 Paper Recovery Stability Monitor",
            STATE_UNSTABLE,
            "Multi-cycle observation is not confirmed because one or more checks failed.",
        )

    return (
        DECISION_CONFIRMED,
        VERDICT_CONFIRMED,
        ACTION_CONTINUE,
        "Mission 70 AI Paper Outcome Learning Engine",
        STATE_CONFIRMED,
        "Multi-cycle paper observation tracking is confirmed and ready to feed AI learning datasets.",
    )


def build_summary(
    db_path: str | Path,
    track_label: str,
    report_label: str,
    created_at: str,
    requested_labels: list[str],
    cycles: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    metrics: dict[str, Any],
    decision: str,
    global_verdict: str,
    recommended_action: str,
    next_mission: str,
    state: str,
    decision_reason: str,
) -> dict[str, Any]:
    counts = Counter(check["check_status"] for check in checks)

    return {
        "track_label": track_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "recovery_review_labels": requested_labels,
        "source_session_label": metrics.get("source_session_label"),
        "source_portfolio_label": metrics.get("source_portfolio_label"),
        "cycle_count": len(cycles),
        "paper_notional": round8(safe_float(metrics.get("paper_notional", 0.0))),
        "cumulative_net_paper_pnl": round8(safe_float(metrics.get("cumulative_net_paper_pnl", 0.0))),
        "cumulative_net_pnl_bps": round8(safe_float(metrics.get("cumulative_net_pnl_bps", 0.0))),
        "average_cycle_net_pnl_bps": round8(safe_float(metrics.get("average_cycle_net_pnl_bps", 0.0))),
        "worst_cycle_net_pnl_bps": round8(safe_float(metrics.get("worst_cycle_net_pnl_bps", 0.0))),
        "worst_position_loss_bps": round8(safe_float(metrics.get("worst_position_loss_bps", 0.0))),
        "average_fee_drag_bps": round8(safe_float(metrics.get("average_fee_drag_bps", 0.0))),
        "total_alert_count": safe_int(metrics.get("total_alert_count", 0)),
        "total_triggered_event_count": safe_int(metrics.get("total_triggered_event_count", 0)),
        "safety_breach_count": safe_int(metrics.get("safety_breach_count", 0)),
        "check_count": len(checks),
        "pass_check_count": counts.get(CHECK_PASS, 0),
        "fail_check_count": counts.get(CHECK_FAIL, 0),
        "cycles": cycles,
        "multi_cycle_checks": checks,
        "multi_cycle_state": state,
        "multi_cycle_decision": decision,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
        "next_mission": next_mission,
        "decision_reason": decision_reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    cycle_lines = []
    for cycle in summary["cycles"]:
        cycle_lines.append(
            "- "
            + f"{cycle['source_recovery_review_label']}: "
            + f"net_bps={cycle['net_paper_pnl_bps']}, "
            + f"max_position_loss_bps={cycle['max_position_loss_bps']}, "
            + f"fee_drag_bps={cycle['fee_drag_bps']}"
        )

    check_lines = []
    for check in summary["multi_cycle_checks"]:
        check_lines.append(
            "- "
            + f"{check['check_category']} / {check['check_name']}: "
            + f"status={check['check_status']}, "
            + f"observed={check['observed_value']}, "
            + f"threshold={check['threshold_value']}"
        )

    cycles_markdown = "\n".join(cycle_lines) or "- None"
    checks_markdown = "\n".join(check_lines) or "- None"

    return f"""# DeltaGrid Mission 69 Multi-Cycle Paper Observation Tracker Report

Report label: {summary['report_label']}
Track label: {summary['track_label']}
Created at: {summary['created_at']}
Recovery review labels: {', '.join(summary['recovery_review_labels'])}
Source session label: {summary['source_session_label']}
Source portfolio label: {summary['source_portfolio_label']}

## Multi-Cycle Summary

Cycle count: {summary['cycle_count']}
Paper notional: {summary['paper_notional']}
Cumulative net paper PnL: {summary['cumulative_net_paper_pnl']}
Cumulative net PnL bps: {summary['cumulative_net_pnl_bps']}
Average cycle net PnL bps: {summary['average_cycle_net_pnl_bps']}
Worst cycle net PnL bps: {summary['worst_cycle_net_pnl_bps']}
Worst position loss bps: {summary['worst_position_loss_bps']}
Average fee drag bps: {summary['average_fee_drag_bps']}
Total alert count: {summary['total_alert_count']}
Total triggered event count: {summary['total_triggered_event_count']}
Safety breach count: {summary['safety_breach_count']}

Check count: {summary['check_count']}
Pass check count: {summary['pass_check_count']}
Fail check count: {summary['fail_check_count']}
Multi-cycle state: {summary['multi_cycle_state']}

## Cycles

{cycles_markdown}

## Checks

{checks_markdown}

## Decision

Multi-cycle decision: {summary['multi_cycle_decision']}
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

Multi-cycle tracking is paper-only and prepares data for AI learning without autonomous trading.
"""


def persist_track(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for cycle in summary["cycles"]:
            conn.execute(
                """
                INSERT OR REPLACE INTO paper_multi_cycle_observation_cycles (
                    cycle_id,
                    track_label,
                    cycle_index,
                    created_at,
                    source_recovery_review_label,
                    source_kill_switch_review_label,
                    source_performance_run_label,
                    source_capital_review_label,
                    source_session_label,
                    source_portfolio_label,
                    paper_notional,
                    monitored_position_count,
                    net_paper_pnl,
                    net_paper_pnl_bps,
                    max_position_loss_bps,
                    fee_drag_bps,
                    alert_count,
                    triggered_event_count,
                    safety_breach_count,
                    recovery_stability_state,
                    recovery_stability_decision,
                    global_verdict,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cycle["cycle_id"],
                    cycle["track_label"],
                    cycle["cycle_index"],
                    cycle["created_at"],
                    cycle["source_recovery_review_label"],
                    cycle["source_kill_switch_review_label"],
                    cycle["source_performance_run_label"],
                    cycle["source_capital_review_label"],
                    cycle["source_session_label"],
                    cycle["source_portfolio_label"],
                    str(cycle["paper_notional"]),
                    cycle["monitored_position_count"],
                    str(cycle["net_paper_pnl"]),
                    str(cycle["net_paper_pnl_bps"]),
                    str(cycle["max_position_loss_bps"]),
                    str(cycle["fee_drag_bps"]),
                    cycle["alert_count"],
                    cycle["triggered_event_count"],
                    cycle["safety_breach_count"],
                    cycle["recovery_stability_state"],
                    cycle["recovery_stability_decision"],
                    cycle["global_verdict"],
                    cycle["live_trading"],
                    cycle["live_order_sent"],
                    cycle["capital_deployment"],
                    json.dumps(cycle["metadata"], sort_keys=True),
                ),
            )

        for check in summary["multi_cycle_checks"]:
            conn.execute(
                """
                INSERT OR REPLACE INTO paper_multi_cycle_observation_checks (
                    check_id,
                    track_label,
                    created_at,
                    check_category,
                    check_name,
                    check_status,
                    observed_value,
                    threshold_value,
                    check_reason,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    check["check_id"],
                    check["track_label"],
                    check["created_at"],
                    check["check_category"],
                    check["check_name"],
                    check["check_status"],
                    check["observed_value"],
                    check["threshold_value"],
                    check["check_reason"],
                    check["live_trading"],
                    check["live_order_sent"],
                    check["capital_deployment"],
                    json.dumps(check["metadata"], sort_keys=True),
                ),
            )

        conn.execute(
            """
            INSERT OR REPLACE INTO paper_multi_cycle_observation_tracks (
                track_label,
                report_label,
                created_at,
                recovery_review_labels_json,
                source_session_label,
                source_portfolio_label,
                cycle_count,
                paper_notional,
                cumulative_net_paper_pnl,
                cumulative_net_pnl_bps,
                average_cycle_net_pnl_bps,
                worst_cycle_net_pnl_bps,
                worst_position_loss_bps,
                average_fee_drag_bps,
                total_alert_count,
                total_triggered_event_count,
                safety_breach_count,
                check_count,
                pass_check_count,
                fail_check_count,
                multi_cycle_state,
                multi_cycle_decision,
                global_verdict,
                recommended_action,
                next_mission,
                live_trading,
                live_order_sent,
                capital_deployment,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["track_label"],
                summary["report_label"],
                summary["created_at"],
                json.dumps(summary["recovery_review_labels"], sort_keys=True),
                summary["source_session_label"],
                summary["source_portfolio_label"],
                summary["cycle_count"],
                str(summary["paper_notional"]),
                str(summary["cumulative_net_paper_pnl"]),
                str(summary["cumulative_net_pnl_bps"]),
                str(summary["average_cycle_net_pnl_bps"]),
                str(summary["worst_cycle_net_pnl_bps"]),
                str(summary["worst_position_loss_bps"]),
                str(summary["average_fee_drag_bps"]),
                summary["total_alert_count"],
                summary["total_triggered_event_count"],
                summary["safety_breach_count"],
                summary["check_count"],
                summary["pass_check_count"],
                summary["fail_check_count"],
                summary["multi_cycle_state"],
                summary["multi_cycle_decision"],
                summary["global_verdict"],
                summary["recommended_action"],
                summary["next_mission"],
                summary["live_trading"],
                summary["live_order_sent"],
                summary["capital_deployment"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.execute(
            """
            INSERT OR REPLACE INTO paper_multi_cycle_observation_reports (
                report_label,
                track_label,
                created_at,
                global_verdict,
                recommended_action,
                report_json,
                markdown_report,
                live_trading,
                live_order_sent,
                capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["track_label"],
                summary["created_at"],
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
                LIVE_TRADING_STATUS,
                LIVE_ORDER_SENT_VALUE,
                CAPITAL_DEPLOYMENT_STATUS,
            ),
        )

        conn.commit()


def run_multi_cycle_paper_observation_tracker(
    db_path: str | Path = "offchain/deltagrid.db",
    track_label: str | None = None,
    report_label: str | None = None,
    recovery_review_labels: str | list[str] | tuple[str, ...] | None = None,
    min_cycles: int = 1,
    max_allowed_cumulative_loss_bps: float = 50.0,
    max_allowed_cycle_loss_bps: float = 10.0,
    max_allowed_position_loss_bps: float = 10.0,
    max_allowed_average_fee_drag_bps: float = 5.0,
    max_allowed_triggered_events: int = 0,
) -> dict[str, Any]:
    if min_cycles <= 0:
        raise ValueError("min_cycles must be positive")

    if max_allowed_cumulative_loss_bps < 0:
        raise ValueError("max_allowed_cumulative_loss_bps cannot be negative")

    if max_allowed_cycle_loss_bps < 0:
        raise ValueError("max_allowed_cycle_loss_bps cannot be negative")

    if max_allowed_position_loss_bps < 0:
        raise ValueError("max_allowed_position_loss_bps cannot be negative")

    if max_allowed_average_fee_drag_bps < 0:
        raise ValueError("max_allowed_average_fee_drag_bps cannot be negative")

    if max_allowed_triggered_events < 0:
        raise ValueError("max_allowed_triggered_events cannot be negative")

    db = Path(db_path)
    track = track_label or new_track_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    requested_labels = parse_labels(recovery_review_labels)

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        loaded_reviews = load_recovery_reviews(conn, requested_labels)

    cycles = build_cycles(track, created_at, requested_labels, loaded_reviews)
    metrics = build_metrics(requested_labels, cycles, loaded_reviews)

    checks = build_checks(
        track_label=track,
        created_at=created_at,
        requested_labels=requested_labels,
        cycles=cycles,
        metrics=metrics,
        min_cycles=min_cycles,
        max_allowed_cumulative_loss_bps=max_allowed_cumulative_loss_bps,
        max_allowed_cycle_loss_bps=max_allowed_cycle_loss_bps,
        max_allowed_position_loss_bps=max_allowed_position_loss_bps,
        max_allowed_average_fee_drag_bps=max_allowed_average_fee_drag_bps,
        max_allowed_triggered_events=max_allowed_triggered_events,
    )

    decision, global_verdict, recommended_action, next_mission, state, decision_reason = decide_outcome(cycles, checks)

    summary = build_summary(
        db_path=db,
        track_label=track,
        report_label=report,
        created_at=created_at,
        requested_labels=requested_labels,
        cycles=cycles,
        checks=checks,
        metrics=metrics,
        decision=decision,
        global_verdict=global_verdict,
        recommended_action=recommended_action,
        next_mission=next_mission,
        state=state,
        decision_reason=decision_reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_track(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid multi-cycle paper observation tracker.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--track-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--recovery-review-labels", default="mission68-final-check")
    parser.add_argument("--min-cycles", type=int, default=1)
    parser.add_argument("--max-allowed-cumulative-loss-bps", type=float, default=50.0)
    parser.add_argument("--max-allowed-cycle-loss-bps", type=float, default=10.0)
    parser.add_argument("--max-allowed-position-loss-bps", type=float, default=10.0)
    parser.add_argument("--max-allowed-average-fee-drag-bps", type=float, default=5.0)
    parser.add_argument("--max-allowed-triggered-events", type=int, default=0)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_multi_cycle_paper_observation_tracker(
        db_path=args.db,
        track_label=args.track_label,
        report_label=args.report_label,
        recovery_review_labels=args.recovery_review_labels,
        min_cycles=args.min_cycles,
        max_allowed_cumulative_loss_bps=args.max_allowed_cumulative_loss_bps,
        max_allowed_cycle_loss_bps=args.max_allowed_cycle_loss_bps,
        max_allowed_position_loss_bps=args.max_allowed_position_loss_bps,
        max_allowed_average_fee_drag_bps=args.max_allowed_average_fee_drag_bps,
        max_allowed_triggered_events=args.max_allowed_triggered_events,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

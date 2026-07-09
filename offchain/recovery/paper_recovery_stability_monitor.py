"""
Mission 68: Paper Recovery Stability Monitor.

This module reviews a paper-only drawdown kill-switch state and decides whether
paper observation is stable enough to continue collecting more paper evidence.

It reads:
- paper_drawdown_kill_switch_reviews
- paper_drawdown_kill_switch_checks
- paper_drawdown_kill_switch_events
- paper_observation_performance_runs
- paper_observation_position_snapshots

It writes:
- paper_recovery_stability_reviews
- paper_recovery_stability_checks
- paper_recovery_stability_events
- paper_recovery_stability_reports

It is paper recovery analytics only.

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


KILL_SWITCH_REVIEWS_TABLE = "paper_drawdown_kill_switch_reviews"
KILL_SWITCH_CHECKS_TABLE = "paper_drawdown_kill_switch_checks"
KILL_SWITCH_EVENTS_TABLE = "paper_drawdown_kill_switch_events"
PERFORMANCE_RUNS_TABLE = "paper_observation_performance_runs"
POSITION_SNAPSHOTS_TABLE = "paper_observation_position_snapshots"

RECOVERY_REVIEWS_TABLE = "paper_recovery_stability_reviews"
RECOVERY_CHECKS_TABLE = "paper_recovery_stability_checks"
RECOVERY_EVENTS_TABLE = "paper_recovery_stability_events"
RECOVERY_REPORTS_TABLE = "paper_recovery_stability_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

KILL_SWITCH_DECISION_ARMED = "PAPER_DRAWDOWN_KILL_SWITCH_ARMED_CONTINUE_OBSERVATION"
KILL_SWITCH_VERDICT_ARMED = "PAPER_DRAWDOWN_KILL_SWITCH_ARMED_SHADOW_ONLY"
KILL_SWITCH_STATE_ARMED = "KILL_SWITCH_STATE_ARMED_NOT_TRIGGERED"

CHECK_PASS = "RECOVERY_STABILITY_CHECK_PASS"
CHECK_FAIL = "RECOVERY_STABILITY_CHECK_FAIL"

EVENT_CONFIRMED = "PAPER_RECOVERY_STABILITY_CONFIRMED"
EVENT_UNSTABLE = "PAPER_RECOVERY_STABILITY_UNSTABLE"
EVENT_MISSING = "PAPER_RECOVERY_STABILITY_MISSING_EVIDENCE"
EVENT_SAFETY_BLOCK = "PAPER_RECOVERY_STABILITY_SAFETY_BLOCK"

DECISION_CONFIRMED = "PAPER_RECOVERY_STABILITY_CONFIRMED_CONTINUE_OBSERVATION"
DECISION_UNSTABLE = "PAPER_RECOVERY_STABILITY_UNSTABLE_STOP_AND_REVIEW"
DECISION_BLOCK_SAFETY = "PAPER_RECOVERY_STABILITY_BLOCKED_BY_SAFETY_POLICY"
DECISION_REJECT_MISSING = "PAPER_RECOVERY_STABILITY_REJECTED_MISSING_EVIDENCE"

VERDICT_CONFIRMED = "PAPER_RECOVERY_STABILITY_CONFIRMED_SHADOW_ONLY"
VERDICT_UNSTABLE = "PAPER_RECOVERY_STABILITY_UNSTABLE_SHADOW_ONLY"
VERDICT_BLOCKED = "PAPER_RECOVERY_STABILITY_BLOCKED_SHADOW_ONLY"
VERDICT_MISSING = "PAPER_RECOVERY_STABILITY_MISSING_EVIDENCE"

ACTION_CONTINUE = "CONTINUE_PAPER_OBSERVATION_AND_BEGIN_MULTI_CYCLE_TRACKING"
ACTION_REVIEW_UNSTABLE = "STOP_PAPER_OBSERVATION_AND_REVIEW_RECOVERY_STABILITY"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_RECOVERY_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_DRAWDOWN_KILL_SWITCH_EVIDENCE"

STATE_CONFIRMED = "RECOVERY_STABILITY_STATE_CONFIRMED"
STATE_UNSTABLE = "RECOVERY_STABILITY_STATE_UNSTABLE"
STATE_BLOCKED = "RECOVERY_STABILITY_STATE_BLOCKED"
STATE_MISSING = "RECOVERY_STABILITY_STATE_MISSING"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_review_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission68-recovery-review-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission68-recovery-report-{stamp}-{uuid.uuid4().hex[:8]}"


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


def parse_symbols(value: str | list[str] | tuple[str, ...] | None) -> list[str] | None:
    if value is None:
        return None

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    symbols: list[str] = []

    for item in raw_items:
        symbol = str(item).strip().upper()

        if not symbol:
            continue

        if not symbol.endswith("USDT"):
            raise ValueError(f"Only USDT symbols are supported for Mission 68: {symbol}")

        if not symbol.replace("_", "").isalnum():
            raise ValueError(f"Invalid symbol: {symbol}")

        if symbol not in symbols:
            symbols.append(symbol)

    if not symbols:
        raise ValueError("At least one symbol is required when symbols are supplied")

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
            CREATE TABLE IF NOT EXISTS paper_recovery_stability_reviews (
                review_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_kill_switch_review_label TEXT NOT NULL,
                source_performance_run_label TEXT,
                source_capital_review_label TEXT,
                source_session_label TEXT,
                source_portfolio_label TEXT,
                paper_notional TEXT NOT NULL,
                monitored_position_count INTEGER NOT NULL,
                check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
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
            CREATE TABLE IF NOT EXISTS paper_recovery_stability_checks (
                check_id TEXT PRIMARY KEY,
                review_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_kill_switch_review_label TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS paper_recovery_stability_events (
                event_id TEXT PRIMARY KEY,
                review_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_kill_switch_review_label TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                threshold_value TEXT NOT NULL,
                event_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_recovery_stability_reports (
                report_label TEXT PRIMARY KEY,
                review_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_kill_switch_review_label TEXT NOT NULL,
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


def load_kill_switch_review(conn: sqlite3.Connection, kill_switch_review_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, KILL_SWITCH_REVIEWS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM paper_drawdown_kill_switch_reviews
        WHERE review_label = ?
        """,
        (kill_switch_review_label,),
    ).fetchone()


def load_kill_switch_checks(conn: sqlite3.Connection, kill_switch_review_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, KILL_SWITCH_CHECKS_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM paper_drawdown_kill_switch_checks
        WHERE review_label = ?
        ORDER BY created_at ASC, check_id ASC
        """,
        (kill_switch_review_label,),
    ).fetchall()


def load_kill_switch_events(conn: sqlite3.Connection, kill_switch_review_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, KILL_SWITCH_EVENTS_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM paper_drawdown_kill_switch_events
        WHERE review_label = ?
        ORDER BY created_at ASC, event_id ASC
        """,
        (kill_switch_review_label,),
    ).fetchall()


def load_performance_run(conn: sqlite3.Connection, performance_run_label: str | None) -> sqlite3.Row | None:
    if not performance_run_label:
        return None

    if not table_exists(conn, PERFORMANCE_RUNS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM paper_observation_performance_runs
        WHERE run_label = ?
        """,
        (performance_run_label,),
    ).fetchone()


def load_position_snapshots(
    conn: sqlite3.Connection,
    performance_run_label: str | None,
    symbols: list[str] | None,
) -> list[sqlite3.Row]:
    if not performance_run_label:
        return []

    if not table_exists(conn, POSITION_SNAPSHOTS_TABLE):
        return []

    params: list[Any] = [performance_run_label]
    symbol_clause = ""

    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        symbol_clause = f" AND symbol IN ({placeholders})"
        params.extend(symbols)

    query = f"""
        SELECT *
        FROM paper_observation_position_snapshots
        WHERE run_label = ?
        {symbol_clause}
        ORDER BY CAST(entry_notional AS REAL) DESC
    """

    return conn.execute(query, params).fetchall()


def stability_check(
    review_label: str,
    created_at: str,
    kill_switch_review_label: str,
    category: str,
    name: str,
    status: str,
    observed_value: Any,
    threshold_value: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{review_label}-{category}-{name}".replace(" ", "_"),
        "review_label": review_label,
        "created_at": created_at,
        "source_kill_switch_review_label": kill_switch_review_label,
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
            "recovery_stability_role": "PAPER_RECOVERY_STABILITY_CHECK_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def stability_event(
    review_label: str,
    created_at: str,
    kill_switch_review_label: str,
    event_type: str,
    observed_value: Any,
    threshold_value: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "event_id": f"{review_label}-{event_type}".replace(" ", "_"),
        "review_label": review_label,
        "created_at": created_at,
        "source_kill_switch_review_label": kill_switch_review_label,
        "event_type": event_type,
        "event_status": "RECORDED",
        "observed_value": str(observed_value),
        "threshold_value": str(threshold_value),
        "event_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "recovery_stability_role": "PAPER_RECOVERY_STABILITY_EVENT_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def is_triggered_kill_event(event: sqlite3.Row | dict[str, Any]) -> bool:
    event_type = str(row_get(event, "event_type", ""))
    return (
        "TRIGGERED" in event_type
        or "SAFETY_BLOCK" in event_type
        or "MISSING" in event_type
    )


def build_missing_checks(
    review_label: str,
    created_at: str,
    kill_switch_review_label: str,
) -> list[dict[str, Any]]:
    return [
        stability_check(
            review_label,
            created_at,
            kill_switch_review_label,
            "availability",
            "kill switch review exists",
            CHECK_FAIL,
            "missing",
            "paper_drawdown_kill_switch_reviews record",
            "No paper drawdown kill-switch review exists for this label.",
        )
    ]


def snapshot_count_for_symbols(
    kill_switch_review: sqlite3.Row,
    performance_run: sqlite3.Row | None,
    snapshots: list[sqlite3.Row],
) -> int:
    if snapshots:
        return len(snapshots)

    return safe_int(
        row_get(
            performance_run,
            "monitored_position_count",
            row_get(kill_switch_review, "monitored_position_count", 0),
        )
    )


def build_checks(
    review_label: str,
    created_at: str,
    kill_switch_review: sqlite3.Row,
    kill_switch_checks: list[sqlite3.Row],
    kill_switch_events: list[sqlite3.Row],
    performance_run: sqlite3.Row | None,
    snapshots: list[sqlite3.Row],
    min_monitored_positions: int,
    min_recovery_net_pnl_bps: float,
    min_position_loss_bps: float,
    max_fee_drag_bps: float,
    max_triggered_events: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    kill_switch_review_label = str(row_get(kill_switch_review, "review_label", ""))
    performance_run_label = row_get(kill_switch_review, "source_performance_run_label", None)

    kill_switch_decision = str(row_get(kill_switch_review, "kill_switch_decision", ""))
    kill_switch_verdict = str(row_get(kill_switch_review, "global_verdict", ""))
    kill_switch_state = str(row_get(kill_switch_review, "kill_switch_state", ""))

    loaded_failed_checks = sum(
        1 for check in kill_switch_checks if str(row_get(check, "check_status", "")) != "DRAWDOWN_CHECK_PASS"
    )

    failed_check_count = safe_int(row_get(kill_switch_review, "fail_check_count", loaded_failed_checks))
    triggered_event_count = safe_int(
        row_get(
            kill_switch_review,
            "triggered_event_count",
            sum(1 for event in kill_switch_events if is_triggered_kill_event(event)),
        )
    )

    safety_count = safe_int(row_get(kill_switch_review, "safety_breach_count", 0))
    safety_count += sum(1 for row in [kill_switch_review, performance_run, *kill_switch_checks, *kill_switch_events, *snapshots] if safety_problem(row))

    monitored_positions = snapshot_count_for_symbols(kill_switch_review, performance_run, snapshots)
    net_bps = safe_float(row_get(kill_switch_review, "net_paper_pnl_bps", row_get(performance_run, "net_paper_pnl_bps", 0.0)))
    max_position_loss = safe_float(row_get(kill_switch_review, "max_position_loss_bps", row_get(performance_run, "max_position_loss_bps", 0.0)))
    fee_drag = safe_float(row_get(kill_switch_review, "fee_drag_bps", row_get(performance_run, "fee_drag_bps", 0.0)))
    alert_count = safe_int(row_get(kill_switch_review, "alert_count", row_get(performance_run, "alert_count", 0)))

    checks = [
        stability_check(
            review_label,
            created_at,
            kill_switch_review_label,
            "safety",
            "safety invariants",
            CHECK_PASS if safety_count == 0 else CHECK_FAIL,
            safety_count,
            0,
            "Recovery stability requires zero live-trading, order-transmission, and capital-deployment breaches.",
        ),
        stability_check(
            review_label,
            created_at,
            kill_switch_review_label,
            "kill_switch",
            "kill switch decision armed",
            CHECK_PASS if kill_switch_decision == KILL_SWITCH_DECISION_ARMED else CHECK_FAIL,
            kill_switch_decision,
            KILL_SWITCH_DECISION_ARMED,
            "Recovery stability requires the paper drawdown kill switch to be armed.",
        ),
        stability_check(
            review_label,
            created_at,
            kill_switch_review_label,
            "kill_switch",
            "kill switch verdict armed",
            CHECK_PASS if kill_switch_verdict == KILL_SWITCH_VERDICT_ARMED else CHECK_FAIL,
            kill_switch_verdict,
            KILL_SWITCH_VERDICT_ARMED,
            "Recovery stability requires the kill-switch global verdict to be armed.",
        ),
        stability_check(
            review_label,
            created_at,
            kill_switch_review_label,
            "kill_switch",
            "kill switch state not triggered",
            CHECK_PASS if kill_switch_state == KILL_SWITCH_STATE_ARMED else CHECK_FAIL,
            kill_switch_state,
            KILL_SWITCH_STATE_ARMED,
            "Recovery stability requires the kill switch state to remain untriggered.",
        ),
        stability_check(
            review_label,
            created_at,
            kill_switch_review_label,
            "drawdown",
            "failed drawdown check count",
            CHECK_PASS if failed_check_count == 0 else CHECK_FAIL,
            failed_check_count,
            0,
            "No drawdown kill-switch checks may be failed.",
        ),
        stability_check(
            review_label,
            created_at,
            kill_switch_review_label,
            "events",
            "triggered kill switch event count",
            CHECK_PASS if triggered_event_count <= max_triggered_events else CHECK_FAIL,
            triggered_event_count,
            f"<= {max_triggered_events}",
            "Triggered kill-switch events must remain inside stability threshold.",
        ),
        stability_check(
            review_label,
            created_at,
            kill_switch_review_label,
            "portfolio",
            "monitored position count",
            CHECK_PASS if monitored_positions >= min_monitored_positions else CHECK_FAIL,
            monitored_positions,
            f">= {min_monitored_positions}",
            "Recovery stability requires enough monitored paper positions.",
        ),
        stability_check(
            review_label,
            created_at,
            kill_switch_review_label,
            "recovery",
            "net paper pnl bps recovery floor",
            CHECK_PASS if net_bps >= min_recovery_net_pnl_bps else CHECK_FAIL,
            round8(net_bps),
            f">= {min_recovery_net_pnl_bps}",
            "Net paper PnL bps must remain above the recovery stability floor.",
        ),
        stability_check(
            review_label,
            created_at,
            kill_switch_review_label,
            "recovery",
            "max position loss bps recovery floor",
            CHECK_PASS if max_position_loss >= -abs(min_position_loss_bps) else CHECK_FAIL,
            round8(max_position_loss),
            f">= {-abs(min_position_loss_bps)}",
            "Worst paper position loss must remain above the recovery stability floor.",
        ),
        stability_check(
            review_label,
            created_at,
            kill_switch_review_label,
            "cost",
            "fee drag bps",
            CHECK_PASS if fee_drag <= max_fee_drag_bps else CHECK_FAIL,
            round8(fee_drag),
            f"<= {max_fee_drag_bps}",
            "Fee drag must remain inside recovery stability threshold.",
        ),
    ]

    metrics = {
        "source_performance_run_label": performance_run_label,
        "source_capital_review_label": row_get(kill_switch_review, "source_capital_review_label", row_get(performance_run, "source_capital_review_label", None)),
        "source_session_label": row_get(kill_switch_review, "source_session_label", row_get(performance_run, "source_session_label", None)),
        "source_portfolio_label": row_get(kill_switch_review, "source_portfolio_label", row_get(performance_run, "source_portfolio_label", None)),
        "paper_notional": round8(safe_float(row_get(kill_switch_review, "paper_notional", row_get(performance_run, "paper_notional", 0.0)))),
        "monitored_position_count": monitored_positions,
        "net_paper_pnl": round8(safe_float(row_get(kill_switch_review, "net_paper_pnl", row_get(performance_run, "net_paper_pnl", 0.0)))),
        "net_paper_pnl_bps": round8(net_bps),
        "max_position_loss_bps": round8(max_position_loss),
        "fee_drag_bps": round8(fee_drag),
        "alert_count": alert_count,
        "triggered_event_count": triggered_event_count,
        "safety_breach_count": safety_count,
    }

    return checks, metrics


def build_events(
    review_label: str,
    created_at: str,
    kill_switch_review_label: str,
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    failed = [check for check in checks if check["check_status"] == CHECK_FAIL]

    if not failed:
        return [
            stability_event(
                review_label,
                created_at,
                kill_switch_review_label,
                EVENT_CONFIRMED,
                "all_checks_passed",
                "stable recovery state",
                "Paper recovery stability is confirmed for continued paper observation.",
            )
        ]

    events = []

    for check in failed:
        if check["check_category"] == "safety":
            event_type = EVENT_SAFETY_BLOCK
        elif check["check_category"] == "availability":
            event_type = EVENT_MISSING
        else:
            event_type = EVENT_UNSTABLE

        events.append(
            stability_event(
                review_label,
                created_at,
                kill_switch_review_label,
                f"{event_type}_{check['check_category']}_{check['check_name']}",
                check["observed_value"],
                check["threshold_value"],
                check["check_reason"],
            )
        )

    return events


def decide_outcome(
    kill_switch_review: sqlite3.Row | None,
    checks: list[dict[str, Any]],
) -> tuple[str, str, str, str, str, str]:
    if kill_switch_review is None:
        return (
            DECISION_REJECT_MISSING,
            VERDICT_MISSING,
            ACTION_REFRESH,
            "Mission 67 Paper Drawdown Kill Switch",
            STATE_MISSING,
            "Paper drawdown kill-switch evidence is missing.",
        )

    failed = [check for check in checks if check["check_status"] == CHECK_FAIL]

    if any(check["check_category"] == "safety" for check in failed):
        return (
            DECISION_BLOCK_SAFETY,
            VERDICT_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 68 safety remediation",
            STATE_BLOCKED,
            "Safety invariant failed during recovery stability monitoring.",
        )

    if failed:
        return (
            DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 67 Paper Drawdown Kill Switch",
            STATE_UNSTABLE,
            "Paper recovery stability is not confirmed because one or more stability checks failed.",
        )

    return (
        DECISION_CONFIRMED,
        VERDICT_CONFIRMED,
        ACTION_CONTINUE,
        "Mission 69 Multi-Cycle Paper Observation Tracker",
        STATE_CONFIRMED,
        "Paper recovery stability is confirmed. Continue paper observation and begin multi-cycle tracking.",
    )


def build_summary(
    db_path: str | Path,
    review_label: str,
    report_label: str,
    created_at: str,
    kill_switch_review_label: str,
    checks: list[dict[str, Any]],
    events: list[dict[str, Any]],
    metrics: dict[str, Any],
    recovery_stability_decision: str,
    global_verdict: str,
    recommended_action: str,
    next_mission: str,
    recovery_stability_state: str,
    decision_reason: str,
) -> dict[str, Any]:
    counts = Counter(check["check_status"] for check in checks)

    return {
        "review_label": review_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_kill_switch_review_label": kill_switch_review_label,
        "source_performance_run_label": metrics.get("source_performance_run_label"),
        "source_capital_review_label": metrics.get("source_capital_review_label"),
        "source_session_label": metrics.get("source_session_label"),
        "source_portfolio_label": metrics.get("source_portfolio_label"),
        "paper_notional": round8(safe_float(metrics.get("paper_notional", 0.0))),
        "monitored_position_count": safe_int(metrics.get("monitored_position_count", 0)),
        "check_count": len(checks),
        "pass_check_count": counts.get(CHECK_PASS, 0),
        "fail_check_count": counts.get(CHECK_FAIL, 0),
        "net_paper_pnl": round8(safe_float(metrics.get("net_paper_pnl", 0.0))),
        "net_paper_pnl_bps": round8(safe_float(metrics.get("net_paper_pnl_bps", 0.0))),
        "max_position_loss_bps": round8(safe_float(metrics.get("max_position_loss_bps", 0.0))),
        "fee_drag_bps": round8(safe_float(metrics.get("fee_drag_bps", 0.0))),
        "alert_count": safe_int(metrics.get("alert_count", 0)),
        "triggered_event_count": safe_int(metrics.get("triggered_event_count", 0)),
        "safety_breach_count": safe_int(metrics.get("safety_breach_count", 0)),
        "recovery_stability_checks": checks,
        "recovery_stability_events": events,
        "recovery_stability_state": recovery_stability_state,
        "recovery_stability_decision": recovery_stability_decision,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
        "next_mission": next_mission,
        "decision_reason": decision_reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    check_lines = []

    for check in summary["recovery_stability_checks"]:
        check_lines.append(
            "- "
            + f"{check['check_category']} / {check['check_name']}: "
            + f"status={check['check_status']}, "
            + f"observed={check['observed_value']}, "
            + f"threshold={check['threshold_value']}"
        )

    event_lines = []

    for event in summary["recovery_stability_events"]:
        event_lines.append(
            "- "
            + f"{event['event_type']}: "
            + f"observed={event['observed_value']}, "
            + f"threshold={event['threshold_value']}"
        )

    checks_markdown = "\n".join(check_lines) or "- None"
    events_markdown = "\n".join(event_lines) or "- None"

    return f"""# DeltaGrid Mission 68 Paper Recovery Stability Monitor Report

Report label: {summary['report_label']}
Review label: {summary['review_label']}
Created at: {summary['created_at']}
Source kill-switch review label: {summary['source_kill_switch_review_label']}
Source performance run label: {summary['source_performance_run_label']}
Source capital review label: {summary['source_capital_review_label']}
Source session label: {summary['source_session_label']}
Source portfolio label: {summary['source_portfolio_label']}

## Recovery Stability Summary

Paper notional: {summary['paper_notional']}
Monitored position count: {summary['monitored_position_count']}
Check count: {summary['check_count']}
Pass check count: {summary['pass_check_count']}
Fail check count: {summary['fail_check_count']}

Net paper PnL: {summary['net_paper_pnl']}
Net paper PnL bps: {summary['net_paper_pnl_bps']}
Max position loss bps: {summary['max_position_loss_bps']}
Fee drag bps: {summary['fee_drag_bps']}
Alert count: {summary['alert_count']}
Triggered event count: {summary['triggered_event_count']}
Safety breach count: {summary['safety_breach_count']}

Recovery stability state: {summary['recovery_stability_state']}

## Checks

{checks_markdown}

## Events

{events_markdown}

## Decision

Recovery stability decision: {summary['recovery_stability_decision']}
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

Recovery stability monitoring is paper-only and cannot send live orders.
"""


def persist_review(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for check in summary["recovery_stability_checks"]:
            conn.execute(
                """
                INSERT OR REPLACE INTO paper_recovery_stability_checks (
                    check_id,
                    review_label,
                    created_at,
                    source_kill_switch_review_label,
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    check["check_id"],
                    check["review_label"],
                    check["created_at"],
                    check["source_kill_switch_review_label"],
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

        for event in summary["recovery_stability_events"]:
            conn.execute(
                """
                INSERT OR REPLACE INTO paper_recovery_stability_events (
                    event_id,
                    review_label,
                    created_at,
                    source_kill_switch_review_label,
                    event_type,
                    event_status,
                    observed_value,
                    threshold_value,
                    event_reason,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    event["review_label"],
                    event["created_at"],
                    event["source_kill_switch_review_label"],
                    event["event_type"],
                    event["event_status"],
                    event["observed_value"],
                    event["threshold_value"],
                    event["event_reason"],
                    event["live_trading"],
                    event["live_order_sent"],
                    event["capital_deployment"],
                    json.dumps(event["metadata"], sort_keys=True),
                ),
            )

        conn.execute(
            """
            INSERT OR REPLACE INTO paper_recovery_stability_reviews (
                review_label,
                report_label,
                created_at,
                source_kill_switch_review_label,
                source_performance_run_label,
                source_capital_review_label,
                source_session_label,
                source_portfolio_label,
                paper_notional,
                monitored_position_count,
                check_count,
                pass_check_count,
                fail_check_count,
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
                summary["review_label"],
                summary["report_label"],
                summary["created_at"],
                summary["source_kill_switch_review_label"],
                summary["source_performance_run_label"],
                summary["source_capital_review_label"],
                summary["source_session_label"],
                summary["source_portfolio_label"],
                str(summary["paper_notional"]),
                summary["monitored_position_count"],
                summary["check_count"],
                summary["pass_check_count"],
                summary["fail_check_count"],
                str(summary["net_paper_pnl"]),
                str(summary["net_paper_pnl_bps"]),
                str(summary["max_position_loss_bps"]),
                str(summary["fee_drag_bps"]),
                summary["alert_count"],
                summary["triggered_event_count"],
                summary["safety_breach_count"],
                summary["recovery_stability_state"],
                summary["recovery_stability_decision"],
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
            INSERT OR REPLACE INTO paper_recovery_stability_reports (
                report_label,
                review_label,
                created_at,
                source_kill_switch_review_label,
                global_verdict,
                recommended_action,
                report_json,
                markdown_report,
                live_trading,
                live_order_sent,
                capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["review_label"],
                summary["created_at"],
                summary["source_kill_switch_review_label"],
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


def run_paper_recovery_stability_monitor(
    db_path: str | Path = "offchain/deltagrid.db",
    review_label: str | None = None,
    report_label: str | None = None,
    kill_switch_review_label: str = "mission67-final-check",
    symbols: str | list[str] | tuple[str, ...] | None = None,
    min_monitored_positions: int = 3,
    min_recovery_net_pnl_bps: float = -10.0,
    min_position_loss_bps: float = 10.0,
    max_fee_drag_bps: float = 5.0,
    max_triggered_events: int = 0,
) -> dict[str, Any]:
    if min_monitored_positions <= 0:
        raise ValueError("min_monitored_positions must be positive")

    if max_fee_drag_bps < 0:
        raise ValueError("max_fee_drag_bps cannot be negative")

    if max_triggered_events < 0:
        raise ValueError("max_triggered_events cannot be negative")

    db = Path(db_path)
    review = review_label or new_review_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    requested_symbols = parse_symbols(symbols)

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        kill_switch_review = load_kill_switch_review(conn, kill_switch_review_label)
        kill_switch_checks = load_kill_switch_checks(conn, kill_switch_review_label)
        kill_switch_events = load_kill_switch_events(conn, kill_switch_review_label)

        performance_run_label = row_get(kill_switch_review, "source_performance_run_label", None)
        performance_run = load_performance_run(conn, performance_run_label)
        snapshots = load_position_snapshots(conn, performance_run_label, requested_symbols)

    if kill_switch_review is None:
        checks = build_missing_checks(review, created_at, kill_switch_review_label)
        metrics: dict[str, Any] = {}
    else:
        checks, metrics = build_checks(
            review_label=review,
            created_at=created_at,
            kill_switch_review=kill_switch_review,
            kill_switch_checks=kill_switch_checks,
            kill_switch_events=kill_switch_events,
            performance_run=performance_run,
            snapshots=snapshots,
            min_monitored_positions=min_monitored_positions,
            min_recovery_net_pnl_bps=min_recovery_net_pnl_bps,
            min_position_loss_bps=min_position_loss_bps,
            max_fee_drag_bps=max_fee_drag_bps,
            max_triggered_events=max_triggered_events,
        )

    events = build_events(review, created_at, kill_switch_review_label, checks)
    recovery_stability_decision, global_verdict, recommended_action, next_mission, recovery_state, decision_reason = decide_outcome(
        kill_switch_review,
        checks,
    )

    summary = build_summary(
        db_path=db,
        review_label=review,
        report_label=report,
        created_at=created_at,
        kill_switch_review_label=kill_switch_review_label,
        checks=checks,
        events=events,
        metrics=metrics,
        recovery_stability_decision=recovery_stability_decision,
        global_verdict=global_verdict,
        recommended_action=recommended_action,
        next_mission=next_mission,
        recovery_stability_state=recovery_state,
        decision_reason=decision_reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_review(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid paper recovery stability monitor.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--review-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--kill-switch-review-label", default="mission67-final-check")
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--min-monitored-positions", type=int, default=3)
    parser.add_argument("--min-recovery-net-pnl-bps", type=float, default=-10.0)
    parser.add_argument("--min-position-loss-bps", type=float, default=10.0)
    parser.add_argument("--max-fee-drag-bps", type=float, default=5.0)
    parser.add_argument("--max-triggered-events", type=int, default=0)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_paper_recovery_stability_monitor(
        db_path=args.db,
        review_label=args.review_label,
        report_label=args.report_label,
        kill_switch_review_label=args.kill_switch_review_label,
        symbols=args.symbols,
        min_monitored_positions=args.min_monitored_positions,
        min_recovery_net_pnl_bps=args.min_recovery_net_pnl_bps,
        min_position_loss_bps=args.min_position_loss_bps,
        max_fee_drag_bps=args.max_fee_drag_bps,
        max_triggered_events=args.max_triggered_events,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

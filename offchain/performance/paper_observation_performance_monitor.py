"""
Mission 66: Paper Observation Performance Monitor.

This module monitors paper-only positions after capital readiness approval.

It reads:
- capital_readiness_reviews
- capital_readiness_decision_records
- paper_sandbox_sessions
- paper_sandbox_orders
- paper_sandbox_positions

It writes:
- paper_observation_performance_runs
- paper_observation_position_snapshots
- paper_observation_performance_alerts
- paper_observation_performance_reports

It is paper observation and analytics only.

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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CAPITAL_REVIEWS_TABLE = "capital_readiness_reviews"
CAPITAL_DECISIONS_TABLE = "capital_readiness_decision_records"
PAPER_SESSIONS_TABLE = "paper_sandbox_sessions"
PAPER_ORDERS_TABLE = "paper_sandbox_orders"
PAPER_POSITIONS_TABLE = "paper_sandbox_positions"

PERFORMANCE_RUNS_TABLE = "paper_observation_performance_runs"
POSITION_SNAPSHOTS_TABLE = "paper_observation_position_snapshots"
PERFORMANCE_ALERTS_TABLE = "paper_observation_performance_alerts"
PERFORMANCE_REPORTS_TABLE = "paper_observation_performance_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

CAPITAL_APPROVED = "CAPITAL_READINESS_APPROVED_FOR_EXTENDED_PAPER_OBSERVATION_ONLY"
CAPITAL_READY = "CAPITAL_READINESS_REVIEW_PAPER_ONLY_READY"
CAPITAL_ACTION_EXTENDED_PAPER = "CONTINUE_EXTENDED_PAPER_OBSERVATION_ONLY"

PERFORMANCE_DECISION_CONTINUE = "PAPER_OBSERVATION_PERFORMANCE_CONTINUE_MONITORING"
PERFORMANCE_DECISION_BLOCK_READINESS = "PAPER_OBSERVATION_PERFORMANCE_BLOCKED_BY_CAPITAL_READINESS"
PERFORMANCE_DECISION_BLOCK_SAFETY = "PAPER_OBSERVATION_PERFORMANCE_BLOCKED_BY_SAFETY_POLICY"
PERFORMANCE_DECISION_BLOCK_LOSS = "PAPER_OBSERVATION_PERFORMANCE_BLOCKED_BY_LOSS_LIMIT"
PERFORMANCE_DECISION_REJECT_MISSING = "PAPER_OBSERVATION_PERFORMANCE_REJECTED_MISSING_EVIDENCE"

PERFORMANCE_READY = "PAPER_OBSERVATION_PERFORMANCE_READY_SHADOW_ONLY"
PERFORMANCE_BLOCKED = "PAPER_OBSERVATION_PERFORMANCE_BLOCKED_SHADOW_ONLY"
PERFORMANCE_MISSING = "PAPER_OBSERVATION_PERFORMANCE_MISSING_EVIDENCE"

ACTION_CONTINUE = "CONTINUE_PAPER_OBSERVATION_AND_COLLECT_MORE_SNAPSHOTS"
ACTION_REVIEW_CAPITAL = "RETURN_TO_CAPITAL_READINESS_REVIEW"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_PERFORMANCE_SAFETY_STATE"
ACTION_REVIEW_LOSS = "REVIEW_PAPER_LOSS_AND_REDUCE_RISK"

HEALTH_STABLE = "PAPER_OBSERVATION_HEALTH_STABLE_BASELINE"
HEALTH_CAUTION = "PAPER_OBSERVATION_HEALTH_CAUTION"
HEALTH_DANGER = "PAPER_OBSERVATION_HEALTH_DANGER"
HEALTH_MISSING = "PAPER_OBSERVATION_HEALTH_MISSING"

SNAPSHOT_OPEN = "PAPER_POSITION_SNAPSHOT_OPEN"
SNAPSHOT_WIN = "PAPER_POSITION_SNAPSHOT_WIN"
SNAPSHOT_LOSS = "PAPER_POSITION_SNAPSHOT_LOSS"

ALERT_TRIGGERED = "PERFORMANCE_ALERT_TRIGGERED"
ALERT_CLEAR = "PERFORMANCE_ALERT_CLEAR"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_run_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission66-performance-run-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission66-performance-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
            raise ValueError(f"Only USDT symbols are supported for Mission 66: {symbol}")

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
            CREATE TABLE IF NOT EXISTS paper_observation_performance_runs (
                run_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_capital_review_label TEXT NOT NULL,
                source_session_label TEXT,
                source_portfolio_label TEXT,
                paper_notional TEXT NOT NULL,
                monitored_position_count INTEGER NOT NULL,
                order_count INTEGER NOT NULL,
                gross_unrealized_paper_pnl TEXT NOT NULL,
                total_simulated_fees TEXT NOT NULL,
                net_paper_pnl TEXT NOT NULL,
                net_paper_pnl_bps TEXT NOT NULL,
                max_position_loss_bps TEXT NOT NULL,
                fee_drag_bps TEXT NOT NULL,
                win_rate_pct TEXT NOT NULL,
                alert_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                performance_health TEXT NOT NULL,
                performance_decision TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS paper_observation_position_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_session_label TEXT,
                position_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                quantity TEXT NOT NULL,
                entry_price TEXT NOT NULL,
                observed_price TEXT NOT NULL,
                entry_notional TEXT NOT NULL,
                gross_paper_pnl TEXT NOT NULL,
                simulated_fee_amount TEXT NOT NULL,
                net_paper_pnl TEXT NOT NULL,
                net_paper_pnl_bps TEXT NOT NULL,
                snapshot_status TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_observation_performance_alerts (
                alert_id TEXT PRIMARY KEY,
                run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_capital_review_label TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                alert_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                threshold_value TEXT NOT NULL,
                alert_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_observation_performance_reports (
                report_label TEXT PRIMARY KEY,
                run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_capital_review_label TEXT NOT NULL,
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


def load_capital_review(conn: sqlite3.Connection, capital_review_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, CAPITAL_REVIEWS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM capital_readiness_reviews
        WHERE review_label = ?
        """,
        (capital_review_label,),
    ).fetchone()


def load_capital_decision(conn: sqlite3.Connection, capital_review_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, CAPITAL_DECISIONS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM capital_readiness_decision_records
        WHERE review_label = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (capital_review_label,),
    ).fetchone()


def load_session(conn: sqlite3.Connection, session_label: str | None) -> sqlite3.Row | None:
    if not session_label:
        return None

    if not table_exists(conn, PAPER_SESSIONS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM paper_sandbox_sessions
        WHERE session_label = ?
        """,
        (session_label,),
    ).fetchone()


def load_orders(conn: sqlite3.Connection, session_label: str | None, symbols: list[str] | None) -> list[sqlite3.Row]:
    if not session_label:
        return []

    if not table_exists(conn, PAPER_ORDERS_TABLE):
        return []

    params: list[Any] = [session_label]
    symbol_clause = ""

    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        symbol_clause = f" AND symbol IN ({placeholders})"
        params.extend(symbols)

    query = f"""
        SELECT *
        FROM paper_sandbox_orders
        WHERE session_label = ?
        {symbol_clause}
        ORDER BY CAST(requested_notional AS REAL) DESC
    """

    return conn.execute(query, params).fetchall()


def load_positions(conn: sqlite3.Connection, session_label: str | None, symbols: list[str] | None) -> list[sqlite3.Row]:
    if not session_label:
        return []

    if not table_exists(conn, PAPER_POSITIONS_TABLE):
        return []

    params: list[Any] = [session_label]
    symbol_clause = ""

    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        symbol_clause = f" AND symbol IN ({placeholders})"
        params.extend(symbols)

    query = f"""
        SELECT *
        FROM paper_sandbox_positions
        WHERE session_label = ?
        {symbol_clause}
        ORDER BY CAST(entry_notional AS REAL) DESC
    """

    return conn.execute(query, params).fetchall()


def capital_is_ready(capital_review: sqlite3.Row | None, capital_decision: sqlite3.Row | None) -> bool:
    if capital_review is None:
        return False

    decision_value = str(row_get(capital_review, "capital_decision", ""))
    verdict_value = str(row_get(capital_review, "global_verdict", ""))
    action_value = str(row_get(capital_review, "recommended_action", ""))

    if capital_decision is not None:
        decision_value = str(row_get(capital_decision, "capital_decision", decision_value))
        verdict_value = str(row_get(capital_decision, "global_verdict", verdict_value))
        action_value = str(row_get(capital_decision, "recommended_action", action_value))

    return (
        decision_value == CAPITAL_APPROVED
        and verdict_value == CAPITAL_READY
        and action_value == CAPITAL_ACTION_EXTENDED_PAPER
    )


def build_position_snapshot(
    run_label: str,
    created_at: str,
    position: sqlite3.Row,
    price_shock_bps: float,
) -> dict[str, Any]:
    position_id = str(row_get(position, "position_id", uuid.uuid4().hex[:8]))
    symbol = str(row_get(position, "symbol", "UNKNOWN"))
    strategy_id = str(row_get(position, "strategy_id", "UNKNOWN_STRATEGY"))
    quantity = safe_float(row_get(position, "quantity", 0.0))
    entry_price = safe_float(row_get(position, "entry_price", 0.0))
    entry_notional = safe_float(row_get(position, "entry_notional", 0.0))
    fee = safe_float(row_get(position, "simulated_fee_amount", 0.0))
    observed_price = round8(entry_price * (1.0 + price_shock_bps / 10000.0))
    gross_pnl = round8((observed_price - entry_price) * quantity)
    net_pnl = round8(gross_pnl - fee)
    pnl_bps = round8((net_pnl / entry_notional) * 10000.0) if entry_notional > 0 else 0.0

    if net_pnl > 0:
        status = SNAPSHOT_WIN
    elif net_pnl < 0:
        status = SNAPSHOT_LOSS
    else:
        status = SNAPSHOT_OPEN

    return {
        "snapshot_id": f"{run_label}-{position_id}-snapshot",
        "run_label": run_label,
        "created_at": created_at,
        "source_session_label": str(row_get(position, "session_label", "")),
        "position_id": position_id,
        "symbol": symbol,
        "strategy_id": strategy_id,
        "quantity": round8(quantity),
        "entry_price": round8(entry_price),
        "observed_price": observed_price,
        "entry_notional": round8(entry_notional),
        "gross_paper_pnl": gross_pnl,
        "simulated_fee_amount": round8(fee),
        "net_paper_pnl": net_pnl,
        "net_paper_pnl_bps": pnl_bps,
        "snapshot_status": status,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "performance_role": "PAPER_OBSERVATION_POSITION_SNAPSHOT_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def build_snapshots(
    run_label: str,
    created_at: str,
    positions: list[sqlite3.Row],
    price_shock_bps: float,
) -> list[dict[str, Any]]:
    return [
        build_position_snapshot(
            run_label=run_label,
            created_at=created_at,
            position=position,
            price_shock_bps=price_shock_bps,
        )
        for position in positions
    ]


def build_alert(
    run_label: str,
    created_at: str,
    capital_review_label: str,
    alert_type: str,
    observed_value: Any,
    threshold_value: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "alert_id": f"{run_label}-{alert_type}".replace(" ", "_"),
        "run_label": run_label,
        "created_at": created_at,
        "source_capital_review_label": capital_review_label,
        "alert_type": alert_type,
        "alert_status": ALERT_TRIGGERED,
        "observed_value": str(observed_value),
        "threshold_value": str(threshold_value),
        "alert_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "performance_role": "PAPER_OBSERVATION_ALERT_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def aggregate_pnl_by_key(snapshots: list[dict[str, Any]], key: str) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)

    for snapshot in snapshots:
        totals[str(snapshot[key])] += safe_float(snapshot["net_paper_pnl"])

    return {name: round8(value) for name, value in sorted(totals.items())}


def build_metrics(
    capital_review: sqlite3.Row | None,
    capital_decision: sqlite3.Row | None,
    session: sqlite3.Row | None,
    orders: list[sqlite3.Row],
    positions: list[sqlite3.Row],
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    paper_notional = safe_float(row_get(session, "paper_notional", row_get(capital_review, "paper_notional", 0.0)))

    if paper_notional <= 0:
        paper_notional = sum(safe_float(snapshot["entry_notional"]) for snapshot in snapshots)

    gross_pnl = round8(sum(safe_float(snapshot["gross_paper_pnl"]) for snapshot in snapshots))
    fees = round8(sum(safe_float(snapshot["simulated_fee_amount"]) for snapshot in snapshots))
    net_pnl = round8(sum(safe_float(snapshot["net_paper_pnl"]) for snapshot in snapshots))
    total_entry_notional = round8(sum(safe_float(snapshot["entry_notional"]) for snapshot in snapshots))

    net_pnl_bps = round8((net_pnl / paper_notional) * 10000.0) if paper_notional > 0 else 0.0
    fee_drag_bps = round8((fees / paper_notional) * 10000.0) if paper_notional > 0 else 0.0
    max_position_loss_bps = round8(min((safe_float(snapshot["net_paper_pnl_bps"]) for snapshot in snapshots), default=0.0))

    wins = sum(1 for snapshot in snapshots if safe_float(snapshot["net_paper_pnl"]) > 0)
    win_rate_pct = round8((wins / len(snapshots)) * 100.0) if snapshots else 0.0

    safety_count = 0
    for row in [capital_review, capital_decision, session, *orders, *positions, *snapshots]:
        if safety_problem(row):
            safety_count += 1

    return {
        "paper_notional": round8(paper_notional),
        "total_entry_notional": total_entry_notional,
        "monitored_position_count": len(snapshots),
        "order_count": len(orders),
        "gross_unrealized_paper_pnl": gross_pnl,
        "total_simulated_fees": fees,
        "net_paper_pnl": net_pnl,
        "net_paper_pnl_bps": net_pnl_bps,
        "max_position_loss_bps": max_position_loss_bps,
        "fee_drag_bps": fee_drag_bps,
        "win_rate_pct": win_rate_pct,
        "symbol_pnl": aggregate_pnl_by_key(snapshots, "symbol"),
        "strategy_pnl": aggregate_pnl_by_key(snapshots, "strategy_id"),
        "safety_breach_count": safety_count,
    }


def build_alerts(
    run_label: str,
    created_at: str,
    capital_review_label: str,
    capital_ready: bool,
    metrics: dict[str, Any],
    max_allowed_net_loss_bps: float,
    max_allowed_position_loss_bps: float,
    max_allowed_fee_drag_bps: float,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    if not capital_ready:
        alerts.append(
            build_alert(
                run_label,
                created_at,
                capital_review_label,
                "capital_readiness_not_approved",
                "not_ready",
                CAPITAL_APPROVED,
                "Capital readiness is not approved for extended paper observation.",
            )
        )

    if safe_float(metrics.get("net_paper_pnl_bps", 0.0)) < -abs(max_allowed_net_loss_bps):
        alerts.append(
            build_alert(
                run_label,
                created_at,
                capital_review_label,
                "net_loss_bps_limit",
                metrics.get("net_paper_pnl_bps", 0.0),
                f">= {-abs(max_allowed_net_loss_bps)}",
                "Net paper PnL breached the allowed observation loss threshold.",
            )
        )

    if safe_float(metrics.get("max_position_loss_bps", 0.0)) < -abs(max_allowed_position_loss_bps):
        alerts.append(
            build_alert(
                run_label,
                created_at,
                capital_review_label,
                "position_loss_bps_limit",
                metrics.get("max_position_loss_bps", 0.0),
                f">= {-abs(max_allowed_position_loss_bps)}",
                "At least one paper position breached the allowed position loss threshold.",
            )
        )

    if safe_float(metrics.get("fee_drag_bps", 0.0)) > max_allowed_fee_drag_bps:
        alerts.append(
            build_alert(
                run_label,
                created_at,
                capital_review_label,
                "fee_drag_bps_limit",
                metrics.get("fee_drag_bps", 0.0),
                f"<= {max_allowed_fee_drag_bps}",
                "Simulated fee drag breached the allowed observation threshold.",
            )
        )

    return alerts


def decide_performance_outcome(
    capital_review: sqlite3.Row | None,
    capital_ready: bool,
    snapshots: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    metrics: dict[str, Any],
    max_allowed_net_loss_bps: float,
    max_allowed_position_loss_bps: float,
) -> tuple[str, str, str, str, str, str]:
    if capital_review is None:
        return (
            PERFORMANCE_DECISION_REJECT_MISSING,
            PERFORMANCE_MISSING,
            ACTION_REVIEW_CAPITAL,
            "Mission 65 Capital Readiness Review",
            HEALTH_MISSING,
            "Capital readiness evidence is missing.",
        )

    if safe_int(metrics.get("safety_breach_count", 0)) > 0:
        return (
            PERFORMANCE_DECISION_BLOCK_SAFETY,
            PERFORMANCE_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 66 safety remediation",
            HEALTH_DANGER,
            "Safety invariant failed during paper observation performance monitoring.",
        )

    if not capital_ready:
        return (
            PERFORMANCE_DECISION_BLOCK_READINESS,
            PERFORMANCE_BLOCKED,
            ACTION_REVIEW_CAPITAL,
            "Mission 65 Capital Readiness Review",
            HEALTH_DANGER,
            "Capital readiness is not approved for extended paper observation.",
        )

    if not snapshots:
        return (
            PERFORMANCE_DECISION_REJECT_MISSING,
            PERFORMANCE_MISSING,
            ACTION_REVIEW_CAPITAL,
            "Mission 63 Paper Trading Sandbox",
            HEALTH_MISSING,
            "No paper positions were available for performance monitoring.",
        )

    net_loss_breached = safe_float(metrics.get("net_paper_pnl_bps", 0.0)) < -abs(max_allowed_net_loss_bps)
    position_loss_breached = safe_float(metrics.get("max_position_loss_bps", 0.0)) < -abs(max_allowed_position_loss_bps)

    if net_loss_breached or position_loss_breached:
        return (
            PERFORMANCE_DECISION_BLOCK_LOSS,
            PERFORMANCE_BLOCKED,
            ACTION_REVIEW_LOSS,
            "Mission 64 Institutional Risk Control Layer",
            HEALTH_DANGER,
            "Paper observation breached loss thresholds.",
        )

    if alerts:
        health = HEALTH_CAUTION
    elif safe_float(metrics.get("net_paper_pnl_bps", 0.0)) < 0:
        health = HEALTH_STABLE
    else:
        health = HEALTH_STABLE

    return (
        PERFORMANCE_DECISION_CONTINUE,
        PERFORMANCE_READY,
        ACTION_CONTINUE,
        "Mission 67 Paper Drawdown Kill Switch",
        health,
        "Paper observation performance is inside monitoring thresholds. Continue collecting paper snapshots.",
    )


def build_summary(
    db_path: str | Path,
    run_label: str,
    report_label: str,
    created_at: str,
    capital_review_label: str,
    capital_review: sqlite3.Row | None,
    session: sqlite3.Row | None,
    snapshots: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    metrics: dict[str, Any],
    performance_decision: str,
    global_verdict: str,
    recommended_action: str,
    next_mission: str,
    health: str,
    decision_reason: str,
) -> dict[str, Any]:
    source_session_label = row_get(capital_review, "source_session_label", row_get(session, "session_label", None))
    source_portfolio_label = row_get(capital_review, "source_portfolio_label", row_get(session, "source_portfolio_label", None))

    return {
        "run_label": run_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_capital_review_label": capital_review_label,
        "source_session_label": source_session_label,
        "source_portfolio_label": source_portfolio_label,
        "paper_notional": round8(safe_float(metrics.get("paper_notional", 0.0))),
        "total_entry_notional": round8(safe_float(metrics.get("total_entry_notional", 0.0))),
        "monitored_position_count": safe_int(metrics.get("monitored_position_count", 0)),
        "order_count": safe_int(metrics.get("order_count", 0)),
        "gross_unrealized_paper_pnl": round8(safe_float(metrics.get("gross_unrealized_paper_pnl", 0.0))),
        "total_simulated_fees": round8(safe_float(metrics.get("total_simulated_fees", 0.0))),
        "net_paper_pnl": round8(safe_float(metrics.get("net_paper_pnl", 0.0))),
        "net_paper_pnl_bps": round8(safe_float(metrics.get("net_paper_pnl_bps", 0.0))),
        "max_position_loss_bps": round8(safe_float(metrics.get("max_position_loss_bps", 0.0))),
        "fee_drag_bps": round8(safe_float(metrics.get("fee_drag_bps", 0.0))),
        "win_rate_pct": round8(safe_float(metrics.get("win_rate_pct", 0.0))),
        "symbol_pnl": metrics.get("symbol_pnl", {}),
        "strategy_pnl": metrics.get("strategy_pnl", {}),
        "position_snapshots": snapshots,
        "performance_alerts": alerts,
        "alert_count": len(alerts),
        "safety_breach_count": safe_int(metrics.get("safety_breach_count", 0)),
        "performance_health": health,
        "performance_decision": performance_decision,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
        "next_mission": next_mission,
        "decision_reason": decision_reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    position_lines = []

    for snapshot in summary["position_snapshots"]:
        position_lines.append(
            "- "
            + f"{snapshot['symbol']} {snapshot['strategy_id']}: "
            + f"entry_notional={snapshot['entry_notional']}, "
            + f"gross_pnl={snapshot['gross_paper_pnl']}, "
            + f"net_pnl={snapshot['net_paper_pnl']}, "
            + f"net_bps={snapshot['net_paper_pnl_bps']}"
        )

    alert_lines = []

    for alert in summary["performance_alerts"]:
        alert_lines.append(
            "- "
            + f"{alert['alert_type']}: "
            + f"observed={alert['observed_value']}, "
            + f"threshold={alert['threshold_value']}"
        )

    positions_markdown = "\n".join(position_lines) or "- None"
    alerts_markdown = "\n".join(alert_lines) or "- None"

    return f"""# DeltaGrid Mission 66 Paper Observation Performance Monitor Report

Report label: {summary['report_label']}
Run label: {summary['run_label']}
Created at: {summary['created_at']}
Source capital review label: {summary['source_capital_review_label']}
Source session label: {summary['source_session_label']}
Source portfolio label: {summary['source_portfolio_label']}

## Performance Summary

Paper notional: {summary['paper_notional']}
Total entry notional: {summary['total_entry_notional']}
Monitored position count: {summary['monitored_position_count']}
Order count: {summary['order_count']}

Gross unrealized paper PnL: {summary['gross_unrealized_paper_pnl']}
Total simulated fees: {summary['total_simulated_fees']}
Net paper PnL: {summary['net_paper_pnl']}
Net paper PnL bps: {summary['net_paper_pnl_bps']}
Max position loss bps: {summary['max_position_loss_bps']}
Fee drag bps: {summary['fee_drag_bps']}
Win rate pct: {summary['win_rate_pct']}

Alert count: {summary['alert_count']}
Safety breach count: {summary['safety_breach_count']}
Performance health: {summary['performance_health']}

## Position Snapshots

{positions_markdown}

## Alerts

{alerts_markdown}

## Decision

Performance decision: {summary['performance_decision']}
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

All monitoring is paper-only local analytics.
"""


def persist_run(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for snapshot in summary["position_snapshots"]:
            conn.execute(
                """
                INSERT OR REPLACE INTO paper_observation_position_snapshots (
                    snapshot_id,
                    run_label,
                    created_at,
                    source_session_label,
                    position_id,
                    symbol,
                    strategy_id,
                    quantity,
                    entry_price,
                    observed_price,
                    entry_notional,
                    gross_paper_pnl,
                    simulated_fee_amount,
                    net_paper_pnl,
                    net_paper_pnl_bps,
                    snapshot_status,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot["snapshot_id"],
                    snapshot["run_label"],
                    snapshot["created_at"],
                    snapshot["source_session_label"],
                    snapshot["position_id"],
                    snapshot["symbol"],
                    snapshot["strategy_id"],
                    str(snapshot["quantity"]),
                    str(snapshot["entry_price"]),
                    str(snapshot["observed_price"]),
                    str(snapshot["entry_notional"]),
                    str(snapshot["gross_paper_pnl"]),
                    str(snapshot["simulated_fee_amount"]),
                    str(snapshot["net_paper_pnl"]),
                    str(snapshot["net_paper_pnl_bps"]),
                    snapshot["snapshot_status"],
                    snapshot["live_trading"],
                    snapshot["live_order_sent"],
                    snapshot["capital_deployment"],
                    json.dumps(snapshot["metadata"], sort_keys=True),
                ),
            )

        for alert in summary["performance_alerts"]:
            conn.execute(
                """
                INSERT OR REPLACE INTO paper_observation_performance_alerts (
                    alert_id,
                    run_label,
                    created_at,
                    source_capital_review_label,
                    alert_type,
                    alert_status,
                    observed_value,
                    threshold_value,
                    alert_reason,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert["alert_id"],
                    alert["run_label"],
                    alert["created_at"],
                    alert["source_capital_review_label"],
                    alert["alert_type"],
                    alert["alert_status"],
                    alert["observed_value"],
                    alert["threshold_value"],
                    alert["alert_reason"],
                    alert["live_trading"],
                    alert["live_order_sent"],
                    alert["capital_deployment"],
                    json.dumps(alert["metadata"], sort_keys=True),
                ),
            )

        conn.execute(
            """
            INSERT OR REPLACE INTO paper_observation_performance_runs (
                run_label,
                report_label,
                created_at,
                source_capital_review_label,
                source_session_label,
                source_portfolio_label,
                paper_notional,
                monitored_position_count,
                order_count,
                gross_unrealized_paper_pnl,
                total_simulated_fees,
                net_paper_pnl,
                net_paper_pnl_bps,
                max_position_loss_bps,
                fee_drag_bps,
                win_rate_pct,
                alert_count,
                safety_breach_count,
                performance_health,
                performance_decision,
                global_verdict,
                recommended_action,
                next_mission,
                live_trading,
                live_order_sent,
                capital_deployment,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["run_label"],
                summary["report_label"],
                summary["created_at"],
                summary["source_capital_review_label"],
                summary["source_session_label"],
                summary["source_portfolio_label"],
                str(summary["paper_notional"]),
                summary["monitored_position_count"],
                summary["order_count"],
                str(summary["gross_unrealized_paper_pnl"]),
                str(summary["total_simulated_fees"]),
                str(summary["net_paper_pnl"]),
                str(summary["net_paper_pnl_bps"]),
                str(summary["max_position_loss_bps"]),
                str(summary["fee_drag_bps"]),
                str(summary["win_rate_pct"]),
                summary["alert_count"],
                summary["safety_breach_count"],
                summary["performance_health"],
                summary["performance_decision"],
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
            INSERT OR REPLACE INTO paper_observation_performance_reports (
                report_label,
                run_label,
                created_at,
                source_capital_review_label,
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
                summary["run_label"],
                summary["created_at"],
                summary["source_capital_review_label"],
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


def run_paper_observation_performance_monitor(
    db_path: str | Path = "offchain/deltagrid.db",
    run_label: str | None = None,
    report_label: str | None = None,
    capital_review_label: str = "mission65-final-confirm",
    symbols: str | list[str] | tuple[str, ...] | None = None,
    price_shock_bps: float = 0.0,
    max_allowed_net_loss_bps: float = 50.0,
    max_allowed_position_loss_bps: float = 75.0,
    max_allowed_fee_drag_bps: float = 5.0,
) -> dict[str, Any]:
    if max_allowed_net_loss_bps < 0:
        raise ValueError("max_allowed_net_loss_bps cannot be negative")

    if max_allowed_position_loss_bps < 0:
        raise ValueError("max_allowed_position_loss_bps cannot be negative")

    if max_allowed_fee_drag_bps < 0:
        raise ValueError("max_allowed_fee_drag_bps cannot be negative")

    db = Path(db_path)
    run = run_label or new_run_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    requested_symbols = parse_symbols(symbols)

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        capital_review = load_capital_review(conn, capital_review_label)
        capital_decision = load_capital_decision(conn, capital_review_label)

        session_label = row_get(capital_review, "source_session_label", None)
        session = load_session(conn, session_label)
        orders = load_orders(conn, session_label, requested_symbols)
        positions = load_positions(conn, session_label, requested_symbols)

    ready = capital_is_ready(capital_review, capital_decision)
    snapshots = build_snapshots(run, created_at, positions, price_shock_bps) if ready else []
    metrics = build_metrics(capital_review, capital_decision, session, orders, positions, snapshots)

    alerts = build_alerts(
        run_label=run,
        created_at=created_at,
        capital_review_label=capital_review_label,
        capital_ready=ready,
        metrics=metrics,
        max_allowed_net_loss_bps=max_allowed_net_loss_bps,
        max_allowed_position_loss_bps=max_allowed_position_loss_bps,
        max_allowed_fee_drag_bps=max_allowed_fee_drag_bps,
    )

    performance_decision, global_verdict, recommended_action, next_mission, health, decision_reason = decide_performance_outcome(
        capital_review=capital_review,
        capital_ready=ready,
        snapshots=snapshots,
        alerts=alerts,
        metrics=metrics,
        max_allowed_net_loss_bps=max_allowed_net_loss_bps,
        max_allowed_position_loss_bps=max_allowed_position_loss_bps,
    )

    summary = build_summary(
        db_path=db,
        run_label=run,
        report_label=report,
        created_at=created_at,
        capital_review_label=capital_review_label,
        capital_review=capital_review,
        session=session,
        snapshots=snapshots,
        alerts=alerts,
        metrics=metrics,
        performance_decision=performance_decision,
        global_verdict=global_verdict,
        recommended_action=recommended_action,
        next_mission=next_mission,
        health=health,
        decision_reason=decision_reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_run(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid paper observation performance monitor.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--run-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--capital-review-label", default="mission65-final-confirm")
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--price-shock-bps", type=float, default=0.0)
    parser.add_argument("--max-allowed-net-loss-bps", type=float, default=50.0)
    parser.add_argument("--max-allowed-position-loss-bps", type=float, default=75.0)
    parser.add_argument("--max-allowed-fee-drag-bps", type=float, default=5.0)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_paper_observation_performance_monitor(
        db_path=args.db,
        run_label=args.run_label,
        report_label=args.report_label,
        capital_review_label=args.capital_review_label,
        symbols=args.symbols,
        price_shock_bps=args.price_shock_bps,
        max_allowed_net_loss_bps=args.max_allowed_net_loss_bps,
        max_allowed_position_loss_bps=args.max_allowed_position_loss_bps,
        max_allowed_fee_drag_bps=args.max_allowed_fee_drag_bps,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

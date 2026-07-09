"""
Mission 57: Shadow Tracking Alert and Invalidation Router.

This module converts shadow tracking performance reports into alert routes.

It is a shadow risk-routing layer, not an execution layer.

It never:
- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- requires paid APIs
- requires real capital
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PERFORMANCE_REPORTS_TABLE = "shadow_tracking_performance_reports"

ROUTES_TABLE = "shadow_tracking_alert_routes"
REPORTS_TABLE = "shadow_tracking_alert_router_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

PERFORMANCE_STRONG = "TRACKING_PERFORMANCE_STRONG_SHADOW_ONLY"
PERFORMANCE_STABLE = "TRACKING_PERFORMANCE_STABLE_SHADOW_ONLY"
PERFORMANCE_DETERIORATING = "TRACKING_PERFORMANCE_DETERIORATING_SHADOW_ONLY"
PERFORMANCE_INVALIDATED = "TRACKING_PERFORMANCE_INVALIDATED_SHADOW_ONLY"
PERFORMANCE_NO_DATA = "TRACKING_PERFORMANCE_NO_MARKET_DATA"
PERFORMANCE_SAFETY_BREACH = "TRACKING_PERFORMANCE_SAFETY_BREACH_BLOCKED"

SYMBOL_HEALTH_STRONG = "SYMBOL_TRACKING_HEALTH_STRONG"
SYMBOL_HEALTH_STABLE = "SYMBOL_TRACKING_HEALTH_STABLE"
SYMBOL_HEALTH_WEAK = "SYMBOL_TRACKING_HEALTH_WEAK"
SYMBOL_HEALTH_INVALIDATED = "SYMBOL_TRACKING_HEALTH_INVALIDATED"
SYMBOL_HEALTH_NO_DATA = "SYMBOL_TRACKING_HEALTH_NO_DATA"
SYMBOL_HEALTH_BLOCKED = "SYMBOL_TRACKING_HEALTH_BLOCKED"

ROUTE_CONTINUE = "ALERT_ROUTE_CONTINUE_SHADOW_TRACKING"
ROUTE_WARNING = "ALERT_ROUTE_WARNING_WEAKENING_SHADOW_TRACKING"
ROUTE_INVALIDATE = "ALERT_ROUTE_INVALIDATE_SHADOW_OBSERVATION"
ROUTE_REFRESH_DATA = "ALERT_ROUTE_REFRESH_PUBLIC_DATA"
ROUTE_SAFETY_BLOCK = "ALERT_ROUTE_SAFETY_BLOCK_REVIEW"

SEVERITY_INFO = "INFO"
SEVERITY_WARNING = "WARNING"
SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_BLOCK = "BLOCK"

NO_PERFORMANCE_HISTORY_VERDICT = "ALERT_ROUTER_NO_PERFORMANCE_HISTORY"
MISSING_PERFORMANCE_TABLE_VERDICT = "ALERT_ROUTER_PERFORMANCE_TABLE_MISSING"
NO_MATCHING_PERFORMANCE_VERDICT = "ALERT_ROUTER_NO_MATCHING_PERFORMANCE_REPORT"
NO_SYMBOL_ROUTES_VERDICT = "ALERT_ROUTER_NO_SYMBOL_ROUTES"
SAFETY_BREACH_VERDICT = "ALERT_ROUTER_SAFETY_BREACH_BLOCKED"
INVALIDATION_VERDICT = "ALERT_ROUTER_INVALIDATION_REQUIRED_SHADOW_ONLY"
WARNING_VERDICT = "ALERT_ROUTER_WARNING_SHADOW_ONLY"
REFRESH_DATA_VERDICT = "ALERT_ROUTER_REFRESH_DATA_SHADOW_ONLY"
CONTINUE_VERDICT = "ALERT_ROUTER_CONTINUE_SHADOW_ONLY"

RECOMMEND_RUN_PERFORMANCE = "RUN_MISSION_56_PERFORMANCE_REPORTER_FIRST"
RECOMMEND_REVIEW_SAFETY = "STOP_AND_REVIEW_ALERT_ROUTER_SAFETY_STATE"
RECOMMEND_INVALIDATE = "MARK_SHADOW_OBSERVATIONS_INVALIDATED_NO_TRADING"
RECOMMEND_WARN = "CONTINUE_WITH_WARNING_AND_TIGHTER_THRESHOLDS"
RECOMMEND_REFRESH = "REFRESH_PUBLIC_DATA_AND_RERUN_TRACKING"
RECOMMEND_CONTINUE = "CONTINUE_SHADOW_TRACKING_ONLY"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_route_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission57-alert-router-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission57-report-{stamp}-{uuid.uuid4().hex[:8]}"


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


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
            raise ValueError(f"Only USDT perpetual symbols are supported for Mission 57: {symbol}")

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
            CREATE TABLE IF NOT EXISTS shadow_tracking_alert_routes (
                route_id TEXT PRIMARY KEY,
                route_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_performance_label TEXT NOT NULL,
                source_report_label TEXT NOT NULL,
                symbol TEXT NOT NULL,
                route_priority INTEGER NOT NULL,
                alert_severity TEXT NOT NULL,
                route_status TEXT NOT NULL,
                action_required TEXT NOT NULL,
                health_status TEXT NOT NULL,
                latest_update_status TEXT,
                average_updated_remaining_carry_bps TEXT NOT NULL,
                average_carry_drift_bps TEXT NOT NULL,
                average_latest_funding_bps TEXT NOT NULL,
                average_latest_spread_bps TEXT NOT NULL,
                average_remaining_funding_events TEXT NOT NULL,
                route_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_tracking_alert_router_reports (
                report_label TEXT PRIMARY KEY,
                route_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_performance_label TEXT,
                source_report_label TEXT,
                requested_symbol_count INTEGER NOT NULL,
                source_symbol_count INTEGER NOT NULL,
                route_count INTEGER NOT NULL,
                continue_route_count INTEGER NOT NULL,
                warning_route_count INTEGER NOT NULL,
                invalidation_route_count INTEGER NOT NULL,
                refresh_data_route_count INTEGER NOT NULL,
                safety_block_route_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                top_symbol TEXT,
                top_alert_severity TEXT,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def latest_performance_label(conn: sqlite3.Connection) -> str | None:
    if not table_exists(conn, PERFORMANCE_REPORTS_TABLE):
        return None

    row = conn.execute(
        """
        SELECT performance_label
        FROM shadow_tracking_performance_reports
        ORDER BY created_at DESC, report_label DESC
        LIMIT 1
        """
    ).fetchone()

    if row is not None:
        return str(row["performance_label"])

    return None


def load_performance_report(conn: sqlite3.Connection, performance_label: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM shadow_tracking_performance_reports
        WHERE performance_label = ?
        ORDER BY created_at DESC, report_label DESC
        LIMIT 1
        """,
        (performance_label,),
    ).fetchone()


def decode_summary(row: sqlite3.Row) -> dict[str, Any]:
    try:
        summary = json.loads(row["summary_json"])
    except (TypeError, ValueError, json.JSONDecodeError):
        summary = {}

    if not isinstance(summary, dict):
        summary = {}

    return summary


def filter_symbol_summaries(summary: dict[str, Any], symbols: list[str] | None) -> list[dict[str, Any]]:
    raw = summary.get("symbol_summaries", [])

    if not isinstance(raw, list):
        return []

    output: list[dict[str, Any]] = []

    for item in raw:
        if not isinstance(item, dict):
            continue

        symbol = str(item.get("symbol", "")).upper()

        if not symbol:
            continue

        if symbols is not None and symbol not in symbols:
            continue

        copied = dict(item)
        copied["symbol"] = symbol
        output.append(copied)

    return output


def route_for_symbol(
    route_label: str,
    created_at: str,
    source_performance_label: str,
    source_report_label: str,
    performance_verdict: str,
    performance_summary: dict[str, Any],
    symbol_summary: dict[str, Any],
    route_priority: int,
    min_continue_carry_bps: float,
    max_warning_spread_bps: float,
) -> dict[str, Any]:
    symbol = str(symbol_summary["symbol"])
    health_status = str(symbol_summary.get("health_status", "UNKNOWN"))
    latest_update_status = symbol_summary.get("latest_update_status")

    remaining_carry = safe_float(symbol_summary.get("average_updated_remaining_carry_bps"))
    carry_drift = safe_float(symbol_summary.get("average_carry_drift_bps"))
    funding_bps = safe_float(symbol_summary.get("average_latest_funding_bps"))
    spread_bps = safe_float(symbol_summary.get("average_latest_spread_bps"))
    remaining_events = safe_float(symbol_summary.get("average_remaining_funding_events"))

    performance_safety_breach = safe_int(performance_summary.get("safety_breach_count")) > 0

    if performance_safety_breach or performance_verdict == PERFORMANCE_SAFETY_BREACH or health_status == SYMBOL_HEALTH_BLOCKED:
        route_status = ROUTE_SAFETY_BLOCK
        alert_severity = SEVERITY_BLOCK
        action_required = "SAFETY_REVIEW_REQUIRED"
        reason = "Safety breach detected; block all shadow routing until reviewed."
    elif performance_verdict == PERFORMANCE_INVALIDATED or health_status == SYMBOL_HEALTH_INVALIDATED:
        route_status = ROUTE_INVALIDATE
        alert_severity = SEVERITY_CRITICAL
        action_required = "INVALIDATE_SHADOW_OBSERVATION"
        reason = "Performance report indicates invalidated shadow tracking."
    elif performance_verdict == PERFORMANCE_NO_DATA or health_status == SYMBOL_HEALTH_NO_DATA:
        route_status = ROUTE_REFRESH_DATA
        alert_severity = SEVERITY_WARNING
        action_required = "REFRESH_PUBLIC_DATA"
        reason = "Tracking data is missing or stale; refresh public dataset."
    elif (
        health_status == SYMBOL_HEALTH_STRONG
        and remaining_carry >= min_continue_carry_bps
        and spread_bps <= max_warning_spread_bps
        and funding_bps >= 0
    ):
        route_status = ROUTE_CONTINUE
        alert_severity = SEVERITY_INFO
        action_required = "CONTINUE_SHADOW_TRACKING"
        reason = "Symbol tracking is strong and remains inside continuation thresholds."
    elif health_status in {SYMBOL_HEALTH_STABLE, SYMBOL_HEALTH_WEAK} or spread_bps > max_warning_spread_bps:
        route_status = ROUTE_WARNING
        alert_severity = SEVERITY_WARNING
        action_required = "CONTINUE_WITH_WARNING"
        reason = "Symbol tracking is not invalidated but requires tighter monitoring."
    elif performance_verdict == PERFORMANCE_DETERIORATING:
        route_status = ROUTE_WARNING
        alert_severity = SEVERITY_WARNING
        action_required = "REVIEW_DETERIORATING_TRACKING"
        reason = "Aggregate tracking performance is deteriorating."
    else:
        route_status = ROUTE_WARNING
        alert_severity = SEVERITY_WARNING
        action_required = "REVIEW_UNCLASSIFIED_TRACKING_STATE"
        reason = "Symbol state is not strongly classified; review before continuing."

    return {
        "route_id": f"{route_label}-{symbol}",
        "route_label": route_label,
        "created_at": created_at,
        "source_performance_label": source_performance_label,
        "source_report_label": source_report_label,
        "symbol": symbol,
        "route_priority": route_priority,
        "alert_severity": alert_severity,
        "route_status": route_status,
        "action_required": action_required,
        "health_status": health_status,
        "latest_update_status": latest_update_status,
        "average_updated_remaining_carry_bps": round(remaining_carry, 8),
        "average_carry_drift_bps": round(carry_drift, 8),
        "average_latest_funding_bps": round(funding_bps, 8),
        "average_latest_spread_bps": round(spread_bps, 8),
        "average_remaining_funding_events": round(remaining_events, 8),
        "route_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "router_role": "SHADOW_ALERT_AND_INVALIDATION_ROUTING_ONLY",
            "performance_verdict": performance_verdict,
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def persist_routes(db_path: str | Path, routes: list[dict[str, Any]]) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for route in routes:
            conn.execute(
                """
                INSERT OR REPLACE INTO shadow_tracking_alert_routes (
                    route_id,
                    route_label,
                    created_at,
                    source_performance_label,
                    source_report_label,
                    symbol,
                    route_priority,
                    alert_severity,
                    route_status,
                    action_required,
                    health_status,
                    latest_update_status,
                    average_updated_remaining_carry_bps,
                    average_carry_drift_bps,
                    average_latest_funding_bps,
                    average_latest_spread_bps,
                    average_remaining_funding_events,
                    route_reason,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    route["route_id"],
                    route["route_label"],
                    route["created_at"],
                    route["source_performance_label"],
                    route["source_report_label"],
                    route["symbol"],
                    route["route_priority"],
                    route["alert_severity"],
                    route["route_status"],
                    route["action_required"],
                    route["health_status"],
                    route["latest_update_status"],
                    str(route["average_updated_remaining_carry_bps"]),
                    str(route["average_carry_drift_bps"]),
                    str(route["average_latest_funding_bps"]),
                    str(route["average_latest_spread_bps"]),
                    str(route["average_remaining_funding_events"]),
                    route["route_reason"],
                    route["live_trading"],
                    route["live_order_sent"],
                    route["capital_deployment"],
                    json.dumps(route["metadata"], sort_keys=True),
                ),
            )

        conn.commit()


def summarize_router(
    db_path: str | Path,
    route_label: str,
    report_label: str,
    created_at: str,
    source_performance_label: str | None,
    source_report_label: str | None,
    requested_symbols: list[str] | None,
    source_symbols: list[dict[str, Any]],
    routes: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts = Counter(route["route_status"] for route in routes)

    continue_count = status_counts.get(ROUTE_CONTINUE, 0)
    warning_count = status_counts.get(ROUTE_WARNING, 0)
    invalidation_count = status_counts.get(ROUTE_INVALIDATE, 0)
    refresh_count = status_counts.get(ROUTE_REFRESH_DATA, 0)
    safety_block_count = status_counts.get(ROUTE_SAFETY_BLOCK, 0)

    safety_breach_count = safety_block_count
    safety_breach_count += sum(
        1
        for route in routes
        if route["live_trading"] != LIVE_TRADING_STATUS
        or int(route["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or route["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS
    )

    top_symbol = routes[0]["symbol"] if routes else None
    top_severity = routes[0]["alert_severity"] if routes else None

    if safety_breach_count > 0:
        global_verdict = SAFETY_BREACH_VERDICT
        recommended_action = RECOMMEND_REVIEW_SAFETY
    elif not routes and not source_symbols:
        global_verdict = NO_SYMBOL_ROUTES_VERDICT
        recommended_action = RECOMMEND_RUN_PERFORMANCE
    elif invalidation_count > 0:
        global_verdict = INVALIDATION_VERDICT
        recommended_action = RECOMMEND_INVALIDATE
    elif warning_count > 0:
        global_verdict = WARNING_VERDICT
        recommended_action = RECOMMEND_WARN
    elif refresh_count > 0:
        global_verdict = REFRESH_DATA_VERDICT
        recommended_action = RECOMMEND_REFRESH
    else:
        global_verdict = CONTINUE_VERDICT
        recommended_action = RECOMMEND_CONTINUE

    return {
        "report_label": report_label,
        "route_label": route_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_performance_label": source_performance_label,
        "source_report_label": source_report_label,
        "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
        "source_symbol_count": len(source_symbols),
        "route_count": len(routes),
        "continue_route_count": continue_count,
        "warning_route_count": warning_count,
        "invalidation_route_count": invalidation_count,
        "refresh_data_route_count": refresh_count,
        "safety_block_route_count": safety_block_count,
        "safety_breach_count": safety_breach_count,
        "top_symbol": top_symbol,
        "top_alert_severity": top_severity,
        "route_status_counts": dict(status_counts),
        "routes": routes,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    route_lines = []

    for route in summary["routes"]:
        route_lines.append(
            "- "
            + f"priority={route['route_priority']} "
            + f"{route['symbol']}: "
            + f"severity={route['alert_severity']}, "
            + f"route={route['route_status']}, "
            + f"action={route['action_required']}, "
            + f"health={route['health_status']}, "
            + f"avg_remaining_carry_bps={route['average_updated_remaining_carry_bps']}"
        )

    routes_markdown = "\n".join(route_lines) or "- None"

    return f"""# DeltaGrid Mission 57 Shadow Tracking Alert and Invalidation Router Report

Report label: {summary['report_label']}
Route label: {summary['route_label']}
Created at: {summary['created_at']}
Source performance label: {summary['source_performance_label']}
Source report label: {summary['source_report_label']}

## Router Summary

Source symbol count: {summary['source_symbol_count']}
Route count: {summary['route_count']}
Continue route count: {summary['continue_route_count']}
Warning route count: {summary['warning_route_count']}
Invalidation route count: {summary['invalidation_route_count']}
Refresh data route count: {summary['refresh_data_route_count']}
Safety block route count: {summary['safety_block_route_count']}
Safety breach count: {summary['safety_breach_count']}

Top symbol: {summary['top_symbol']}
Top alert severity: {summary['top_alert_severity']}

## Alert Routes

{routes_markdown}

## Verdict

Global verdict: {summary['global_verdict']}
Recommended action: {summary['recommended_action']}

## Safety Statement

Live trading remains disabled.
Capital deployment remains blocked.
No private keys were read.
No signatures were produced.
No exchange orders were sent.
No real capital was used.
No paid APIs were used.
"""


def persist_report(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO shadow_tracking_alert_router_reports (
                report_label,
                route_label,
                created_at,
                source_performance_label,
                source_report_label,
                requested_symbol_count,
                source_symbol_count,
                route_count,
                continue_route_count,
                warning_route_count,
                invalidation_route_count,
                refresh_data_route_count,
                safety_block_route_count,
                safety_breach_count,
                top_symbol,
                top_alert_severity,
                global_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["route_label"],
                summary["created_at"],
                summary["source_performance_label"],
                summary["source_report_label"],
                summary["requested_symbol_count"],
                summary["source_symbol_count"],
                summary["route_count"],
                summary["continue_route_count"],
                summary["warning_route_count"],
                summary["invalidation_route_count"],
                summary["refresh_data_route_count"],
                summary["safety_block_route_count"],
                summary["safety_breach_count"],
                summary["top_symbol"],
                summary["top_alert_severity"],
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def run_shadow_tracking_alert_invalidation_router(
    db_path: str | Path = "offchain/deltagrid.db",
    route_label: str | None = None,
    report_label: str | None = None,
    performance_label: str | None = None,
    symbols: str | list[str] | tuple[str, ...] | None = None,
    min_continue_carry_bps: float = 10.0,
    max_warning_spread_bps: float = 1.0,
) -> dict[str, Any]:
    db = Path(db_path)
    label = route_label or new_route_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    if min_continue_carry_bps < 0:
        raise ValueError("min_continue_carry_bps must be non-negative")

    if max_warning_spread_bps < 0:
        raise ValueError("max_warning_spread_bps must be non-negative")

    requested_symbols = parse_symbols(symbols)

    if not db.exists():
        summary = {
            "report_label": report,
            "route_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": False,
            "source_performance_label": performance_label,
            "source_report_label": None,
            "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
            "source_symbol_count": 0,
            "route_count": 0,
            "continue_route_count": 0,
            "warning_route_count": 0,
            "invalidation_route_count": 0,
            "refresh_data_route_count": 0,
            "safety_block_route_count": 0,
            "safety_breach_count": 0,
            "top_symbol": None,
            "top_alert_severity": None,
            "route_status_counts": {},
            "routes": [],
            "global_verdict": NO_PERFORMANCE_HISTORY_VERDICT,
            "recommended_action": RECOMMEND_RUN_PERFORMANCE,
        }
        summary["markdown_report"] = build_markdown_report(summary)
        return summary

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        if not table_exists(conn, PERFORMANCE_REPORTS_TABLE):
            summary = {
                "report_label": report,
                "route_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "missing_tables": [PERFORMANCE_REPORTS_TABLE],
                "source_performance_label": performance_label,
                "source_report_label": None,
                "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
                "source_symbol_count": 0,
                "route_count": 0,
                "continue_route_count": 0,
                "warning_route_count": 0,
                "invalidation_route_count": 0,
                "refresh_data_route_count": 0,
                "safety_block_route_count": 0,
                "safety_breach_count": 0,
                "top_symbol": None,
                "top_alert_severity": None,
                "route_status_counts": {},
                "routes": [],
                "global_verdict": MISSING_PERFORMANCE_TABLE_VERDICT,
                "recommended_action": RECOMMEND_RUN_PERFORMANCE,
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        resolved_performance_label = performance_label or latest_performance_label(conn)

        if resolved_performance_label is None:
            summary = {
                "report_label": report,
                "route_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "source_performance_label": None,
                "source_report_label": None,
                "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
                "source_symbol_count": 0,
                "route_count": 0,
                "continue_route_count": 0,
                "warning_route_count": 0,
                "invalidation_route_count": 0,
                "refresh_data_route_count": 0,
                "safety_block_route_count": 0,
                "safety_breach_count": 0,
                "top_symbol": None,
                "top_alert_severity": None,
                "route_status_counts": {},
                "routes": [],
                "global_verdict": NO_MATCHING_PERFORMANCE_VERDICT,
                "recommended_action": RECOMMEND_RUN_PERFORMANCE,
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        row = load_performance_report(conn, resolved_performance_label)

    if row is None:
        summary = {
            "report_label": report,
            "route_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": True,
            "source_performance_label": resolved_performance_label,
            "source_report_label": None,
            "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
            "source_symbol_count": 0,
            "route_count": 0,
            "continue_route_count": 0,
            "warning_route_count": 0,
            "invalidation_route_count": 0,
            "refresh_data_route_count": 0,
            "safety_block_route_count": 0,
            "safety_breach_count": 0,
            "top_symbol": None,
            "top_alert_severity": None,
            "route_status_counts": {},
            "routes": [],
            "global_verdict": NO_MATCHING_PERFORMANCE_VERDICT,
            "recommended_action": RECOMMEND_RUN_PERFORMANCE,
        }
        summary["markdown_report"] = build_markdown_report(summary)
        persist_report(db, summary, summary["markdown_report"])
        return summary

    performance_summary = decode_summary(row)
    performance_verdict = str(row["global_verdict"])
    source_report_label = str(row["report_label"])

    symbol_summaries = filter_symbol_summaries(performance_summary, requested_symbols)

    routes = [
        route_for_symbol(
            route_label=label,
            created_at=created_at,
            source_performance_label=resolved_performance_label,
            source_report_label=source_report_label,
            performance_verdict=performance_verdict,
            performance_summary=performance_summary,
            symbol_summary=symbol_summary,
            route_priority=index,
            min_continue_carry_bps=min_continue_carry_bps,
            max_warning_spread_bps=max_warning_spread_bps,
        )
        for index, symbol_summary in enumerate(symbol_summaries, start=1)
    ]

    persist_routes(db, routes)

    summary = summarize_router(
        db_path=db,
        route_label=label,
        report_label=report,
        created_at=created_at,
        source_performance_label=resolved_performance_label,
        source_report_label=source_report_label,
        requested_symbols=requested_symbols,
        source_symbols=symbol_summaries,
        routes=routes,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_report(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid shadow tracking alert and invalidation router."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--route-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--performance-label", default=None)
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--min-continue-carry-bps", type=float, default=10.0)
    parser.add_argument("--max-warning-spread-bps", type=float, default=1.0)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_shadow_tracking_alert_invalidation_router(
        db_path=args.db,
        route_label=args.route_label,
        report_label=args.report_label,
        performance_label=args.performance_label,
        symbols=args.symbols,
        min_continue_carry_bps=args.min_continue_carry_bps,
        max_warning_spread_bps=args.max_warning_spread_bps,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

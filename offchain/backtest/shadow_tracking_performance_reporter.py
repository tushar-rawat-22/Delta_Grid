"""
Mission 56: Shadow Tracking Performance Reporter.

This module summarizes shadow ledger tracking updates into performance
reports.

It is a shadow analytics layer, not an execution layer.

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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TRACKING_UPDATES_TABLE = "shadow_ledger_tracking_updates"
TRACKING_UPDATE_REPORTS_TABLE = "shadow_ledger_tracking_update_reports"

PERFORMANCE_REPORTS_TABLE = "shadow_tracking_performance_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

UPDATE_STATUS_ACTIVE = "TRACKING_UPDATE_ACTIVE_SHADOW_ONLY"
UPDATE_STATUS_INVALIDATED_NEGATIVE_FUNDING = "TRACKING_UPDATE_INVALIDATED_NEGATIVE_FUNDING"
UPDATE_STATUS_INVALIDATED_COST_DRIFT = "TRACKING_UPDATE_INVALIDATED_COST_DRIFT"
UPDATE_STATUS_COMPLETE = "TRACKING_UPDATE_COMPLETE_SHADOW_ONLY"
UPDATE_STATUS_BLOCKED_SAFETY = "TRACKING_UPDATE_BLOCKED_SAFETY_REVIEW"
UPDATE_STATUS_NO_MARKET_DATA = "TRACKING_UPDATE_NO_MARKET_DATA"

SYMBOL_HEALTH_STRONG = "SYMBOL_TRACKING_HEALTH_STRONG"
SYMBOL_HEALTH_STABLE = "SYMBOL_TRACKING_HEALTH_STABLE"
SYMBOL_HEALTH_WEAK = "SYMBOL_TRACKING_HEALTH_WEAK"
SYMBOL_HEALTH_INVALIDATED = "SYMBOL_TRACKING_HEALTH_INVALIDATED"
SYMBOL_HEALTH_NO_DATA = "SYMBOL_TRACKING_HEALTH_NO_DATA"
SYMBOL_HEALTH_BLOCKED = "SYMBOL_TRACKING_HEALTH_BLOCKED"

NO_TRACKING_HISTORY_VERDICT = "TRACKING_PERFORMANCE_NO_TRACKING_HISTORY"
MISSING_TRACKING_TABLE_VERDICT = "TRACKING_PERFORMANCE_TABLE_MISSING"
NO_MATCHING_UPDATES_VERDICT = "TRACKING_PERFORMANCE_NO_MATCHING_UPDATES"
SAFETY_BREACH_VERDICT = "TRACKING_PERFORMANCE_SAFETY_BREACH_BLOCKED"
STRONG_VERDICT = "TRACKING_PERFORMANCE_STRONG_SHADOW_ONLY"
STABLE_VERDICT = "TRACKING_PERFORMANCE_STABLE_SHADOW_ONLY"
DETERIORATING_VERDICT = "TRACKING_PERFORMANCE_DETERIORATING_SHADOW_ONLY"
INVALIDATED_VERDICT = "TRACKING_PERFORMANCE_INVALIDATED_SHADOW_ONLY"
NO_DATA_VERDICT = "TRACKING_PERFORMANCE_NO_MARKET_DATA"

RECOMMEND_RUN_TRACKER = "RUN_MISSION_55_TRACKING_UPDATER_FIRST"
RECOMMEND_REVIEW_SAFETY = "STOP_AND_REVIEW_TRACKING_PERFORMANCE_SAFETY_STATE"
RECOMMEND_CONTINUE_SHADOW = "CONTINUE_SHADOW_TRACKING_ONLY"
RECOMMEND_TIGHTEN_THRESHOLDS = "TIGHTEN_SHADOW_TRACKING_THRESHOLDS_AND_CONTINUE_OBSERVATION"
RECOMMEND_REVIEW_INVALIDATED = "REVIEW_INVALIDATED_OBSERVATIONS_NO_TRADING"
RECOMMEND_REFRESH_DATA = "REFRESH_PUBLIC_DATA_AND_RERUN_TRACKING"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_performance_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission56-performance-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission56-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
            raise ValueError(f"Only USDT perpetual symbols are supported for Mission 56: {symbol}")

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
            CREATE TABLE IF NOT EXISTS shadow_tracking_performance_reports (
                report_label TEXT PRIMARY KEY,
                performance_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_update_label TEXT,
                requested_symbol_count INTEGER NOT NULL,
                tracking_update_count INTEGER NOT NULL,
                active_count INTEGER NOT NULL,
                invalidated_count INTEGER NOT NULL,
                complete_count INTEGER NOT NULL,
                no_market_data_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                average_updated_remaining_carry_bps TEXT NOT NULL,
                average_carry_drift_bps TEXT NOT NULL,
                average_latest_funding_bps TEXT NOT NULL,
                average_latest_spread_bps TEXT NOT NULL,
                average_remaining_funding_events TEXT NOT NULL,
                strongest_symbol TEXT,
                weakest_symbol TEXT,
                strongest_updated_remaining_carry_bps TEXT NOT NULL,
                weakest_updated_remaining_carry_bps TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def latest_update_label(conn: sqlite3.Connection) -> str | None:
    if table_exists(conn, TRACKING_UPDATE_REPORTS_TABLE):
        row = conn.execute(
            """
            SELECT update_label
            FROM shadow_ledger_tracking_update_reports
            ORDER BY created_at DESC, report_label DESC
            LIMIT 1
            """
        ).fetchone()

        if row is not None:
            return str(row["update_label"])

    if table_exists(conn, TRACKING_UPDATES_TABLE):
        row = conn.execute(
            """
            SELECT update_label
            FROM shadow_ledger_tracking_updates
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()

        if row is not None:
            return str(row["update_label"])

    return None


def load_tracking_updates(
    conn: sqlite3.Connection,
    update_label: str,
    symbols: list[str] | None,
) -> list[sqlite3.Row]:
    params: list[Any] = [update_label]
    symbol_clause = ""

    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        symbol_clause = f" AND symbol IN ({placeholders})"
        params.extend(symbols)

    query = f"""
        SELECT *
        FROM shadow_ledger_tracking_updates
        WHERE update_label = ?
        {symbol_clause}
        ORDER BY updated_expected_remaining_carry_bps DESC, symbol ASC
    """

    return conn.execute(query, params).fetchall()


def update_has_safety_breach(row: sqlite3.Row) -> bool:
    return (
        row["live_trading"] != LIVE_TRADING_STATUS
        or int(row["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or row["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS
        or row["update_status"] == UPDATE_STATUS_BLOCKED_SAFETY
    )


def summarize_symbol(
    symbol: str,
    rows: list[sqlite3.Row],
    strong_carry_bps: float,
    min_funding_bps: float,
    max_spread_bps: float,
) -> dict[str, Any]:
    update_count = len(rows)
    active_count = sum(1 for row in rows if row["update_status"] == UPDATE_STATUS_ACTIVE)
    invalidated_count = sum(
        1
        for row in rows
        if row["update_status"] in {UPDATE_STATUS_INVALIDATED_NEGATIVE_FUNDING, UPDATE_STATUS_INVALIDATED_COST_DRIFT}
    )
    complete_count = sum(1 for row in rows if row["update_status"] == UPDATE_STATUS_COMPLETE)
    no_data_count = sum(1 for row in rows if row["update_status"] == UPDATE_STATUS_NO_MARKET_DATA)
    blocked_count = sum(1 for row in rows if update_has_safety_breach(row))

    latest_row = rows[0] if rows else None

    avg_remaining_carry = 0.0
    avg_carry_drift = 0.0
    avg_funding = 0.0
    avg_spread = 0.0
    avg_remaining_events = 0.0

    if rows:
        avg_remaining_carry = round(
            sum(safe_float(row["updated_expected_remaining_carry_bps"]) for row in rows) / len(rows),
            8,
        )
        avg_carry_drift = round(
            sum(safe_float(row["carry_drift_bps"]) for row in rows) / len(rows),
            8,
        )
        avg_funding = round(
            sum(safe_float(row["latest_funding_rate_bps"]) for row in rows) / len(rows),
            8,
        )
        avg_spread = round(
            sum(safe_float(row["latest_spread_bps"]) for row in rows) / len(rows),
            8,
        )
        avg_remaining_events = round(
            sum(safe_int(row["remaining_funding_events_after_update"]) for row in rows) / len(rows),
            8,
        )

    if blocked_count > 0:
        health = SYMBOL_HEALTH_BLOCKED
    elif no_data_count == update_count and update_count > 0:
        health = SYMBOL_HEALTH_NO_DATA
    elif invalidated_count > 0:
        health = SYMBOL_HEALTH_INVALIDATED
    elif active_count > 0 and avg_remaining_carry >= strong_carry_bps and avg_funding >= min_funding_bps and avg_spread <= max_spread_bps:
        health = SYMBOL_HEALTH_STRONG
    elif active_count > 0 and avg_remaining_carry > 0:
        health = SYMBOL_HEALTH_STABLE
    else:
        health = SYMBOL_HEALTH_WEAK

    return {
        "symbol": symbol,
        "update_count": update_count,
        "active_count": active_count,
        "invalidated_count": invalidated_count,
        "complete_count": complete_count,
        "no_market_data_count": no_data_count,
        "blocked_count": blocked_count,
        "average_updated_remaining_carry_bps": avg_remaining_carry,
        "average_carry_drift_bps": avg_carry_drift,
        "average_latest_funding_bps": avg_funding,
        "average_latest_spread_bps": avg_spread,
        "average_remaining_funding_events": avg_remaining_events,
        "latest_update_status": latest_row["update_status"] if latest_row else None,
        "latest_observation_state": latest_row["observation_state_after"] if latest_row else None,
        "health_status": health,
    }


def build_symbol_summaries(
    updates: list[sqlite3.Row],
    strong_carry_bps: float,
    min_funding_bps: float,
    max_spread_bps: float,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)

    for row in updates:
        grouped[str(row["symbol"])].append(row)

    summaries = [
        summarize_symbol(
            symbol=symbol,
            rows=rows,
            strong_carry_bps=strong_carry_bps,
            min_funding_bps=min_funding_bps,
            max_spread_bps=max_spread_bps,
        )
        for symbol, rows in grouped.items()
    ]

    summaries.sort(
        key=lambda item: (
            item["average_updated_remaining_carry_bps"],
            item["average_carry_drift_bps"],
        ),
        reverse=True,
    )

    return summaries


def summarize_performance(
    db_path: str | Path,
    performance_label: str,
    report_label: str,
    created_at: str,
    source_update_label: str | None,
    requested_symbols: list[str] | None,
    updates: list[sqlite3.Row],
    strong_carry_bps: float,
    min_funding_bps: float,
    max_spread_bps: float,
) -> dict[str, Any]:
    status_counts = Counter(row["update_status"] for row in updates)

    active_count = status_counts.get(UPDATE_STATUS_ACTIVE, 0)
    invalidated_count = (
        status_counts.get(UPDATE_STATUS_INVALIDATED_NEGATIVE_FUNDING, 0)
        + status_counts.get(UPDATE_STATUS_INVALIDATED_COST_DRIFT, 0)
    )
    complete_count = status_counts.get(UPDATE_STATUS_COMPLETE, 0)
    no_market_data_count = status_counts.get(UPDATE_STATUS_NO_MARKET_DATA, 0)
    safety_breach_count = sum(1 for row in updates if update_has_safety_breach(row))

    average_remaining_carry = 0.0
    average_carry_drift = 0.0
    average_funding = 0.0
    average_spread = 0.0
    average_remaining_events = 0.0

    if updates:
        average_remaining_carry = round(
            sum(safe_float(row["updated_expected_remaining_carry_bps"]) for row in updates) / len(updates),
            8,
        )
        average_carry_drift = round(
            sum(safe_float(row["carry_drift_bps"]) for row in updates) / len(updates),
            8,
        )
        average_funding = round(
            sum(safe_float(row["latest_funding_rate_bps"]) for row in updates) / len(updates),
            8,
        )
        average_spread = round(
            sum(safe_float(row["latest_spread_bps"]) for row in updates) / len(updates),
            8,
        )
        average_remaining_events = round(
            sum(safe_int(row["remaining_funding_events_after_update"]) for row in updates) / len(updates),
            8,
        )

    symbol_summaries = build_symbol_summaries(
        updates=updates,
        strong_carry_bps=strong_carry_bps,
        min_funding_bps=min_funding_bps,
        max_spread_bps=max_spread_bps,
    )

    strongest_symbol = symbol_summaries[0]["symbol"] if symbol_summaries else None
    weakest_symbol = symbol_summaries[-1]["symbol"] if symbol_summaries else None

    strongest_carry = (
        symbol_summaries[0]["average_updated_remaining_carry_bps"] if symbol_summaries else 0.0
    )
    weakest_carry = (
        symbol_summaries[-1]["average_updated_remaining_carry_bps"] if symbol_summaries else 0.0
    )

    if safety_breach_count > 0:
        global_verdict = SAFETY_BREACH_VERDICT
        recommended_action = RECOMMEND_REVIEW_SAFETY
    elif not updates:
        global_verdict = NO_MATCHING_UPDATES_VERDICT
        recommended_action = RECOMMEND_RUN_TRACKER
    elif no_market_data_count == len(updates):
        global_verdict = NO_DATA_VERDICT
        recommended_action = RECOMMEND_REFRESH_DATA
    elif invalidated_count > 0:
        global_verdict = INVALIDATED_VERDICT
        recommended_action = RECOMMEND_REVIEW_INVALIDATED
    elif active_count > 0 and average_remaining_carry >= strong_carry_bps and average_carry_drift > 0:
        global_verdict = STRONG_VERDICT
        recommended_action = RECOMMEND_CONTINUE_SHADOW
    elif active_count > 0 and average_remaining_carry > 0:
        global_verdict = STABLE_VERDICT
        recommended_action = RECOMMEND_TIGHTEN_THRESHOLDS
    else:
        global_verdict = DETERIORATING_VERDICT
        recommended_action = RECOMMEND_REVIEW_INVALIDATED

    return {
        "report_label": report_label,
        "performance_label": performance_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_update_label": source_update_label,
        "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
        "tracking_update_count": len(updates),
        "active_count": active_count,
        "invalidated_count": invalidated_count,
        "complete_count": complete_count,
        "no_market_data_count": no_market_data_count,
        "safety_breach_count": safety_breach_count,
        "average_updated_remaining_carry_bps": average_remaining_carry,
        "average_carry_drift_bps": average_carry_drift,
        "average_latest_funding_bps": average_funding,
        "average_latest_spread_bps": average_spread,
        "average_remaining_funding_events": average_remaining_events,
        "strongest_symbol": strongest_symbol,
        "weakest_symbol": weakest_symbol,
        "strongest_updated_remaining_carry_bps": round(strongest_carry, 8),
        "weakest_updated_remaining_carry_bps": round(weakest_carry, 8),
        "update_status_counts": dict(status_counts),
        "symbol_summaries": symbol_summaries,
        "thresholds": {
            "strong_carry_bps": strong_carry_bps,
            "min_funding_bps": min_funding_bps,
            "max_spread_bps": max_spread_bps,
        },
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    symbol_lines = []

    for item in summary["symbol_summaries"]:
        symbol_lines.append(
            "- "
            + item["symbol"]
            + ": "
            + f"health={item['health_status']}, "
            + f"active={item['active_count']}, "
            + f"invalidated={item['invalidated_count']}, "
            + f"avg_remaining_carry_bps={item['average_updated_remaining_carry_bps']}, "
            + f"avg_drift_bps={item['average_carry_drift_bps']}, "
            + f"avg_funding_bps={item['average_latest_funding_bps']}, "
            + f"avg_spread_bps={item['average_latest_spread_bps']}, "
            + f"avg_remaining_events={item['average_remaining_funding_events']}"
        )

    symbols_markdown = "\n".join(symbol_lines) or "- None"

    return f"""# DeltaGrid Mission 56 Shadow Tracking Performance Reporter

Report label: {summary['report_label']}
Performance label: {summary['performance_label']}
Created at: {summary['created_at']}
Source update label: {summary['source_update_label']}

## Performance Summary

Tracking update count: {summary['tracking_update_count']}
Active count: {summary['active_count']}
Invalidated count: {summary['invalidated_count']}
Complete count: {summary['complete_count']}
No market data count: {summary['no_market_data_count']}
Safety breach count: {summary['safety_breach_count']}

Average updated remaining carry bps: {summary['average_updated_remaining_carry_bps']}
Average carry drift bps: {summary['average_carry_drift_bps']}
Average latest funding bps: {summary['average_latest_funding_bps']}
Average latest spread bps: {summary['average_latest_spread_bps']}
Average remaining funding events: {summary['average_remaining_funding_events']}

Strongest symbol: {summary['strongest_symbol']}
Weakest symbol: {summary['weakest_symbol']}

## Symbol Performance

{symbols_markdown}

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
            INSERT OR REPLACE INTO shadow_tracking_performance_reports (
                report_label,
                performance_label,
                created_at,
                source_update_label,
                requested_symbol_count,
                tracking_update_count,
                active_count,
                invalidated_count,
                complete_count,
                no_market_data_count,
                safety_breach_count,
                average_updated_remaining_carry_bps,
                average_carry_drift_bps,
                average_latest_funding_bps,
                average_latest_spread_bps,
                average_remaining_funding_events,
                strongest_symbol,
                weakest_symbol,
                strongest_updated_remaining_carry_bps,
                weakest_updated_remaining_carry_bps,
                global_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["performance_label"],
                summary["created_at"],
                summary["source_update_label"],
                summary["requested_symbol_count"],
                summary["tracking_update_count"],
                summary["active_count"],
                summary["invalidated_count"],
                summary["complete_count"],
                summary["no_market_data_count"],
                summary["safety_breach_count"],
                str(summary["average_updated_remaining_carry_bps"]),
                str(summary["average_carry_drift_bps"]),
                str(summary["average_latest_funding_bps"]),
                str(summary["average_latest_spread_bps"]),
                str(summary["average_remaining_funding_events"]),
                summary["strongest_symbol"],
                summary["weakest_symbol"],
                str(summary["strongest_updated_remaining_carry_bps"]),
                str(summary["weakest_updated_remaining_carry_bps"]),
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def run_shadow_tracking_performance_reporter(
    db_path: str | Path = "offchain/deltagrid.db",
    performance_label: str | None = None,
    report_label: str | None = None,
    update_label: str | None = None,
    symbols: str | list[str] | tuple[str, ...] | None = None,
    strong_carry_bps: float = 10.0,
    min_funding_bps: float = 0.0,
    max_spread_bps: float = 1.0,
) -> dict[str, Any]:
    db = Path(db_path)
    label = performance_label or new_performance_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    if strong_carry_bps < 0:
        raise ValueError("strong_carry_bps must be non-negative")

    if max_spread_bps < 0:
        raise ValueError("max_spread_bps must be non-negative")

    requested_symbols = parse_symbols(symbols)

    if not db.exists():
        summary = {
            "report_label": report,
            "performance_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": False,
            "source_update_label": update_label,
            "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
            "tracking_update_count": 0,
            "active_count": 0,
            "invalidated_count": 0,
            "complete_count": 0,
            "no_market_data_count": 0,
            "safety_breach_count": 0,
            "average_updated_remaining_carry_bps": 0.0,
            "average_carry_drift_bps": 0.0,
            "average_latest_funding_bps": 0.0,
            "average_latest_spread_bps": 0.0,
            "average_remaining_funding_events": 0.0,
            "strongest_symbol": None,
            "weakest_symbol": None,
            "strongest_updated_remaining_carry_bps": 0.0,
            "weakest_updated_remaining_carry_bps": 0.0,
            "update_status_counts": {},
            "symbol_summaries": [],
            "thresholds": {
                "strong_carry_bps": strong_carry_bps,
                "min_funding_bps": min_funding_bps,
                "max_spread_bps": max_spread_bps,
            },
            "global_verdict": NO_TRACKING_HISTORY_VERDICT,
            "recommended_action": RECOMMEND_RUN_TRACKER,
        }
        summary["markdown_report"] = build_markdown_report(summary)
        return summary

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        if not table_exists(conn, TRACKING_UPDATES_TABLE):
            summary = {
                "report_label": report,
                "performance_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "missing_tables": [TRACKING_UPDATES_TABLE],
                "source_update_label": update_label,
                "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
                "tracking_update_count": 0,
                "active_count": 0,
                "invalidated_count": 0,
                "complete_count": 0,
                "no_market_data_count": 0,
                "safety_breach_count": 0,
                "average_updated_remaining_carry_bps": 0.0,
                "average_carry_drift_bps": 0.0,
                "average_latest_funding_bps": 0.0,
                "average_latest_spread_bps": 0.0,
                "average_remaining_funding_events": 0.0,
                "strongest_symbol": None,
                "weakest_symbol": None,
                "strongest_updated_remaining_carry_bps": 0.0,
                "weakest_updated_remaining_carry_bps": 0.0,
                "update_status_counts": {},
                "symbol_summaries": [],
                "thresholds": {
                    "strong_carry_bps": strong_carry_bps,
                    "min_funding_bps": min_funding_bps,
                    "max_spread_bps": max_spread_bps,
                },
                "global_verdict": MISSING_TRACKING_TABLE_VERDICT,
                "recommended_action": RECOMMEND_RUN_TRACKER,
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        resolved_update_label = update_label or latest_update_label(conn)

        if resolved_update_label is None:
            summary = {
                "report_label": report,
                "performance_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "source_update_label": None,
                "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
                "tracking_update_count": 0,
                "active_count": 0,
                "invalidated_count": 0,
                "complete_count": 0,
                "no_market_data_count": 0,
                "safety_breach_count": 0,
                "average_updated_remaining_carry_bps": 0.0,
                "average_carry_drift_bps": 0.0,
                "average_latest_funding_bps": 0.0,
                "average_latest_spread_bps": 0.0,
                "average_remaining_funding_events": 0.0,
                "strongest_symbol": None,
                "weakest_symbol": None,
                "strongest_updated_remaining_carry_bps": 0.0,
                "weakest_updated_remaining_carry_bps": 0.0,
                "update_status_counts": {},
                "symbol_summaries": [],
                "thresholds": {
                    "strong_carry_bps": strong_carry_bps,
                    "min_funding_bps": min_funding_bps,
                    "max_spread_bps": max_spread_bps,
                },
                "global_verdict": NO_MATCHING_UPDATES_VERDICT,
                "recommended_action": RECOMMEND_RUN_TRACKER,
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        updates = load_tracking_updates(
            conn=conn,
            update_label=resolved_update_label,
            symbols=requested_symbols,
        )

    summary = summarize_performance(
        db_path=db,
        performance_label=label,
        report_label=report,
        created_at=created_at,
        source_update_label=resolved_update_label,
        requested_symbols=requested_symbols,
        updates=updates,
        strong_carry_bps=strong_carry_bps,
        min_funding_bps=min_funding_bps,
        max_spread_bps=max_spread_bps,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_report(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid shadow tracking performance reporter."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--performance-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--update-label", default=None)
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--strong-carry-bps", type=float, default=10.0)
    parser.add_argument("--min-funding-bps", type=float, default=0.0)
    parser.add_argument("--max-spread-bps", type=float, default=1.0)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_shadow_tracking_performance_reporter(
        db_path=args.db,
        performance_label=args.performance_label,
        report_label=args.report_label,
        update_label=args.update_label,
        symbols=args.symbols,
        strong_carry_bps=args.strong_carry_bps,
        min_funding_bps=args.min_funding_bps,
        max_spread_bps=args.max_spread_bps,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

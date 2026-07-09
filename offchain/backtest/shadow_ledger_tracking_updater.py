"""
Mission 55: Shadow Ledger Tracking Updater.

This module updates formal shadow ledger entries using public market data.

It is a shadow tracking layer, not an execution layer.

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


LEDGER_TABLE = "shadow_observation_ledger_entries"
BRIDGE_REPORTS_TABLE = "shadow_plan_to_ledger_bridge_reports"

FUNDING_TABLE = "historical_public_funding_rates"
BASIS_TABLE = "historical_public_basis_observations"
DATASET_REPORTS_TABLE = "historical_public_funding_basis_dataset_reports"

UPDATES_TABLE = "shadow_ledger_tracking_updates"
REPORTS_TABLE = "shadow_ledger_tracking_update_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

LEDGER_STATUS_ACTIVE = "LEDGER_ENTRY_ACTIVE_SHADOW_TRACKING"

UPDATE_STATUS_ACTIVE = "TRACKING_UPDATE_ACTIVE_SHADOW_ONLY"
UPDATE_STATUS_INVALIDATED_NEGATIVE_FUNDING = "TRACKING_UPDATE_INVALIDATED_NEGATIVE_FUNDING"
UPDATE_STATUS_INVALIDATED_COST_DRIFT = "TRACKING_UPDATE_INVALIDATED_COST_DRIFT"
UPDATE_STATUS_COMPLETE = "TRACKING_UPDATE_COMPLETE_SHADOW_ONLY"
UPDATE_STATUS_BLOCKED_SAFETY = "TRACKING_UPDATE_BLOCKED_SAFETY_REVIEW"
UPDATE_STATUS_NO_MARKET_DATA = "TRACKING_UPDATE_NO_MARKET_DATA"

STATE_ACTIVE = "TRACKING_ACTIVE_SHADOW_ONLY"
STATE_INVALIDATED = "TRACKING_INVALIDATED_SHADOW_ONLY"
STATE_COMPLETE = "TRACKING_COMPLETE_SHADOW_ONLY"
STATE_BLOCKED = "BLOCKED_SAFETY_REVIEW"
STATE_NO_DATA = "TRACKING_WAITING_FOR_PUBLIC_DATA"

NO_LEDGER_HISTORY_VERDICT = "LEDGER_TRACKING_NO_LEDGER_HISTORY"
MISSING_LEDGER_TABLE_VERDICT = "LEDGER_TRACKING_LEDGER_TABLE_MISSING"
NO_MATCHING_LEDGER_ENTRIES_VERDICT = "LEDGER_TRACKING_NO_MATCHING_LEDGER_ENTRIES"
NO_MARKET_DATA_VERDICT = "LEDGER_TRACKING_NO_MARKET_DATA"
SAFETY_BREACH_VERDICT = "LEDGER_TRACKING_SAFETY_BREACH_BLOCKED"
ACTIVE_VERDICT = "LEDGER_TRACKING_ACTIVE_SHADOW_ONLY"
INVALIDATED_VERDICT = "LEDGER_TRACKING_INVALIDATED_SHADOW_ONLY"
COMPLETE_VERDICT = "LEDGER_TRACKING_COMPLETE_SHADOW_ONLY"

RECOMMEND_RUN_BRIDGE = "RUN_MISSION_54_PLAN_TO_LEDGER_BRIDGE_FIRST"
RECOMMEND_RUN_MARKET_DATA = "RUN_MISSION_50_PUBLIC_DATASET_BUILDER_OR_REFRESH_PUBLIC_DATA"
RECOMMEND_REVIEW_SAFETY = "STOP_AND_REVIEW_LEDGER_TRACKING_SAFETY_STATE"
RECOMMEND_CONTINUE_TRACKING = "CONTINUE_SHADOW_LEDGER_TRACKING_ONLY"
RECOMMEND_REVIEW_INVALIDATED = "REVIEW_INVALIDATED_SHADOW_OBSERVATIONS_NO_TRADING"
RECOMMEND_FINALIZE_COMPLETE = "FINALIZE_COMPLETED_SHADOW_OBSERVATIONS"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_update_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission55-ledger-tracking-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission55-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
            raise ValueError(f"Only USDT perpetual symbols are supported for Mission 55: {symbol}")

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
            CREATE TABLE IF NOT EXISTS shadow_ledger_tracking_updates (
                tracking_update_id TEXT PRIMARY KEY,
                update_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_bridge_label TEXT,
                source_ledger_entry_id TEXT NOT NULL,
                source_market_dataset_label TEXT,
                symbol TEXT NOT NULL,
                previous_remaining_funding_events INTEGER NOT NULL,
                observed_funding_events_increment INTEGER NOT NULL,
                remaining_funding_events_after_update INTEGER NOT NULL,
                latest_funding_rate_bps TEXT NOT NULL,
                latest_basis_bps TEXT NOT NULL,
                latest_spread_bps TEXT NOT NULL,
                previous_expected_net_carry_bps TEXT NOT NULL,
                updated_expected_remaining_carry_bps TEXT NOT NULL,
                carry_drift_bps TEXT NOT NULL,
                update_status TEXT NOT NULL,
                observation_state_after TEXT NOT NULL,
                update_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_ledger_tracking_update_reports (
                report_label TEXT PRIMARY KEY,
                update_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_bridge_label TEXT,
                source_market_dataset_label TEXT,
                requested_symbol_count INTEGER NOT NULL,
                source_ledger_entry_count INTEGER NOT NULL,
                tracking_update_count INTEGER NOT NULL,
                active_after_update_count INTEGER NOT NULL,
                invalidated_count INTEGER NOT NULL,
                complete_count INTEGER NOT NULL,
                no_market_data_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                top_symbol TEXT,
                top_updated_expected_remaining_carry_bps TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def latest_bridge_label(conn: sqlite3.Connection) -> str | None:
    if table_exists(conn, BRIDGE_REPORTS_TABLE):
        row = conn.execute(
            """
            SELECT bridge_label
            FROM shadow_plan_to_ledger_bridge_reports
            ORDER BY created_at DESC, report_label DESC
            LIMIT 1
            """
        ).fetchone()

        if row is not None:
            return str(row["bridge_label"])

    if table_exists(conn, LEDGER_TABLE):
        row = conn.execute(
            """
            SELECT bridge_label
            FROM shadow_observation_ledger_entries
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()

        if row is not None:
            return str(row["bridge_label"])

    return None


def latest_market_dataset_label(conn: sqlite3.Connection) -> str | None:
    if table_exists(conn, DATASET_REPORTS_TABLE):
        row = conn.execute(
            """
            SELECT dataset_label
            FROM historical_public_funding_basis_dataset_reports
            ORDER BY created_at DESC, report_label DESC
            LIMIT 1
            """
        ).fetchone()

        if row is not None:
            return str(row["dataset_label"])

    if table_exists(conn, FUNDING_TABLE):
        row = conn.execute(
            """
            SELECT dataset_label
            FROM historical_public_funding_rates
            ORDER BY funding_time DESC
            LIMIT 1
            """
        ).fetchone()

        if row is not None:
            return str(row["dataset_label"])

    return None


def load_ledger_entries(
    conn: sqlite3.Connection,
    bridge_label: str,
    symbols: list[str] | None,
) -> list[sqlite3.Row]:
    params: list[Any] = [bridge_label]
    symbol_clause = ""

    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        symbol_clause = f" AND symbol IN ({placeholders})"
        params.extend(symbols)

    query = f"""
        SELECT *
        FROM shadow_observation_ledger_entries
        WHERE bridge_label = ?
        {symbol_clause}
        ORDER BY observation_priority ASC, expected_net_carry_bps DESC
    """

    return conn.execute(query, params).fetchall()


def ledger_entry_has_safety_breach(row: sqlite3.Row) -> bool:
    return (
        row["live_trading"] != LIVE_TRADING_STATUS
        or int(row["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or row["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS
    )


def load_latest_funding_row(
    conn: sqlite3.Connection,
    dataset_label: str,
    symbol: str,
) -> sqlite3.Row | None:
    if not table_exists(conn, FUNDING_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM historical_public_funding_rates
        WHERE dataset_label = ?
        AND symbol = ?
        ORDER BY funding_time DESC
        LIMIT 1
        """,
        (dataset_label, symbol),
    ).fetchone()


def load_latest_basis_row(
    conn: sqlite3.Connection,
    dataset_label: str,
    symbol: str,
) -> sqlite3.Row | None:
    if not table_exists(conn, BASIS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM historical_public_basis_observations
        WHERE dataset_label = ?
        AND symbol = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (dataset_label, symbol),
    ).fetchone()


def build_tracking_update(
    update_label: str,
    created_at: str,
    market_dataset_label: str | None,
    ledger_entry: sqlite3.Row,
    funding_row: sqlite3.Row | None,
    basis_row: sqlite3.Row | None,
    observed_funding_events_increment: int,
    min_latest_funding_bps: float,
    min_remaining_net_carry_bps: float,
    max_spread_bps: float,
) -> dict[str, Any]:
    symbol = str(ledger_entry["symbol"])
    previous_remaining = safe_int(ledger_entry["remaining_holding_funding_events"])
    remaining_after = max(0, previous_remaining - observed_funding_events_increment)

    previous_expected_net = safe_float(ledger_entry["expected_net_carry_bps"])
    estimated_cost_bps = safe_float(ledger_entry["estimated_cost_bps"])

    latest_funding_bps = safe_float(funding_row["funding_rate_bps"]) if funding_row is not None else 0.0
    latest_basis_bps = safe_float(basis_row["basis_bps"]) if basis_row is not None else 0.0
    latest_spread_bps = safe_float(basis_row["spread_bps"]) if basis_row is not None else safe_float(ledger_entry["latest_spread_bps"])

    updated_remaining_carry = round(
        (latest_funding_bps * remaining_after) - estimated_cost_bps,
        8,
    )
    carry_drift = round(updated_remaining_carry - previous_expected_net, 8)

    has_market_data = funding_row is not None and basis_row is not None
    safety_breach = ledger_entry_has_safety_breach(ledger_entry)

    if safety_breach:
        update_status = UPDATE_STATUS_BLOCKED_SAFETY
        observation_state_after = STATE_BLOCKED
        update_reason = "Ledger entry safety state is not clean; tracking update blocked."
    elif not has_market_data:
        update_status = UPDATE_STATUS_NO_MARKET_DATA
        observation_state_after = STATE_NO_DATA
        update_reason = "No matching public market data was found for the ledger entry."
    elif latest_funding_bps <= min_latest_funding_bps:
        update_status = UPDATE_STATUS_INVALIDATED_NEGATIVE_FUNDING
        observation_state_after = STATE_INVALIDATED
        update_reason = "Latest funding rate is at or below the minimum threshold."
    elif latest_spread_bps > max_spread_bps:
        update_status = UPDATE_STATUS_INVALIDATED_COST_DRIFT
        observation_state_after = STATE_INVALIDATED
        update_reason = "Latest spread exceeds the maximum allowed tracking threshold."
    elif updated_remaining_carry < min_remaining_net_carry_bps:
        update_status = UPDATE_STATUS_INVALIDATED_COST_DRIFT
        observation_state_after = STATE_INVALIDATED
        update_reason = "Updated expected remaining carry is below threshold."
    elif remaining_after == 0:
        update_status = UPDATE_STATUS_COMPLETE
        observation_state_after = STATE_COMPLETE
        update_reason = "Planned funding-event horizon is complete."
    else:
        update_status = UPDATE_STATUS_ACTIVE
        observation_state_after = STATE_ACTIVE
        update_reason = "Ledger entry remains valid for shadow tracking."

    return {
        "tracking_update_id": f"{update_label}-{symbol}",
        "update_label": update_label,
        "created_at": created_at,
        "source_bridge_label": ledger_entry["bridge_label"],
        "source_ledger_entry_id": ledger_entry["ledger_entry_id"],
        "source_market_dataset_label": market_dataset_label,
        "symbol": symbol,
        "previous_remaining_funding_events": previous_remaining,
        "observed_funding_events_increment": observed_funding_events_increment,
        "remaining_funding_events_after_update": remaining_after,
        "latest_funding_rate_bps": round(latest_funding_bps, 8),
        "latest_basis_bps": round(latest_basis_bps, 8),
        "latest_spread_bps": round(latest_spread_bps, 8),
        "previous_expected_net_carry_bps": round(previous_expected_net, 8),
        "updated_expected_remaining_carry_bps": updated_remaining_carry,
        "carry_drift_bps": carry_drift,
        "update_status": update_status,
        "observation_state_after": observation_state_after,
        "update_reason": update_reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "tracking_role": "SHADOW_LEDGER_TRACKING_UPDATE_ONLY",
            "source_ledger_status": ledger_entry["ledger_status"],
            "source_observation_state": ledger_entry["observation_state"],
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def persist_updates(db_path: str | Path, updates: list[dict[str, Any]]) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for update in updates:
            conn.execute(
                """
                INSERT OR REPLACE INTO shadow_ledger_tracking_updates (
                    tracking_update_id,
                    update_label,
                    created_at,
                    source_bridge_label,
                    source_ledger_entry_id,
                    source_market_dataset_label,
                    symbol,
                    previous_remaining_funding_events,
                    observed_funding_events_increment,
                    remaining_funding_events_after_update,
                    latest_funding_rate_bps,
                    latest_basis_bps,
                    latest_spread_bps,
                    previous_expected_net_carry_bps,
                    updated_expected_remaining_carry_bps,
                    carry_drift_bps,
                    update_status,
                    observation_state_after,
                    update_reason,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    update["tracking_update_id"],
                    update["update_label"],
                    update["created_at"],
                    update["source_bridge_label"],
                    update["source_ledger_entry_id"],
                    update["source_market_dataset_label"],
                    update["symbol"],
                    update["previous_remaining_funding_events"],
                    update["observed_funding_events_increment"],
                    update["remaining_funding_events_after_update"],
                    str(update["latest_funding_rate_bps"]),
                    str(update["latest_basis_bps"]),
                    str(update["latest_spread_bps"]),
                    str(update["previous_expected_net_carry_bps"]),
                    str(update["updated_expected_remaining_carry_bps"]),
                    str(update["carry_drift_bps"]),
                    update["update_status"],
                    update["observation_state_after"],
                    update["update_reason"],
                    update["live_trading"],
                    update["live_order_sent"],
                    update["capital_deployment"],
                    json.dumps(update["metadata"], sort_keys=True),
                ),
            )

            conn.execute(
                """
                UPDATE shadow_observation_ledger_entries
                SET remaining_holding_funding_events = ?,
                    observation_state = ?
                WHERE ledger_entry_id = ?
                """,
                (
                    update["remaining_funding_events_after_update"],
                    update["observation_state_after"],
                    update["source_ledger_entry_id"],
                ),
            )

        conn.commit()


def summarize_updates(
    db_path: str | Path,
    update_label: str,
    report_label: str,
    created_at: str,
    source_bridge_label: str | None,
    source_market_dataset_label: str | None,
    requested_symbols: list[str] | None,
    ledger_entries: list[sqlite3.Row],
    updates: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts = Counter(update["update_status"] for update in updates)

    active_after_update_count = status_counts.get(UPDATE_STATUS_ACTIVE, 0)
    invalidated_count = (
        status_counts.get(UPDATE_STATUS_INVALIDATED_NEGATIVE_FUNDING, 0)
        + status_counts.get(UPDATE_STATUS_INVALIDATED_COST_DRIFT, 0)
    )
    complete_count = status_counts.get(UPDATE_STATUS_COMPLETE, 0)
    no_market_data_count = status_counts.get(UPDATE_STATUS_NO_MARKET_DATA, 0)

    safety_breach_count = sum(1 for row in ledger_entries if ledger_entry_has_safety_breach(row))
    safety_breach_count += sum(
        1
        for update in updates
        if update["live_trading"] != LIVE_TRADING_STATUS
        or int(update["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or update["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS
        or update["update_status"] == UPDATE_STATUS_BLOCKED_SAFETY
    )

    top_symbol = updates[0]["symbol"] if updates else None
    top_remaining_carry = safe_float(updates[0]["updated_expected_remaining_carry_bps"]) if updates else 0.0

    if safety_breach_count > 0:
        global_verdict = SAFETY_BREACH_VERDICT
        recommended_action = RECOMMEND_REVIEW_SAFETY
    elif not ledger_entries:
        global_verdict = NO_MATCHING_LEDGER_ENTRIES_VERDICT
        recommended_action = RECOMMEND_RUN_BRIDGE
    elif no_market_data_count == len(updates) and updates:
        global_verdict = NO_MARKET_DATA_VERDICT
        recommended_action = RECOMMEND_RUN_MARKET_DATA
    elif active_after_update_count > 0:
        global_verdict = ACTIVE_VERDICT
        recommended_action = RECOMMEND_CONTINUE_TRACKING
    elif complete_count > 0 and invalidated_count == 0:
        global_verdict = COMPLETE_VERDICT
        recommended_action = RECOMMEND_FINALIZE_COMPLETE
    else:
        global_verdict = INVALIDATED_VERDICT
        recommended_action = RECOMMEND_REVIEW_INVALIDATED

    return {
        "report_label": report_label,
        "update_label": update_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_bridge_label": source_bridge_label,
        "source_market_dataset_label": source_market_dataset_label,
        "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
        "source_ledger_entry_count": len(ledger_entries),
        "tracking_update_count": len(updates),
        "active_after_update_count": active_after_update_count,
        "invalidated_count": invalidated_count,
        "complete_count": complete_count,
        "no_market_data_count": no_market_data_count,
        "safety_breach_count": safety_breach_count,
        "top_symbol": top_symbol,
        "top_updated_expected_remaining_carry_bps": round(top_remaining_carry, 8),
        "update_status_counts": dict(status_counts),
        "tracking_updates": updates,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    update_lines = []

    for update in summary["tracking_updates"]:
        update_lines.append(
            "- "
            + update["symbol"]
            + ": "
            + f"status={update['update_status']}, "
            + f"state={update['observation_state_after']}, "
            + f"remaining_events={update['remaining_funding_events_after_update']}, "
            + f"latest_funding_bps={update['latest_funding_rate_bps']}, "
            + f"latest_spread_bps={update['latest_spread_bps']}, "
            + f"updated_remaining_carry_bps={update['updated_expected_remaining_carry_bps']}"
        )

    updates_markdown = "\n".join(update_lines) or "- None"

    return f"""# DeltaGrid Mission 55 Shadow Ledger Tracking Updater Report

Report label: {summary['report_label']}
Update label: {summary['update_label']}
Created at: {summary['created_at']}
Source bridge label: {summary['source_bridge_label']}
Source market dataset label: {summary['source_market_dataset_label']}

## Tracking Summary

Source ledger entry count: {summary['source_ledger_entry_count']}
Tracking update count: {summary['tracking_update_count']}
Active after update count: {summary['active_after_update_count']}
Invalidated count: {summary['invalidated_count']}
Complete count: {summary['complete_count']}
No market data count: {summary['no_market_data_count']}
Safety breach count: {summary['safety_breach_count']}

Top symbol: {summary['top_symbol']}
Top updated expected remaining carry bps: {summary['top_updated_expected_remaining_carry_bps']}

## Tracking Updates

{updates_markdown}

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
            INSERT OR REPLACE INTO shadow_ledger_tracking_update_reports (
                report_label,
                update_label,
                created_at,
                source_bridge_label,
                source_market_dataset_label,
                requested_symbol_count,
                source_ledger_entry_count,
                tracking_update_count,
                active_after_update_count,
                invalidated_count,
                complete_count,
                no_market_data_count,
                safety_breach_count,
                top_symbol,
                top_updated_expected_remaining_carry_bps,
                global_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["update_label"],
                summary["created_at"],
                summary["source_bridge_label"],
                summary["source_market_dataset_label"],
                summary["requested_symbol_count"],
                summary["source_ledger_entry_count"],
                summary["tracking_update_count"],
                summary["active_after_update_count"],
                summary["invalidated_count"],
                summary["complete_count"],
                summary["no_market_data_count"],
                summary["safety_breach_count"],
                summary["top_symbol"],
                str(summary["top_updated_expected_remaining_carry_bps"]),
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def run_shadow_ledger_tracking_updater(
    db_path: str | Path = "offchain/deltagrid.db",
    update_label: str | None = None,
    report_label: str | None = None,
    bridge_label: str | None = None,
    market_dataset_label: str | None = None,
    symbols: str | list[str] | tuple[str, ...] | None = None,
    observed_funding_events_increment: int = 1,
    min_latest_funding_bps: float = 0.0,
    min_remaining_net_carry_bps: float = 0.25,
    max_spread_bps: float = 1.0,
) -> dict[str, Any]:
    db = Path(db_path)
    label = update_label or new_update_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    if observed_funding_events_increment <= 0:
        raise ValueError("observed_funding_events_increment must be greater than 0")

    if max_spread_bps < 0:
        raise ValueError("max_spread_bps must be non-negative")

    requested_symbols = parse_symbols(symbols)

    if not db.exists():
        summary = {
            "report_label": report,
            "update_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": False,
            "source_bridge_label": bridge_label,
            "source_market_dataset_label": market_dataset_label,
            "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
            "source_ledger_entry_count": 0,
            "tracking_update_count": 0,
            "active_after_update_count": 0,
            "invalidated_count": 0,
            "complete_count": 0,
            "no_market_data_count": 0,
            "safety_breach_count": 0,
            "top_symbol": None,
            "top_updated_expected_remaining_carry_bps": 0.0,
            "update_status_counts": {},
            "tracking_updates": [],
            "global_verdict": NO_LEDGER_HISTORY_VERDICT,
            "recommended_action": RECOMMEND_RUN_BRIDGE,
        }
        summary["markdown_report"] = build_markdown_report(summary)
        return summary

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        if not table_exists(conn, LEDGER_TABLE):
            summary = {
                "report_label": report,
                "update_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "missing_tables": [LEDGER_TABLE],
                "source_bridge_label": bridge_label,
                "source_market_dataset_label": market_dataset_label,
                "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
                "source_ledger_entry_count": 0,
                "tracking_update_count": 0,
                "active_after_update_count": 0,
                "invalidated_count": 0,
                "complete_count": 0,
                "no_market_data_count": 0,
                "safety_breach_count": 0,
                "top_symbol": None,
                "top_updated_expected_remaining_carry_bps": 0.0,
                "update_status_counts": {},
                "tracking_updates": [],
                "global_verdict": MISSING_LEDGER_TABLE_VERDICT,
                "recommended_action": RECOMMEND_RUN_BRIDGE,
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        resolved_bridge_label = bridge_label or latest_bridge_label(conn)

        if resolved_bridge_label is None:
            summary = {
                "report_label": report,
                "update_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "source_bridge_label": None,
                "source_market_dataset_label": market_dataset_label,
                "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
                "source_ledger_entry_count": 0,
                "tracking_update_count": 0,
                "active_after_update_count": 0,
                "invalidated_count": 0,
                "complete_count": 0,
                "no_market_data_count": 0,
                "safety_breach_count": 0,
                "top_symbol": None,
                "top_updated_expected_remaining_carry_bps": 0.0,
                "update_status_counts": {},
                "tracking_updates": [],
                "global_verdict": NO_MATCHING_LEDGER_ENTRIES_VERDICT,
                "recommended_action": RECOMMEND_RUN_BRIDGE,
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        ledger_entries = load_ledger_entries(
            conn=conn,
            bridge_label=resolved_bridge_label,
            symbols=requested_symbols,
        )

        resolved_market_dataset_label = market_dataset_label or latest_market_dataset_label(conn)

        updates: list[dict[str, Any]] = []

        for entry in ledger_entries:
            funding_row = None
            basis_row = None

            if resolved_market_dataset_label is not None:
                funding_row = load_latest_funding_row(
                    conn=conn,
                    dataset_label=resolved_market_dataset_label,
                    symbol=str(entry["symbol"]),
                )
                basis_row = load_latest_basis_row(
                    conn=conn,
                    dataset_label=resolved_market_dataset_label,
                    symbol=str(entry["symbol"]),
                )

            updates.append(
                build_tracking_update(
                    update_label=label,
                    created_at=created_at,
                    market_dataset_label=resolved_market_dataset_label,
                    ledger_entry=entry,
                    funding_row=funding_row,
                    basis_row=basis_row,
                    observed_funding_events_increment=observed_funding_events_increment,
                    min_latest_funding_bps=min_latest_funding_bps,
                    min_remaining_net_carry_bps=min_remaining_net_carry_bps,
                    max_spread_bps=max_spread_bps,
                )
            )

    persist_updates(db, updates)

    summary = summarize_updates(
        db_path=db,
        update_label=label,
        report_label=report,
        created_at=created_at,
        source_bridge_label=resolved_bridge_label,
        source_market_dataset_label=resolved_market_dataset_label,
        requested_symbols=requested_symbols,
        ledger_entries=ledger_entries,
        updates=updates,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_report(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid shadow ledger tracking updater."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--update-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--bridge-label", default=None)
    parser.add_argument("--market-dataset-label", default=None)
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--observed-funding-events-increment", type=int, default=1)
    parser.add_argument("--min-latest-funding-bps", type=float, default=0.0)
    parser.add_argument("--min-remaining-net-carry-bps", type=float, default=0.25)
    parser.add_argument("--max-spread-bps", type=float, default=1.0)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_shadow_ledger_tracking_updater(
        db_path=args.db,
        update_label=args.update_label,
        report_label=args.report_label,
        bridge_label=args.bridge_label,
        market_dataset_label=args.market_dataset_label,
        symbols=args.symbols,
        observed_funding_events_increment=args.observed_funding_events_increment,
        min_latest_funding_bps=args.min_latest_funding_bps,
        min_remaining_net_carry_bps=args.min_remaining_net_carry_bps,
        max_spread_bps=args.max_spread_bps,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

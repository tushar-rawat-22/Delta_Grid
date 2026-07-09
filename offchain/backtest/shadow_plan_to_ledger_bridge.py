"""
Mission 54: Shadow Plan-to-Ledger Bridge.

This module converts calibrated shadow observation plans into formal
shadow ledger entries.

It is a shadow accounting bridge, not an execution layer.

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


SOURCE_PLANS_TABLE = "calibrated_shadow_observation_plans"
SOURCE_REPORTS_TABLE = "calibrated_shadow_observation_plan_reports"

LEDGER_TABLE = "shadow_observation_ledger_entries"
REPORTS_TABLE = "shadow_plan_to_ledger_bridge_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

PLAN_STATUS_READY = "PLANNED_SHADOW_OBSERVATION_READY"

LEDGER_STATUS_ACTIVE = "LEDGER_ENTRY_ACTIVE_SHADOW_TRACKING"
LEDGER_STATUS_BLOCKED = "LEDGER_ENTRY_BLOCKED_SAFETY_REVIEW"

NO_PLAN_HISTORY_VERDICT = "PLAN_TO_LEDGER_NO_PLAN_HISTORY"
MISSING_PLAN_TABLE_VERDICT = "PLAN_TO_LEDGER_PLAN_TABLE_MISSING"
NO_MATCHING_PLANS_VERDICT = "PLAN_TO_LEDGER_NO_MATCHING_PLANS"
NO_READY_PLANS_VERDICT = "PLAN_TO_LEDGER_NO_READY_PLANS"
SAFETY_BREACH_VERDICT = "PLAN_TO_LEDGER_SAFETY_BREACH_BLOCKED"
READY_VERDICT = "PLAN_TO_LEDGER_READY_SHADOW_ONLY"

RECOMMEND_RUN_PLANNER = "RUN_MISSION_53_PLANNER_FIRST"
RECOMMEND_CONTINUE_PLANNING = "CONTINUE_PLANNING_NO_LEDGER_ENTRIES_CREATED"
RECOMMEND_REVIEW_SAFETY = "STOP_AND_REVIEW_PLAN_TO_LEDGER_SAFETY_STATE"
RECOMMEND_TRACK_SHADOW_LEDGER = "TRACK_SHADOW_LEDGER_ENTRIES_ONLY"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_bridge_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission54-plan-ledger-bridge-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission54-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
            raise ValueError(f"Only USDT perpetual symbols are supported for Mission 54: {symbol}")

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
            CREATE TABLE IF NOT EXISTS shadow_observation_ledger_entries (
                ledger_entry_id TEXT PRIMARY KEY,
                bridge_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_plan_label TEXT NOT NULL,
                source_plan_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                observation_priority INTEGER NOT NULL,
                ledger_status TEXT NOT NULL,
                shadow_notional_usd TEXT NOT NULL,
                planned_holding_funding_events INTEGER NOT NULL,
                remaining_holding_funding_events INTEGER NOT NULL,
                fee_bps_per_side TEXT NOT NULL,
                slippage_bps TEXT NOT NULL,
                average_funding_rate_bps TEXT NOT NULL,
                latest_spread_bps TEXT NOT NULL,
                gross_horizon_carry_bps TEXT NOT NULL,
                estimated_cost_bps TEXT NOT NULL,
                expected_net_carry_bps TEXT NOT NULL,
                break_even_funding_bps TEXT NOT NULL,
                funding_gap_to_break_even_bps TEXT NOT NULL,
                observation_state TEXT NOT NULL,
                ledger_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_plan_to_ledger_bridge_reports (
                report_label TEXT PRIMARY KEY,
                bridge_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_plan_label TEXT,
                requested_symbol_count INTEGER NOT NULL,
                source_plan_count INTEGER NOT NULL,
                ready_source_plan_count INTEGER NOT NULL,
                ledger_entry_count INTEGER NOT NULL,
                active_ledger_entry_count INTEGER NOT NULL,
                blocked_ledger_entry_count INTEGER NOT NULL,
                excluded_symbol_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                top_symbol TEXT,
                top_expected_net_carry_bps TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def latest_plan_label(conn: sqlite3.Connection) -> str | None:
    if table_exists(conn, SOURCE_REPORTS_TABLE):
        row = conn.execute(
            """
            SELECT plan_label
            FROM calibrated_shadow_observation_plan_reports
            ORDER BY created_at DESC, report_label DESC
            LIMIT 1
            """
        ).fetchone()

        if row is not None:
            return str(row["plan_label"])

    if table_exists(conn, SOURCE_PLANS_TABLE):
        row = conn.execute(
            """
            SELECT plan_label
            FROM calibrated_shadow_observation_plans
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()

        if row is not None:
            return str(row["plan_label"])

    return None


def load_source_plans(
    conn: sqlite3.Connection,
    plan_label: str,
    symbols: list[str] | None,
) -> list[sqlite3.Row]:
    params: list[Any] = [plan_label]
    symbol_clause = ""

    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        symbol_clause = f" AND symbol IN ({placeholders})"
        params.extend(symbols)

    query = f"""
        SELECT *
        FROM calibrated_shadow_observation_plans
        WHERE plan_label = ?
        {symbol_clause}
        ORDER BY observation_priority ASC, net_carry_bps DESC
    """

    return conn.execute(query, params).fetchall()


def plan_has_safety_breach(row: sqlite3.Row) -> bool:
    return (
        row["live_trading"] != LIVE_TRADING_STATUS
        or int(row["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or row["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS
    )


def choose_ready_plans(
    plans: list[sqlite3.Row],
    min_net_carry_bps: float,
) -> list[sqlite3.Row]:
    ready: list[sqlite3.Row] = []

    for row in plans:
        if row["plan_status"] != PLAN_STATUS_READY:
            continue

        if safe_float(row["net_carry_bps"]) < min_net_carry_bps:
            continue

        ready.append(row)

    return sorted(
        ready,
        key=lambda item: (
            safe_int(item["observation_priority"]) * -1,
            safe_float(item["net_carry_bps"]),
        ),
        reverse=True,
    )


def build_ledger_entry(
    bridge_label: str,
    created_at: str,
    plan: sqlite3.Row,
) -> dict[str, Any]:
    safety_breach = plan_has_safety_breach(plan)

    ledger_status = LEDGER_STATUS_BLOCKED if safety_breach else LEDGER_STATUS_ACTIVE

    if safety_breach:
        ledger_reason = "Source plan safety state is not clean; ledger entry blocked."
        observation_state = "BLOCKED_SAFETY_REVIEW"
    else:
        ledger_reason = "Ready calibrated shadow plan bridged into shadow ledger tracking."
        observation_state = "TRACKING_NOT_STARTED_SHADOW_ONLY"

    holding_events = safe_int(plan["holding_funding_events"])

    return {
        "ledger_entry_id": f"{bridge_label}-{plan['symbol']}",
        "bridge_label": bridge_label,
        "created_at": created_at,
        "source_plan_label": plan["plan_label"],
        "source_plan_id": plan["plan_id"],
        "symbol": plan["symbol"],
        "observation_priority": safe_int(plan["observation_priority"]),
        "ledger_status": ledger_status,
        "shadow_notional_usd": safe_float(plan["planned_notional_usd"]),
        "planned_holding_funding_events": holding_events,
        "remaining_holding_funding_events": holding_events,
        "fee_bps_per_side": safe_float(plan["fee_bps_per_side"]),
        "slippage_bps": safe_float(plan["slippage_bps"]),
        "average_funding_rate_bps": safe_float(plan["average_funding_rate_bps"]),
        "latest_spread_bps": safe_float(plan["latest_spread_bps"]),
        "gross_horizon_carry_bps": safe_float(plan["gross_horizon_carry_bps"]),
        "estimated_cost_bps": safe_float(plan["estimated_cost_bps"]),
        "expected_net_carry_bps": safe_float(plan["net_carry_bps"]),
        "break_even_funding_bps": safe_float(plan["break_even_funding_bps"]),
        "funding_gap_to_break_even_bps": safe_float(plan["funding_gap_to_break_even_bps"]),
        "observation_state": observation_state,
        "ledger_reason": ledger_reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "bridge_role": "SHADOW_PLAN_TO_LEDGER_ONLY",
            "source_plan_status": plan["plan_status"],
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def persist_ledger_entries(db_path: str | Path, entries: list[dict[str, Any]]) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for entry in entries:
            conn.execute(
                """
                INSERT OR REPLACE INTO shadow_observation_ledger_entries (
                    ledger_entry_id,
                    bridge_label,
                    created_at,
                    source_plan_label,
                    source_plan_id,
                    symbol,
                    observation_priority,
                    ledger_status,
                    shadow_notional_usd,
                    planned_holding_funding_events,
                    remaining_holding_funding_events,
                    fee_bps_per_side,
                    slippage_bps,
                    average_funding_rate_bps,
                    latest_spread_bps,
                    gross_horizon_carry_bps,
                    estimated_cost_bps,
                    expected_net_carry_bps,
                    break_even_funding_bps,
                    funding_gap_to_break_even_bps,
                    observation_state,
                    ledger_reason,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry["ledger_entry_id"],
                    entry["bridge_label"],
                    entry["created_at"],
                    entry["source_plan_label"],
                    entry["source_plan_id"],
                    entry["symbol"],
                    entry["observation_priority"],
                    entry["ledger_status"],
                    str(entry["shadow_notional_usd"]),
                    entry["planned_holding_funding_events"],
                    entry["remaining_holding_funding_events"],
                    str(entry["fee_bps_per_side"]),
                    str(entry["slippage_bps"]),
                    str(entry["average_funding_rate_bps"]),
                    str(entry["latest_spread_bps"]),
                    str(entry["gross_horizon_carry_bps"]),
                    str(entry["estimated_cost_bps"]),
                    str(entry["expected_net_carry_bps"]),
                    str(entry["break_even_funding_bps"]),
                    str(entry["funding_gap_to_break_even_bps"]),
                    entry["observation_state"],
                    entry["ledger_reason"],
                    entry["live_trading"],
                    entry["live_order_sent"],
                    entry["capital_deployment"],
                    json.dumps(entry["metadata"], sort_keys=True),
                ),
            )

        conn.commit()


def summarize_bridge(
    db_path: str | Path,
    bridge_label: str,
    report_label: str,
    created_at: str,
    source_plan_label: str | None,
    requested_symbols: list[str] | None,
    source_plans: list[sqlite3.Row],
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    ready_source_plan_count = sum(1 for row in source_plans if row["plan_status"] == PLAN_STATUS_READY)

    source_symbols = sorted(set(str(row["symbol"]) for row in source_plans))
    entry_symbols = sorted(set(str(entry["symbol"]) for entry in entries))

    if requested_symbols is not None:
        excluded_symbols = sorted(set(requested_symbols) - set(entry_symbols))
    else:
        excluded_symbols = sorted(set(source_symbols) - set(entry_symbols))

    active_count = sum(1 for entry in entries if entry["ledger_status"] == LEDGER_STATUS_ACTIVE)
    blocked_count = sum(1 for entry in entries if entry["ledger_status"] == LEDGER_STATUS_BLOCKED)

    safety_breach_count = sum(1 for row in source_plans if plan_has_safety_breach(row))
    safety_breach_count += sum(
        1
        for entry in entries
        if entry["live_trading"] != LIVE_TRADING_STATUS
        or int(entry["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or entry["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS
        or entry["ledger_status"] == LEDGER_STATUS_BLOCKED
    )

    top_symbol = entries[0]["symbol"] if entries else None
    top_expected_net = safe_float(entries[0]["expected_net_carry_bps"]) if entries else 0.0

    status_counts = dict(Counter(entry["ledger_status"] for entry in entries))

    if safety_breach_count > 0:
        global_verdict = SAFETY_BREACH_VERDICT
        recommended_action = RECOMMEND_REVIEW_SAFETY
    elif not source_plans:
        global_verdict = NO_MATCHING_PLANS_VERDICT
        recommended_action = RECOMMEND_RUN_PLANNER
    elif not entries:
        global_verdict = NO_READY_PLANS_VERDICT
        recommended_action = RECOMMEND_CONTINUE_PLANNING
    else:
        global_verdict = READY_VERDICT
        recommended_action = RECOMMEND_TRACK_SHADOW_LEDGER

    return {
        "report_label": report_label,
        "bridge_label": bridge_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_plan_label": source_plan_label,
        "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
        "source_plan_count": len(source_plans),
        "ready_source_plan_count": ready_source_plan_count,
        "ledger_entry_count": len(entries),
        "active_ledger_entry_count": active_count,
        "blocked_ledger_entry_count": blocked_count,
        "excluded_symbol_count": len(excluded_symbols),
        "excluded_symbols": excluded_symbols,
        "safety_breach_count": safety_breach_count,
        "top_symbol": top_symbol,
        "top_expected_net_carry_bps": round(top_expected_net, 8),
        "ledger_status_counts": status_counts,
        "ledger_entries": entries,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    entry_lines = []

    for entry in summary["ledger_entries"]:
        entry_lines.append(
            "- "
            + f"priority={entry['observation_priority']} "
            + f"{entry['symbol']}: "
            + f"status={entry['ledger_status']}, "
            + f"state={entry['observation_state']}, "
            + f"expected_net_carry_bps={entry['expected_net_carry_bps']}, "
            + f"holding_events={entry['planned_holding_funding_events']}, "
            + f"shadow_notional_usd={entry['shadow_notional_usd']}"
        )

    entries_markdown = "\n".join(entry_lines) or "- None"

    return f"""# DeltaGrid Mission 54 Shadow Plan-to-Ledger Bridge Report

Report label: {summary['report_label']}
Bridge label: {summary['bridge_label']}
Created at: {summary['created_at']}
Source plan label: {summary['source_plan_label']}

## Bridge Summary

Source plan count: {summary['source_plan_count']}
Ready source plan count: {summary['ready_source_plan_count']}
Ledger entry count: {summary['ledger_entry_count']}
Active ledger entry count: {summary['active_ledger_entry_count']}
Blocked ledger entry count: {summary['blocked_ledger_entry_count']}
Excluded symbol count: {summary['excluded_symbol_count']}
Excluded symbols: {summary['excluded_symbols']}
Safety breach count: {summary['safety_breach_count']}

Top symbol: {summary['top_symbol']}
Top expected net carry bps: {summary['top_expected_net_carry_bps']}

## Shadow Ledger Entries

{entries_markdown}

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
            INSERT OR REPLACE INTO shadow_plan_to_ledger_bridge_reports (
                report_label,
                bridge_label,
                created_at,
                source_plan_label,
                requested_symbol_count,
                source_plan_count,
                ready_source_plan_count,
                ledger_entry_count,
                active_ledger_entry_count,
                blocked_ledger_entry_count,
                excluded_symbol_count,
                safety_breach_count,
                top_symbol,
                top_expected_net_carry_bps,
                global_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["bridge_label"],
                summary["created_at"],
                summary["source_plan_label"],
                summary["requested_symbol_count"],
                summary["source_plan_count"],
                summary["ready_source_plan_count"],
                summary["ledger_entry_count"],
                summary["active_ledger_entry_count"],
                summary["blocked_ledger_entry_count"],
                summary["excluded_symbol_count"],
                summary["safety_breach_count"],
                summary["top_symbol"],
                str(summary["top_expected_net_carry_bps"]),
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def run_shadow_plan_to_ledger_bridge(
    db_path: str | Path = "offchain/deltagrid.db",
    bridge_label: str | None = None,
    report_label: str | None = None,
    plan_label: str | None = None,
    symbols: str | list[str] | tuple[str, ...] | None = None,
    max_entries: int = 2,
    min_net_carry_bps: float = 0.25,
) -> dict[str, Any]:
    db = Path(db_path)
    label = bridge_label or new_bridge_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    if max_entries <= 0:
        raise ValueError("max_entries must be greater than 0")

    requested_symbols = parse_symbols(symbols)

    if not db.exists():
        summary = {
            "report_label": report,
            "bridge_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": False,
            "source_plan_label": plan_label,
            "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
            "source_plan_count": 0,
            "ready_source_plan_count": 0,
            "ledger_entry_count": 0,
            "active_ledger_entry_count": 0,
            "blocked_ledger_entry_count": 0,
            "excluded_symbol_count": 0,
            "excluded_symbols": [],
            "safety_breach_count": 0,
            "top_symbol": None,
            "top_expected_net_carry_bps": 0.0,
            "ledger_status_counts": {},
            "ledger_entries": [],
            "global_verdict": NO_PLAN_HISTORY_VERDICT,
            "recommended_action": RECOMMEND_RUN_PLANNER,
        }
        summary["markdown_report"] = build_markdown_report(summary)
        return summary

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        if not table_exists(conn, SOURCE_PLANS_TABLE):
            summary = {
                "report_label": report,
                "bridge_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "missing_tables": [SOURCE_PLANS_TABLE],
                "source_plan_label": plan_label,
                "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
                "source_plan_count": 0,
                "ready_source_plan_count": 0,
                "ledger_entry_count": 0,
                "active_ledger_entry_count": 0,
                "blocked_ledger_entry_count": 0,
                "excluded_symbol_count": 0,
                "excluded_symbols": [],
                "safety_breach_count": 0,
                "top_symbol": None,
                "top_expected_net_carry_bps": 0.0,
                "ledger_status_counts": {},
                "ledger_entries": [],
                "global_verdict": MISSING_PLAN_TABLE_VERDICT,
                "recommended_action": RECOMMEND_RUN_PLANNER,
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        resolved_plan_label = plan_label or latest_plan_label(conn)

        if resolved_plan_label is None:
            summary = {
                "report_label": report,
                "bridge_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "source_plan_label": None,
                "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
                "source_plan_count": 0,
                "ready_source_plan_count": 0,
                "ledger_entry_count": 0,
                "active_ledger_entry_count": 0,
                "blocked_ledger_entry_count": 0,
                "excluded_symbol_count": 0,
                "excluded_symbols": [],
                "safety_breach_count": 0,
                "top_symbol": None,
                "top_expected_net_carry_bps": 0.0,
                "ledger_status_counts": {},
                "ledger_entries": [],
                "global_verdict": NO_MATCHING_PLANS_VERDICT,
                "recommended_action": RECOMMEND_RUN_PLANNER,
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        source_plans = load_source_plans(
            conn=conn,
            plan_label=resolved_plan_label,
            symbols=requested_symbols,
        )

    ready_plans = choose_ready_plans(
        plans=source_plans,
        min_net_carry_bps=min_net_carry_bps,
    )[:max_entries]

    entries = [
        build_ledger_entry(
            bridge_label=label,
            created_at=created_at,
            plan=plan,
        )
        for plan in ready_plans
    ]

    persist_ledger_entries(db, entries)

    summary = summarize_bridge(
        db_path=db,
        bridge_label=label,
        report_label=report,
        created_at=created_at,
        source_plan_label=resolved_plan_label,
        requested_symbols=requested_symbols,
        source_plans=source_plans,
        entries=entries,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_report(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid shadow plan-to-ledger bridge."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--bridge-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--plan-label", default=None)
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--max-entries", type=int, default=2)
    parser.add_argument("--min-net-carry-bps", type=float, default=0.25)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_shadow_plan_to_ledger_bridge(
        db_path=args.db,
        bridge_label=args.bridge_label,
        report_label=args.report_label,
        plan_label=args.plan_label,
        symbols=args.symbols,
        max_entries=args.max_entries,
        min_net_carry_bps=args.min_net_carry_bps,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

"""
Mission 43: Shadow Observation Break-Even Tracker.

This module converts Mission 40 PnL attribution records into break-even timing
estimates.

It is a research and reporting layer, not an execution layer.

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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_DECISION = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

PNL_ATTRIBUTION_TABLE = "shadow_observation_pnl_attribution"
BREAK_EVEN_TABLE = "shadow_observation_break_even_tracking"
BREAK_EVEN_REPORTS_TABLE = "shadow_observation_break_even_reports"

NO_PNL_ATTRIBUTION_HISTORY_VERDICT = "BREAK_EVEN_NO_PNL_ATTRIBUTION_HISTORY"
MISSING_PNL_ATTRIBUTION_TABLE_VERDICT = "BREAK_EVEN_PNL_ATTRIBUTION_TABLE_MISSING"
NO_MATCHING_ATTRIBUTIONS_VERDICT = "BREAK_EVEN_NO_MATCHING_ATTRIBUTIONS"
SAFETY_BREACH_VERDICT = "BREAK_EVEN_SAFETY_BREACH_BLOCKED"
RISK_REVIEW_VERDICT = "BREAK_EVEN_RISK_REVIEW_REQUIRED"
IMPOSSIBLE_VERDICT = "BREAK_EVEN_IMPOSSIBLE_WITH_CURRENT_FUNDING"
PENDING_VERDICT = "BREAK_EVEN_PENDING_CONTINUE_OBSERVATION"
REACHED_VERDICT = "BREAK_EVEN_REACHED_COST_COVERED"
MIXED_VERDICT = "BREAK_EVEN_MIXED_OBSERVATION_SET"

STATUS_SAFETY_BREACH = "SAFETY_BREACH"
STATUS_RISK_REVIEW = "RISK_REVIEW"
STATUS_IMPOSSIBLE = "BREAK_EVEN_IMPOSSIBLE"
STATUS_PENDING = "BREAK_EVEN_PENDING"
STATUS_REACHED = "BREAK_EVEN_REACHED"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_utc(value: str) -> datetime:
    cleaned = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(cleaned)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def new_tracker_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission43-break-even-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission43-report-{stamp}-{uuid.uuid4().hex[:8]}"


def safe_json_loads(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
            CREATE TABLE IF NOT EXISTS shadow_observation_break_even_tracking (
                break_even_id TEXT PRIMARY KEY,
                tracker_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                attribution_label TEXT NOT NULL,
                observation_id TEXT NOT NULL,
                ledger_label TEXT NOT NULL,
                source_gate_label TEXT NOT NULL,
                symbol TEXT NOT NULL,
                status TEXT NOT NULL,
                simulated_notional_usd TEXT NOT NULL,
                expected_annualized_funding TEXT NOT NULL,
                funding_per_hour_usd TEXT NOT NULL,
                gross_expected_funding_pnl_usd TEXT NOT NULL,
                total_cost_usd TEXT NOT NULL,
                net_expected_pnl_usd TEXT NOT NULL,
                cost_remaining_usd TEXT NOT NULL,
                age_hours TEXT NOT NULL,
                break_even_hours TEXT,
                remaining_hours_to_break_even TEXT,
                projected_break_even_at TEXT,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                risk_flags_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_observation_break_even_reports (
                report_label TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                tracker_label TEXT NOT NULL,
                source_attribution_label TEXT,
                observation_count INTEGER NOT NULL,
                reached_count INTEGER NOT NULL,
                pending_count INTEGER NOT NULL,
                impossible_count INTEGER NOT NULL,
                risk_review_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                average_remaining_hours_to_break_even TEXT NOT NULL,
                max_remaining_hours_to_break_even TEXT NOT NULL,
                total_cost_remaining_usd TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def latest_attribution_label(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        """
        SELECT attribution_label
        FROM shadow_observation_pnl_attribution
        ORDER BY created_at DESC, attribution_label DESC
        LIMIT 1
        """
    ).fetchone()

    if row is None:
        return None

    return str(row["attribution_label"])


def load_attributions(
    conn: sqlite3.Connection,
    attribution_label: str | None,
    gate_label: str | None,
) -> tuple[str | None, list[sqlite3.Row]]:
    resolved = attribution_label or latest_attribution_label(conn)

    if resolved is None:
        return None, []

    query = """
        SELECT
            attribution_id,
            attribution_label,
            created_at,
            snapshot_label,
            observation_id,
            ledger_label,
            source_gate_label,
            symbol,
            lifecycle_status,
            simulated_notional_usd,
            gross_expected_funding_pnl_usd,
            fee_cost_usd,
            spread_cost_usd,
            slippage_cost_usd,
            total_cost_usd,
            net_expected_pnl_usd,
            net_expected_return_bps,
            edge_to_cost_ratio,
            attribution_status,
            live_trading,
            live_order_sent,
            capital_deployment,
            risk_flags_json,
            metadata_json
        FROM shadow_observation_pnl_attribution
        WHERE attribution_label = ?
    """
    params: list[Any] = [resolved]

    if gate_label is not None:
        query += " AND source_gate_label = ?"
        params.append(gate_label)

    query += " ORDER BY observation_id ASC"

    return resolved, conn.execute(query, params).fetchall()


def evaluate_break_even_row(
    row: sqlite3.Row,
    tracker_label: str,
    created_at: str,
) -> dict[str, Any]:
    metadata = safe_json_loads(row["metadata_json"], {})
    risk_flags = safe_json_loads(row["risk_flags_json"], [])

    simulated_notional = safe_float(row["simulated_notional_usd"])
    expected_annualized_funding = safe_float(metadata.get("expected_annualized_funding"))
    age_hours = safe_float(metadata.get("age_hours"))

    gross_expected = safe_float(row["gross_expected_funding_pnl_usd"])
    total_cost = safe_float(row["total_cost_usd"])
    net_expected = safe_float(row["net_expected_pnl_usd"])
    cost_remaining = round(max(total_cost - gross_expected, 0.0), 8)

    funding_per_hour = round(
        simulated_notional * expected_annualized_funding / 8760.0,
        12,
    )

    safety_breach = (
        row["live_trading"] != LIVE_TRADING_STATUS
        or int(row["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or row["capital_deployment"] != CAPITAL_DEPLOYMENT_DECISION
    )

    break_even_hours: float | None = None
    remaining_hours: float | None = None
    projected_break_even_at: str | None = None

    if safety_breach:
        status = STATUS_SAFETY_BREACH
    elif str(row["attribution_status"]) in {"SAFETY_BREACH"}:
        status = STATUS_SAFETY_BREACH
    elif str(row["attribution_status"]) == "RISK_REVIEW" or risk_flags:
        status = STATUS_RISK_REVIEW
    elif expected_annualized_funding <= 0 or funding_per_hour <= 0:
        status = STATUS_IMPOSSIBLE
    else:
        break_even_hours = round(total_cost / funding_per_hour, 6)
        remaining_hours = round(max(break_even_hours - age_hours, 0.0), 6)

        if net_expected >= 0 or remaining_hours <= 0:
            status = STATUS_REACHED
            remaining_hours = 0.0
            projected_break_even_at = created_at
        else:
            status = STATUS_PENDING
            projected = parse_utc(created_at) + timedelta(hours=remaining_hours)
            projected_break_even_at = projected.replace(microsecond=0).isoformat()

    break_even_id = f"{tracker_label}-{row['observation_id']}"

    return {
        "break_even_id": break_even_id,
        "tracker_label": tracker_label,
        "created_at": created_at,
        "attribution_label": row["attribution_label"],
        "observation_id": row["observation_id"],
        "ledger_label": row["ledger_label"],
        "source_gate_label": row["source_gate_label"],
        "symbol": row["symbol"],
        "status": status,
        "simulated_notional_usd": simulated_notional,
        "expected_annualized_funding": expected_annualized_funding,
        "funding_per_hour_usd": funding_per_hour,
        "gross_expected_funding_pnl_usd": gross_expected,
        "total_cost_usd": total_cost,
        "net_expected_pnl_usd": net_expected,
        "cost_remaining_usd": cost_remaining,
        "age_hours": age_hours,
        "break_even_hours": break_even_hours,
        "remaining_hours_to_break_even": remaining_hours,
        "projected_break_even_at": projected_break_even_at,
        "live_trading": row["live_trading"],
        "live_order_sent": int(row["live_order_sent"]),
        "capital_deployment": row["capital_deployment"],
        "risk_flags": risk_flags,
        "metadata": {
            "attribution_id": row["attribution_id"],
            "snapshot_label": row["snapshot_label"],
            "lifecycle_status": row["lifecycle_status"],
            "attribution_status": row["attribution_status"],
            "fee_cost_usd": safe_float(row["fee_cost_usd"]),
            "spread_cost_usd": safe_float(row["spread_cost_usd"]),
            "slippage_cost_usd": safe_float(row["slippage_cost_usd"]),
            "net_expected_return_bps": safe_float(row["net_expected_return_bps"]),
            "edge_to_cost_ratio": safe_float(row["edge_to_cost_ratio"]),
            "source_metadata": metadata,
        },
    }


def persist_break_even_rows(
    db_path: str | Path,
    rows: list[dict[str, Any]],
) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for item in rows:
            conn.execute(
                """
                INSERT OR REPLACE INTO shadow_observation_break_even_tracking (
                    break_even_id,
                    tracker_label,
                    created_at,
                    attribution_label,
                    observation_id,
                    ledger_label,
                    source_gate_label,
                    symbol,
                    status,
                    simulated_notional_usd,
                    expected_annualized_funding,
                    funding_per_hour_usd,
                    gross_expected_funding_pnl_usd,
                    total_cost_usd,
                    net_expected_pnl_usd,
                    cost_remaining_usd,
                    age_hours,
                    break_even_hours,
                    remaining_hours_to_break_even,
                    projected_break_even_at,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    risk_flags_json,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["break_even_id"],
                    item["tracker_label"],
                    item["created_at"],
                    item["attribution_label"],
                    item["observation_id"],
                    item["ledger_label"],
                    item["source_gate_label"],
                    item["symbol"],
                    item["status"],
                    str(item["simulated_notional_usd"]),
                    str(item["expected_annualized_funding"]),
                    str(item["funding_per_hour_usd"]),
                    str(item["gross_expected_funding_pnl_usd"]),
                    str(item["total_cost_usd"]),
                    str(item["net_expected_pnl_usd"]),
                    str(item["cost_remaining_usd"]),
                    str(item["age_hours"]),
                    None if item["break_even_hours"] is None else str(item["break_even_hours"]),
                    None if item["remaining_hours_to_break_even"] is None else str(item["remaining_hours_to_break_even"]),
                    item["projected_break_even_at"],
                    item["live_trading"],
                    item["live_order_sent"],
                    item["capital_deployment"],
                    json.dumps(item["risk_flags"], sort_keys=True),
                    json.dumps(item["metadata"], sort_keys=True),
                ),
            )

        conn.commit()


def summarize_break_even(
    db_path: str | Path,
    report_label: str,
    tracker_label: str,
    created_at: str,
    source_attribution_label: str | None,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    observation_count = len(rows)

    reached_count = sum(1 for item in rows if item["status"] == STATUS_REACHED)
    pending_count = sum(1 for item in rows if item["status"] == STATUS_PENDING)
    impossible_count = sum(1 for item in rows if item["status"] == STATUS_IMPOSSIBLE)
    risk_review_count = sum(1 for item in rows if item["status"] == STATUS_RISK_REVIEW)
    safety_breach_count = sum(1 for item in rows if item["status"] == STATUS_SAFETY_BREACH)

    pending_remaining_hours = [
        safe_float(item["remaining_hours_to_break_even"])
        for item in rows
        if item["remaining_hours_to_break_even"] is not None
    ]

    average_remaining = 0.0
    max_remaining = 0.0

    if pending_remaining_hours:
        average_remaining = round(sum(pending_remaining_hours) / len(pending_remaining_hours), 6)
        max_remaining = round(max(pending_remaining_hours), 6)

    total_cost_remaining = round(
        sum(safe_float(item["cost_remaining_usd"]) for item in rows),
        8,
    )

    status_counts = dict(Counter(item["status"] for item in rows))
    symbol_counts = dict(Counter(item["symbol"] for item in rows))

    if observation_count == 0:
        global_verdict = NO_MATCHING_ATTRIBUTIONS_VERDICT
        recommended_action = "RUN_MISSION_40_PNL_ATTRIBUTION"
    elif safety_breach_count > 0:
        global_verdict = SAFETY_BREACH_VERDICT
        recommended_action = "STOP_AND_REVIEW_BREAK_EVEN_SAFETY_BREACH"
    elif risk_review_count > 0:
        global_verdict = RISK_REVIEW_VERDICT
        recommended_action = "REVIEW_RISK_FLAGS_BEFORE_INTERPRETING_BREAK_EVEN"
    elif impossible_count > 0 and pending_count == 0 and reached_count == 0:
        global_verdict = IMPOSSIBLE_VERDICT
        recommended_action = "REJECT_OR_REWORK_FUNDING_THESIS"
    elif pending_count > 0:
        global_verdict = PENDING_VERDICT
        recommended_action = "CONTINUE_SHADOW_OBSERVATION_UNTIL_BREAK_EVEN_WINDOW"
    elif reached_count == observation_count:
        global_verdict = REACHED_VERDICT
        recommended_action = "REVIEW_FOR_COST_ADJUSTED_SHADOW_OUTCOME"
    else:
        global_verdict = MIXED_VERDICT
        recommended_action = "REVIEW_MIXED_BREAK_EVEN_OBSERVATION_SET"

    return {
        "report_label": report_label,
        "tracker_label": tracker_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_attribution_label": source_attribution_label,
        "observation_count": observation_count,
        "reached_count": reached_count,
        "pending_count": pending_count,
        "impossible_count": impossible_count,
        "risk_review_count": risk_review_count,
        "safety_breach_count": safety_breach_count,
        "average_remaining_hours_to_break_even": average_remaining,
        "max_remaining_hours_to_break_even": max_remaining,
        "total_cost_remaining_usd": total_cost_remaining,
        "status_counts": status_counts,
        "symbol_counts": symbol_counts,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
        "break_even_rows": rows,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    status_counts = "\n".join(
        f"- {name}: {count}"
        for name, count in summary["status_counts"].items()
    ) or "- None"

    symbol_counts = "\n".join(
        f"- {name}: {count}"
        for name, count in summary["symbol_counts"].items()
    ) or "- None"

    return f"""# DeltaGrid Mission 43 Shadow Observation Break-Even Report

Report label: {summary['report_label']}
Tracker label: {summary['tracker_label']}
Created at: {summary['created_at']}
Source attribution label: {summary['source_attribution_label']}

## Break-Even Summary

Observation count: {summary['observation_count']}
Reached count: {summary['reached_count']}
Pending count: {summary['pending_count']}
Impossible count: {summary['impossible_count']}
Risk review count: {summary['risk_review_count']}
Safety breach count: {summary['safety_breach_count']}

Average remaining hours to break-even: {summary['average_remaining_hours_to_break_even']}
Max remaining hours to break-even: {summary['max_remaining_hours_to_break_even']}
Total cost remaining USD: {summary['total_cost_remaining_usd']}

## Status Counts

{status_counts}

## Symbol Counts

{symbol_counts}

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
"""


def persist_report(
    db_path: str | Path,
    summary: dict[str, Any],
    markdown_report: str,
) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO shadow_observation_break_even_reports (
                report_label,
                created_at,
                tracker_label,
                source_attribution_label,
                observation_count,
                reached_count,
                pending_count,
                impossible_count,
                risk_review_count,
                safety_breach_count,
                average_remaining_hours_to_break_even,
                max_remaining_hours_to_break_even,
                total_cost_remaining_usd,
                global_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["created_at"],
                summary["tracker_label"],
                summary["source_attribution_label"],
                summary["observation_count"],
                summary["reached_count"],
                summary["pending_count"],
                summary["impossible_count"],
                summary["risk_review_count"],
                summary["safety_breach_count"],
                str(summary["average_remaining_hours_to_break_even"]),
                str(summary["max_remaining_hours_to_break_even"]),
                str(summary["total_cost_remaining_usd"]),
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def run_shadow_observation_break_even_tracker(
    db_path: str | Path = "offchain/deltagrid.db",
    tracker_label: str | None = None,
    report_label: str | None = None,
    attribution_label: str | None = None,
    gate_label: str | None = None,
) -> dict[str, Any]:
    db = Path(db_path)
    label = tracker_label or new_tracker_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    if not db.exists():
        summary = {
            "report_label": report,
            "tracker_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": False,
            "tables_present": False,
            "source_attribution_label": attribution_label,
            "observation_count": 0,
            "reached_count": 0,
            "pending_count": 0,
            "impossible_count": 0,
            "risk_review_count": 0,
            "safety_breach_count": 0,
            "average_remaining_hours_to_break_even": 0.0,
            "max_remaining_hours_to_break_even": 0.0,
            "total_cost_remaining_usd": 0.0,
            "status_counts": {},
            "symbol_counts": {},
            "global_verdict": NO_PNL_ATTRIBUTION_HISTORY_VERDICT,
            "recommended_action": "RUN_MISSION_40_PNL_ATTRIBUTION",
            "break_even_rows": [],
        }
        summary["markdown_report"] = build_markdown_report(summary)
        return summary

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        if not table_exists(conn, PNL_ATTRIBUTION_TABLE):
            summary = {
                "report_label": report,
                "tracker_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "tables_present": False,
                "missing_tables": [PNL_ATTRIBUTION_TABLE],
                "source_attribution_label": attribution_label,
                "observation_count": 0,
                "reached_count": 0,
                "pending_count": 0,
                "impossible_count": 0,
                "risk_review_count": 0,
                "safety_breach_count": 0,
                "average_remaining_hours_to_break_even": 0.0,
                "max_remaining_hours_to_break_even": 0.0,
                "total_cost_remaining_usd": 0.0,
                "status_counts": {},
                "symbol_counts": {},
                "global_verdict": MISSING_PNL_ATTRIBUTION_TABLE_VERDICT,
                "recommended_action": "RUN_MISSION_40_PNL_ATTRIBUTION",
                "break_even_rows": [],
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        resolved_attribution_label, attribution_rows = load_attributions(
            conn=conn,
            attribution_label=attribution_label,
            gate_label=gate_label,
        )

    rows = [
        evaluate_break_even_row(
            row=row,
            tracker_label=label,
            created_at=created_at,
        )
        for row in attribution_rows
    ]

    persist_break_even_rows(db, rows)

    summary = summarize_break_even(
        db_path=db,
        report_label=report,
        tracker_label=label,
        created_at=created_at,
        source_attribution_label=resolved_attribution_label,
        rows=rows,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_report(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid shadow observation break-even tracker."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--tracker-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--attribution-label", default=None)
    parser.add_argument("--gate-label", default=None)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_shadow_observation_break_even_tracker(
        db_path=args.db,
        tracker_label=args.tracker_label,
        report_label=args.report_label,
        attribution_label=args.attribution_label,
        gate_label=args.gate_label,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

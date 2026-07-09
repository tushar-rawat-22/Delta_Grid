"""
Mission 46: Shadow Observation Outcome Analytics Dashboard.

This module aggregates Mission 45 shadow observation outcomes into an executive
analytics report.

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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_DECISION = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

OUTCOMES_TABLE = "shadow_observation_outcomes"
ANALYTICS_REPORTS_TABLE = "shadow_observation_outcome_analytics_reports"

NO_OUTCOME_HISTORY_VERDICT = "OUTCOME_ANALYTICS_NO_OUTCOME_HISTORY"
MISSING_OUTCOMES_TABLE_VERDICT = "OUTCOME_ANALYTICS_OUTCOMES_TABLE_MISSING"
NO_MATCHING_OUTCOMES_VERDICT = "OUTCOME_ANALYTICS_NO_MATCHING_OUTCOMES"
SAFETY_BLOCKED_VERDICT = "OUTCOME_ANALYTICS_SAFETY_BLOCKED"
RISK_REVIEW_VERDICT = "OUTCOME_ANALYTICS_RISK_REVIEW_REQUIRED"
REJECTED_VERDICT = "OUTCOME_ANALYTICS_REJECTED_UNECONOMIC"
CLOSE_READY_VERDICT = "OUTCOME_ANALYTICS_CLOSE_READY"
CONTINUED_TRACKING_VERDICT = "OUTCOME_ANALYTICS_CONTINUED_TRACKING"
MIXED_VERDICT = "OUTCOME_ANALYTICS_MIXED_OUTCOME_SET"

OUTCOME_CONTINUED_TRACKING = "OUTCOME_CONTINUED_TRACKING"
OUTCOME_SHADOW_CLOSE_READY = "OUTCOME_SHADOW_CLOSE_READY"
OUTCOME_REJECTED_UNECONOMIC = "OUTCOME_REJECTED_UNECONOMIC"
OUTCOME_RISK_REVIEW_REQUIRED = "OUTCOME_RISK_REVIEW_REQUIRED"
OUTCOME_SAFETY_BLOCKED = "OUTCOME_SAFETY_BLOCKED"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_analytics_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission46-outcome-analytics-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission46-report-{stamp}-{uuid.uuid4().hex[:8]}"


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


def safe_rate(count: int, total: int) -> float:
    if total <= 0:
        return 0.0

    return round(count / total, 6)


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
            CREATE TABLE IF NOT EXISTS shadow_observation_outcome_analytics_reports (
                report_label TEXT PRIMARY KEY,
                analytics_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_outcome_label TEXT,
                observation_count INTEGER NOT NULL,
                continued_count INTEGER NOT NULL,
                close_ready_count INTEGER NOT NULL,
                rejected_count INTEGER NOT NULL,
                risk_review_count INTEGER NOT NULL,
                safety_blocked_count INTEGER NOT NULL,
                continued_rate TEXT NOT NULL,
                close_ready_rate TEXT NOT NULL,
                rejected_rate TEXT NOT NULL,
                total_cost_remaining_usd TEXT NOT NULL,
                total_net_expected_pnl_usd TEXT NOT NULL,
                average_remaining_hours_to_break_even TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def latest_outcome_label(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        """
        SELECT outcome_label
        FROM shadow_observation_outcomes
        ORDER BY created_at DESC, outcome_label DESC
        LIMIT 1
        """
    ).fetchone()

    if row is None:
        return None

    return str(row["outcome_label"])


def load_outcomes(
    conn: sqlite3.Connection,
    outcome_label: str | None,
    gate_label: str | None,
    symbol: str | None,
) -> tuple[str | None, list[sqlite3.Row]]:
    resolved = outcome_label or latest_outcome_label(conn)

    if resolved is None:
        return None, []

    query = """
        SELECT
            outcome_id,
            outcome_label,
            created_at,
            source_decision_label,
            observation_id,
            ledger_label,
            source_gate_label,
            symbol,
            close_decision,
            final_outcome,
            outcome_reason,
            close_ready,
            continued_tracking,
            rejected,
            risk_review_required,
            safety_blocked,
            cost_remaining_usd,
            net_expected_pnl_usd,
            total_cost_usd,
            remaining_hours_to_break_even,
            live_trading,
            live_order_sent,
            capital_deployment,
            risk_flags_json,
            metadata_json
        FROM shadow_observation_outcomes
        WHERE outcome_label = ?
    """
    params: list[Any] = [resolved]

    if gate_label is not None:
        query += " AND source_gate_label = ?"
        params.append(gate_label)

    if symbol is not None:
        query += " AND symbol = ?"
        params.append(symbol)

    query += " ORDER BY symbol ASC, observation_id ASC"

    return resolved, conn.execute(query, params).fetchall()


def build_symbol_summary(rows: list[sqlite3.Row]) -> dict[str, Any]:
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)

    for row in rows:
        grouped[str(row["symbol"])].append(row)

    output: dict[str, Any] = {}

    for symbol, symbol_rows in sorted(grouped.items()):
        outcome_counts = Counter(str(row["final_outcome"]) for row in symbol_rows)
        total = len(symbol_rows)
        total_cost_remaining = round(
            sum(safe_float(row["cost_remaining_usd"]) for row in symbol_rows),
            8,
        )
        total_net_expected = round(
            sum(safe_float(row["net_expected_pnl_usd"]) for row in symbol_rows),
            8,
        )

        remaining_hours = [
            safe_float(row["remaining_hours_to_break_even"])
            for row in symbol_rows
            if row["remaining_hours_to_break_even"] is not None
        ]

        average_remaining = 0.0

        if remaining_hours:
            average_remaining = round(sum(remaining_hours) / len(remaining_hours), 6)

        output[symbol] = {
            "observation_count": total,
            "outcome_counts": dict(outcome_counts),
            "continued_count": outcome_counts.get(OUTCOME_CONTINUED_TRACKING, 0),
            "close_ready_count": outcome_counts.get(OUTCOME_SHADOW_CLOSE_READY, 0),
            "rejected_count": outcome_counts.get(OUTCOME_REJECTED_UNECONOMIC, 0),
            "risk_review_count": outcome_counts.get(OUTCOME_RISK_REVIEW_REQUIRED, 0),
            "safety_blocked_count": outcome_counts.get(OUTCOME_SAFETY_BLOCKED, 0),
            "total_cost_remaining_usd": total_cost_remaining,
            "total_net_expected_pnl_usd": total_net_expected,
            "average_remaining_hours_to_break_even": average_remaining,
        }

    return output


def summarize_outcome_analytics(
    db_path: str | Path,
    report_label: str,
    analytics_label: str,
    created_at: str,
    source_outcome_label: str | None,
    rows: list[sqlite3.Row],
) -> dict[str, Any]:
    observation_count = len(rows)
    outcome_counts = Counter(str(row["final_outcome"]) for row in rows)

    continued_count = outcome_counts.get(OUTCOME_CONTINUED_TRACKING, 0)
    close_ready_count = outcome_counts.get(OUTCOME_SHADOW_CLOSE_READY, 0)
    rejected_count = outcome_counts.get(OUTCOME_REJECTED_UNECONOMIC, 0)
    risk_review_count = outcome_counts.get(OUTCOME_RISK_REVIEW_REQUIRED, 0)
    safety_blocked_count = outcome_counts.get(OUTCOME_SAFETY_BLOCKED, 0)

    total_cost_remaining = round(
        sum(safe_float(row["cost_remaining_usd"]) for row in rows),
        8,
    )
    total_net_expected = round(
        sum(safe_float(row["net_expected_pnl_usd"]) for row in rows),
        8,
    )

    remaining_hours = [
        safe_float(row["remaining_hours_to_break_even"])
        for row in rows
        if row["remaining_hours_to_break_even"] is not None
    ]

    average_remaining = 0.0

    if remaining_hours:
        average_remaining = round(sum(remaining_hours) / len(remaining_hours), 6)

    safety_state_breach_count = sum(
        1
        for row in rows
        if row["live_trading"] != LIVE_TRADING_STATUS
        or int(row["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or row["capital_deployment"] != CAPITAL_DEPLOYMENT_DECISION
    )

    symbol_summary = build_symbol_summary(rows)

    if observation_count == 0:
        global_verdict = NO_MATCHING_OUTCOMES_VERDICT
        recommended_action = "RUN_MISSION_45_OUTCOME_FINALIZER"
    elif safety_blocked_count > 0 or safety_state_breach_count > 0:
        global_verdict = SAFETY_BLOCKED_VERDICT
        recommended_action = "STOP_AND_REVIEW_OUTCOME_ANALYTICS_SAFETY_BLOCK"
    elif risk_review_count > 0:
        global_verdict = RISK_REVIEW_VERDICT
        recommended_action = "REVIEW_RISK_OUTCOMES_BEFORE_NEXT_STAGE"
    elif rejected_count > 0 and continued_count == 0 and close_ready_count == 0:
        global_verdict = REJECTED_VERDICT
        recommended_action = "REWORK_OR_REJECT_UNECONOMIC_SHADOW_THESIS"
    elif close_ready_count > 0 and continued_count == 0 and rejected_count == 0:
        global_verdict = CLOSE_READY_VERDICT
        recommended_action = "PREPARE_SHADOW_CLOSE_ACCOUNTING_REVIEW"
    elif continued_count > 0 and close_ready_count == 0 and rejected_count == 0:
        global_verdict = CONTINUED_TRACKING_VERDICT
        recommended_action = "CONTINUE_SHADOW_MONITORING_AND_WAIT_FOR_BREAK_EVEN"
    else:
        global_verdict = MIXED_VERDICT
        recommended_action = "REVIEW_MIXED_OUTCOME_ANALYTICS"

    return {
        "report_label": report_label,
        "analytics_label": analytics_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_outcome_label": source_outcome_label,
        "observation_count": observation_count,
        "continued_count": continued_count,
        "close_ready_count": close_ready_count,
        "rejected_count": rejected_count,
        "risk_review_count": risk_review_count,
        "safety_blocked_count": safety_blocked_count,
        "safety_state_breach_count": safety_state_breach_count,
        "continued_rate": safe_rate(continued_count, observation_count),
        "close_ready_rate": safe_rate(close_ready_count, observation_count),
        "rejected_rate": safe_rate(rejected_count, observation_count),
        "total_cost_remaining_usd": total_cost_remaining,
        "total_net_expected_pnl_usd": total_net_expected,
        "average_remaining_hours_to_break_even": average_remaining,
        "outcome_counts": dict(outcome_counts),
        "symbol_summary": symbol_summary,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    outcome_counts = "\n".join(
        f"- {name}: {count}"
        for name, count in summary["outcome_counts"].items()
    ) or "- None"

    symbol_lines = []

    for symbol, data in summary["symbol_summary"].items():
        symbol_lines.append(
            "- "
            + symbol
            + ": "
            + f"observations={data['observation_count']}, "
            + f"continued={data['continued_count']}, "
            + f"close_ready={data['close_ready_count']}, "
            + f"rejected={data['rejected_count']}, "
            + f"cost_remaining={data['total_cost_remaining_usd']}, "
            + f"net_expected={data['total_net_expected_pnl_usd']}"
        )

    symbol_summary = "\n".join(symbol_lines) or "- None"

    return f"""# DeltaGrid Mission 46 Shadow Observation Outcome Analytics Report

Report label: {summary['report_label']}
Analytics label: {summary['analytics_label']}
Created at: {summary['created_at']}
Source outcome label: {summary['source_outcome_label']}

## Executive Summary

Observation count: {summary['observation_count']}
Continued count: {summary['continued_count']}
Close ready count: {summary['close_ready_count']}
Rejected count: {summary['rejected_count']}
Risk review count: {summary['risk_review_count']}
Safety blocked count: {summary['safety_blocked_count']}
Safety state breach count: {summary['safety_state_breach_count']}

Continued rate: {summary['continued_rate']}
Close ready rate: {summary['close_ready_rate']}
Rejected rate: {summary['rejected_rate']}

Total cost remaining USD: {summary['total_cost_remaining_usd']}
Total net expected PnL USD: {summary['total_net_expected_pnl_usd']}
Average remaining hours to break-even: {summary['average_remaining_hours_to_break_even']}

## Outcome Counts

{outcome_counts}

## Symbol Summary

{symbol_summary}

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
            INSERT OR REPLACE INTO shadow_observation_outcome_analytics_reports (
                report_label,
                analytics_label,
                created_at,
                source_outcome_label,
                observation_count,
                continued_count,
                close_ready_count,
                rejected_count,
                risk_review_count,
                safety_blocked_count,
                continued_rate,
                close_ready_rate,
                rejected_rate,
                total_cost_remaining_usd,
                total_net_expected_pnl_usd,
                average_remaining_hours_to_break_even,
                global_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["analytics_label"],
                summary["created_at"],
                summary["source_outcome_label"],
                summary["observation_count"],
                summary["continued_count"],
                summary["close_ready_count"],
                summary["rejected_count"],
                summary["risk_review_count"],
                summary["safety_blocked_count"],
                str(summary["continued_rate"]),
                str(summary["close_ready_rate"]),
                str(summary["rejected_rate"]),
                str(summary["total_cost_remaining_usd"]),
                str(summary["total_net_expected_pnl_usd"]),
                str(summary["average_remaining_hours_to_break_even"]),
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def run_shadow_observation_outcome_analytics_dashboard(
    db_path: str | Path = "offchain/deltagrid.db",
    analytics_label: str | None = None,
    report_label: str | None = None,
    outcome_label: str | None = None,
    gate_label: str | None = None,
    symbol: str | None = None,
) -> dict[str, Any]:
    db = Path(db_path)
    label = analytics_label or new_analytics_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    if not db.exists():
        summary = {
            "report_label": report,
            "analytics_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": False,
            "tables_present": False,
            "source_outcome_label": outcome_label,
            "observation_count": 0,
            "continued_count": 0,
            "close_ready_count": 0,
            "rejected_count": 0,
            "risk_review_count": 0,
            "safety_blocked_count": 0,
            "safety_state_breach_count": 0,
            "continued_rate": 0.0,
            "close_ready_rate": 0.0,
            "rejected_rate": 0.0,
            "total_cost_remaining_usd": 0.0,
            "total_net_expected_pnl_usd": 0.0,
            "average_remaining_hours_to_break_even": 0.0,
            "outcome_counts": {},
            "symbol_summary": {},
            "global_verdict": NO_OUTCOME_HISTORY_VERDICT,
            "recommended_action": "RUN_MISSION_45_OUTCOME_FINALIZER",
        }
        summary["markdown_report"] = build_markdown_report(summary)
        return summary

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        if not table_exists(conn, OUTCOMES_TABLE):
            summary = {
                "report_label": report,
                "analytics_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "tables_present": False,
                "missing_tables": [OUTCOMES_TABLE],
                "source_outcome_label": outcome_label,
                "observation_count": 0,
                "continued_count": 0,
                "close_ready_count": 0,
                "rejected_count": 0,
                "risk_review_count": 0,
                "safety_blocked_count": 0,
                "safety_state_breach_count": 0,
                "continued_rate": 0.0,
                "close_ready_rate": 0.0,
                "rejected_rate": 0.0,
                "total_cost_remaining_usd": 0.0,
                "total_net_expected_pnl_usd": 0.0,
                "average_remaining_hours_to_break_even": 0.0,
                "outcome_counts": {},
                "symbol_summary": {},
                "global_verdict": MISSING_OUTCOMES_TABLE_VERDICT,
                "recommended_action": "RUN_MISSION_45_OUTCOME_FINALIZER",
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        resolved_outcome_label, rows = load_outcomes(
            conn=conn,
            outcome_label=outcome_label,
            gate_label=gate_label,
            symbol=symbol,
        )

    summary = summarize_outcome_analytics(
        db_path=db,
        report_label=report,
        analytics_label=label,
        created_at=created_at,
        source_outcome_label=resolved_outcome_label,
        rows=rows,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_report(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid shadow observation outcome analytics dashboard."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--analytics-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--outcome-label", default=None)
    parser.add_argument("--gate-label", default=None)
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_shadow_observation_outcome_analytics_dashboard(
        db_path=args.db,
        analytics_label=args.analytics_label,
        report_label=args.report_label,
        outcome_label=args.outcome_label,
        gate_label=args.gate_label,
        symbol=args.symbol,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

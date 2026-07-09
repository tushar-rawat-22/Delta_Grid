"""
Mission 47: Shadow Research Executive Daily Report.

This module aggregates latest shadow research report tables into one executive
daily report.

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_DECISION = "BLOCKED"

EXECUTIVE_DAILY_REPORTS_TABLE = "shadow_research_executive_daily_reports"

NO_DATABASE_VERDICT = "EXECUTIVE_DAILY_NO_DATABASE_HISTORY"
NO_REPORT_SECTIONS_VERDICT = "EXECUTIVE_DAILY_NO_REPORT_SECTIONS"
SAFETY_BLOCKED_VERDICT = "EXECUTIVE_DAILY_SAFETY_BLOCKED"
RISK_REVIEW_VERDICT = "EXECUTIVE_DAILY_RISK_REVIEW_REQUIRED"
CONTINUE_SHADOW_RESEARCH_VERDICT = "EXECUTIVE_DAILY_CONTINUE_SHADOW_RESEARCH_NO_LIVE_TRADING"

SAFETY_KEYS = {
    "safety_breach_count",
    "safety_blocked_count",
    "safety_state_breach_count",
    "live_trading_breach_count",
    "breach_count",
}

RISK_KEYS = {
    "risk_review_count",
    "risk_review_required_count",
}

IMPORTANT_VALUE_KEYS = {
    "observation_count",
    "candidate_count",
    "scenario_count",
    "pipeline_run_count",
    "approved_count",
    "rejected_count",
    "continued_count",
    "continue_count",
    "close_ready_count",
    "close_eligible_count",
    "pending_count",
    "reached_count",
    "positive_count",
    "negative_count",
    "total_cost_remaining_usd",
    "total_net_expected_pnl_usd",
    "total_net_expected_pnl_usd",
    "total_cost_usd",
    "total_gross_expected_funding_pnl_usd",
    "average_remaining_hours_to_break_even",
    "max_remaining_hours_to_break_even",
    "approval_rate",
    "continued_rate",
    "close_ready_rate",
    "rejected_rate",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_daily_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission47-executive-daily-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission47-report-{stamp}-{uuid.uuid4().hex[:8]}"


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


def safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


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


def table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({quote_identifier(table_name)})").fetchall()
    return [str(row[1]) for row in rows]


def ensure_schema(db_path: str | Path) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_research_executive_daily_reports (
                report_label TEXT PRIMARY KEY,
                daily_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_report_section_count INTEGER NOT NULL,
                present_section_count INTEGER NOT NULL,
                safety_issue_count INTEGER NOT NULL,
                risk_review_count INTEGER NOT NULL,
                live_trading_status TEXT NOT NULL,
                capital_deployment_status TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def discover_report_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name LIKE 'shadow_%'
        ORDER BY name ASC
        """
    ).fetchall()

    tables = []

    for row in rows:
        table = str(row["name"])

        if table == EXECUTIVE_DAILY_REPORTS_TABLE:
            continue

        if table.endswith("_reports") or table.endswith("_report") or "_reports" in table:
            tables.append(table)

    return tables


def latest_row_from_table(
    conn: sqlite3.Connection,
    table_name: str,
) -> dict[str, Any] | None:
    columns = table_columns(conn, table_name)

    if not columns:
        return None

    if "created_at" in columns:
        order_clause = f"{quote_identifier('created_at')} DESC"
    else:
        order_clause = "rowid DESC"

    query = f"""
        SELECT *
        FROM {quote_identifier(table_name)}
        ORDER BY {order_clause}
        LIMIT 1
    """

    row = conn.execute(query).fetchone()

    if row is None:
        return None

    return {key: row[key] for key in row.keys()}


def extract_label(row: dict[str, Any]) -> str | None:
    for key in [
        "report_label",
        "daily_label",
        "analytics_label",
        "outcome_label",
        "decision_label",
        "tracker_label",
        "attribution_label",
        "gate_label",
        "replay_label",
        "ledger_label",
        "snapshot_label",
    ]:
        if key in row and row[key] is not None:
            return str(row[key])

    return None


def extract_metrics(row: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}

    for key, value in row.items():
        if key in IMPORTANT_VALUE_KEYS:
            output[key] = value
        elif key.endswith("_count"):
            output[key] = value
        elif key.endswith("_rate"):
            output[key] = value
        elif key.startswith("total_"):
            output[key] = value
        elif key.startswith("average_"):
            output[key] = value
        elif key.startswith("max_"):
            output[key] = value

    return output


def build_section(table_name: str, row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {
            "table_name": table_name,
            "status": "EMPTY",
            "label": None,
            "global_verdict": None,
            "recommended_action": None,
            "metrics": {},
            "latest_row": None,
        }

    return {
        "table_name": table_name,
        "status": "PRESENT",
        "label": extract_label(row),
        "created_at": row.get("created_at"),
        "global_verdict": row.get("global_verdict"),
        "recommended_action": row.get("recommended_action"),
        "metrics": extract_metrics(row),
        "latest_row": row,
    }


def section_safety_count(section: dict[str, Any]) -> int:
    row = section.get("latest_row") or {}
    metrics = section.get("metrics") or {}
    total = 0

    for key in SAFETY_KEYS:
        total += safe_int(row.get(key))
        if key not in row:
            total += safe_int(metrics.get(key))

    return total


def section_risk_count(section: dict[str, Any]) -> int:
    row = section.get("latest_row") or {}
    metrics = section.get("metrics") or {}
    total = 0

    for key in RISK_KEYS:
        total += safe_int(row.get(key))
        if key not in row:
            total += safe_int(metrics.get(key))

    return total


def build_markdown_report(summary: dict[str, Any]) -> str:
    section_lines = []

    for section in summary["sections"]:
        metrics = section.get("metrics") or {}
        metric_preview = ", ".join(
            f"{key}={value}"
            for key, value in list(metrics.items())[:8]
        )

        if not metric_preview:
            metric_preview = "no compact metrics"

        section_lines.append(
            "- "
            + section["table_name"]
            + ": "
            + f"status={section['status']}, "
            + f"label={section.get('label')}, "
            + f"verdict={section.get('global_verdict')}, "
            + metric_preview
        )

    sections_markdown = "\n".join(section_lines) or "- None"

    return f"""# DeltaGrid Mission 47 Shadow Research Executive Daily Report

Report label: {summary['report_label']}
Daily label: {summary['daily_label']}
Created at: {summary['created_at']}

## Executive Control Summary

Source report section count: {summary['source_report_section_count']}
Present section count: {summary['present_section_count']}
Safety issue count: {summary['safety_issue_count']}
Risk review count: {summary['risk_review_count']}

Live trading status: {summary['live_trading_status']}
Capital deployment status: {summary['capital_deployment_status']}

## Section Summary

{sections_markdown}

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
            INSERT OR REPLACE INTO shadow_research_executive_daily_reports (
                report_label,
                daily_label,
                created_at,
                source_report_section_count,
                present_section_count,
                safety_issue_count,
                risk_review_count,
                live_trading_status,
                capital_deployment_status,
                global_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["daily_label"],
                summary["created_at"],
                summary["source_report_section_count"],
                summary["present_section_count"],
                summary["safety_issue_count"],
                summary["risk_review_count"],
                summary["live_trading_status"],
                summary["capital_deployment_status"],
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def summarize_sections(
    db_path: str | Path,
    report_label: str,
    daily_label: str,
    created_at: str,
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    present_sections = [
        section for section in sections
        if section["status"] == "PRESENT"
    ]

    safety_issue_count = sum(section_safety_count(section) for section in present_sections)
    risk_review_count = sum(section_risk_count(section) for section in present_sections)

    if not sections:
        global_verdict = NO_REPORT_SECTIONS_VERDICT
        recommended_action = "RUN_SHADOW_RESEARCH_PIPELINE_REPORTS_FIRST"
    elif safety_issue_count > 0:
        global_verdict = SAFETY_BLOCKED_VERDICT
        recommended_action = "STOP_AND_REVIEW_EXECUTIVE_DAILY_SAFETY_ISSUES"
    elif risk_review_count > 0:
        global_verdict = RISK_REVIEW_VERDICT
        recommended_action = "REVIEW_RISK_SECTIONS_BEFORE_NEXT_RESEARCH_STAGE"
    else:
        global_verdict = CONTINUE_SHADOW_RESEARCH_VERDICT
        recommended_action = "CONTINUE_SHADOW_RESEARCH_NO_LIVE_TRADING"

    return {
        "report_label": report_label,
        "daily_label": daily_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_report_section_count": len(sections),
        "present_section_count": len(present_sections),
        "safety_issue_count": safety_issue_count,
        "risk_review_count": risk_review_count,
        "live_trading_status": LIVE_TRADING_STATUS,
        "capital_deployment_status": CAPITAL_DEPLOYMENT_DECISION,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
        "sections": sections,
    }


def run_shadow_research_executive_daily_report(
    db_path: str | Path = "offchain/deltagrid.db",
    daily_label: str | None = None,
    report_label: str | None = None,
) -> dict[str, Any]:
    db = Path(db_path)
    daily = daily_label or new_daily_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    if not db.exists():
        summary = {
            "report_label": report,
            "daily_label": daily,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": False,
            "source_report_section_count": 0,
            "present_section_count": 0,
            "safety_issue_count": 0,
            "risk_review_count": 0,
            "live_trading_status": LIVE_TRADING_STATUS,
            "capital_deployment_status": CAPITAL_DEPLOYMENT_DECISION,
            "global_verdict": NO_DATABASE_VERDICT,
            "recommended_action": "RUN_SHADOW_RESEARCH_PIPELINE_REPORTS_FIRST",
            "sections": [],
        }
        summary["markdown_report"] = build_markdown_report(summary)
        return summary

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        report_tables = discover_report_tables(conn)
        sections = [
            build_section(
                table_name=table_name,
                row=latest_row_from_table(conn, table_name),
            )
            for table_name in report_tables
        ]

    summary = summarize_sections(
        db_path=db,
        report_label=report,
        daily_label=daily,
        created_at=created_at,
        sections=sections,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_report(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid shadow research executive daily report."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--daily-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_shadow_research_executive_daily_report(
        db_path=args.db,
        daily_label=args.daily_label,
        report_label=args.report_label,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

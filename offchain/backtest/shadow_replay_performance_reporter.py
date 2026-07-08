"""
Mission 36: Shadow Replay Performance Reporter.

This module summarizes Mission 35 shadow candidate replay results into a
performance-style research report.

It is local, free, read-mostly, and safe.

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


LIVE_TRADING_REQUIRED_STATUS = "DISABLED"

NO_REPLAY_HISTORY_VERDICT = "NO_SHADOW_REPLAY_HISTORY_FOUND"
MISSING_REPLAY_TABLES_VERDICT = "SHADOW_REPLAY_TABLES_MISSING"
SAFETY_BREACH_VERDICT = "PERFORMANCE_REVIEW_SAFETY_BREACH_DETECTED"
NO_APPROVED_REPLAY_VERDICT = "PERFORMANCE_REVIEW_REJECTIONS_ONLY_CONTINUE_SHADOW_RESEARCH"
APPROVED_REPLAY_VERDICT = "PERFORMANCE_REVIEW_SHADOW_REPLAY_APPROVED_NO_LIVE_TRADING"

REPLAY_RUNS_TABLE = "shadow_candidate_replay_runs"
REPLAY_SCENARIOS_TABLE = "shadow_candidate_replay_scenarios"
PERFORMANCE_REPORTS_TABLE = "shadow_replay_performance_reports"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission36-performance-{stamp}-{uuid.uuid4().hex[:8]}"


def safe_json_loads(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


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


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0

    return round(float(numerator) / float(denominator), 6)


def ensure_schema(db_path: str | Path) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_replay_performance_reports (
                report_label TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                source_replay_label TEXT,
                replay_count INTEGER NOT NULL,
                scenario_count INTEGER NOT NULL,
                pipeline_run_count INTEGER NOT NULL,
                total_approved_count INTEGER NOT NULL,
                total_rejected_count INTEGER NOT NULL,
                total_paper_positions_count INTEGER NOT NULL,
                approval_rate TEXT NOT NULL,
                rejection_rate TEXT NOT NULL,
                paper_position_rate TEXT NOT NULL,
                live_trading_breach_count INTEGER NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def load_replay_rows(
    conn: sqlite3.Connection,
    replay_label: str | None,
    limit: int,
) -> list[sqlite3.Row]:
    query = """
        SELECT
            replay_label,
            created_at,
            live_trading,
            scenario_count,
            pipeline_run_count,
            total_approved_count,
            total_rejected_count,
            total_paper_positions_count,
            global_verdict,
            recommended_action,
            scenarios_json,
            history_summary_json
        FROM shadow_candidate_replay_runs
    """
    params: list[Any] = []

    if replay_label is not None:
        query += " WHERE replay_label = ?"
        params.append(replay_label)

    query += " ORDER BY created_at DESC, replay_label DESC LIMIT ?"
    params.append(limit)

    return conn.execute(query, params).fetchall()


def load_scenario_rows(
    conn: sqlite3.Connection,
    replay_labels: list[str],
) -> list[sqlite3.Row]:
    if not replay_labels:
        return []

    placeholders = ", ".join("?" for _ in replay_labels)

    return conn.execute(
        f"""
        SELECT
            replay_label,
            scenario_name,
            run_label,
            live_trading,
            approved_count,
            rejected_count,
            paper_positions_count,
            verdict,
            recommended_action
        FROM shadow_candidate_replay_scenarios
        WHERE replay_label IN ({placeholders})
        ORDER BY id ASC
        """,
        replay_labels,
    ).fetchall()


def build_markdown_report(summary: dict[str, Any]) -> str:
    scenario_distribution = "\n".join(
        f"- {name}: {count}"
        for name, count in summary["scenario_distribution"].items()
    ) or "- None"

    verdict_counts = "\n".join(
        f"- {name}: {count}"
        for name, count in summary["scenario_verdict_counts"].items()
    ) or "- None"

    return f"""# DeltaGrid Mission 36 Shadow Replay Performance Report

Report label: {summary['report_label']}
Created at: {summary['created_at']}
Source replay label: {summary['source_replay_label']}

## Aggregate Metrics

Replay count: {summary['replay_count']}
Scenario count: {summary['scenario_count']}
Pipeline run count: {summary['pipeline_run_count']}

Approved candidates: {summary['total_approved_count']}
Rejected candidates: {summary['total_rejected_count']}
Shadow paper positions: {summary['total_paper_positions_count']}

Approval rate: {summary['approval_rate']}
Rejection rate: {summary['rejection_rate']}
Paper position rate: {summary['paper_position_rate']}

## Safety

Live trading required status: {summary['live_trading_required_status']}
Live trading breach count: {summary['live_trading_breach_count']}
Live trading breach labels: {summary['live_trading_breach_labels']}

## Scenario Distribution

{scenario_distribution}

## Scenario Verdict Counts

{verdict_counts}

## Verdict

Global verdict: {summary['global_verdict']}
Recommended action: {summary['recommended_action']}

## Safety Statement

No private keys were read.
No signatures were produced.
No exchange orders were sent.
No live capital was used.
"""


def persist_performance_report(
    db_path: str | Path,
    summary: dict[str, Any],
    markdown_report: str,
) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO shadow_replay_performance_reports (
                report_label,
                created_at,
                source_replay_label,
                replay_count,
                scenario_count,
                pipeline_run_count,
                total_approved_count,
                total_rejected_count,
                total_paper_positions_count,
                approval_rate,
                rejection_rate,
                paper_position_rate,
                live_trading_breach_count,
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
                summary["source_replay_label"],
                summary["replay_count"],
                summary["scenario_count"],
                summary["pipeline_run_count"],
                summary["total_approved_count"],
                summary["total_rejected_count"],
                summary["total_paper_positions_count"],
                str(summary["approval_rate"]),
                str(summary["rejection_rate"]),
                str(summary["paper_position_rate"]),
                summary["live_trading_breach_count"],
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def generate_shadow_replay_performance_report(
    db_path: str | Path = "offchain/deltagrid.db",
    report_label: str | None = None,
    replay_label: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    if limit <= 0:
        raise ValueError("limit must be greater than 0")

    db = Path(db_path)
    label = report_label or new_report_label()
    created_at = utc_now()

    if not db.exists():
        summary = {
            "report_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": False,
            "source_replay_label": replay_label,
            "replay_count": 0,
            "scenario_count": 0,
            "pipeline_run_count": 0,
            "total_approved_count": 0,
            "total_rejected_count": 0,
            "total_paper_positions_count": 0,
            "approval_rate": 0.0,
            "rejection_rate": 0.0,
            "paper_position_rate": 0.0,
            "scenario_distribution": {},
            "scenario_verdict_counts": {},
            "live_trading_required_status": LIVE_TRADING_REQUIRED_STATUS,
            "live_trading_breach_count": 0,
            "live_trading_breach_labels": [],
            "global_verdict": NO_REPLAY_HISTORY_VERDICT,
            "recommended_action": "RUN_MISSION_35_SHADOW_CANDIDATE_REPLAY",
        }
        summary["markdown_report"] = build_markdown_report(summary)
        return summary

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        replay_table_present = table_exists(conn, REPLAY_RUNS_TABLE)
        scenario_table_present = table_exists(conn, REPLAY_SCENARIOS_TABLE)

        if not replay_table_present or not scenario_table_present:
            missing = []
            if not replay_table_present:
                missing.append(REPLAY_RUNS_TABLE)
            if not scenario_table_present:
                missing.append(REPLAY_SCENARIOS_TABLE)

            summary = {
                "report_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "tables_present": False,
                "missing_tables": missing,
                "source_replay_label": replay_label,
                "replay_count": 0,
                "scenario_count": 0,
                "pipeline_run_count": 0,
                "total_approved_count": 0,
                "total_rejected_count": 0,
                "total_paper_positions_count": 0,
                "approval_rate": 0.0,
                "rejection_rate": 0.0,
                "paper_position_rate": 0.0,
                "scenario_distribution": {},
                "scenario_verdict_counts": {},
                "live_trading_required_status": LIVE_TRADING_REQUIRED_STATUS,
                "live_trading_breach_count": 0,
                "live_trading_breach_labels": [],
                "global_verdict": MISSING_REPLAY_TABLES_VERDICT,
                "recommended_action": "RUN_MISSION_35_TO_CREATE_REPLAY_TABLES",
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_performance_report(db, summary, summary["markdown_report"])
            return summary

        replay_rows = load_replay_rows(
            conn=conn,
            replay_label=replay_label,
            limit=limit,
        )

        replay_labels = [row["replay_label"] for row in replay_rows]
        scenario_rows = load_scenario_rows(conn, replay_labels)

    replay_count = len(replay_rows)
    scenario_count = sum(int(row["scenario_count"]) for row in replay_rows)
    pipeline_run_count = sum(int(row["pipeline_run_count"]) for row in replay_rows)
    total_approved = sum(int(row["total_approved_count"]) for row in replay_rows)
    total_rejected = sum(int(row["total_rejected_count"]) for row in replay_rows)
    total_paper_positions = sum(int(row["total_paper_positions_count"]) for row in replay_rows)

    candidate_total = total_approved + total_rejected

    scenario_distribution = dict(
        Counter(str(row["scenario_name"]) for row in scenario_rows)
    )
    scenario_verdict_counts = dict(
        Counter(str(row["verdict"]) for row in scenario_rows)
    )

    live_trading_breach_labels: list[str] = []

    for row in replay_rows:
        if row["live_trading"] != LIVE_TRADING_REQUIRED_STATUS:
            live_trading_breach_labels.append(row["replay_label"])

        history = safe_json_loads(row["history_summary_json"], {})
        if int(history.get("breach_count", 0)) > 0:
            live_trading_breach_labels.append(row["replay_label"])

    for row in scenario_rows:
        if row["live_trading"] != LIVE_TRADING_REQUIRED_STATUS:
            live_trading_breach_labels.append(row["run_label"])

    live_trading_breach_labels = sorted(set(live_trading_breach_labels))
    live_trading_breach_count = len(live_trading_breach_labels)

    if replay_count == 0:
        global_verdict = NO_REPLAY_HISTORY_VERDICT
        recommended_action = "RUN_MISSION_35_SHADOW_CANDIDATE_REPLAY"
    elif live_trading_breach_count > 0:
        global_verdict = SAFETY_BREACH_VERDICT
        recommended_action = "STOP_AND_REVIEW_REPLAY_SAFETY_BREACH"
    elif total_approved > 0:
        global_verdict = APPROVED_REPLAY_VERDICT
        recommended_action = "USE_PERFORMANCE_REPORT_FOR_SHADOW_RESEARCH_DECISIONS"
    else:
        global_verdict = NO_APPROVED_REPLAY_VERDICT
        recommended_action = "KEEP_REPLAYING_STRONGER_SHADOW_CANDIDATES"

    summary = {
        "report_label": label,
        "created_at": created_at,
        "db_path": str(db),
        "database_exists": True,
        "tables_present": True,
        "source_replay_label": replay_label,
        "limit": limit,
        "replay_count": replay_count,
        "scenario_count": scenario_count,
        "pipeline_run_count": pipeline_run_count,
        "total_approved_count": total_approved,
        "total_rejected_count": total_rejected,
        "total_paper_positions_count": total_paper_positions,
        "approval_rate": safe_rate(total_approved, candidate_total),
        "rejection_rate": safe_rate(total_rejected, candidate_total),
        "paper_position_rate": safe_rate(total_paper_positions, max(pipeline_run_count, 1)),
        "scenario_distribution": scenario_distribution,
        "scenario_verdict_counts": scenario_verdict_counts,
        "live_trading_required_status": LIVE_TRADING_REQUIRED_STATUS,
        "live_trading_breach_count": live_trading_breach_count,
        "live_trading_breach_labels": live_trading_breach_labels,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
    }

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_performance_report(
        db_path=db,
        summary=summary,
        markdown_report=markdown_report,
    )

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate DeltaGrid shadow replay performance report."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--replay-label", default=None)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = generate_shadow_replay_performance_report(
        db_path=args.db,
        report_label=args.report_label,
        replay_label=args.replay_label,
        limit=args.limit,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

"""
Mission 34: Shadow Research Run History Inspector.

This module reads Mission 33 research pipeline runs from SQLite and produces
a safe, read-only summary of shadow research history.

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
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LIVE_TRADING_REQUIRED_STATUS = "DISABLED"

NO_HISTORY_VERDICT = "NO_RESEARCH_PIPELINE_HISTORY_FOUND"
NO_MATCHING_RUNS_VERDICT = "NO_MATCHING_RESEARCH_PIPELINE_RUNS_FOUND"
MISSING_TABLES_VERDICT = "RESEARCH_PIPELINE_HISTORY_TABLES_MISSING"
SAFETY_BREACH_VERDICT = "SAFETY_BREACH_LIVE_TRADING_FLAG_PRESENT"
NO_GO_HISTORY_VERDICT = "HISTORY_REVIEW_NO_GO_CONTINUE_SHADOW_RESEARCH"
SHADOW_APPROVED_HISTORY_VERDICT = "HISTORY_REVIEW_SHADOW_APPROVED_NO_LIVE_TRADING"
GENERAL_HISTORY_VERDICT = "HISTORY_REVIEW_COMPLETE_NO_LIVE_TRADING"

PIPELINE_RUNS_TABLE = "research_pipeline_runs"
PIPELINE_STAGE_TABLE = "research_pipeline_stage_results"
PIPELINE_REPORTS_TABLE = "research_pipeline_reports"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def inspect_research_run_history(
    db_path: str | Path = "offchain/deltagrid.db",
    limit: int = 10,
    run_label: str | None = None,
    include_reports: bool = False,
) -> dict[str, Any]:
    db = Path(db_path)

    if limit <= 0:
        raise ValueError("limit must be greater than 0")

    if not db.exists():
        return {
            "inspected_at": utc_now(),
            "db_path": str(db),
            "database_exists": False,
            "tables_present": False,
            "total_runs": 0,
            "runs": [],
            "verdict_counts": {},
            "safety": {
                "live_trading_disabled_all": True,
                "live_trading_required_status": LIVE_TRADING_REQUIRED_STATUS,
                "breach_count": 0,
            },
            "global_verdict": NO_HISTORY_VERDICT,
            "recommended_action": "RUN_MISSION_33_SHADOW_PIPELINE",
        }

    with sqlite3.connect(db) as conn:
        runs_table_present = table_exists(conn, PIPELINE_RUNS_TABLE)
        stage_table_present = table_exists(conn, PIPELINE_STAGE_TABLE)
        reports_table_present = table_exists(conn, PIPELINE_REPORTS_TABLE)

        if not runs_table_present:
            return {
                "inspected_at": utc_now(),
                "db_path": str(db),
                "database_exists": True,
                "tables_present": False,
                "missing_tables": [PIPELINE_RUNS_TABLE],
                "total_runs": 0,
                "runs": [],
                "verdict_counts": {},
                "safety": {
                    "live_trading_disabled_all": True,
                    "live_trading_required_status": LIVE_TRADING_REQUIRED_STATUS,
                    "breach_count": 0,
                },
                "global_verdict": MISSING_TABLES_VERDICT,
                "recommended_action": "RUN_MISSION_33_SHADOW_PIPELINE_TO_CREATE_HISTORY",
            }

        query = """
            SELECT
                run_label,
                created_at,
                mode,
                live_trading,
                verdict,
                recommended_action,
                symbols_json,
                approved_count,
                rejected_count,
                paper_positions_count,
                alerts_json
            FROM research_pipeline_runs
        """
        params: list[Any] = []

        if run_label is not None:
            query += " WHERE run_label = ?"
            params.append(run_label)

        query += " ORDER BY created_at DESC, run_label DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

        runs: list[dict[str, Any]] = []

        for row in rows:
            current_run_label = row[0]
            alerts = safe_json_loads(row[10], [])
            symbols = safe_json_loads(row[6], [])

            stage_rows: list[dict[str, Any]] = []
            if stage_table_present:
                raw_stages = conn.execute(
                    """
                    SELECT stage_name, status, details_json
                    FROM research_pipeline_stage_results
                    WHERE run_label = ?
                    ORDER BY id ASC
                    """,
                    (current_run_label,),
                ).fetchall()

                for stage in raw_stages:
                    stage_rows.append(
                        {
                            "stage_name": stage[0],
                            "status": stage[1],
                            "details": safe_json_loads(stage[2], {}),
                        }
                    )

            report_length = None
            report_text = None
            if reports_table_present:
                report = conn.execute(
                    """
                    SELECT markdown_report
                    FROM research_pipeline_reports
                    WHERE run_label = ?
                    """,
                    (current_run_label,),
                ).fetchone()

                if report is not None:
                    report_text = report[0]
                    report_length = len(report_text)

            blocking_alert_count = sum(
                1
                for alert in alerts
                if str(alert.get("level", "")).upper() == "BLOCKING"
            )

            run_data = {
                "run_label": current_run_label,
                "created_at": row[1],
                "mode": row[2],
                "live_trading": row[3],
                "verdict": row[4],
                "recommended_action": row[5],
                "symbols": symbols,
                "approved_count": int(row[7]),
                "rejected_count": int(row[8]),
                "paper_positions_count": int(row[9]),
                "alert_count": len(alerts),
                "blocking_alert_count": blocking_alert_count,
                "alerts": alerts,
                "stage_count": len(stage_rows),
                "stages": stage_rows,
                "report_length": report_length,
            }

            if include_reports:
                run_data["markdown_report"] = report_text

            runs.append(run_data)

    verdict_counts = dict(Counter(run["verdict"] for run in runs))
    live_trading_breaches = [
        run
        for run in runs
        if run["live_trading"] != LIVE_TRADING_REQUIRED_STATUS
    ]

    live_trading_disabled_all = len(live_trading_breaches) == 0

    if not runs:
        global_verdict = NO_MATCHING_RUNS_VERDICT if run_label else NO_HISTORY_VERDICT
        recommended_action = "RUN_OR_SELECT_VALID_MISSION_33_PIPELINE_RUN"
    elif not live_trading_disabled_all:
        global_verdict = SAFETY_BREACH_VERDICT
        recommended_action = "STOP_AND_REVIEW_HISTORY_FOR_UNSAFE_LIVE_TRADING_FLAG"
    elif any(run["approved_count"] > 0 for run in runs):
        global_verdict = SHADOW_APPROVED_HISTORY_VERDICT
        recommended_action = "CONTINUE_SHADOW_OBSERVATION_AND_COLLECT_MORE_HISTORY"
    elif all(run["approved_count"] == 0 for run in runs):
        global_verdict = NO_GO_HISTORY_VERDICT
        recommended_action = "KEEP_SCANNING_FOR_STRONGER_FUNDING_EDGE"
    else:
        global_verdict = GENERAL_HISTORY_VERDICT
        recommended_action = "CONTINUE_SHADOW_RESEARCH"

    return {
        "inspected_at": utc_now(),
        "db_path": str(db),
        "database_exists": True,
        "tables_present": True,
        "stage_table_present": stage_table_present,
        "reports_table_present": reports_table_present,
        "limit": limit,
        "filter_run_label": run_label,
        "total_runs": len(runs),
        "verdict_counts": verdict_counts,
        "latest_run_label": None if not runs else runs[0]["run_label"],
        "latest_verdict": None if not runs else runs[0]["verdict"],
        "runs": runs,
        "safety": {
            "live_trading_disabled_all": live_trading_disabled_all,
            "live_trading_required_status": LIVE_TRADING_REQUIRED_STATUS,
            "breach_count": len(live_trading_breaches),
            "breach_run_labels": [
                run["run_label"]
                for run in live_trading_breaches
            ],
        },
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect DeltaGrid Mission 33 shadow research run history."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--run-label", default=None)
    parser.add_argument("--include-reports", action="store_true")

    args = parser.parse_args()

    result = inspect_research_run_history(
        db_path=args.db,
        limit=args.limit,
        run_label=args.run_label,
        include_reports=args.include_reports,
    )

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

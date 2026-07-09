"""
Mission 37: Shadow Research Decision Gate.

This module turns Mission 36 shadow replay performance reports into strict
board-level go/no-go decisions.

It is a governance layer, not an execution layer.

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


LIVE_TRADING_DECISION = "BLOCKED"
CAPITAL_DEPLOYMENT_DECISION = "BLOCKED"
LIVE_TRADING_REQUIRED_STATUS = "DISABLED"

NO_PERFORMANCE_HISTORY_DECISION = "DECISION_GATE_NO_PERFORMANCE_HISTORY"
MISSING_PERFORMANCE_TABLE_DECISION = "DECISION_GATE_PERFORMANCE_TABLE_MISSING"
NO_MATCHING_REPORT_DECISION = "DECISION_GATE_NO_MATCHING_PERFORMANCE_REPORT"
SAFETY_BREACH_DECISION = "DECISION_GATE_BLOCK_LIVE_TRADING_SAFETY_BREACH"
REQUIRE_MORE_SAMPLES_DECISION = "DECISION_GATE_REQUIRE_MORE_SHADOW_SAMPLES"
REJECT_WEAK_REPLAY_DECISION = "DECISION_GATE_REJECT_WEAK_REPLAY_SET"
APPROVE_SHADOW_ONLY_DECISION = "DECISION_GATE_APPROVE_SHADOW_OBSERVATION_ONLY_NO_LIVE_TRADING"

PERFORMANCE_REPORTS_TABLE = "shadow_replay_performance_reports"
DECISION_GATE_TABLE = "shadow_research_decision_gate_reports"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_gate_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission37-decision-gate-{stamp}-{uuid.uuid4().hex[:8]}"


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_json_loads(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0

    return round(float(numerator) / float(denominator), 6)


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
            CREATE TABLE IF NOT EXISTS shadow_research_decision_gate_reports (
                gate_label TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                source_report_label TEXT,
                source_report_count INTEGER NOT NULL,
                gate_decision TEXT NOT NULL,
                live_trading_decision TEXT NOT NULL,
                capital_deployment_decision TEXT NOT NULL,
                approved_next_stage TEXT NOT NULL,
                reason_count INTEGER NOT NULL,
                reasons_json TEXT NOT NULL,
                board_votes_json TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def load_performance_rows(
    conn: sqlite3.Connection,
    report_label: str | None,
    limit: int,
) -> list[sqlite3.Row]:
    query = """
        SELECT
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
            summary_json
        FROM shadow_replay_performance_reports
    """
    params: list[Any] = []

    if report_label is not None:
        query += " WHERE report_label = ?"
        params.append(report_label)

    query += " ORDER BY created_at DESC, report_label DESC LIMIT ?"
    params.append(limit)

    return conn.execute(query, params).fetchall()


def build_board_votes(gate_decision: str) -> dict[str, str]:
    if gate_decision == APPROVE_SHADOW_ONLY_DECISION:
        return {
            "CEO": "APPROVE_SHADOW_OBSERVATION_ONLY",
            "CTO": "APPROVE_RESEARCH_PIPELINE_CONTINUATION",
            "CFO_QUANT_LEAD": "BLOCK_CAPITAL_DEPLOYMENT_APPROVE_SHADOW_ONLY",
        }

    if gate_decision == REQUIRE_MORE_SAMPLES_DECISION:
        return {
            "CEO": "REQUIRE_MORE_RESEARCH_HISTORY",
            "CTO": "REQUIRE_MORE_VALIDATION_SAMPLES",
            "CFO_QUANT_LEAD": "BLOCK_CAPITAL_DEPLOYMENT_INSUFFICIENT_SAMPLE",
        }

    if gate_decision == SAFETY_BREACH_DECISION:
        return {
            "CEO": "STOP_AND_REVIEW",
            "CTO": "BLOCK_UNSAFE_STATE",
            "CFO_QUANT_LEAD": "BLOCK_ALL_CAPITAL_AND_EXECUTION",
        }

    if gate_decision == REJECT_WEAK_REPLAY_DECISION:
        return {
            "CEO": "REJECT_WEAK_REPLAY_SET_CONTINUE_RESEARCH",
            "CTO": "KEEP_SYSTEM_IN_SHADOW_MODE",
            "CFO_QUANT_LEAD": "BLOCK_CAPITAL_DEPLOYMENT_WEAK_EDGE",
        }

    return {
        "CEO": "NO_GO",
        "CTO": "NO_GO",
        "CFO_QUANT_LEAD": "NO_GO",
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    reasons = "\n".join(
        f"- {reason}"
        for reason in summary["reasons"]
    ) or "- None"

    votes = "\n".join(
        f"- {role}: {vote}"
        for role, vote in summary["board_votes"].items()
    ) or "- None"

    metrics = summary["metrics"]

    return f"""# DeltaGrid Mission 37 Shadow Research Decision Gate

Gate label: {summary['gate_label']}
Created at: {summary['created_at']}
Source report label: {summary['source_report_label']}
Source report count: {summary['source_report_count']}

## Decision

Gate decision: {summary['gate_decision']}
Approved next stage: {summary['approved_next_stage']}

Live trading decision: {summary['live_trading_decision']}
Capital deployment decision: {summary['capital_deployment_decision']}

## Aggregate Metrics

Replay count: {metrics['replay_count']}
Scenario count: {metrics['scenario_count']}
Pipeline run count: {metrics['pipeline_run_count']}
Candidate count: {metrics['candidate_count']}

Approved candidates: {metrics['total_approved_count']}
Rejected candidates: {metrics['total_rejected_count']}
Shadow paper positions: {metrics['total_paper_positions_count']}

Approval rate: {metrics['approval_rate']}
Rejection rate: {metrics['rejection_rate']}
Paper position rate: {metrics['paper_position_rate']}

Live trading breach count: {metrics['live_trading_breach_count']}

## Reasons

{reasons}

## Board Votes

{votes}

## Non-Negotiable Safety Statement

Live trading remains blocked.
Capital deployment remains blocked.
No private keys are allowed.
No signing is allowed.
No exchange orders are allowed.
No real capital is allowed.
"""


def persist_decision_gate_report(
    db_path: str | Path,
    summary: dict[str, Any],
) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO shadow_research_decision_gate_reports (
                gate_label,
                created_at,
                source_report_label,
                source_report_count,
                gate_decision,
                live_trading_decision,
                capital_deployment_decision,
                approved_next_stage,
                reason_count,
                reasons_json,
                board_votes_json,
                metrics_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["gate_label"],
                summary["created_at"],
                summary["source_report_label"],
                summary["source_report_count"],
                summary["gate_decision"],
                summary["live_trading_decision"],
                summary["capital_deployment_decision"],
                summary["approved_next_stage"],
                len(summary["reasons"]),
                json.dumps(summary["reasons"], sort_keys=True),
                json.dumps(summary["board_votes"], sort_keys=True),
                json.dumps(summary["metrics"], sort_keys=True),
                summary["markdown_report"],
            ),
        )

        conn.commit()


def run_shadow_research_decision_gate(
    db_path: str | Path = "offchain/deltagrid.db",
    gate_label: str | None = None,
    report_label: str | None = None,
    limit: int = 1,
    min_replay_count: int = 1,
    min_scenario_count: int = 4,
    min_pipeline_run_count: int = 4,
    min_candidate_count: int = 8,
    min_approval_rate: float = 0.05,
) -> dict[str, Any]:
    if limit <= 0:
        raise ValueError("limit must be greater than 0")

    db = Path(db_path)
    label = gate_label or new_gate_label()
    created_at = utc_now()

    if not db.exists():
        metrics = {
            "replay_count": 0,
            "scenario_count": 0,
            "pipeline_run_count": 0,
            "candidate_count": 0,
            "total_approved_count": 0,
            "total_rejected_count": 0,
            "total_paper_positions_count": 0,
            "approval_rate": 0.0,
            "rejection_rate": 0.0,
            "paper_position_rate": 0.0,
            "live_trading_breach_count": 0,
        }

        summary = {
            "gate_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": False,
            "tables_present": False,
            "source_report_label": report_label,
            "source_report_count": 0,
            "metrics": metrics,
            "gate_decision": NO_PERFORMANCE_HISTORY_DECISION,
            "live_trading_decision": LIVE_TRADING_DECISION,
            "capital_deployment_decision": CAPITAL_DEPLOYMENT_DECISION,
            "approved_next_stage": "RUN_MISSION_36_PERFORMANCE_REPORTER",
            "reasons": ["No SQLite database exists for performance-report review."],
            "board_votes": build_board_votes(NO_PERFORMANCE_HISTORY_DECISION),
        }

        summary["markdown_report"] = build_markdown_report(summary)
        return summary

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        if not table_exists(conn, PERFORMANCE_REPORTS_TABLE):
            metrics = {
                "replay_count": 0,
                "scenario_count": 0,
                "pipeline_run_count": 0,
                "candidate_count": 0,
                "total_approved_count": 0,
                "total_rejected_count": 0,
                "total_paper_positions_count": 0,
                "approval_rate": 0.0,
                "rejection_rate": 0.0,
                "paper_position_rate": 0.0,
                "live_trading_breach_count": 0,
            }

            summary = {
                "gate_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "tables_present": False,
                "missing_tables": [PERFORMANCE_REPORTS_TABLE],
                "source_report_label": report_label,
                "source_report_count": 0,
                "metrics": metrics,
                "gate_decision": MISSING_PERFORMANCE_TABLE_DECISION,
                "live_trading_decision": LIVE_TRADING_DECISION,
                "capital_deployment_decision": CAPITAL_DEPLOYMENT_DECISION,
                "approved_next_stage": "RUN_MISSION_36_PERFORMANCE_REPORTER",
                "reasons": ["Mission 36 performance report table is missing."],
                "board_votes": build_board_votes(MISSING_PERFORMANCE_TABLE_DECISION),
            }

            summary["markdown_report"] = build_markdown_report(summary)
            persist_decision_gate_report(db, summary)
            return summary

        rows = load_performance_rows(
            conn=conn,
            report_label=report_label,
            limit=limit,
        )

    if not rows:
        metrics = {
            "replay_count": 0,
            "scenario_count": 0,
            "pipeline_run_count": 0,
            "candidate_count": 0,
            "total_approved_count": 0,
            "total_rejected_count": 0,
            "total_paper_positions_count": 0,
            "approval_rate": 0.0,
            "rejection_rate": 0.0,
            "paper_position_rate": 0.0,
            "live_trading_breach_count": 0,
        }

        summary = {
            "gate_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": True,
            "tables_present": True,
            "source_report_label": report_label,
            "source_report_count": 0,
            "metrics": metrics,
            "gate_decision": NO_MATCHING_REPORT_DECISION,
            "live_trading_decision": LIVE_TRADING_DECISION,
            "capital_deployment_decision": CAPITAL_DEPLOYMENT_DECISION,
            "approved_next_stage": "GENERATE_MATCHING_MISSION_36_REPORT",
            "reasons": ["No matching Mission 36 performance report was found."],
            "board_votes": build_board_votes(NO_MATCHING_REPORT_DECISION),
        }

        summary["markdown_report"] = build_markdown_report(summary)
        persist_decision_gate_report(db, summary)
        return summary

    source_report_labels = [str(row["report_label"]) for row in rows]

    replay_count = sum(int(row["replay_count"]) for row in rows)
    scenario_count = sum(int(row["scenario_count"]) for row in rows)
    pipeline_run_count = sum(int(row["pipeline_run_count"]) for row in rows)
    total_approved = sum(int(row["total_approved_count"]) for row in rows)
    total_rejected = sum(int(row["total_rejected_count"]) for row in rows)
    total_paper_positions = sum(int(row["total_paper_positions_count"]) for row in rows)
    live_trading_breach_count = sum(int(row["live_trading_breach_count"]) for row in rows)

    candidate_count = total_approved + total_rejected
    approval_rate = safe_rate(total_approved, candidate_count)
    rejection_rate = safe_rate(total_rejected, candidate_count)
    paper_position_rate = safe_rate(total_paper_positions, max(pipeline_run_count, 1))

    reasons: list[str] = []

    if live_trading_breach_count > 0:
        gate_decision = SAFETY_BREACH_DECISION
        approved_next_stage = "STOP_AND_REVIEW_SAFETY_BREACH"
        reasons.append("Live trading breach count is greater than zero.")

    elif (
        replay_count < min_replay_count
        or scenario_count < min_scenario_count
        or pipeline_run_count < min_pipeline_run_count
        or candidate_count < min_candidate_count
    ):
        gate_decision = REQUIRE_MORE_SAMPLES_DECISION
        approved_next_stage = "COLLECT_MORE_SHADOW_REPLAY_SAMPLES"

        if replay_count < min_replay_count:
            reasons.append(f"Replay count below minimum: {replay_count} < {min_replay_count}.")
        if scenario_count < min_scenario_count:
            reasons.append(f"Scenario count below minimum: {scenario_count} < {min_scenario_count}.")
        if pipeline_run_count < min_pipeline_run_count:
            reasons.append(f"Pipeline run count below minimum: {pipeline_run_count} < {min_pipeline_run_count}.")
        if candidate_count < min_candidate_count:
            reasons.append(f"Candidate count below minimum: {candidate_count} < {min_candidate_count}.")

    elif total_approved <= 0:
        gate_decision = REJECT_WEAK_REPLAY_DECISION
        approved_next_stage = "CONTINUE_SHADOW_RESEARCH_NO_APPROVAL"
        reasons.append("No candidates were approved by the replay performance report.")

    elif approval_rate < min_approval_rate:
        gate_decision = REJECT_WEAK_REPLAY_DECISION
        approved_next_stage = "CONTINUE_SHADOW_RESEARCH_WEAK_APPROVAL_RATE"
        reasons.append(f"Approval rate below minimum: {approval_rate} < {min_approval_rate}.")

    elif total_paper_positions <= 0:
        gate_decision = REJECT_WEAK_REPLAY_DECISION
        approved_next_stage = "CONTINUE_SHADOW_RESEARCH_NO_PAPER_POSITIONS"
        reasons.append("No shadow paper positions were produced.")

    else:
        gate_decision = APPROVE_SHADOW_ONLY_DECISION
        approved_next_stage = "SHADOW_PAPER_OBSERVATION_ONLY"
        reasons.append("Performance report passed minimum shadow observation thresholds.")
        reasons.append("Live trading remains blocked despite shadow observation approval.")
        reasons.append("Capital deployment remains blocked.")

    metrics = {
        "source_report_labels": source_report_labels,
        "replay_count": replay_count,
        "scenario_count": scenario_count,
        "pipeline_run_count": pipeline_run_count,
        "candidate_count": candidate_count,
        "total_approved_count": total_approved,
        "total_rejected_count": total_rejected,
        "total_paper_positions_count": total_paper_positions,
        "approval_rate": approval_rate,
        "rejection_rate": rejection_rate,
        "paper_position_rate": paper_position_rate,
        "live_trading_breach_count": live_trading_breach_count,
        "min_replay_count": min_replay_count,
        "min_scenario_count": min_scenario_count,
        "min_pipeline_run_count": min_pipeline_run_count,
        "min_candidate_count": min_candidate_count,
        "min_approval_rate": min_approval_rate,
    }

    summary = {
        "gate_label": label,
        "created_at": created_at,
        "db_path": str(db),
        "database_exists": True,
        "tables_present": True,
        "source_report_label": report_label if report_label is not None else source_report_labels[0],
        "source_report_count": len(rows),
        "metrics": metrics,
        "gate_decision": gate_decision,
        "live_trading_decision": LIVE_TRADING_DECISION,
        "capital_deployment_decision": CAPITAL_DEPLOYMENT_DECISION,
        "approved_next_stage": approved_next_stage,
        "reasons": reasons,
        "board_votes": build_board_votes(gate_decision),
    }

    summary["markdown_report"] = build_markdown_report(summary)

    persist_decision_gate_report(db, summary)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid shadow research decision gate."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--gate-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--min-replay-count", type=int, default=1)
    parser.add_argument("--min-scenario-count", type=int, default=4)
    parser.add_argument("--min-pipeline-run-count", type=int, default=4)
    parser.add_argument("--min-candidate-count", type=int, default=8)
    parser.add_argument("--min-approval-rate", type=float, default=0.05)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_shadow_research_decision_gate(
        db_path=args.db,
        gate_label=args.gate_label,
        report_label=args.report_label,
        limit=args.limit,
        min_replay_count=args.min_replay_count,
        min_scenario_count=args.min_scenario_count,
        min_pipeline_run_count=args.min_pipeline_run_count,
        min_candidate_count=args.min_candidate_count,
        min_approval_rate=args.min_approval_rate,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

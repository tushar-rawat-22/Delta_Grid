"""
Mission 45: Shadow Observation Outcome Finalizer.

This module converts Mission 44 close eligibility decisions into final shadow
observation outcomes.

It is a research and governance layer, not an execution layer.

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


LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_DECISION = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

CLOSE_DECISIONS_TABLE = "shadow_observation_close_decisions"
OUTCOMES_TABLE = "shadow_observation_outcomes"
OUTCOME_REPORTS_TABLE = "shadow_observation_outcome_reports"

NO_CLOSE_DECISION_HISTORY_VERDICT = "OUTCOME_FINALIZER_NO_CLOSE_DECISION_HISTORY"
MISSING_CLOSE_DECISION_TABLE_VERDICT = "OUTCOME_FINALIZER_CLOSE_DECISION_TABLE_MISSING"
NO_MATCHING_CLOSE_DECISIONS_VERDICT = "OUTCOME_FINALIZER_NO_MATCHING_CLOSE_DECISIONS"
SAFETY_BLOCKED_VERDICT = "OUTCOME_FINALIZER_SAFETY_BLOCKED"
RISK_REVIEW_VERDICT = "OUTCOME_FINALIZER_RISK_REVIEW_REQUIRED"
REJECTED_VERDICT = "OUTCOME_FINALIZER_REJECTED_UNECONOMIC"
CLOSE_READY_VERDICT = "OUTCOME_FINALIZER_CLOSE_READY"
CONTINUED_TRACKING_VERDICT = "OUTCOME_FINALIZER_CONTINUED_TRACKING"
MIXED_OUTCOME_VERDICT = "OUTCOME_FINALIZER_MIXED_OUTCOME_SET"

OUTCOME_CONTINUED_TRACKING = "OUTCOME_CONTINUED_TRACKING"
OUTCOME_SHADOW_CLOSE_READY = "OUTCOME_SHADOW_CLOSE_READY"
OUTCOME_REJECTED_UNECONOMIC = "OUTCOME_REJECTED_UNECONOMIC"
OUTCOME_RISK_REVIEW_REQUIRED = "OUTCOME_RISK_REVIEW_REQUIRED"
OUTCOME_SAFETY_BLOCKED = "OUTCOME_SAFETY_BLOCKED"

CLOSE_DECISION_CONTINUE = "CONTINUE_TRACKING"
CLOSE_DECISION_BREAK_EVEN = "CLOSE_ELIGIBLE_BREAK_EVEN_REACHED"
CLOSE_DECISION_NEAR_BREAK_EVEN = "CLOSE_ELIGIBLE_NEAR_BREAK_EVEN"
CLOSE_DECISION_REJECT_UNECONOMIC = "REJECT_UNECONOMIC_TOO_LONG_TO_BREAK_EVEN"
CLOSE_DECISION_REJECT_IMPOSSIBLE = "REJECT_UNECONOMIC_BREAK_EVEN_IMPOSSIBLE"
CLOSE_DECISION_RISK_REVIEW = "RISK_REVIEW_REQUIRED"
CLOSE_DECISION_SAFETY_BREACH = "SAFETY_BREACH_BLOCKED"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_outcome_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission45-outcome-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission45-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
            CREATE TABLE IF NOT EXISTS shadow_observation_outcomes (
                outcome_id TEXT PRIMARY KEY,
                outcome_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_decision_label TEXT NOT NULL,
                observation_id TEXT NOT NULL,
                ledger_label TEXT NOT NULL,
                source_gate_label TEXT NOT NULL,
                symbol TEXT NOT NULL,
                close_decision TEXT NOT NULL,
                final_outcome TEXT NOT NULL,
                outcome_reason TEXT NOT NULL,
                close_ready INTEGER NOT NULL,
                continued_tracking INTEGER NOT NULL,
                rejected INTEGER NOT NULL,
                risk_review_required INTEGER NOT NULL,
                safety_blocked INTEGER NOT NULL,
                cost_remaining_usd TEXT NOT NULL,
                net_expected_pnl_usd TEXT NOT NULL,
                total_cost_usd TEXT NOT NULL,
                remaining_hours_to_break_even TEXT,
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
            CREATE TABLE IF NOT EXISTS shadow_observation_outcome_reports (
                report_label TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                outcome_label TEXT NOT NULL,
                source_decision_label TEXT,
                observation_count INTEGER NOT NULL,
                continued_count INTEGER NOT NULL,
                close_ready_count INTEGER NOT NULL,
                rejected_count INTEGER NOT NULL,
                risk_review_count INTEGER NOT NULL,
                safety_blocked_count INTEGER NOT NULL,
                total_cost_remaining_usd TEXT NOT NULL,
                total_net_expected_pnl_usd TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def latest_decision_label(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        """
        SELECT decision_label
        FROM shadow_observation_close_decisions
        ORDER BY created_at DESC, decision_label DESC
        LIMIT 1
        """
    ).fetchone()

    if row is None:
        return None

    return str(row["decision_label"])


def load_close_decisions(
    conn: sqlite3.Connection,
    decision_label: str | None,
    gate_label: str | None,
) -> tuple[str | None, list[sqlite3.Row]]:
    resolved = decision_label or latest_decision_label(conn)

    if resolved is None:
        return None, []

    query = """
        SELECT
            close_decision_id,
            decision_label,
            created_at,
            tracker_label,
            observation_id,
            ledger_label,
            source_gate_label,
            symbol,
            break_even_status,
            close_decision,
            close_reason,
            continue_reason,
            remaining_hours_to_break_even,
            projected_break_even_at,
            cost_remaining_usd,
            net_expected_pnl_usd,
            total_cost_usd,
            simulated_notional_usd,
            live_trading,
            live_order_sent,
            capital_deployment,
            risk_flags_json,
            metadata_json
        FROM shadow_observation_close_decisions
        WHERE decision_label = ?
    """
    params: list[Any] = [resolved]

    if gate_label is not None:
        query += " AND source_gate_label = ?"
        params.append(gate_label)

    query += " ORDER BY observation_id ASC"

    return resolved, conn.execute(query, params).fetchall()


def map_close_decision_to_outcome(row: sqlite3.Row) -> tuple[str, str]:
    close_decision = str(row["close_decision"])
    close_reason = row["close_reason"]
    continue_reason = row["continue_reason"]

    if close_decision == CLOSE_DECISION_SAFETY_BREACH:
        return OUTCOME_SAFETY_BLOCKED, close_reason or "Safety breach blocked shadow outcome."

    if close_decision == CLOSE_DECISION_RISK_REVIEW:
        return OUTCOME_RISK_REVIEW_REQUIRED, continue_reason or "Risk review required before final outcome."

    if close_decision in {CLOSE_DECISION_REJECT_UNECONOMIC, CLOSE_DECISION_REJECT_IMPOSSIBLE}:
        return OUTCOME_REJECTED_UNECONOMIC, close_reason or "Observation rejected as uneconomic."

    if close_decision in {CLOSE_DECISION_BREAK_EVEN, CLOSE_DECISION_NEAR_BREAK_EVEN}:
        return OUTCOME_SHADOW_CLOSE_READY, close_reason or "Observation is close-ready in shadow accounting."

    if close_decision == CLOSE_DECISION_CONTINUE:
        return OUTCOME_CONTINUED_TRACKING, continue_reason or "Observation continues tracking."

    return OUTCOME_RISK_REVIEW_REQUIRED, f"Unknown close decision requires review: {close_decision}"


def finalize_outcome_row(
    row: sqlite3.Row,
    outcome_label: str,
    created_at: str,
) -> dict[str, Any]:
    risk_flags = safe_json_loads(row["risk_flags_json"], [])
    metadata = safe_json_loads(row["metadata_json"], {})
    final_outcome, outcome_reason = map_close_decision_to_outcome(row)

    safety_breach = (
        row["live_trading"] != LIVE_TRADING_STATUS
        or int(row["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or row["capital_deployment"] != CAPITAL_DEPLOYMENT_DECISION
    )

    if safety_breach:
        final_outcome = OUTCOME_SAFETY_BLOCKED
        outcome_reason = "Safety state mismatch blocked final outcome."

    outcome_id = f"{outcome_label}-{row['observation_id']}"

    return {
        "outcome_id": outcome_id,
        "outcome_label": outcome_label,
        "created_at": created_at,
        "source_decision_label": row["decision_label"],
        "observation_id": row["observation_id"],
        "ledger_label": row["ledger_label"],
        "source_gate_label": row["source_gate_label"],
        "symbol": row["symbol"],
        "close_decision": row["close_decision"],
        "final_outcome": final_outcome,
        "outcome_reason": outcome_reason,
        "close_ready": 1 if final_outcome == OUTCOME_SHADOW_CLOSE_READY else 0,
        "continued_tracking": 1 if final_outcome == OUTCOME_CONTINUED_TRACKING else 0,
        "rejected": 1 if final_outcome == OUTCOME_REJECTED_UNECONOMIC else 0,
        "risk_review_required": 1 if final_outcome == OUTCOME_RISK_REVIEW_REQUIRED else 0,
        "safety_blocked": 1 if final_outcome == OUTCOME_SAFETY_BLOCKED else 0,
        "cost_remaining_usd": safe_float(row["cost_remaining_usd"]),
        "net_expected_pnl_usd": safe_float(row["net_expected_pnl_usd"]),
        "total_cost_usd": safe_float(row["total_cost_usd"]),
        "remaining_hours_to_break_even": (
            None
            if row["remaining_hours_to_break_even"] is None
            else safe_float(row["remaining_hours_to_break_even"])
        ),
        "live_trading": row["live_trading"],
        "live_order_sent": int(row["live_order_sent"]),
        "capital_deployment": row["capital_deployment"],
        "risk_flags": risk_flags,
        "metadata": {
            "close_decision_id": row["close_decision_id"],
            "tracker_label": row["tracker_label"],
            "break_even_status": row["break_even_status"],
            "projected_break_even_at": row["projected_break_even_at"],
            "simulated_notional_usd": safe_float(row["simulated_notional_usd"]),
            "close_decision_metadata": metadata,
        },
    }


def persist_outcomes(
    db_path: str | Path,
    outcomes: list[dict[str, Any]],
) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for item in outcomes:
            conn.execute(
                """
                INSERT OR REPLACE INTO shadow_observation_outcomes (
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
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["outcome_id"],
                    item["outcome_label"],
                    item["created_at"],
                    item["source_decision_label"],
                    item["observation_id"],
                    item["ledger_label"],
                    item["source_gate_label"],
                    item["symbol"],
                    item["close_decision"],
                    item["final_outcome"],
                    item["outcome_reason"],
                    item["close_ready"],
                    item["continued_tracking"],
                    item["rejected"],
                    item["risk_review_required"],
                    item["safety_blocked"],
                    str(item["cost_remaining_usd"]),
                    str(item["net_expected_pnl_usd"]),
                    str(item["total_cost_usd"]),
                    None if item["remaining_hours_to_break_even"] is None else str(item["remaining_hours_to_break_even"]),
                    item["live_trading"],
                    item["live_order_sent"],
                    item["capital_deployment"],
                    json.dumps(item["risk_flags"], sort_keys=True),
                    json.dumps(item["metadata"], sort_keys=True),
                ),
            )

        conn.commit()


def summarize_outcomes(
    db_path: str | Path,
    report_label: str,
    outcome_label: str,
    created_at: str,
    source_decision_label: str | None,
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    observation_count = len(outcomes)

    continued_count = sum(1 for item in outcomes if item["final_outcome"] == OUTCOME_CONTINUED_TRACKING)
    close_ready_count = sum(1 for item in outcomes if item["final_outcome"] == OUTCOME_SHADOW_CLOSE_READY)
    rejected_count = sum(1 for item in outcomes if item["final_outcome"] == OUTCOME_REJECTED_UNECONOMIC)
    risk_review_count = sum(1 for item in outcomes if item["final_outcome"] == OUTCOME_RISK_REVIEW_REQUIRED)
    safety_blocked_count = sum(1 for item in outcomes if item["final_outcome"] == OUTCOME_SAFETY_BLOCKED)

    total_cost_remaining = round(sum(safe_float(item["cost_remaining_usd"]) for item in outcomes), 8)
    total_net_expected = round(sum(safe_float(item["net_expected_pnl_usd"]) for item in outcomes), 8)

    outcome_counts = dict(Counter(item["final_outcome"] for item in outcomes))
    symbol_counts = dict(Counter(item["symbol"] for item in outcomes))

    if observation_count == 0:
        global_verdict = NO_MATCHING_CLOSE_DECISIONS_VERDICT
        recommended_action = "RUN_MISSION_44_CLOSE_ELIGIBILITY_ENGINE"
    elif safety_blocked_count > 0:
        global_verdict = SAFETY_BLOCKED_VERDICT
        recommended_action = "STOP_AND_REVIEW_SAFETY_BLOCKED_OUTCOMES"
    elif risk_review_count > 0:
        global_verdict = RISK_REVIEW_VERDICT
        recommended_action = "REVIEW_RISK_OUTCOMES_BEFORE_NEXT_STAGE"
    elif rejected_count > 0 and continued_count == 0 and close_ready_count == 0:
        global_verdict = REJECTED_VERDICT
        recommended_action = "REJECT_UNECONOMIC_SHADOW_OBSERVATIONS"
    elif close_ready_count > 0 and continued_count == 0 and rejected_count == 0:
        global_verdict = CLOSE_READY_VERDICT
        recommended_action = "MARK_SHADOW_OBSERVATIONS_READY_FOR_CLOSE_ACCOUNTING"
    elif continued_count > 0 and close_ready_count == 0 and rejected_count == 0:
        global_verdict = CONTINUED_TRACKING_VERDICT
        recommended_action = "CONTINUE_SHADOW_OBSERVATION_MONITORING"
    else:
        global_verdict = MIXED_OUTCOME_VERDICT
        recommended_action = "REVIEW_MIXED_SHADOW_OUTCOME_SET"

    return {
        "report_label": report_label,
        "outcome_label": outcome_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_decision_label": source_decision_label,
        "observation_count": observation_count,
        "continued_count": continued_count,
        "close_ready_count": close_ready_count,
        "rejected_count": rejected_count,
        "risk_review_count": risk_review_count,
        "safety_blocked_count": safety_blocked_count,
        "total_cost_remaining_usd": total_cost_remaining,
        "total_net_expected_pnl_usd": total_net_expected,
        "outcome_counts": outcome_counts,
        "symbol_counts": symbol_counts,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
        "outcomes": outcomes,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    outcome_counts = "\n".join(
        f"- {name}: {count}"
        for name, count in summary["outcome_counts"].items()
    ) or "- None"

    symbol_counts = "\n".join(
        f"- {name}: {count}"
        for name, count in summary["symbol_counts"].items()
    ) or "- None"

    return f"""# DeltaGrid Mission 45 Shadow Observation Outcome Report

Report label: {summary['report_label']}
Outcome label: {summary['outcome_label']}
Created at: {summary['created_at']}
Source decision label: {summary['source_decision_label']}

## Outcome Summary

Observation count: {summary['observation_count']}
Continued count: {summary['continued_count']}
Close ready count: {summary['close_ready_count']}
Rejected count: {summary['rejected_count']}
Risk review count: {summary['risk_review_count']}
Safety blocked count: {summary['safety_blocked_count']}

Total cost remaining USD: {summary['total_cost_remaining_usd']}
Total net expected PnL USD: {summary['total_net_expected_pnl_usd']}

## Outcome Counts

{outcome_counts}

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
            INSERT OR REPLACE INTO shadow_observation_outcome_reports (
                report_label,
                created_at,
                outcome_label,
                source_decision_label,
                observation_count,
                continued_count,
                close_ready_count,
                rejected_count,
                risk_review_count,
                safety_blocked_count,
                total_cost_remaining_usd,
                total_net_expected_pnl_usd,
                global_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["created_at"],
                summary["outcome_label"],
                summary["source_decision_label"],
                summary["observation_count"],
                summary["continued_count"],
                summary["close_ready_count"],
                summary["rejected_count"],
                summary["risk_review_count"],
                summary["safety_blocked_count"],
                str(summary["total_cost_remaining_usd"]),
                str(summary["total_net_expected_pnl_usd"]),
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def run_shadow_observation_outcome_finalizer(
    db_path: str | Path = "offchain/deltagrid.db",
    outcome_label: str | None = None,
    report_label: str | None = None,
    decision_label: str | None = None,
    gate_label: str | None = None,
) -> dict[str, Any]:
    db = Path(db_path)
    label = outcome_label or new_outcome_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    if not db.exists():
        summary = {
            "report_label": report,
            "outcome_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": False,
            "tables_present": False,
            "source_decision_label": decision_label,
            "observation_count": 0,
            "continued_count": 0,
            "close_ready_count": 0,
            "rejected_count": 0,
            "risk_review_count": 0,
            "safety_blocked_count": 0,
            "total_cost_remaining_usd": 0.0,
            "total_net_expected_pnl_usd": 0.0,
            "outcome_counts": {},
            "symbol_counts": {},
            "global_verdict": NO_CLOSE_DECISION_HISTORY_VERDICT,
            "recommended_action": "RUN_MISSION_44_CLOSE_ELIGIBILITY_ENGINE",
            "outcomes": [],
        }
        summary["markdown_report"] = build_markdown_report(summary)
        return summary

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        if not table_exists(conn, CLOSE_DECISIONS_TABLE):
            summary = {
                "report_label": report,
                "outcome_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "tables_present": False,
                "missing_tables": [CLOSE_DECISIONS_TABLE],
                "source_decision_label": decision_label,
                "observation_count": 0,
                "continued_count": 0,
                "close_ready_count": 0,
                "rejected_count": 0,
                "risk_review_count": 0,
                "safety_blocked_count": 0,
                "total_cost_remaining_usd": 0.0,
                "total_net_expected_pnl_usd": 0.0,
                "outcome_counts": {},
                "symbol_counts": {},
                "global_verdict": MISSING_CLOSE_DECISION_TABLE_VERDICT,
                "recommended_action": "RUN_MISSION_44_CLOSE_ELIGIBILITY_ENGINE",
                "outcomes": [],
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        resolved_decision_label, rows = load_close_decisions(
            conn=conn,
            decision_label=decision_label,
            gate_label=gate_label,
        )

    outcomes = [
        finalize_outcome_row(
            row=row,
            outcome_label=label,
            created_at=created_at,
        )
        for row in rows
    ]

    persist_outcomes(db, outcomes)

    summary = summarize_outcomes(
        db_path=db,
        report_label=report,
        outcome_label=label,
        created_at=created_at,
        source_decision_label=resolved_decision_label,
        outcomes=outcomes,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_report(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid shadow observation outcome finalizer."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--outcome-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--decision-label", default=None)
    parser.add_argument("--gate-label", default=None)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_shadow_observation_outcome_finalizer(
        db_path=args.db,
        outcome_label=args.outcome_label,
        report_label=args.report_label,
        decision_label=args.decision_label,
        gate_label=args.gate_label,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

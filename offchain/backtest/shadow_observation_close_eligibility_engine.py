"""
Mission 44: Shadow Observation Close Eligibility Engine.

This module converts Mission 43 break-even tracking records into close,
continue, reject, or review decisions.

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

BREAK_EVEN_TABLE = "shadow_observation_break_even_tracking"
CLOSE_DECISIONS_TABLE = "shadow_observation_close_decisions"
CLOSE_REPORTS_TABLE = "shadow_observation_close_decision_reports"

NO_BREAK_EVEN_HISTORY_VERDICT = "CLOSE_ELIGIBILITY_NO_BREAK_EVEN_HISTORY"
MISSING_BREAK_EVEN_TABLE_VERDICT = "CLOSE_ELIGIBILITY_BREAK_EVEN_TABLE_MISSING"
NO_MATCHING_BREAK_EVEN_ROWS_VERDICT = "CLOSE_ELIGIBILITY_NO_MATCHING_BREAK_EVEN_ROWS"
SAFETY_BREACH_VERDICT = "CLOSE_ELIGIBILITY_SAFETY_BREACH_BLOCKED"
RISK_REVIEW_VERDICT = "CLOSE_ELIGIBILITY_RISK_REVIEW_REQUIRED"
REJECT_UNECONOMIC_VERDICT = "CLOSE_ELIGIBILITY_REJECT_UNECONOMIC"
CONTINUE_TRACKING_VERDICT = "CLOSE_ELIGIBILITY_CONTINUE_TRACKING"
CLOSE_READY_VERDICT = "CLOSE_ELIGIBILITY_READY_FOR_SHADOW_CLOSE"
MIXED_VERDICT = "CLOSE_ELIGIBILITY_MIXED_DECISION_SET"

DECISION_CONTINUE_TRACKING = "CONTINUE_TRACKING"
DECISION_CLOSE_ELIGIBLE_BREAK_EVEN = "CLOSE_ELIGIBLE_BREAK_EVEN_REACHED"
DECISION_CLOSE_ELIGIBLE_NEAR_BREAK_EVEN = "CLOSE_ELIGIBLE_NEAR_BREAK_EVEN"
DECISION_REJECT_UNECONOMIC = "REJECT_UNECONOMIC_TOO_LONG_TO_BREAK_EVEN"
DECISION_REJECT_IMPOSSIBLE = "REJECT_UNECONOMIC_BREAK_EVEN_IMPOSSIBLE"
DECISION_RISK_REVIEW = "RISK_REVIEW_REQUIRED"
DECISION_SAFETY_BREACH = "SAFETY_BREACH_BLOCKED"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_decision_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission44-close-decision-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission44-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
            CREATE TABLE IF NOT EXISTS shadow_observation_close_decisions (
                close_decision_id TEXT PRIMARY KEY,
                decision_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                tracker_label TEXT NOT NULL,
                observation_id TEXT NOT NULL,
                ledger_label TEXT NOT NULL,
                source_gate_label TEXT NOT NULL,
                symbol TEXT NOT NULL,
                break_even_status TEXT NOT NULL,
                close_decision TEXT NOT NULL,
                close_reason TEXT,
                continue_reason TEXT,
                remaining_hours_to_break_even TEXT,
                projected_break_even_at TEXT,
                cost_remaining_usd TEXT NOT NULL,
                net_expected_pnl_usd TEXT NOT NULL,
                total_cost_usd TEXT NOT NULL,
                simulated_notional_usd TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS shadow_observation_close_decision_reports (
                report_label TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                source_tracker_label TEXT,
                decision_label TEXT NOT NULL,
                observation_count INTEGER NOT NULL,
                continue_count INTEGER NOT NULL,
                close_eligible_count INTEGER NOT NULL,
                reject_count INTEGER NOT NULL,
                risk_review_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                total_cost_remaining_usd TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def latest_tracker_label(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        """
        SELECT tracker_label
        FROM shadow_observation_break_even_tracking
        ORDER BY created_at DESC, tracker_label DESC
        LIMIT 1
        """
    ).fetchone()

    if row is None:
        return None

    return str(row["tracker_label"])


def load_break_even_rows(
    conn: sqlite3.Connection,
    tracker_label: str | None,
    gate_label: str | None,
) -> tuple[str | None, list[sqlite3.Row]]:
    resolved = tracker_label or latest_tracker_label(conn)

    if resolved is None:
        return None, []

    query = """
        SELECT
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
        FROM shadow_observation_break_even_tracking
        WHERE tracker_label = ?
    """
    params: list[Any] = [resolved]

    if gate_label is not None:
        query += " AND source_gate_label = ?"
        params.append(gate_label)

    query += " ORDER BY observation_id ASC"

    return resolved, conn.execute(query, params).fetchall()


def evaluate_close_decision_row(
    row: sqlite3.Row,
    decision_label: str,
    created_at: str,
    close_window_hours: float,
    max_cost_remaining_usd: float,
    max_remaining_hours_to_keep: float,
) -> dict[str, Any]:
    risk_flags = safe_json_loads(row["risk_flags_json"], [])
    metadata = safe_json_loads(row["metadata_json"], {})

    break_even_status = str(row["status"])
    remaining_hours = (
        None
        if row["remaining_hours_to_break_even"] is None
        else safe_float(row["remaining_hours_to_break_even"])
    )
    cost_remaining = safe_float(row["cost_remaining_usd"])
    net_expected = safe_float(row["net_expected_pnl_usd"])

    safety_breach = (
        row["live_trading"] != LIVE_TRADING_STATUS
        or int(row["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or row["capital_deployment"] != CAPITAL_DEPLOYMENT_DECISION
    )

    close_reason = None
    continue_reason = None

    if safety_breach or break_even_status == "SAFETY_BREACH":
        close_decision = DECISION_SAFETY_BREACH
        close_reason = "Safety breach detected. Shadow close review required."

    elif break_even_status == "RISK_REVIEW" or risk_flags:
        close_decision = DECISION_RISK_REVIEW
        continue_reason = "Risk flags require review before close/continue decision."

    elif break_even_status == "BREAK_EVEN_REACHED" or net_expected >= 0:
        close_decision = DECISION_CLOSE_ELIGIBLE_BREAK_EVEN
        close_reason = "Break-even reached or expected net PnL is non-negative."

    elif break_even_status == "BREAK_EVEN_IMPOSSIBLE":
        close_decision = DECISION_REJECT_IMPOSSIBLE
        close_reason = "Break-even is impossible with current funding assumptions."

    elif remaining_hours is None:
        close_decision = DECISION_RISK_REVIEW
        continue_reason = "Remaining break-even hours are unavailable."

    elif remaining_hours <= close_window_hours and cost_remaining <= max_cost_remaining_usd:
        close_decision = DECISION_CLOSE_ELIGIBLE_NEAR_BREAK_EVEN
        close_reason = "Observation is within close window and remaining cost is small."

    elif remaining_hours > max_remaining_hours_to_keep:
        close_decision = DECISION_REJECT_UNECONOMIC
        close_reason = "Break-even is too far away under current funding assumptions."

    else:
        close_decision = DECISION_CONTINUE_TRACKING
        continue_reason = "Break-even is pending and still within allowed observation window."

    close_decision_id = f"{decision_label}-{row['observation_id']}"

    return {
        "close_decision_id": close_decision_id,
        "decision_label": decision_label,
        "created_at": created_at,
        "tracker_label": row["tracker_label"],
        "observation_id": row["observation_id"],
        "ledger_label": row["ledger_label"],
        "source_gate_label": row["source_gate_label"],
        "symbol": row["symbol"],
        "break_even_status": break_even_status,
        "close_decision": close_decision,
        "close_reason": close_reason,
        "continue_reason": continue_reason,
        "remaining_hours_to_break_even": remaining_hours,
        "projected_break_even_at": row["projected_break_even_at"],
        "cost_remaining_usd": cost_remaining,
        "net_expected_pnl_usd": net_expected,
        "total_cost_usd": safe_float(row["total_cost_usd"]),
        "simulated_notional_usd": safe_float(row["simulated_notional_usd"]),
        "live_trading": row["live_trading"],
        "live_order_sent": int(row["live_order_sent"]),
        "capital_deployment": row["capital_deployment"],
        "risk_flags": risk_flags,
        "metadata": {
            "break_even_id": row["break_even_id"],
            "attribution_label": row["attribution_label"],
            "expected_annualized_funding": safe_float(row["expected_annualized_funding"]),
            "funding_per_hour_usd": safe_float(row["funding_per_hour_usd"]),
            "gross_expected_funding_pnl_usd": safe_float(row["gross_expected_funding_pnl_usd"]),
            "age_hours": safe_float(row["age_hours"]),
            "break_even_hours": safe_float(row["break_even_hours"]),
            "close_window_hours": close_window_hours,
            "max_cost_remaining_usd": max_cost_remaining_usd,
            "max_remaining_hours_to_keep": max_remaining_hours_to_keep,
            "break_even_metadata": metadata,
        },
    }


def persist_decisions(
    db_path: str | Path,
    decisions: list[dict[str, Any]],
) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for item in decisions:
            conn.execute(
                """
                INSERT OR REPLACE INTO shadow_observation_close_decisions (
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
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["close_decision_id"],
                    item["decision_label"],
                    item["created_at"],
                    item["tracker_label"],
                    item["observation_id"],
                    item["ledger_label"],
                    item["source_gate_label"],
                    item["symbol"],
                    item["break_even_status"],
                    item["close_decision"],
                    item["close_reason"],
                    item["continue_reason"],
                    None if item["remaining_hours_to_break_even"] is None else str(item["remaining_hours_to_break_even"]),
                    item["projected_break_even_at"],
                    str(item["cost_remaining_usd"]),
                    str(item["net_expected_pnl_usd"]),
                    str(item["total_cost_usd"]),
                    str(item["simulated_notional_usd"]),
                    item["live_trading"],
                    item["live_order_sent"],
                    item["capital_deployment"],
                    json.dumps(item["risk_flags"], sort_keys=True),
                    json.dumps(item["metadata"], sort_keys=True),
                ),
            )

        conn.commit()


def summarize_decisions(
    db_path: str | Path,
    report_label: str,
    decision_label: str,
    created_at: str,
    source_tracker_label: str | None,
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    observation_count = len(decisions)

    continue_count = sum(
        1 for item in decisions
        if item["close_decision"] == DECISION_CONTINUE_TRACKING
    )
    close_eligible_count = sum(
        1 for item in decisions
        if item["close_decision"] in {
            DECISION_CLOSE_ELIGIBLE_BREAK_EVEN,
            DECISION_CLOSE_ELIGIBLE_NEAR_BREAK_EVEN,
        }
    )
    reject_count = sum(
        1 for item in decisions
        if item["close_decision"] in {
            DECISION_REJECT_UNECONOMIC,
            DECISION_REJECT_IMPOSSIBLE,
        }
    )
    risk_review_count = sum(
        1 for item in decisions
        if item["close_decision"] == DECISION_RISK_REVIEW
    )
    safety_breach_count = sum(
        1 for item in decisions
        if item["close_decision"] == DECISION_SAFETY_BREACH
    )

    total_cost_remaining = round(
        sum(safe_float(item["cost_remaining_usd"]) for item in decisions),
        8,
    )

    decision_counts = dict(Counter(item["close_decision"] for item in decisions))
    symbol_counts = dict(Counter(item["symbol"] for item in decisions))

    if observation_count == 0:
        global_verdict = NO_MATCHING_BREAK_EVEN_ROWS_VERDICT
        recommended_action = "RUN_MISSION_43_BREAK_EVEN_TRACKER"
    elif safety_breach_count > 0:
        global_verdict = SAFETY_BREACH_VERDICT
        recommended_action = "STOP_AND_REVIEW_CLOSE_ELIGIBILITY_SAFETY_BREACH"
    elif risk_review_count > 0:
        global_verdict = RISK_REVIEW_VERDICT
        recommended_action = "REVIEW_RISK_FLAGS_BEFORE_CLOSE_DECISION"
    elif reject_count > 0 and continue_count == 0 and close_eligible_count == 0:
        global_verdict = REJECT_UNECONOMIC_VERDICT
        recommended_action = "REJECT_OR_REWORK_UNECONOMIC_SHADOW_OBSERVATIONS"
    elif close_eligible_count > 0 and continue_count == 0 and reject_count == 0:
        global_verdict = CLOSE_READY_VERDICT
        recommended_action = "MARK_SHADOW_OBSERVATIONS_CLOSE_ELIGIBLE"
    elif continue_count > 0 and close_eligible_count == 0 and reject_count == 0:
        global_verdict = CONTINUE_TRACKING_VERDICT
        recommended_action = "CONTINUE_TRACKING_UNTIL_BREAK_EVEN_OR_MAX_WINDOW"
    else:
        global_verdict = MIXED_VERDICT
        recommended_action = "REVIEW_MIXED_CLOSE_ELIGIBILITY_DECISIONS"

    return {
        "report_label": report_label,
        "decision_label": decision_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_tracker_label": source_tracker_label,
        "observation_count": observation_count,
        "continue_count": continue_count,
        "close_eligible_count": close_eligible_count,
        "reject_count": reject_count,
        "risk_review_count": risk_review_count,
        "safety_breach_count": safety_breach_count,
        "total_cost_remaining_usd": total_cost_remaining,
        "decision_counts": decision_counts,
        "symbol_counts": symbol_counts,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
        "decisions": decisions,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    decision_counts = "\n".join(
        f"- {name}: {count}"
        for name, count in summary["decision_counts"].items()
    ) or "- None"

    symbol_counts = "\n".join(
        f"- {name}: {count}"
        for name, count in summary["symbol_counts"].items()
    ) or "- None"

    return f"""# DeltaGrid Mission 44 Shadow Observation Close Eligibility Report

Report label: {summary['report_label']}
Decision label: {summary['decision_label']}
Created at: {summary['created_at']}
Source tracker label: {summary['source_tracker_label']}

## Close Eligibility Summary

Observation count: {summary['observation_count']}
Continue count: {summary['continue_count']}
Close eligible count: {summary['close_eligible_count']}
Reject count: {summary['reject_count']}
Risk review count: {summary['risk_review_count']}
Safety breach count: {summary['safety_breach_count']}

Total cost remaining USD: {summary['total_cost_remaining_usd']}

## Decision Counts

{decision_counts}

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
            INSERT OR REPLACE INTO shadow_observation_close_decision_reports (
                report_label,
                created_at,
                source_tracker_label,
                decision_label,
                observation_count,
                continue_count,
                close_eligible_count,
                reject_count,
                risk_review_count,
                safety_breach_count,
                total_cost_remaining_usd,
                global_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["created_at"],
                summary["source_tracker_label"],
                summary["decision_label"],
                summary["observation_count"],
                summary["continue_count"],
                summary["close_eligible_count"],
                summary["reject_count"],
                summary["risk_review_count"],
                summary["safety_breach_count"],
                str(summary["total_cost_remaining_usd"]),
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def run_shadow_observation_close_eligibility_engine(
    db_path: str | Path = "offchain/deltagrid.db",
    decision_label: str | None = None,
    report_label: str | None = None,
    tracker_label: str | None = None,
    gate_label: str | None = None,
    close_window_hours: float = 1.0,
    max_cost_remaining_usd: float = 0.05,
    max_remaining_hours_to_keep: float = 72.0,
) -> dict[str, Any]:
    db = Path(db_path)
    label = decision_label or new_decision_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    if close_window_hours < 0:
        raise ValueError("close_window_hours must be greater than or equal to 0")

    if max_cost_remaining_usd < 0:
        raise ValueError("max_cost_remaining_usd must be greater than or equal to 0")

    if max_remaining_hours_to_keep <= 0:
        raise ValueError("max_remaining_hours_to_keep must be greater than 0")

    if not db.exists():
        summary = {
            "report_label": report,
            "decision_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": False,
            "tables_present": False,
            "source_tracker_label": tracker_label,
            "observation_count": 0,
            "continue_count": 0,
            "close_eligible_count": 0,
            "reject_count": 0,
            "risk_review_count": 0,
            "safety_breach_count": 0,
            "total_cost_remaining_usd": 0.0,
            "decision_counts": {},
            "symbol_counts": {},
            "global_verdict": NO_BREAK_EVEN_HISTORY_VERDICT,
            "recommended_action": "RUN_MISSION_43_BREAK_EVEN_TRACKER",
            "decisions": [],
        }
        summary["markdown_report"] = build_markdown_report(summary)
        return summary

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        if not table_exists(conn, BREAK_EVEN_TABLE):
            summary = {
                "report_label": report,
                "decision_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "tables_present": False,
                "missing_tables": [BREAK_EVEN_TABLE],
                "source_tracker_label": tracker_label,
                "observation_count": 0,
                "continue_count": 0,
                "close_eligible_count": 0,
                "reject_count": 0,
                "risk_review_count": 0,
                "safety_breach_count": 0,
                "total_cost_remaining_usd": 0.0,
                "decision_counts": {},
                "symbol_counts": {},
                "global_verdict": MISSING_BREAK_EVEN_TABLE_VERDICT,
                "recommended_action": "RUN_MISSION_43_BREAK_EVEN_TRACKER",
                "decisions": [],
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        resolved_tracker_label, rows = load_break_even_rows(
            conn=conn,
            tracker_label=tracker_label,
            gate_label=gate_label,
        )

    decisions = [
        evaluate_close_decision_row(
            row=row,
            decision_label=label,
            created_at=created_at,
            close_window_hours=close_window_hours,
            max_cost_remaining_usd=max_cost_remaining_usd,
            max_remaining_hours_to_keep=max_remaining_hours_to_keep,
        )
        for row in rows
    ]

    persist_decisions(db, decisions)

    summary = summarize_decisions(
        db_path=db,
        report_label=report,
        decision_label=label,
        created_at=created_at,
        source_tracker_label=resolved_tracker_label,
        decisions=decisions,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_report(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid shadow observation close eligibility engine."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--decision-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--tracker-label", default=None)
    parser.add_argument("--gate-label", default=None)
    parser.add_argument("--close-window-hours", type=float, default=1.0)
    parser.add_argument("--max-cost-remaining-usd", type=float, default=0.05)
    parser.add_argument("--max-remaining-hours-to-keep", type=float, default=72.0)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_shadow_observation_close_eligibility_engine(
        db_path=args.db,
        decision_label=args.decision_label,
        report_label=args.report_label,
        tracker_label=args.tracker_label,
        gate_label=args.gate_label,
        close_window_hours=args.close_window_hours,
        max_cost_remaining_usd=args.max_cost_remaining_usd,
        max_remaining_hours_to_keep=args.max_remaining_hours_to_keep,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

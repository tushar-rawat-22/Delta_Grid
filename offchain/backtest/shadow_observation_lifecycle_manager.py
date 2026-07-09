"""
Mission 39: Shadow Observation Lifecycle Manager.

This module evaluates open shadow-paper observations created by Mission 38.
It tracks age, expected funding accrual, risk status, close eligibility, and
safety state.

It is an observation and reporting layer, not an execution layer.

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

OBSERVATION_LEDGER_TABLE = "shadow_paper_observation_ledger"
LIFECYCLE_SNAPSHOTS_TABLE = "shadow_observation_lifecycle_snapshots"
LIFECYCLE_REPORTS_TABLE = "shadow_observation_lifecycle_reports"

NO_LEDGER_HISTORY_VERDICT = "LIFECYCLE_MANAGER_NO_OBSERVATION_LEDGER_HISTORY"
MISSING_LEDGER_TABLE_VERDICT = "LIFECYCLE_MANAGER_OBSERVATION_LEDGER_TABLE_MISSING"
NO_OPEN_OBSERVATIONS_VERDICT = "LIFECYCLE_MANAGER_NO_OPEN_OBSERVATIONS"
TRACKING_VERDICT = "LIFECYCLE_MANAGER_TRACKING_OPEN_OBSERVATIONS"
CLOSE_ELIGIBLE_VERDICT = "LIFECYCLE_MANAGER_CLOSE_ELIGIBLE_OBSERVATIONS_FOUND"
SAFETY_BREACH_VERDICT = "LIFECYCLE_MANAGER_SAFETY_BREACH_BLOCKED"
RISK_REVIEW_VERDICT = "LIFECYCLE_MANAGER_RISK_REVIEW_REQUIRED"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_utc(value: str) -> datetime:
    cleaned = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(cleaned)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def new_snapshot_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission39-lifecycle-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission39-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
            CREATE TABLE IF NOT EXISTS shadow_observation_lifecycle_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                snapshot_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                observation_id TEXT NOT NULL,
                ledger_label TEXT NOT NULL,
                source_gate_label TEXT NOT NULL,
                symbol TEXT NOT NULL,
                observation_status TEXT NOT NULL,
                lifecycle_status TEXT NOT NULL,
                age_hours TEXT NOT NULL,
                max_holding_hours TEXT NOT NULL,
                close_eligible INTEGER NOT NULL,
                close_reason TEXT,
                simulated_notional_usd TEXT NOT NULL,
                expected_annualized_funding TEXT NOT NULL,
                expected_funding_pnl_usd TEXT NOT NULL,
                expected_funding_return_bps TEXT NOT NULL,
                liquidation_buffer TEXT NOT NULL,
                spread_bps TEXT NOT NULL,
                slippage_bps TEXT NOT NULL,
                liquidity_score TEXT NOT NULL,
                risk_flags_json TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_observation_lifecycle_reports (
                report_label TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                source_snapshot_label TEXT,
                source_gate_label TEXT,
                observation_count INTEGER NOT NULL,
                tracking_count INTEGER NOT NULL,
                close_eligible_count INTEGER NOT NULL,
                risk_review_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                total_expected_funding_pnl_usd TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def load_open_observations(
    conn: sqlite3.Connection,
    gate_label: str | None,
) -> list[sqlite3.Row]:
    query = """
        SELECT
            observation_id,
            ledger_label,
            created_at,
            opened_at,
            status,
            mode,
            symbol,
            thesis,
            simulated_notional_usd,
            expected_funding_edge_bps,
            expected_annualized_funding,
            risk_snapshot_json,
            source_gate_label,
            source_report_label,
            source_replay_label,
            source_run_label,
            source_scenario_name,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        FROM shadow_paper_observation_ledger
        WHERE status = 'OPEN'
    """
    params: list[Any] = []

    if gate_label is not None:
        query += " AND source_gate_label = ?"
        params.append(gate_label)

    query += " ORDER BY opened_at DESC, observation_id DESC"

    return conn.execute(query, params).fetchall()


def evaluate_single_observation(
    row: sqlite3.Row,
    snapshot_label: str,
    created_at: str,
    now_dt: datetime,
    max_holding_hours: float,
    min_liquidation_buffer: float,
    max_spread_bps: float,
    max_slippage_bps: float,
    min_liquidity_score: float,
) -> dict[str, Any]:
    opened_at = parse_utc(str(row["opened_at"]))
    age_seconds = max((now_dt - opened_at).total_seconds(), 0.0)
    age_hours = round(age_seconds / 3600.0, 6)

    simulated_notional = safe_float(row["simulated_notional_usd"])
    expected_annualized_funding = safe_float(row["expected_annualized_funding"])

    expected_funding_pnl_usd = round(
        simulated_notional * expected_annualized_funding * (age_hours / 8760.0),
        8,
    )

    expected_funding_return_bps = 0.0
    if simulated_notional > 0:
        expected_funding_return_bps = round(
            (expected_funding_pnl_usd / simulated_notional) * 10000.0,
            6,
        )

    risk_snapshot = safe_json_loads(row["risk_snapshot_json"], {})
    liquidation_buffer = safe_float(risk_snapshot.get("stressed_liquidation_buffer"))
    spread_bps = safe_float(risk_snapshot.get("spread_bps"))
    slippage_bps = safe_float(risk_snapshot.get("estimated_slippage_bps"))
    liquidity_score = safe_float(risk_snapshot.get("liquidity_score"))

    risk_flags: list[str] = []

    safety_breach = False

    if row["live_trading"] != LIVE_TRADING_STATUS:
        risk_flags.append("LIVE_TRADING_NOT_DISABLED")
        safety_breach = True

    if int(row["live_order_sent"]) != LIVE_ORDER_SENT_VALUE:
        risk_flags.append("LIVE_ORDER_SENT_NOT_FALSE")
        safety_breach = True

    if row["capital_deployment"] != CAPITAL_DEPLOYMENT_DECISION:
        risk_flags.append("CAPITAL_DEPLOYMENT_NOT_BLOCKED")
        safety_breach = True

    if liquidation_buffer < min_liquidation_buffer:
        risk_flags.append("LIQUIDATION_BUFFER_BELOW_MINIMUM")

    if spread_bps > max_spread_bps:
        risk_flags.append("SPREAD_ABOVE_MAXIMUM")

    if slippage_bps > max_slippage_bps:
        risk_flags.append("SLIPPAGE_ABOVE_MAXIMUM")

    if liquidity_score < min_liquidity_score:
        risk_flags.append("LIQUIDITY_SCORE_BELOW_MINIMUM")

    close_eligible = False
    close_reason = None

    if age_hours >= max_holding_hours:
        close_eligible = True
        close_reason = "MAX_HOLDING_PERIOD_REACHED"

    if safety_breach:
        lifecycle_status = "SAFETY_BREACH"
        close_eligible = True
        close_reason = "SAFETY_BREACH_REVIEW_REQUIRED"
    elif close_eligible:
        lifecycle_status = "CLOSE_ELIGIBLE"
    elif risk_flags:
        lifecycle_status = "RISK_REVIEW"
    else:
        lifecycle_status = "TRACKING"

    snapshot_id = f"{snapshot_label}-{row['observation_id']}"

    return {
        "snapshot_id": snapshot_id,
        "snapshot_label": snapshot_label,
        "created_at": created_at,
        "observation_id": row["observation_id"],
        "ledger_label": row["ledger_label"],
        "source_gate_label": row["source_gate_label"],
        "symbol": row["symbol"],
        "observation_status": row["status"],
        "lifecycle_status": lifecycle_status,
        "age_hours": age_hours,
        "max_holding_hours": max_holding_hours,
        "close_eligible": close_eligible,
        "close_reason": close_reason,
        "simulated_notional_usd": simulated_notional,
        "expected_annualized_funding": expected_annualized_funding,
        "expected_funding_pnl_usd": expected_funding_pnl_usd,
        "expected_funding_return_bps": expected_funding_return_bps,
        "liquidation_buffer": liquidation_buffer,
        "spread_bps": spread_bps,
        "slippage_bps": slippage_bps,
        "liquidity_score": liquidity_score,
        "risk_flags": risk_flags,
        "live_trading": row["live_trading"],
        "live_order_sent": int(row["live_order_sent"]),
        "capital_deployment": row["capital_deployment"],
        "metadata": {
            "mode": row["mode"],
            "thesis": row["thesis"],
            "source_report_label": row["source_report_label"],
            "source_replay_label": row["source_replay_label"],
            "source_run_label": row["source_run_label"],
            "source_scenario_name": row["source_scenario_name"],
            "expected_funding_edge_bps": safe_float(row["expected_funding_edge_bps"]),
            "ledger_metadata": safe_json_loads(row["metadata_json"], {}),
            "risk_snapshot": risk_snapshot,
        },
    }


def persist_snapshots(
    db_path: str | Path,
    snapshots: list[dict[str, Any]],
) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for item in snapshots:
            conn.execute(
                """
                INSERT OR REPLACE INTO shadow_observation_lifecycle_snapshots (
                    snapshot_id,
                    snapshot_label,
                    created_at,
                    observation_id,
                    ledger_label,
                    source_gate_label,
                    symbol,
                    observation_status,
                    lifecycle_status,
                    age_hours,
                    max_holding_hours,
                    close_eligible,
                    close_reason,
                    simulated_notional_usd,
                    expected_annualized_funding,
                    expected_funding_pnl_usd,
                    expected_funding_return_bps,
                    liquidation_buffer,
                    spread_bps,
                    slippage_bps,
                    liquidity_score,
                    risk_flags_json,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["snapshot_id"],
                    item["snapshot_label"],
                    item["created_at"],
                    item["observation_id"],
                    item["ledger_label"],
                    item["source_gate_label"],
                    item["symbol"],
                    item["observation_status"],
                    item["lifecycle_status"],
                    str(item["age_hours"]),
                    str(item["max_holding_hours"]),
                    1 if item["close_eligible"] else 0,
                    item["close_reason"],
                    str(item["simulated_notional_usd"]),
                    str(item["expected_annualized_funding"]),
                    str(item["expected_funding_pnl_usd"]),
                    str(item["expected_funding_return_bps"]),
                    str(item["liquidation_buffer"]),
                    str(item["spread_bps"]),
                    str(item["slippage_bps"]),
                    str(item["liquidity_score"]),
                    json.dumps(item["risk_flags"], sort_keys=True),
                    item["live_trading"],
                    item["live_order_sent"],
                    item["capital_deployment"],
                    json.dumps(item["metadata"], sort_keys=True),
                ),
            )

        conn.commit()


def summarize_snapshots(
    snapshot_label: str,
    created_at: str,
    db_path: str | Path,
    source_gate_label: str | None,
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    observation_count = len(snapshots)
    tracking_count = sum(1 for item in snapshots if item["lifecycle_status"] == "TRACKING")
    close_eligible_count = sum(1 for item in snapshots if item["lifecycle_status"] == "CLOSE_ELIGIBLE")
    risk_review_count = sum(1 for item in snapshots if item["lifecycle_status"] == "RISK_REVIEW")
    safety_breach_count = sum(1 for item in snapshots if item["lifecycle_status"] == "SAFETY_BREACH")

    total_expected_funding_pnl = round(
        sum(safe_float(item["expected_funding_pnl_usd"]) for item in snapshots),
        8,
    )

    status_counts = dict(Counter(item["lifecycle_status"] for item in snapshots))
    symbol_counts = dict(Counter(item["symbol"] for item in snapshots))

    if safety_breach_count > 0:
        global_verdict = SAFETY_BREACH_VERDICT
        recommended_action = "STOP_AND_REVIEW_LIFECYCLE_SAFETY_BREACH"
    elif risk_review_count > 0:
        global_verdict = RISK_REVIEW_VERDICT
        recommended_action = "REVIEW_RISK_FLAGS_BEFORE_CONTINUING_OBSERVATION"
    elif close_eligible_count > 0:
        global_verdict = CLOSE_ELIGIBLE_VERDICT
        recommended_action = "CLOSE_OR_REVIEW_CLOSE_ELIGIBLE_SHADOW_OBSERVATIONS"
    elif observation_count > 0:
        global_verdict = TRACKING_VERDICT
        recommended_action = "CONTINUE_TRACKING_OPEN_SHADOW_OBSERVATIONS"
    else:
        global_verdict = NO_OPEN_OBSERVATIONS_VERDICT
        recommended_action = "OPEN_SHADOW_OBSERVATIONS_FROM_APPROVED_GATE"

    return {
        "snapshot_label": snapshot_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_gate_label": source_gate_label,
        "observation_count": observation_count,
        "tracking_count": tracking_count,
        "close_eligible_count": close_eligible_count,
        "risk_review_count": risk_review_count,
        "safety_breach_count": safety_breach_count,
        "total_expected_funding_pnl_usd": total_expected_funding_pnl,
        "status_counts": status_counts,
        "symbol_counts": symbol_counts,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
        "snapshots": snapshots,
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

    return f"""# DeltaGrid Mission 39 Shadow Observation Lifecycle Report

Snapshot label: {summary['snapshot_label']}
Created at: {summary['created_at']}
Source gate label: {summary['source_gate_label']}

## Lifecycle Summary

Observation count: {summary['observation_count']}
Tracking count: {summary['tracking_count']}
Close eligible count: {summary['close_eligible_count']}
Risk review count: {summary['risk_review_count']}
Safety breach count: {summary['safety_breach_count']}

Total expected funding PnL USD: {summary['total_expected_funding_pnl_usd']}

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


def persist_lifecycle_report(
    db_path: str | Path,
    report_label: str,
    summary: dict[str, Any],
    markdown_report: str,
) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO shadow_observation_lifecycle_reports (
                report_label,
                created_at,
                source_snapshot_label,
                source_gate_label,
                observation_count,
                tracking_count,
                close_eligible_count,
                risk_review_count,
                safety_breach_count,
                total_expected_funding_pnl_usd,
                global_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_label,
                summary["created_at"],
                summary["snapshot_label"],
                summary["source_gate_label"],
                summary["observation_count"],
                summary["tracking_count"],
                summary["close_eligible_count"],
                summary["risk_review_count"],
                summary["safety_breach_count"],
                str(summary["total_expected_funding_pnl_usd"]),
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def evaluate_shadow_observation_lifecycle(
    db_path: str | Path = "offchain/deltagrid.db",
    snapshot_label: str | None = None,
    gate_label: str | None = None,
    report_label: str | None = None,
    max_holding_hours: float = 72.0,
    min_liquidation_buffer: float = 0.35,
    max_spread_bps: float = 4.0,
    max_slippage_bps: float = 6.0,
    min_liquidity_score: float = 80.0,
) -> dict[str, Any]:
    db = Path(db_path)
    label = snapshot_label or new_snapshot_label()
    created_at = utc_now()
    lifecycle_report_label = report_label or new_report_label()

    if max_holding_hours <= 0:
        raise ValueError("max_holding_hours must be greater than 0")

    if not db.exists():
        return {
            "snapshot_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": False,
            "tables_present": False,
            "source_gate_label": gate_label,
            "observation_count": 0,
            "tracking_count": 0,
            "close_eligible_count": 0,
            "risk_review_count": 0,
            "safety_breach_count": 0,
            "total_expected_funding_pnl_usd": 0.0,
            "status_counts": {},
            "symbol_counts": {},
            "snapshots": [],
            "global_verdict": NO_LEDGER_HISTORY_VERDICT,
            "recommended_action": "RUN_MISSION_38_OBSERVATION_LEDGER",
        }

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        if not table_exists(conn, OBSERVATION_LEDGER_TABLE):
            return {
                "snapshot_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "tables_present": False,
                "missing_tables": [OBSERVATION_LEDGER_TABLE],
                "source_gate_label": gate_label,
                "observation_count": 0,
                "tracking_count": 0,
                "close_eligible_count": 0,
                "risk_review_count": 0,
                "safety_breach_count": 0,
                "total_expected_funding_pnl_usd": 0.0,
                "status_counts": {},
                "symbol_counts": {},
                "snapshots": [],
                "global_verdict": MISSING_LEDGER_TABLE_VERDICT,
                "recommended_action": "RUN_MISSION_38_OBSERVATION_LEDGER",
            }

        rows = load_open_observations(conn, gate_label)

    now_dt = parse_utc(created_at)

    snapshots = [
        evaluate_single_observation(
            row=row,
            snapshot_label=label,
            created_at=created_at,
            now_dt=now_dt,
            max_holding_hours=max_holding_hours,
            min_liquidation_buffer=min_liquidation_buffer,
            max_spread_bps=max_spread_bps,
            max_slippage_bps=max_slippage_bps,
            min_liquidity_score=min_liquidity_score,
        )
        for row in rows
    ]

    persist_snapshots(db, snapshots)

    summary = summarize_snapshots(
        snapshot_label=label,
        created_at=created_at,
        db_path=db,
        source_gate_label=gate_label,
        snapshots=snapshots,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report
    summary["report_label"] = lifecycle_report_label

    persist_lifecycle_report(
        db_path=db,
        report_label=lifecycle_report_label,
        summary=summary,
        markdown_report=markdown_report,
    )

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate DeltaGrid shadow observation lifecycle."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--snapshot-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--gate-label", default=None)
    parser.add_argument("--max-holding-hours", type=float, default=72.0)
    parser.add_argument("--min-liquidation-buffer", type=float, default=0.35)
    parser.add_argument("--max-spread-bps", type=float, default=4.0)
    parser.add_argument("--max-slippage-bps", type=float, default=6.0)
    parser.add_argument("--min-liquidity-score", type=float, default=80.0)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = evaluate_shadow_observation_lifecycle(
        db_path=args.db,
        snapshot_label=args.snapshot_label,
        report_label=args.report_label,
        gate_label=args.gate_label,
        max_holding_hours=args.max_holding_hours,
        min_liquidation_buffer=args.min_liquidation_buffer,
        max_spread_bps=args.max_spread_bps,
        max_slippage_bps=args.max_slippage_bps,
        min_liquidity_score=args.min_liquidity_score,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

"""
Mission 38: Shadow Paper Observation Ledger.

This module creates an auditable ledger for shadow-paper observations approved
by the Mission 37 decision gate.

It is a ledger and reporting layer, not an execution layer.

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
LIVE_TRADING_DECISION = "BLOCKED"
CAPITAL_DEPLOYMENT_DECISION = "BLOCKED"
LIVE_ORDER_SENT = False

APPROVED_GATE_DECISION = "DECISION_GATE_APPROVE_SHADOW_OBSERVATION_ONLY_NO_LIVE_TRADING"

NO_GATE_HISTORY_VERDICT = "OBSERVATION_LEDGER_NO_DECISION_GATE_HISTORY"
MISSING_GATE_TABLE_VERDICT = "OBSERVATION_LEDGER_DECISION_GATE_TABLE_MISSING"
NO_MATCHING_GATE_VERDICT = "OBSERVATION_LEDGER_NO_MATCHING_DECISION_GATE"
GATE_NOT_APPROVED_VERDICT = "OBSERVATION_LEDGER_GATE_NOT_APPROVED_FOR_SHADOW_OBSERVATION"
SOURCE_REPORT_MISSING_VERDICT = "OBSERVATION_LEDGER_SOURCE_PERFORMANCE_REPORT_MISSING"
SOURCE_REPLAY_MISSING_VERDICT = "OBSERVATION_LEDGER_SOURCE_REPLAY_SCENARIOS_MISSING"
NO_ELIGIBLE_SCENARIOS_VERDICT = "OBSERVATION_LEDGER_NO_APPROVED_SHADOW_SCENARIOS"
SAFETY_BREACH_VERDICT = "OBSERVATION_LEDGER_SAFETY_BREACH_BLOCKED"
OBSERVATIONS_OPENED_VERDICT = "OBSERVATION_LEDGER_OPENED_SHADOW_OBSERVATIONS_NO_LIVE_TRADING"
OBSERVATION_CLOSED_VERDICT = "OBSERVATION_LEDGER_CLOSED_SHADOW_OBSERVATION"
REPORT_GENERATED_VERDICT = "OBSERVATION_LEDGER_REPORT_GENERATED"

DECISION_GATE_TABLE = "shadow_research_decision_gate_reports"
PERFORMANCE_REPORTS_TABLE = "shadow_replay_performance_reports"
REPLAY_SCENARIOS_TABLE = "shadow_candidate_replay_scenarios"
OBSERVATION_LEDGER_TABLE = "shadow_paper_observation_ledger"
OBSERVATION_REPORTS_TABLE = "shadow_paper_observation_reports"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_ledger_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission38-ledger-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission38-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
            CREATE TABLE IF NOT EXISTS shadow_paper_observation_ledger (
                observation_id TEXT PRIMARY KEY,
                ledger_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                status TEXT NOT NULL,
                mode TEXT NOT NULL,
                symbol TEXT NOT NULL,
                thesis TEXT NOT NULL,
                simulated_notional_usd TEXT NOT NULL,
                expected_funding_edge_bps TEXT NOT NULL,
                expected_annualized_funding TEXT NOT NULL,
                risk_snapshot_json TEXT NOT NULL,
                source_gate_label TEXT NOT NULL,
                source_report_label TEXT NOT NULL,
                source_replay_label TEXT NOT NULL,
                source_run_label TEXT NOT NULL,
                source_scenario_name TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                realized_pnl_usd TEXT,
                realized_return_bps TEXT,
                realized_funding_bps TEXT,
                fees_bps TEXT,
                slippage_bps TEXT,
                close_reason TEXT,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_paper_observation_reports (
                report_label TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                source_gate_label TEXT,
                observation_count INTEGER NOT NULL,
                open_count INTEGER NOT NULL,
                closed_count INTEGER NOT NULL,
                total_simulated_notional_usd TEXT NOT NULL,
                total_realized_pnl_usd TEXT NOT NULL,
                live_trading_breach_count INTEGER NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def derive_observation_spec(scenario_name: str) -> dict[str, Any]:
    known = {
        "approved_shadow_btc": {
            "symbol": "BTCUSDT",
            "thesis": "Strong BTCUSDT positive funding candidate approved for shadow-paper observation only.",
            "expected_funding_edge_bps": 120.0,
            "expected_annualized_funding": 0.42,
            "risk_snapshot": {
                "basis_bps": 12.0,
                "spread_bps": 2.0,
                "estimated_slippage_bps": 3.0,
                "stressed_liquidation_buffer": 0.50,
                "liquidity_score": 95.0,
                "leverage": 1.0,
            },
        },
        "mixed_shadow_set": {
            "symbol": "BTCUSDT",
            "thesis": "BTCUSDT candidate from mixed replay set approved for shadow-paper observation only.",
            "expected_funding_edge_bps": 125.0,
            "expected_annualized_funding": 0.40,
            "risk_snapshot": {
                "basis_bps": 10.0,
                "spread_bps": 2.0,
                "estimated_slippage_bps": 3.0,
                "stressed_liquidation_buffer": 0.52,
                "liquidity_score": 98.0,
                "leverage": 1.0,
            },
        },
    }

    fallback = {
        "symbol": "BTCUSDT",
        "thesis": f"Approved shadow-paper scenario: {scenario_name}.",
        "expected_funding_edge_bps": 0.0,
        "expected_annualized_funding": 0.0,
        "risk_snapshot": {
            "basis_bps": 0.0,
            "spread_bps": 0.0,
            "estimated_slippage_bps": 0.0,
            "stressed_liquidation_buffer": 0.0,
            "liquidity_score": 0.0,
            "leverage": 1.0,
        },
    }

    return known.get(scenario_name, fallback)


def load_gate_row(
    conn: sqlite3.Connection,
    gate_label: str | None,
) -> sqlite3.Row | None:
    query = """
        SELECT
            gate_label,
            created_at,
            source_report_label,
            gate_decision,
            live_trading_decision,
            capital_deployment_decision,
            approved_next_stage,
            metrics_json
        FROM shadow_research_decision_gate_reports
    """
    params: list[Any] = []

    if gate_label is not None:
        query += " WHERE gate_label = ?"
        params.append(gate_label)

    query += " ORDER BY created_at DESC, gate_label DESC LIMIT 1"

    return conn.execute(query, params).fetchone()


def load_performance_source_replay(
    conn: sqlite3.Connection,
    report_label: str,
) -> str | None:
    row = conn.execute(
        """
        SELECT source_replay_label
        FROM shadow_replay_performance_reports
        WHERE report_label = ?
        """,
        (report_label,),
    ).fetchone()

    if row is None:
        return None

    return str(row["source_replay_label"])


def load_eligible_replay_scenarios(
    conn: sqlite3.Connection,
    replay_label: str,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            replay_label,
            scenario_name,
            run_label,
            description,
            live_trading,
            approved_count,
            rejected_count,
            paper_positions_count,
            verdict,
            recommended_action,
            alerts_json,
            created_at
        FROM shadow_candidate_replay_scenarios
        WHERE replay_label = ?
        AND approved_count > 0
        AND paper_positions_count > 0
        ORDER BY id ASC
        """,
        (replay_label,),
    ).fetchall()


def open_shadow_paper_observations(
    db_path: str | Path = "offchain/deltagrid.db",
    ledger_label: str | None = None,
    gate_label: str | None = None,
    simulated_notional_usd: float = 1000.0,
) -> dict[str, Any]:
    db = Path(db_path)
    label = ledger_label or new_ledger_label()
    created_at = utc_now()

    if not db.exists():
        return {
            "ledger_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": False,
            "tables_present": False,
            "source_gate_label": gate_label,
            "opened_count": 0,
            "observation_ids": [],
            "live_trading": LIVE_TRADING_STATUS,
            "live_order_sent": LIVE_ORDER_SENT,
            "capital_deployment": CAPITAL_DEPLOYMENT_DECISION,
            "global_verdict": NO_GATE_HISTORY_VERDICT,
            "recommended_action": "RUN_MISSION_37_DECISION_GATE",
        }

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        if not table_exists(conn, DECISION_GATE_TABLE):
            return {
                "ledger_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "tables_present": False,
                "missing_tables": [DECISION_GATE_TABLE],
                "source_gate_label": gate_label,
                "opened_count": 0,
                "observation_ids": [],
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT,
                "capital_deployment": CAPITAL_DEPLOYMENT_DECISION,
                "global_verdict": MISSING_GATE_TABLE_VERDICT,
                "recommended_action": "RUN_MISSION_37_DECISION_GATE",
            }

        gate = load_gate_row(conn, gate_label)

        if gate is None:
            return {
                "ledger_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "tables_present": True,
                "source_gate_label": gate_label,
                "opened_count": 0,
                "observation_ids": [],
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT,
                "capital_deployment": CAPITAL_DEPLOYMENT_DECISION,
                "global_verdict": NO_MATCHING_GATE_VERDICT,
                "recommended_action": "RUN_MATCHING_MISSION_37_DECISION_GATE",
            }

        if (
            gate["live_trading_decision"] != LIVE_TRADING_DECISION
            or gate["capital_deployment_decision"] != CAPITAL_DEPLOYMENT_DECISION
        ):
            return {
                "ledger_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "tables_present": True,
                "source_gate_label": gate["gate_label"],
                "source_report_label": gate["source_report_label"],
                "opened_count": 0,
                "observation_ids": [],
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT,
                "capital_deployment": CAPITAL_DEPLOYMENT_DECISION,
                "global_verdict": SAFETY_BREACH_VERDICT,
                "recommended_action": "STOP_AND_REVIEW_GATE_SAFETY_STATE",
            }

        if gate["gate_decision"] != APPROVED_GATE_DECISION:
            return {
                "ledger_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "tables_present": True,
                "source_gate_label": gate["gate_label"],
                "source_report_label": gate["source_report_label"],
                "gate_decision": gate["gate_decision"],
                "opened_count": 0,
                "observation_ids": [],
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT,
                "capital_deployment": CAPITAL_DEPLOYMENT_DECISION,
                "global_verdict": GATE_NOT_APPROVED_VERDICT,
                "recommended_action": "WAIT_FOR_APPROVED_SHADOW_OBSERVATION_GATE",
            }

        if not table_exists(conn, PERFORMANCE_REPORTS_TABLE):
            return {
                "ledger_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "tables_present": False,
                "missing_tables": [PERFORMANCE_REPORTS_TABLE],
                "source_gate_label": gate["gate_label"],
                "source_report_label": gate["source_report_label"],
                "opened_count": 0,
                "observation_ids": [],
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT,
                "capital_deployment": CAPITAL_DEPLOYMENT_DECISION,
                "global_verdict": SOURCE_REPORT_MISSING_VERDICT,
                "recommended_action": "RUN_MISSION_36_PERFORMANCE_REPORTER",
            }

        source_replay_label = load_performance_source_replay(
            conn=conn,
            report_label=str(gate["source_report_label"]),
        )

        if source_replay_label is None:
            return {
                "ledger_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "tables_present": True,
                "source_gate_label": gate["gate_label"],
                "source_report_label": gate["source_report_label"],
                "opened_count": 0,
                "observation_ids": [],
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT,
                "capital_deployment": CAPITAL_DEPLOYMENT_DECISION,
                "global_verdict": SOURCE_REPORT_MISSING_VERDICT,
                "recommended_action": "GENERATE_MATCHING_PERFORMANCE_REPORT",
            }

        if not table_exists(conn, REPLAY_SCENARIOS_TABLE):
            return {
                "ledger_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "tables_present": False,
                "missing_tables": [REPLAY_SCENARIOS_TABLE],
                "source_gate_label": gate["gate_label"],
                "source_report_label": gate["source_report_label"],
                "source_replay_label": source_replay_label,
                "opened_count": 0,
                "observation_ids": [],
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT,
                "capital_deployment": CAPITAL_DEPLOYMENT_DECISION,
                "global_verdict": SOURCE_REPLAY_MISSING_VERDICT,
                "recommended_action": "RUN_MISSION_35_REPLAY_HARNESS",
            }

        scenarios = load_eligible_replay_scenarios(
            conn=conn,
            replay_label=source_replay_label,
        )

        if not scenarios:
            return {
                "ledger_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "tables_present": True,
                "source_gate_label": gate["gate_label"],
                "source_report_label": gate["source_report_label"],
                "source_replay_label": source_replay_label,
                "opened_count": 0,
                "observation_ids": [],
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT,
                "capital_deployment": CAPITAL_DEPLOYMENT_DECISION,
                "global_verdict": NO_ELIGIBLE_SCENARIOS_VERDICT,
                "recommended_action": "GENERATE_APPROVED_SHADOW_REPLAY_SCENARIOS",
            }

        observation_ids: list[str] = []
        inserted_count = 0

        for scenario in scenarios:
            paper_positions_count = int(scenario["paper_positions_count"])
            spec = derive_observation_spec(str(scenario["scenario_name"]))

            for position_index in range(1, paper_positions_count + 1):
                observation_id = (
                    f"{label}-{scenario['scenario_name']}-{position_index}"
                )

                metadata = {
                    "approved_count": int(scenario["approved_count"]),
                    "rejected_count": int(scenario["rejected_count"]),
                    "scenario_verdict": scenario["verdict"],
                    "scenario_recommended_action": scenario["recommended_action"],
                    "scenario_alerts": safe_json_loads(scenario["alerts_json"], []),
                    "decision_gate_metrics": safe_json_loads(gate["metrics_json"], {}),
                }

                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO shadow_paper_observation_ledger (
                        observation_id,
                        ledger_label,
                        created_at,
                        opened_at,
                        closed_at,
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
                        realized_pnl_usd,
                        realized_return_bps,
                        realized_funding_bps,
                        fees_bps,
                        slippage_bps,
                        close_reason,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observation_id,
                        label,
                        created_at,
                        created_at,
                        None,
                        "OPEN",
                        "SHADOW_PAPER",
                        spec["symbol"],
                        spec["thesis"],
                        str(simulated_notional_usd),
                        str(spec["expected_funding_edge_bps"]),
                        str(spec["expected_annualized_funding"]),
                        json.dumps(spec["risk_snapshot"], sort_keys=True),
                        gate["gate_label"],
                        gate["source_report_label"],
                        source_replay_label,
                        scenario["run_label"],
                        scenario["scenario_name"],
                        LIVE_TRADING_STATUS,
                        1 if LIVE_ORDER_SENT else 0,
                        CAPITAL_DEPLOYMENT_DECISION,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        json.dumps(metadata, sort_keys=True),
                    ),
                )

                observation_ids.append(observation_id)
                inserted_count += int(cursor.rowcount)

        conn.commit()

    return {
        "ledger_label": label,
        "created_at": created_at,
        "db_path": str(db),
        "database_exists": True,
        "tables_present": True,
        "source_gate_label": gate["gate_label"],
        "source_report_label": gate["source_report_label"],
        "source_replay_label": source_replay_label,
        "gate_decision": gate["gate_decision"],
        "eligible_scenario_count": len(scenarios),
        "opened_count": inserted_count,
        "observation_ids": observation_ids,
        "simulated_notional_usd": simulated_notional_usd,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT,
        "capital_deployment": CAPITAL_DEPLOYMENT_DECISION,
        "global_verdict": OBSERVATIONS_OPENED_VERDICT,
        "recommended_action": "TRACK_SHADOW_OBSERVATIONS_UNTIL_CLOSE",
    }


def close_shadow_paper_observation(
    db_path: str | Path,
    observation_id: str,
    realized_pnl_usd: float,
    realized_funding_bps: float,
    fees_bps: float,
    slippage_bps: float,
    close_reason: str,
) -> dict[str, Any]:
    db = Path(db_path)

    ensure_schema(db)

    closed_at = utc_now()

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            """
            SELECT observation_id, simulated_notional_usd, status
            FROM shadow_paper_observation_ledger
            WHERE observation_id = ?
            """,
            (observation_id,),
        ).fetchone()

        if row is None:
            return {
                "observation_id": observation_id,
                "closed": False,
                "global_verdict": "OBSERVATION_LEDGER_CLOSE_FAILED_NOT_FOUND",
                "recommended_action": "CHECK_OBSERVATION_ID",
            }

        simulated_notional = safe_float(row["simulated_notional_usd"])
        realized_return_bps = safe_rate(realized_pnl_usd, simulated_notional) * 10000

        conn.execute(
            """
            UPDATE shadow_paper_observation_ledger
            SET
                status = 'CLOSED',
                closed_at = ?,
                realized_pnl_usd = ?,
                realized_return_bps = ?,
                realized_funding_bps = ?,
                fees_bps = ?,
                slippage_bps = ?,
                close_reason = ?
            WHERE observation_id = ?
            """,
            (
                closed_at,
                str(realized_pnl_usd),
                str(round(realized_return_bps, 6)),
                str(realized_funding_bps),
                str(fees_bps),
                str(slippage_bps),
                close_reason,
                observation_id,
            ),
        )

        conn.commit()

    return {
        "observation_id": observation_id,
        "closed": True,
        "closed_at": closed_at,
        "realized_pnl_usd": realized_pnl_usd,
        "realized_return_bps": round(realized_return_bps, 6),
        "realized_funding_bps": realized_funding_bps,
        "fees_bps": fees_bps,
        "slippage_bps": slippage_bps,
        "close_reason": close_reason,
        "global_verdict": OBSERVATION_CLOSED_VERDICT,
        "recommended_action": "INCLUDE_CLOSED_OBSERVATION_IN_REPORT",
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    status_counts = "\n".join(
        f"- {status}: {count}"
        for status, count in summary["status_counts"].items()
    ) or "- None"

    symbol_counts = "\n".join(
        f"- {symbol}: {count}"
        for symbol, count in summary["symbol_counts"].items()
    ) or "- None"

    return f"""# DeltaGrid Mission 38 Shadow Paper Observation Ledger Report

Report label: {summary['report_label']}
Created at: {summary['created_at']}
Source gate label: {summary['source_gate_label']}

## Observation Summary

Observation count: {summary['observation_count']}
Open count: {summary['open_count']}
Closed count: {summary['closed_count']}

Total simulated notional USD: {summary['total_simulated_notional_usd']}
Total realized PnL USD: {summary['total_realized_pnl_usd']}

Live trading breach count: {summary['live_trading_breach_count']}

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


def generate_shadow_paper_observation_report(
    db_path: str | Path = "offchain/deltagrid.db",
    report_label: str | None = None,
    gate_label: str | None = None,
) -> dict[str, Any]:
    db = Path(db_path)
    label = report_label or new_report_label()
    created_at = utc_now()

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        query = """
            SELECT
                observation_id,
                status,
                symbol,
                simulated_notional_usd,
                source_gate_label,
                live_trading,
                live_order_sent,
                capital_deployment,
                realized_pnl_usd
            FROM shadow_paper_observation_ledger
        """
        params: list[Any] = []

        if gate_label is not None:
            query += " WHERE source_gate_label = ?"
            params.append(gate_label)

        query += " ORDER BY opened_at DESC, observation_id DESC"

        rows = conn.execute(query, params).fetchall()

        observation_count = len(rows)
        open_count = sum(1 for row in rows if row["status"] == "OPEN")
        closed_count = sum(1 for row in rows if row["status"] == "CLOSED")

        total_notional = round(
            sum(safe_float(row["simulated_notional_usd"]) for row in rows),
            6,
        )
        total_realized_pnl = round(
            sum(safe_float(row["realized_pnl_usd"]) for row in rows),
            6,
        )

        live_trading_breaches = [
            row["observation_id"]
            for row in rows
            if row["live_trading"] != LIVE_TRADING_STATUS
            or int(row["live_order_sent"]) != 0
            or row["capital_deployment"] != CAPITAL_DEPLOYMENT_DECISION
        ]

        status_counts = dict(Counter(str(row["status"]) for row in rows))
        symbol_counts = dict(Counter(str(row["symbol"]) for row in rows))

        if live_trading_breaches:
            global_verdict = SAFETY_BREACH_VERDICT
            recommended_action = "STOP_AND_REVIEW_OBSERVATION_LEDGER_SAFETY"
        elif observation_count == 0:
            global_verdict = "OBSERVATION_LEDGER_REPORT_NO_OBSERVATIONS"
            recommended_action = "OPEN_SHADOW_OBSERVATIONS_FROM_APPROVED_GATE"
        elif open_count > 0:
            global_verdict = "OBSERVATION_LEDGER_REPORT_OPEN_OBSERVATIONS_TRACKING"
            recommended_action = "CONTINUE_TRACKING_OPEN_SHADOW_OBSERVATIONS"
        else:
            global_verdict = REPORT_GENERATED_VERDICT
            recommended_action = "REVIEW_CLOSED_SHADOW_OBSERVATION_OUTCOMES"

        summary = {
            "report_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "source_gate_label": gate_label,
            "observation_count": observation_count,
            "open_count": open_count,
            "closed_count": closed_count,
            "total_simulated_notional_usd": total_notional,
            "total_realized_pnl_usd": total_realized_pnl,
            "live_trading_breach_count": len(live_trading_breaches),
            "live_trading_breach_observation_ids": live_trading_breaches,
            "status_counts": status_counts,
            "symbol_counts": symbol_counts,
            "global_verdict": global_verdict,
            "recommended_action": recommended_action,
        }

        markdown_report = build_markdown_report(summary)
        summary["markdown_report"] = markdown_report

        conn.execute(
            """
            INSERT OR REPLACE INTO shadow_paper_observation_reports (
                report_label,
                created_at,
                source_gate_label,
                observation_count,
                open_count,
                closed_count,
                total_simulated_notional_usd,
                total_realized_pnl_usd,
                live_trading_breach_count,
                global_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["created_at"],
                summary["source_gate_label"],
                summary["observation_count"],
                summary["open_count"],
                summary["closed_count"],
                str(summary["total_simulated_notional_usd"]),
                str(summary["total_realized_pnl_usd"]),
                summary["live_trading_breach_count"],
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage DeltaGrid shadow paper observation ledger."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--ledger-label", default=None)
    parser.add_argument("--gate-label", default=None)
    parser.add_argument("--simulated-notional-usd", type=float, default=1000.0)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    if args.report:
        result = generate_shadow_paper_observation_report(
            db_path=args.db,
            report_label=args.report_label,
            gate_label=args.gate_label,
        )
    else:
        result = open_shadow_paper_observations(
            db_path=args.db,
            ledger_label=args.ledger_label,
            gate_label=args.gate_label,
            simulated_notional_usd=args.simulated_notional_usd,
        )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

"""
Mission 40: Shadow Observation PnL Attribution Engine.

This module converts Mission 39 lifecycle snapshots into simulated PnL
attribution records.

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_DECISION = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

LIFECYCLE_SNAPSHOTS_TABLE = "shadow_observation_lifecycle_snapshots"
PNL_ATTRIBUTION_TABLE = "shadow_observation_pnl_attribution"
PNL_ATTRIBUTION_REPORTS_TABLE = "shadow_observation_pnl_attribution_reports"

NO_LIFECYCLE_HISTORY_VERDICT = "PNL_ATTRIBUTION_NO_LIFECYCLE_HISTORY"
MISSING_LIFECYCLE_TABLE_VERDICT = "PNL_ATTRIBUTION_LIFECYCLE_TABLE_MISSING"
NO_MATCHING_SNAPSHOTS_VERDICT = "PNL_ATTRIBUTION_NO_MATCHING_LIFECYCLE_SNAPSHOTS"
SAFETY_BREACH_VERDICT = "PNL_ATTRIBUTION_SAFETY_BREACH_BLOCKED"
RISK_REVIEW_VERDICT = "PNL_ATTRIBUTION_RISK_REVIEW_REQUIRED"
NEGATIVE_NET_VERDICT = "PNL_ATTRIBUTION_NEGATIVE_EXPECTED_AFTER_COST"
MIXED_NET_VERDICT = "PNL_ATTRIBUTION_MIXED_EXPECTED_NET_EDGE"
POSITIVE_NET_VERDICT = "PNL_ATTRIBUTION_POSITIVE_EXPECTED_NET_EDGE"

ATTRIBUTION_STATUS_SAFETY_BREACH = "SAFETY_BREACH"
ATTRIBUTION_STATUS_RISK_REVIEW = "RISK_REVIEW"
ATTRIBUTION_STATUS_NEGATIVE = "NEGATIVE_EXPECTED_AFTER_COST"
ATTRIBUTION_STATUS_MARGINAL = "MARGINAL_EXPECTED_NET_EDGE"
ATTRIBUTION_STATUS_POSITIVE = "POSITIVE_EXPECTED_NET_EDGE"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_attribution_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission40-pnl-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission40-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
            CREATE TABLE IF NOT EXISTS shadow_observation_pnl_attribution (
                attribution_id TEXT PRIMARY KEY,
                attribution_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                snapshot_label TEXT NOT NULL,
                observation_id TEXT NOT NULL,
                ledger_label TEXT NOT NULL,
                source_gate_label TEXT NOT NULL,
                symbol TEXT NOT NULL,
                lifecycle_status TEXT NOT NULL,
                simulated_notional_usd TEXT NOT NULL,
                gross_expected_funding_pnl_usd TEXT NOT NULL,
                fee_cost_usd TEXT NOT NULL,
                spread_cost_usd TEXT NOT NULL,
                slippage_cost_usd TEXT NOT NULL,
                total_cost_usd TEXT NOT NULL,
                net_expected_pnl_usd TEXT NOT NULL,
                net_expected_return_bps TEXT NOT NULL,
                edge_to_cost_ratio TEXT NOT NULL,
                attribution_status TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS shadow_observation_pnl_attribution_reports (
                report_label TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                source_snapshot_label TEXT,
                attribution_label TEXT NOT NULL,
                observation_count INTEGER NOT NULL,
                positive_count INTEGER NOT NULL,
                marginal_count INTEGER NOT NULL,
                negative_count INTEGER NOT NULL,
                risk_review_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                total_gross_expected_funding_pnl_usd TEXT NOT NULL,
                total_cost_usd TEXT NOT NULL,
                total_net_expected_pnl_usd TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def get_latest_snapshot_label(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        """
        SELECT snapshot_label
        FROM shadow_observation_lifecycle_snapshots
        ORDER BY created_at DESC, snapshot_label DESC
        LIMIT 1
        """
    ).fetchone()

    if row is None:
        return None

    return str(row["snapshot_label"])


def load_lifecycle_snapshots(
    conn: sqlite3.Connection,
    snapshot_label: str | None,
    gate_label: str | None,
) -> tuple[str | None, list[sqlite3.Row]]:
    resolved_snapshot_label = snapshot_label

    if resolved_snapshot_label is None:
        resolved_snapshot_label = get_latest_snapshot_label(conn)

    if resolved_snapshot_label is None:
        return None, []

    query = """
        SELECT
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
        FROM shadow_observation_lifecycle_snapshots
        WHERE snapshot_label = ?
    """
    params: list[Any] = [resolved_snapshot_label]

    if gate_label is not None:
        query += " AND source_gate_label = ?"
        params.append(gate_label)

    query += " ORDER BY observation_id ASC"

    return resolved_snapshot_label, conn.execute(query, params).fetchall()


def evaluate_single_snapshot(
    row: sqlite3.Row,
    attribution_label: str,
    created_at: str,
    fee_bps: float,
    min_edge_to_cost_ratio: float,
) -> dict[str, Any]:
    simulated_notional = safe_float(row["simulated_notional_usd"])
    gross_expected_funding_pnl = safe_float(row["expected_funding_pnl_usd"])

    spread_bps = safe_float(row["spread_bps"])
    slippage_bps = safe_float(row["slippage_bps"])

    fee_cost_usd = round(simulated_notional * fee_bps / 10000.0, 8)
    spread_cost_usd = round(simulated_notional * spread_bps / 10000.0, 8)
    slippage_cost_usd = round(simulated_notional * slippage_bps / 10000.0, 8)

    total_cost_usd = round(
        fee_cost_usd + spread_cost_usd + slippage_cost_usd,
        8,
    )

    net_expected_pnl_usd = round(
        gross_expected_funding_pnl - total_cost_usd,
        8,
    )

    net_expected_return_bps = 0.0
    if simulated_notional > 0:
        net_expected_return_bps = round(
            (net_expected_pnl_usd / simulated_notional) * 10000.0,
            6,
        )

    edge_to_cost_ratio = 0.0
    if total_cost_usd > 0:
        edge_to_cost_ratio = round(
            gross_expected_funding_pnl / total_cost_usd,
            6,
        )

    risk_flags = safe_json_loads(row["risk_flags_json"], [])

    safety_breach = (
        row["live_trading"] != LIVE_TRADING_STATUS
        or int(row["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or row["capital_deployment"] != CAPITAL_DEPLOYMENT_DECISION
    )

    if safety_breach:
        attribution_status = ATTRIBUTION_STATUS_SAFETY_BREACH
    elif str(row["lifecycle_status"]) in {"SAFETY_BREACH"}:
        attribution_status = ATTRIBUTION_STATUS_SAFETY_BREACH
    elif str(row["lifecycle_status"]) in {"RISK_REVIEW"} or risk_flags:
        attribution_status = ATTRIBUTION_STATUS_RISK_REVIEW
    elif net_expected_pnl_usd > 0 and edge_to_cost_ratio >= min_edge_to_cost_ratio:
        attribution_status = ATTRIBUTION_STATUS_POSITIVE
    elif net_expected_pnl_usd > 0:
        attribution_status = ATTRIBUTION_STATUS_MARGINAL
    else:
        attribution_status = ATTRIBUTION_STATUS_NEGATIVE

    attribution_id = f"{attribution_label}-{row['observation_id']}"

    return {
        "attribution_id": attribution_id,
        "attribution_label": attribution_label,
        "created_at": created_at,
        "snapshot_label": row["snapshot_label"],
        "observation_id": row["observation_id"],
        "ledger_label": row["ledger_label"],
        "source_gate_label": row["source_gate_label"],
        "symbol": row["symbol"],
        "lifecycle_status": row["lifecycle_status"],
        "simulated_notional_usd": simulated_notional,
        "gross_expected_funding_pnl_usd": gross_expected_funding_pnl,
        "fee_cost_usd": fee_cost_usd,
        "spread_cost_usd": spread_cost_usd,
        "slippage_cost_usd": slippage_cost_usd,
        "total_cost_usd": total_cost_usd,
        "net_expected_pnl_usd": net_expected_pnl_usd,
        "net_expected_return_bps": net_expected_return_bps,
        "edge_to_cost_ratio": edge_to_cost_ratio,
        "attribution_status": attribution_status,
        "live_trading": row["live_trading"],
        "live_order_sent": int(row["live_order_sent"]),
        "capital_deployment": row["capital_deployment"],
        "risk_flags": risk_flags,
        "metadata": {
            "snapshot_id": row["snapshot_id"],
            "observation_status": row["observation_status"],
            "age_hours": safe_float(row["age_hours"]),
            "max_holding_hours": safe_float(row["max_holding_hours"]),
            "close_eligible": bool(row["close_eligible"]),
            "close_reason": row["close_reason"],
            "expected_annualized_funding": safe_float(row["expected_annualized_funding"]),
            "expected_funding_return_bps": safe_float(row["expected_funding_return_bps"]),
            "liquidation_buffer": safe_float(row["liquidation_buffer"]),
            "spread_bps": spread_bps,
            "slippage_bps": slippage_bps,
            "liquidity_score": safe_float(row["liquidity_score"]),
            "lifecycle_metadata": safe_json_loads(row["metadata_json"], {}),
            "fee_bps": fee_bps,
            "min_edge_to_cost_ratio": min_edge_to_cost_ratio,
        },
    }


def persist_attributions(
    db_path: str | Path,
    attributions: list[dict[str, Any]],
) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for item in attributions:
            conn.execute(
                """
                INSERT OR REPLACE INTO shadow_observation_pnl_attribution (
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
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["attribution_id"],
                    item["attribution_label"],
                    item["created_at"],
                    item["snapshot_label"],
                    item["observation_id"],
                    item["ledger_label"],
                    item["source_gate_label"],
                    item["symbol"],
                    item["lifecycle_status"],
                    str(item["simulated_notional_usd"]),
                    str(item["gross_expected_funding_pnl_usd"]),
                    str(item["fee_cost_usd"]),
                    str(item["spread_cost_usd"]),
                    str(item["slippage_cost_usd"]),
                    str(item["total_cost_usd"]),
                    str(item["net_expected_pnl_usd"]),
                    str(item["net_expected_return_bps"]),
                    str(item["edge_to_cost_ratio"]),
                    item["attribution_status"],
                    item["live_trading"],
                    item["live_order_sent"],
                    item["capital_deployment"],
                    json.dumps(item["risk_flags"], sort_keys=True),
                    json.dumps(item["metadata"], sort_keys=True),
                ),
            )

        conn.commit()


def summarize_attributions(
    db_path: str | Path,
    attribution_label: str,
    report_label: str,
    created_at: str,
    source_snapshot_label: str | None,
    attributions: list[dict[str, Any]],
) -> dict[str, Any]:
    observation_count = len(attributions)

    positive_count = sum(
        1 for item in attributions
        if item["attribution_status"] == ATTRIBUTION_STATUS_POSITIVE
    )
    marginal_count = sum(
        1 for item in attributions
        if item["attribution_status"] == ATTRIBUTION_STATUS_MARGINAL
    )
    negative_count = sum(
        1 for item in attributions
        if item["attribution_status"] == ATTRIBUTION_STATUS_NEGATIVE
    )
    risk_review_count = sum(
        1 for item in attributions
        if item["attribution_status"] == ATTRIBUTION_STATUS_RISK_REVIEW
    )
    safety_breach_count = sum(
        1 for item in attributions
        if item["attribution_status"] == ATTRIBUTION_STATUS_SAFETY_BREACH
    )

    total_gross = round(
        sum(safe_float(item["gross_expected_funding_pnl_usd"]) for item in attributions),
        8,
    )
    total_cost = round(
        sum(safe_float(item["total_cost_usd"]) for item in attributions),
        8,
    )
    total_net = round(
        sum(safe_float(item["net_expected_pnl_usd"]) for item in attributions),
        8,
    )

    status_counts = dict(Counter(item["attribution_status"] for item in attributions))
    symbol_counts = dict(Counter(item["symbol"] for item in attributions))

    if observation_count == 0:
        global_verdict = NO_MATCHING_SNAPSHOTS_VERDICT
        recommended_action = "RUN_MISSION_39_LIFECYCLE_MANAGER"
    elif safety_breach_count > 0:
        global_verdict = SAFETY_BREACH_VERDICT
        recommended_action = "STOP_AND_REVIEW_PNL_ATTRIBUTION_SAFETY_BREACH"
    elif risk_review_count > 0:
        global_verdict = RISK_REVIEW_VERDICT
        recommended_action = "REVIEW_RISK_FLAGS_BEFORE_PNL_INTERPRETATION"
    elif positive_count > 0 and negative_count == 0 and marginal_count == 0:
        global_verdict = POSITIVE_NET_VERDICT
        recommended_action = "CONTINUE_SHADOW_OBSERVATION_AND_VALIDATE_MORE_SAMPLES"
    elif positive_count > 0 or marginal_count > 0:
        global_verdict = MIXED_NET_VERDICT
        recommended_action = "CONTINUE_OBSERVATION_AND_AVOID_EARLY_CLOSE"
    else:
        global_verdict = NEGATIVE_NET_VERDICT
        recommended_action = "CONTINUE_OBSERVATION_UNTIL_FUNDING_ACCRUAL_CAN_COVER_COSTS"

    return {
        "report_label": report_label,
        "attribution_label": attribution_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_snapshot_label": source_snapshot_label,
        "observation_count": observation_count,
        "positive_count": positive_count,
        "marginal_count": marginal_count,
        "negative_count": negative_count,
        "risk_review_count": risk_review_count,
        "safety_breach_count": safety_breach_count,
        "total_gross_expected_funding_pnl_usd": total_gross,
        "total_cost_usd": total_cost,
        "total_net_expected_pnl_usd": total_net,
        "status_counts": status_counts,
        "symbol_counts": symbol_counts,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
        "attributions": attributions,
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

    return f"""# DeltaGrid Mission 40 Shadow Observation PnL Attribution Report

Report label: {summary['report_label']}
Attribution label: {summary['attribution_label']}
Created at: {summary['created_at']}
Source snapshot label: {summary['source_snapshot_label']}

## Attribution Summary

Observation count: {summary['observation_count']}
Positive count: {summary['positive_count']}
Marginal count: {summary['marginal_count']}
Negative count: {summary['negative_count']}
Risk review count: {summary['risk_review_count']}
Safety breach count: {summary['safety_breach_count']}

Total gross expected funding PnL USD: {summary['total_gross_expected_funding_pnl_usd']}
Total cost USD: {summary['total_cost_usd']}
Total net expected PnL USD: {summary['total_net_expected_pnl_usd']}

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
            INSERT OR REPLACE INTO shadow_observation_pnl_attribution_reports (
                report_label,
                created_at,
                source_snapshot_label,
                attribution_label,
                observation_count,
                positive_count,
                marginal_count,
                negative_count,
                risk_review_count,
                safety_breach_count,
                total_gross_expected_funding_pnl_usd,
                total_cost_usd,
                total_net_expected_pnl_usd,
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
                summary["source_snapshot_label"],
                summary["attribution_label"],
                summary["observation_count"],
                summary["positive_count"],
                summary["marginal_count"],
                summary["negative_count"],
                summary["risk_review_count"],
                summary["safety_breach_count"],
                str(summary["total_gross_expected_funding_pnl_usd"]),
                str(summary["total_cost_usd"]),
                str(summary["total_net_expected_pnl_usd"]),
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def run_shadow_observation_pnl_attribution(
    db_path: str | Path = "offchain/deltagrid.db",
    attribution_label: str | None = None,
    report_label: str | None = None,
    snapshot_label: str | None = None,
    gate_label: str | None = None,
    fee_bps: float = 4.0,
    min_edge_to_cost_ratio: float = 1.2,
) -> dict[str, Any]:
    db = Path(db_path)
    label = attribution_label or new_attribution_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    if fee_bps < 0:
        raise ValueError("fee_bps must be greater than or equal to 0")

    if min_edge_to_cost_ratio < 0:
        raise ValueError("min_edge_to_cost_ratio must be greater than or equal to 0")

    if not db.exists():
        summary = {
            "report_label": report,
            "attribution_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": False,
            "tables_present": False,
            "source_snapshot_label": snapshot_label,
            "observation_count": 0,
            "positive_count": 0,
            "marginal_count": 0,
            "negative_count": 0,
            "risk_review_count": 0,
            "safety_breach_count": 0,
            "total_gross_expected_funding_pnl_usd": 0.0,
            "total_cost_usd": 0.0,
            "total_net_expected_pnl_usd": 0.0,
            "status_counts": {},
            "symbol_counts": {},
            "global_verdict": NO_LIFECYCLE_HISTORY_VERDICT,
            "recommended_action": "RUN_MISSION_39_LIFECYCLE_MANAGER",
            "attributions": [],
        }
        summary["markdown_report"] = build_markdown_report(summary)
        return summary

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        if not table_exists(conn, LIFECYCLE_SNAPSHOTS_TABLE):
            summary = {
                "report_label": report,
                "attribution_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "tables_present": False,
                "missing_tables": [LIFECYCLE_SNAPSHOTS_TABLE],
                "source_snapshot_label": snapshot_label,
                "observation_count": 0,
                "positive_count": 0,
                "marginal_count": 0,
                "negative_count": 0,
                "risk_review_count": 0,
                "safety_breach_count": 0,
                "total_gross_expected_funding_pnl_usd": 0.0,
                "total_cost_usd": 0.0,
                "total_net_expected_pnl_usd": 0.0,
                "status_counts": {},
                "symbol_counts": {},
                "global_verdict": MISSING_LIFECYCLE_TABLE_VERDICT,
                "recommended_action": "RUN_MISSION_39_LIFECYCLE_MANAGER",
                "attributions": [],
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        resolved_snapshot_label, rows = load_lifecycle_snapshots(
            conn=conn,
            snapshot_label=snapshot_label,
            gate_label=gate_label,
        )

    attributions = [
        evaluate_single_snapshot(
            row=row,
            attribution_label=label,
            created_at=created_at,
            fee_bps=fee_bps,
            min_edge_to_cost_ratio=min_edge_to_cost_ratio,
        )
        for row in rows
    ]

    persist_attributions(db, attributions)

    summary = summarize_attributions(
        db_path=db,
        attribution_label=label,
        report_label=report,
        created_at=created_at,
        source_snapshot_label=resolved_snapshot_label,
        attributions=attributions,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_report(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid shadow observation PnL attribution."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--attribution-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--snapshot-label", default=None)
    parser.add_argument("--gate-label", default=None)
    parser.add_argument("--fee-bps", type=float, default=4.0)
    parser.add_argument("--min-edge-to-cost-ratio", type=float, default=1.2)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_shadow_observation_pnl_attribution(
        db_path=args.db,
        attribution_label=args.attribution_label,
        report_label=args.report_label,
        snapshot_label=args.snapshot_label,
        gate_label=args.gate_label,
        fee_bps=args.fee_bps,
        min_edge_to_cost_ratio=args.min_edge_to_cost_ratio,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

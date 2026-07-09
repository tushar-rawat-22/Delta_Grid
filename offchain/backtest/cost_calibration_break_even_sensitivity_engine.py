"""
Mission 52: Cost Calibration and Break-Even Sensitivity Engine.

This module stress-tests funding/basis alpha candidates across execution
cost assumptions and holding-duration assumptions.

It is a shadow-only research calibration layer, not an execution layer.

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
import math
import sqlite3
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CANDIDATES_TABLE = "funding_basis_alpha_candidates"
SCANNER_REPORTS_TABLE = "funding_basis_alpha_scanner_reports"

SCENARIOS_TABLE = "cost_calibration_break_even_scenarios"
REPORTS_TABLE = "cost_calibration_break_even_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

NO_SCANNER_HISTORY_VERDICT = "COST_CALIBRATION_NO_SCANNER_HISTORY"
MISSING_SCANNER_TABLE_VERDICT = "COST_CALIBRATION_SCANNER_TABLE_MISSING"
NO_MATCHING_CANDIDATES_VERDICT = "COST_CALIBRATION_NO_MATCHING_CANDIDATES"
SAFETY_BREACH_VERDICT = "COST_CALIBRATION_SAFETY_BREACH_BLOCKED"
POSITIVE_SCENARIOS_VERDICT = "COST_CALIBRATION_POSITIVE_SCENARIOS_FOUND_SHADOW_ONLY"
NO_POSITIVE_SCENARIOS_VERDICT = "COST_CALIBRATION_NO_POSITIVE_SCENARIOS_SHADOW_ONLY"

RECOMMEND_RUN_SCANNER = "RUN_MISSION_51_ALPHA_SCANNER_FIRST"
RECOMMEND_REVIEW_SAFETY = "STOP_AND_REVIEW_COST_CALIBRATION_SAFETY_STATE"
RECOMMEND_SHADOW_ONLY_LOW_COST_RESEARCH = "USE_LOW_COST_LONGER_HORIZON_SCENARIOS_FOR_SHADOW_RESEARCH_ONLY"
RECOMMEND_CONTINUE_DATA_COLLECTION = "CONTINUE_DATA_COLLECTION_AND_REJECT_LIVE_TRADING"

SCENARIO_POSITIVE = "SCENARIO_POSITIVE_AFTER_COST"
SCENARIO_NEGATIVE = "SCENARIO_NEGATIVE_AFTER_COST"
SCENARIO_REJECT_NEGATIVE_AVERAGE = "SCENARIO_REJECT_NEGATIVE_AVERAGE_FUNDING"
SCENARIO_SAFETY_BLOCKED = "SCENARIO_SAFETY_BLOCKED"

SYMBOL_POSSIBLE = "CALIBRATION_POSSIBLE_WITH_LOWER_COST_OR_LONGER_HOLD"
SYMBOL_NOT_POSITIVE = "CALIBRATION_NOT_POSITIVE_WITH_CURRENT_GRID"
SYMBOL_REJECT_NEGATIVE_AVERAGE = "CALIBRATION_REJECT_NEGATIVE_AVERAGE_FUNDING"
SYMBOL_REJECT_SAFETY = "CALIBRATION_REJECT_SAFETY_BREACH"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_calibration_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission52-cost-calibration-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission52-report-{stamp}-{uuid.uuid4().hex[:8]}"


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


def parse_float_grid(value: str | list[float] | tuple[float, ...] | None, default: list[float]) -> list[float]:
    if value is None:
        return list(default)

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    output: list[float] = []

    for item in raw_items:
        number = safe_float(str(item).strip())

        if number < 0:
            raise ValueError("Cost grid values must be non-negative")

        if number not in output:
            output.append(number)

    if not output:
        raise ValueError("At least one cost grid value is required")

    return sorted(output)


def parse_int_grid(value: str | list[int] | tuple[int, ...] | None, default: list[int]) -> list[int]:
    if value is None:
        return list(default)

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    output: list[int] = []

    for item in raw_items:
        number = safe_int(str(item).strip())

        if number <= 0:
            raise ValueError("Holding-events grid values must be greater than 0")

        if number not in output:
            output.append(number)

    if not output:
        raise ValueError("At least one holding-events grid value is required")

    return sorted(output)


def parse_symbols(value: str | list[str] | tuple[str, ...] | None) -> list[str] | None:
    if value is None:
        return None

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    symbols: list[str] = []

    for item in raw_items:
        symbol = str(item).strip().upper()

        if not symbol:
            continue

        if not symbol.endswith("USDT"):
            raise ValueError(f"Only USDT perpetual symbols are supported for Mission 52: {symbol}")

        if not symbol.replace("_", "").isalnum():
            raise ValueError(f"Invalid symbol: {symbol}")

        if symbol not in symbols:
            symbols.append(symbol)

    if not symbols:
        raise ValueError("At least one symbol is required when symbols are supplied")

    return symbols


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
            CREATE TABLE IF NOT EXISTS cost_calibration_break_even_scenarios (
                scenario_id TEXT PRIMARY KEY,
                calibration_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_scanner_label TEXT,
                source_candidate_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                fee_bps_per_side TEXT NOT NULL,
                slippage_bps TEXT NOT NULL,
                holding_funding_events INTEGER NOT NULL,
                average_funding_rate_bps TEXT NOT NULL,
                latest_spread_bps TEXT NOT NULL,
                gross_horizon_carry_bps TEXT NOT NULL,
                estimated_cost_bps TEXT NOT NULL,
                net_carry_bps TEXT NOT NULL,
                break_even_funding_bps TEXT NOT NULL,
                funding_gap_to_break_even_bps TEXT NOT NULL,
                scenario_status TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cost_calibration_break_even_reports (
                report_label TEXT PRIMARY KEY,
                calibration_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_scanner_label TEXT,
                candidate_count INTEGER NOT NULL,
                scenario_count INTEGER NOT NULL,
                positive_scenario_count INTEGER NOT NULL,
                negative_scenario_count INTEGER NOT NULL,
                viable_symbol_count INTEGER NOT NULL,
                rejected_symbol_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                top_symbol TEXT,
                top_best_net_carry_bps TEXT NOT NULL,
                average_best_net_carry_bps TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def latest_scanner_label(conn: sqlite3.Connection) -> str | None:
    if table_exists(conn, SCANNER_REPORTS_TABLE):
        row = conn.execute(
            """
            SELECT scanner_label
            FROM funding_basis_alpha_scanner_reports
            ORDER BY created_at DESC, report_label DESC
            LIMIT 1
            """
        ).fetchone()

        if row is not None:
            return str(row["scanner_label"])

    if table_exists(conn, CANDIDATES_TABLE):
        row = conn.execute(
            """
            SELECT scanner_label
            FROM funding_basis_alpha_candidates
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()

        if row is not None:
            return str(row["scanner_label"])

    return None


def load_candidates(
    conn: sqlite3.Connection,
    scanner_label: str,
    symbols: list[str] | None,
) -> list[sqlite3.Row]:
    params: list[Any] = [scanner_label]
    symbol_clause = ""

    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        symbol_clause = f" AND symbol IN ({placeholders})"
        params.extend(symbols)

    query = f"""
        SELECT *
        FROM funding_basis_alpha_candidates
        WHERE scanner_label = ?
        {symbol_clause}
        ORDER BY candidate_rank ASC, alpha_score DESC
    """

    return conn.execute(query, params).fetchall()


def candidate_has_safety_breach(row: sqlite3.Row) -> bool:
    return (
        row["live_trading"] != LIVE_TRADING_STATUS
        or int(row["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or row["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS
        or str(row["scanner_status"]) == "REJECT_SAFETY_BREACH"
    )


def scenario_id(
    calibration_label: str,
    symbol: str,
    fee_bps_per_side: float,
    slippage_bps: float,
    holding_funding_events: int,
) -> str:
    fee = str(fee_bps_per_side).replace(".", "p")
    slip = str(slippage_bps).replace(".", "p")
    return f"{calibration_label}-{symbol}-fee{fee}-slip{slip}-hold{holding_funding_events}"


def compute_scenario(
    calibration_label: str,
    created_at: str,
    source_scanner_label: str,
    candidate: sqlite3.Row,
    fee_bps_per_side: float,
    slippage_bps: float,
    holding_funding_events: int,
) -> dict[str, Any]:
    symbol = str(candidate["symbol"])
    average_funding_rate_bps = safe_float(candidate["average_funding_rate_bps"])
    latest_spread_bps = safe_float(candidate["latest_spread_bps"])
    safety_breach = candidate_has_safety_breach(candidate)

    estimated_cost_bps = round((fee_bps_per_side * 2.0) + slippage_bps + max(latest_spread_bps, 0.0), 8)
    gross_horizon_carry_bps = round(average_funding_rate_bps * holding_funding_events, 8)
    net_carry_bps = round(gross_horizon_carry_bps - estimated_cost_bps, 8)
    break_even_funding_bps = round(estimated_cost_bps / holding_funding_events, 8)
    funding_gap = round(average_funding_rate_bps - break_even_funding_bps, 8)

    if safety_breach:
        scenario_status = SCENARIO_SAFETY_BLOCKED
    elif average_funding_rate_bps <= 0:
        scenario_status = SCENARIO_REJECT_NEGATIVE_AVERAGE
    elif net_carry_bps >= 0:
        scenario_status = SCENARIO_POSITIVE
    else:
        scenario_status = SCENARIO_NEGATIVE

    return {
        "scenario_id": scenario_id(
            calibration_label=calibration_label,
            symbol=symbol,
            fee_bps_per_side=fee_bps_per_side,
            slippage_bps=slippage_bps,
            holding_funding_events=holding_funding_events,
        ),
        "calibration_label": calibration_label,
        "created_at": created_at,
        "source_scanner_label": source_scanner_label,
        "source_candidate_id": candidate["candidate_id"],
        "symbol": symbol,
        "fee_bps_per_side": round(fee_bps_per_side, 8),
        "slippage_bps": round(slippage_bps, 8),
        "holding_funding_events": holding_funding_events,
        "average_funding_rate_bps": round(average_funding_rate_bps, 8),
        "latest_spread_bps": round(latest_spread_bps, 8),
        "gross_horizon_carry_bps": gross_horizon_carry_bps,
        "estimated_cost_bps": estimated_cost_bps,
        "net_carry_bps": net_carry_bps,
        "break_even_funding_bps": break_even_funding_bps,
        "funding_gap_to_break_even_bps": funding_gap,
        "scenario_status": scenario_status,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "source_scanner_status": candidate["scanner_status"],
            "source_alpha_score": safe_float(candidate["alpha_score"]),
            "source_positive_funding_ratio": safe_float(candidate["positive_funding_ratio"]),
            "source_cost_adjusted_carry_bps": safe_float(candidate["cost_adjusted_carry_bps"]),
            "calibration_role": "BREAK_EVEN_SENSITIVITY_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
        },
    }


def build_scenarios(
    calibration_label: str,
    created_at: str,
    source_scanner_label: str,
    candidates: list[sqlite3.Row],
    fee_grid: list[float],
    slippage_grid: list[float],
    holding_events_grid: list[int],
) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []

    for candidate in candidates:
        for fee in fee_grid:
            for slippage in slippage_grid:
                for holding_events in holding_events_grid:
                    scenarios.append(
                        compute_scenario(
                            calibration_label=calibration_label,
                            created_at=created_at,
                            source_scanner_label=source_scanner_label,
                            candidate=candidate,
                            fee_bps_per_side=fee,
                            slippage_bps=slippage,
                            holding_funding_events=holding_events,
                        )
                    )

    return scenarios


def persist_scenarios(db_path: str | Path, scenarios: list[dict[str, Any]]) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for row in scenarios:
            conn.execute(
                """
                INSERT OR REPLACE INTO cost_calibration_break_even_scenarios (
                    scenario_id,
                    calibration_label,
                    created_at,
                    source_scanner_label,
                    source_candidate_id,
                    symbol,
                    fee_bps_per_side,
                    slippage_bps,
                    holding_funding_events,
                    average_funding_rate_bps,
                    latest_spread_bps,
                    gross_horizon_carry_bps,
                    estimated_cost_bps,
                    net_carry_bps,
                    break_even_funding_bps,
                    funding_gap_to_break_even_bps,
                    scenario_status,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["scenario_id"],
                    row["calibration_label"],
                    row["created_at"],
                    row["source_scanner_label"],
                    row["source_candidate_id"],
                    row["symbol"],
                    str(row["fee_bps_per_side"]),
                    str(row["slippage_bps"]),
                    row["holding_funding_events"],
                    str(row["average_funding_rate_bps"]),
                    str(row["latest_spread_bps"]),
                    str(row["gross_horizon_carry_bps"]),
                    str(row["estimated_cost_bps"]),
                    str(row["net_carry_bps"]),
                    str(row["break_even_funding_bps"]),
                    str(row["funding_gap_to_break_even_bps"]),
                    row["scenario_status"],
                    row["live_trading"],
                    row["live_order_sent"],
                    row["capital_deployment"],
                    json.dumps(row["metadata"], sort_keys=True),
                ),
            )

        conn.commit()


def summarize_symbol(symbol: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    positive_rows = [row for row in rows if row["scenario_status"] == SCENARIO_POSITIVE]
    safety_rows = [row for row in rows if row["scenario_status"] == SCENARIO_SAFETY_BLOCKED]
    negative_average_rows = [row for row in rows if row["scenario_status"] == SCENARIO_REJECT_NEGATIVE_AVERAGE]

    best_row = max(rows, key=lambda item: item["net_carry_bps"]) if rows else None
    best_positive = max(positive_rows, key=lambda item: item["net_carry_bps"]) if positive_rows else None

    minimum_positive_holding_events = None

    if positive_rows:
        minimum_positive_holding_events = min(row["holding_funding_events"] for row in positive_rows)

    if safety_rows:
        calibration_status = SYMBOL_REJECT_SAFETY
    elif positive_rows:
        calibration_status = SYMBOL_POSSIBLE
    elif negative_average_rows and len(negative_average_rows) == len(rows):
        calibration_status = SYMBOL_REJECT_NEGATIVE_AVERAGE
    else:
        calibration_status = SYMBOL_NOT_POSITIVE

    return {
        "symbol": symbol,
        "scenario_count": len(rows),
        "positive_scenario_count": len(positive_rows),
        "negative_scenario_count": len(rows) - len(positive_rows),
        "minimum_positive_holding_events": minimum_positive_holding_events,
        "best_net_carry_bps": round(best_row["net_carry_bps"], 8) if best_row else 0.0,
        "best_fee_bps_per_side": best_row["fee_bps_per_side"] if best_row else None,
        "best_slippage_bps": best_row["slippage_bps"] if best_row else None,
        "best_holding_funding_events": best_row["holding_funding_events"] if best_row else None,
        "best_break_even_funding_bps": best_row["break_even_funding_bps"] if best_row else None,
        "best_positive_net_carry_bps": round(best_positive["net_carry_bps"], 8) if best_positive else 0.0,
        "calibration_status": calibration_status,
    }


def summarize_calibration(
    db_path: str | Path,
    calibration_label: str,
    report_label: str,
    created_at: str,
    source_scanner_label: str | None,
    candidates: list[sqlite3.Row],
    scenarios: list[dict[str, Any]],
    fee_grid: list[float],
    slippage_grid: list[float],
    holding_events_grid: list[int],
) -> dict[str, Any]:
    symbol_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in scenarios:
        symbol_groups[row["symbol"]].append(row)

    symbol_summaries = [
        summarize_symbol(symbol=symbol, rows=rows)
        for symbol, rows in symbol_groups.items()
    ]
    symbol_summaries.sort(
        key=lambda item: (
            item["positive_scenario_count"],
            item["best_net_carry_bps"],
        ),
        reverse=True,
    )

    positive_scenario_count = sum(1 for row in scenarios if row["scenario_status"] == SCENARIO_POSITIVE)
    safety_breach_count = sum(1 for row in scenarios if row["scenario_status"] == SCENARIO_SAFETY_BLOCKED)

    viable_symbol_count = sum(1 for item in symbol_summaries if item["calibration_status"] == SYMBOL_POSSIBLE)
    rejected_symbol_count = sum(
        1
        for item in symbol_summaries
        if item["calibration_status"] in {SYMBOL_REJECT_NEGATIVE_AVERAGE, SYMBOL_REJECT_SAFETY}
    )

    top_symbol = symbol_summaries[0]["symbol"] if symbol_summaries else None
    top_best_net = symbol_summaries[0]["best_net_carry_bps"] if symbol_summaries else 0.0

    average_best_net = 0.0

    if symbol_summaries:
        average_best_net = round(
            sum(safe_float(item["best_net_carry_bps"]) for item in symbol_summaries) / len(symbol_summaries),
            8,
        )

    if safety_breach_count > 0:
        global_verdict = SAFETY_BREACH_VERDICT
        recommended_action = RECOMMEND_REVIEW_SAFETY
    elif not candidates:
        global_verdict = NO_MATCHING_CANDIDATES_VERDICT
        recommended_action = RECOMMEND_RUN_SCANNER
    elif positive_scenario_count > 0:
        global_verdict = POSITIVE_SCENARIOS_VERDICT
        recommended_action = RECOMMEND_SHADOW_ONLY_LOW_COST_RESEARCH
    else:
        global_verdict = NO_POSITIVE_SCENARIOS_VERDICT
        recommended_action = RECOMMEND_CONTINUE_DATA_COLLECTION

    status_counts = dict(Counter(row["scenario_status"] for row in scenarios))

    return {
        "report_label": report_label,
        "calibration_label": calibration_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_scanner_label": source_scanner_label,
        "candidate_count": len(candidates),
        "scenario_count": len(scenarios),
        "positive_scenario_count": positive_scenario_count,
        "negative_scenario_count": len(scenarios) - positive_scenario_count,
        "viable_symbol_count": viable_symbol_count,
        "rejected_symbol_count": rejected_symbol_count,
        "safety_breach_count": safety_breach_count,
        "top_symbol": top_symbol,
        "top_best_net_carry_bps": round(top_best_net, 8),
        "average_best_net_carry_bps": average_best_net,
        "fee_bps_grid": fee_grid,
        "slippage_bps_grid": slippage_grid,
        "holding_events_grid": holding_events_grid,
        "scenario_status_counts": status_counts,
        "symbol_summaries": symbol_summaries,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    symbol_lines = []

    for item in summary["symbol_summaries"]:
        symbol_lines.append(
            "- "
            + item["symbol"]
            + ": "
            + f"status={item['calibration_status']}, "
            + f"positive_scenarios={item['positive_scenario_count']}, "
            + f"best_net_carry_bps={item['best_net_carry_bps']}, "
            + f"best_fee_bps_per_side={item['best_fee_bps_per_side']}, "
            + f"best_slippage_bps={item['best_slippage_bps']}, "
            + f"best_holding_events={item['best_holding_funding_events']}, "
            + f"minimum_positive_holding_events={item['minimum_positive_holding_events']}"
        )

    symbol_markdown = "\n".join(symbol_lines) or "- None"

    return f"""# DeltaGrid Mission 52 Cost Calibration and Break-Even Sensitivity Report

Report label: {summary['report_label']}
Calibration label: {summary['calibration_label']}
Created at: {summary['created_at']}
Source scanner label: {summary['source_scanner_label']}

## Calibration Summary

Candidate count: {summary['candidate_count']}
Scenario count: {summary['scenario_count']}
Positive scenario count: {summary['positive_scenario_count']}
Negative scenario count: {summary['negative_scenario_count']}

Viable symbol count: {summary['viable_symbol_count']}
Rejected symbol count: {summary['rejected_symbol_count']}
Safety breach count: {summary['safety_breach_count']}

Top symbol: {summary['top_symbol']}
Top best net carry bps: {summary['top_best_net_carry_bps']}
Average best net carry bps: {summary['average_best_net_carry_bps']}

Fee bps grid: {summary['fee_bps_grid']}
Slippage bps grid: {summary['slippage_bps_grid']}
Holding events grid: {summary['holding_events_grid']}

## Symbol Break-Even Summary

{symbol_markdown}

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
No paid APIs were used.
"""


def persist_report(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO cost_calibration_break_even_reports (
                report_label,
                calibration_label,
                created_at,
                source_scanner_label,
                candidate_count,
                scenario_count,
                positive_scenario_count,
                negative_scenario_count,
                viable_symbol_count,
                rejected_symbol_count,
                safety_breach_count,
                top_symbol,
                top_best_net_carry_bps,
                average_best_net_carry_bps,
                global_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["calibration_label"],
                summary["created_at"],
                summary["source_scanner_label"],
                summary["candidate_count"],
                summary["scenario_count"],
                summary["positive_scenario_count"],
                summary["negative_scenario_count"],
                summary["viable_symbol_count"],
                summary["rejected_symbol_count"],
                summary["safety_breach_count"],
                summary["top_symbol"],
                str(summary["top_best_net_carry_bps"]),
                str(summary["average_best_net_carry_bps"]),
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def run_cost_calibration_break_even_sensitivity_engine(
    db_path: str | Path = "offchain/deltagrid.db",
    calibration_label: str | None = None,
    report_label: str | None = None,
    scanner_label: str | None = None,
    symbols: str | list[str] | tuple[str, ...] | None = None,
    fee_bps_grid: str | list[float] | tuple[float, ...] | None = None,
    slippage_bps_grid: str | list[float] | tuple[float, ...] | None = None,
    holding_events_grid: str | list[int] | tuple[int, ...] | None = None,
) -> dict[str, Any]:
    db = Path(db_path)
    label = calibration_label or new_calibration_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    fees = parse_float_grid(fee_bps_grid, default=[0.1, 1.0, 2.0, 4.0])
    slippages = parse_float_grid(slippage_bps_grid, default=[0.1, 1.0, 3.0])
    holding_events = parse_int_grid(holding_events_grid, default=[1, 3, 9, 27, 81])
    requested_symbols = parse_symbols(symbols)

    if not db.exists():
        summary = {
            "report_label": report,
            "calibration_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": False,
            "source_scanner_label": scanner_label,
            "candidate_count": 0,
            "scenario_count": 0,
            "positive_scenario_count": 0,
            "negative_scenario_count": 0,
            "viable_symbol_count": 0,
            "rejected_symbol_count": 0,
            "safety_breach_count": 0,
            "top_symbol": None,
            "top_best_net_carry_bps": 0.0,
            "average_best_net_carry_bps": 0.0,
            "fee_bps_grid": fees,
            "slippage_bps_grid": slippages,
            "holding_events_grid": holding_events,
            "scenario_status_counts": {},
            "symbol_summaries": [],
            "global_verdict": NO_SCANNER_HISTORY_VERDICT,
            "recommended_action": RECOMMEND_RUN_SCANNER,
        }
        summary["markdown_report"] = build_markdown_report(summary)
        return summary

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        if not table_exists(conn, CANDIDATES_TABLE):
            summary = {
                "report_label": report,
                "calibration_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "missing_tables": [CANDIDATES_TABLE],
                "source_scanner_label": scanner_label,
                "candidate_count": 0,
                "scenario_count": 0,
                "positive_scenario_count": 0,
                "negative_scenario_count": 0,
                "viable_symbol_count": 0,
                "rejected_symbol_count": 0,
                "safety_breach_count": 0,
                "top_symbol": None,
                "top_best_net_carry_bps": 0.0,
                "average_best_net_carry_bps": 0.0,
                "fee_bps_grid": fees,
                "slippage_bps_grid": slippages,
                "holding_events_grid": holding_events,
                "scenario_status_counts": {},
                "symbol_summaries": [],
                "global_verdict": MISSING_SCANNER_TABLE_VERDICT,
                "recommended_action": RECOMMEND_RUN_SCANNER,
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        resolved_scanner_label = scanner_label or latest_scanner_label(conn)

        if resolved_scanner_label is None:
            summary = {
                "report_label": report,
                "calibration_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "source_scanner_label": None,
                "candidate_count": 0,
                "scenario_count": 0,
                "positive_scenario_count": 0,
                "negative_scenario_count": 0,
                "viable_symbol_count": 0,
                "rejected_symbol_count": 0,
                "safety_breach_count": 0,
                "top_symbol": None,
                "top_best_net_carry_bps": 0.0,
                "average_best_net_carry_bps": 0.0,
                "fee_bps_grid": fees,
                "slippage_bps_grid": slippages,
                "holding_events_grid": holding_events,
                "scenario_status_counts": {},
                "symbol_summaries": [],
                "global_verdict": NO_MATCHING_CANDIDATES_VERDICT,
                "recommended_action": RECOMMEND_RUN_SCANNER,
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        candidates = load_candidates(
            conn=conn,
            scanner_label=resolved_scanner_label,
            symbols=requested_symbols,
        )

    scenarios = build_scenarios(
        calibration_label=label,
        created_at=created_at,
        source_scanner_label=resolved_scanner_label,
        candidates=candidates,
        fee_grid=fees,
        slippage_grid=slippages,
        holding_events_grid=holding_events,
    )

    persist_scenarios(db, scenarios)

    summary = summarize_calibration(
        db_path=db,
        calibration_label=label,
        report_label=report,
        created_at=created_at,
        source_scanner_label=resolved_scanner_label,
        candidates=candidates,
        scenarios=scenarios,
        fee_grid=fees,
        slippage_grid=slippages,
        holding_events_grid=holding_events,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_report(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid cost calibration and break-even sensitivity engine."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--calibration-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--scanner-label", default=None)
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--fee-bps-grid", default="0.1,1.0,2.0,4.0")
    parser.add_argument("--slippage-bps-grid", default="0.1,1.0,3.0")
    parser.add_argument("--holding-events-grid", default="1,3,9,27,81")
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_cost_calibration_break_even_sensitivity_engine(
        db_path=args.db,
        calibration_label=args.calibration_label,
        report_label=args.report_label,
        scanner_label=args.scanner_label,
        symbols=args.symbols,
        fee_bps_grid=args.fee_bps_grid,
        slippage_bps_grid=args.slippage_bps_grid,
        holding_events_grid=args.holding_events_grid,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

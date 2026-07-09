"""
Mission 53: Calibrated Shadow Observation Planner.

This module converts positive cost-calibrated scenarios into shadow-only
observation plans.

It is a planning layer, not an execution layer.

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


SOURCE_SCENARIOS_TABLE = "cost_calibration_break_even_scenarios"
SOURCE_REPORTS_TABLE = "cost_calibration_break_even_reports"

PLANS_TABLE = "calibrated_shadow_observation_plans"
REPORTS_TABLE = "calibrated_shadow_observation_plan_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

SCENARIO_POSITIVE = "SCENARIO_POSITIVE_AFTER_COST"
SCENARIO_SAFETY_BLOCKED = "SCENARIO_SAFETY_BLOCKED"

PLAN_STATUS_READY = "PLANNED_SHADOW_OBSERVATION_READY"
PLAN_STATUS_BLOCKED = "PLANNED_SHADOW_OBSERVATION_BLOCKED"

NO_CALIBRATION_HISTORY_VERDICT = "SHADOW_PLAN_NO_CALIBRATION_HISTORY"
MISSING_CALIBRATION_TABLE_VERDICT = "SHADOW_PLAN_CALIBRATION_TABLE_MISSING"
NO_MATCHING_SCENARIOS_VERDICT = "SHADOW_PLAN_NO_MATCHING_SCENARIOS"
NO_VIABLE_SCENARIOS_VERDICT = "SHADOW_PLAN_NO_VIABLE_SCENARIOS"
SAFETY_BREACH_VERDICT = "SHADOW_PLAN_SAFETY_BREACH_BLOCKED"
READY_VERDICT = "SHADOW_PLAN_READY_SHADOW_ONLY"

RECOMMEND_RUN_CALIBRATION = "RUN_MISSION_52_COST_CALIBRATION_FIRST"
RECOMMEND_CONTINUE_DATA_COLLECTION = "CONTINUE_DATA_COLLECTION_AND_DO_NOT_PLAN_OBSERVATIONS"
RECOMMEND_REVIEW_SAFETY = "STOP_AND_REVIEW_SHADOW_PLAN_SAFETY_STATE"
RECOMMEND_CREATE_SHADOW_LEDGER_ENTRIES = "CREATE_SHADOW_LEDGER_ENTRIES_FROM_PLANS_ONLY"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_plan_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission53-shadow-plan-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission53-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
            raise ValueError(f"Only USDT perpetual symbols are supported for Mission 53: {symbol}")

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
            CREATE TABLE IF NOT EXISTS calibrated_shadow_observation_plans (
                plan_id TEXT PRIMARY KEY,
                plan_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_calibration_label TEXT NOT NULL,
                source_scenario_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                observation_priority INTEGER NOT NULL,
                plan_status TEXT NOT NULL,
                planned_notional_usd TEXT NOT NULL,
                holding_funding_events INTEGER NOT NULL,
                fee_bps_per_side TEXT NOT NULL,
                slippage_bps TEXT NOT NULL,
                average_funding_rate_bps TEXT NOT NULL,
                latest_spread_bps TEXT NOT NULL,
                gross_horizon_carry_bps TEXT NOT NULL,
                estimated_cost_bps TEXT NOT NULL,
                net_carry_bps TEXT NOT NULL,
                break_even_funding_bps TEXT NOT NULL,
                funding_gap_to_break_even_bps TEXT NOT NULL,
                planning_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS calibrated_shadow_observation_plan_reports (
                report_label TEXT PRIMARY KEY,
                plan_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_calibration_label TEXT,
                requested_symbol_count INTEGER NOT NULL,
                source_scenario_count INTEGER NOT NULL,
                positive_source_scenario_count INTEGER NOT NULL,
                plan_count INTEGER NOT NULL,
                ready_plan_count INTEGER NOT NULL,
                blocked_plan_count INTEGER NOT NULL,
                excluded_symbol_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                top_symbol TEXT,
                top_net_carry_bps TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def latest_calibration_label(conn: sqlite3.Connection) -> str | None:
    if table_exists(conn, SOURCE_REPORTS_TABLE):
        row = conn.execute(
            """
            SELECT calibration_label
            FROM cost_calibration_break_even_reports
            ORDER BY created_at DESC, report_label DESC
            LIMIT 1
            """
        ).fetchone()

        if row is not None:
            return str(row["calibration_label"])

    if table_exists(conn, SOURCE_SCENARIOS_TABLE):
        row = conn.execute(
            """
            SELECT calibration_label
            FROM cost_calibration_break_even_scenarios
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()

        if row is not None:
            return str(row["calibration_label"])

    return None


def load_source_scenarios(
    conn: sqlite3.Connection,
    calibration_label: str,
    symbols: list[str] | None,
) -> list[sqlite3.Row]:
    params: list[Any] = [calibration_label]
    symbol_clause = ""

    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        symbol_clause = f" AND symbol IN ({placeholders})"
        params.extend(symbols)

    query = f"""
        SELECT *
        FROM cost_calibration_break_even_scenarios
        WHERE calibration_label = ?
        {symbol_clause}
        ORDER BY symbol ASC, net_carry_bps DESC
    """

    return conn.execute(query, params).fetchall()


def scenario_has_safety_breach(row: sqlite3.Row) -> bool:
    return (
        row["live_trading"] != LIVE_TRADING_STATUS
        or int(row["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or row["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS
        or row["scenario_status"] == SCENARIO_SAFETY_BLOCKED
    )


def choose_best_positive_scenarios(
    scenarios: list[sqlite3.Row],
    min_net_carry_bps: float,
) -> list[sqlite3.Row]:
    best_by_symbol: dict[str, sqlite3.Row] = {}

    for row in scenarios:
        if row["scenario_status"] != SCENARIO_POSITIVE:
            continue

        if safe_float(row["net_carry_bps"]) < min_net_carry_bps:
            continue

        symbol = str(row["symbol"])

        current = best_by_symbol.get(symbol)

        if current is None:
            best_by_symbol[symbol] = row
            continue

        if safe_float(row["net_carry_bps"]) > safe_float(current["net_carry_bps"]):
            best_by_symbol[symbol] = row

    return sorted(
        best_by_symbol.values(),
        key=lambda item: safe_float(item["net_carry_bps"]),
        reverse=True,
    )


def build_plan_from_scenario(
    plan_label: str,
    created_at: str,
    scenario: sqlite3.Row,
    observation_priority: int,
    planned_notional_usd: float,
) -> dict[str, Any]:
    safety_breach = scenario_has_safety_breach(scenario)

    plan_status = PLAN_STATUS_BLOCKED if safety_breach else PLAN_STATUS_READY

    if safety_breach:
        planning_reason = "Source scenario has safety breach; observation plan blocked."
    else:
        planning_reason = "Best positive calibrated scenario selected for shadow observation planning."

    return {
        "plan_id": f"{plan_label}-{scenario['symbol']}",
        "plan_label": plan_label,
        "created_at": created_at,
        "source_calibration_label": scenario["calibration_label"],
        "source_scenario_id": scenario["scenario_id"],
        "symbol": scenario["symbol"],
        "observation_priority": observation_priority,
        "plan_status": plan_status,
        "planned_notional_usd": round(planned_notional_usd, 8),
        "holding_funding_events": safe_int(scenario["holding_funding_events"]),
        "fee_bps_per_side": safe_float(scenario["fee_bps_per_side"]),
        "slippage_bps": safe_float(scenario["slippage_bps"]),
        "average_funding_rate_bps": safe_float(scenario["average_funding_rate_bps"]),
        "latest_spread_bps": safe_float(scenario["latest_spread_bps"]),
        "gross_horizon_carry_bps": safe_float(scenario["gross_horizon_carry_bps"]),
        "estimated_cost_bps": safe_float(scenario["estimated_cost_bps"]),
        "net_carry_bps": safe_float(scenario["net_carry_bps"]),
        "break_even_funding_bps": safe_float(scenario["break_even_funding_bps"]),
        "funding_gap_to_break_even_bps": safe_float(scenario["funding_gap_to_break_even_bps"]),
        "planning_reason": planning_reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "planning_role": "SHADOW_OBSERVATION_PLAN_ONLY",
            "source_scenario_status": scenario["scenario_status"],
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def persist_plans(db_path: str | Path, plans: list[dict[str, Any]]) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for plan in plans:
            conn.execute(
                """
                INSERT OR REPLACE INTO calibrated_shadow_observation_plans (
                    plan_id,
                    plan_label,
                    created_at,
                    source_calibration_label,
                    source_scenario_id,
                    symbol,
                    observation_priority,
                    plan_status,
                    planned_notional_usd,
                    holding_funding_events,
                    fee_bps_per_side,
                    slippage_bps,
                    average_funding_rate_bps,
                    latest_spread_bps,
                    gross_horizon_carry_bps,
                    estimated_cost_bps,
                    net_carry_bps,
                    break_even_funding_bps,
                    funding_gap_to_break_even_bps,
                    planning_reason,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan["plan_id"],
                    plan["plan_label"],
                    plan["created_at"],
                    plan["source_calibration_label"],
                    plan["source_scenario_id"],
                    plan["symbol"],
                    plan["observation_priority"],
                    plan["plan_status"],
                    str(plan["planned_notional_usd"]),
                    plan["holding_funding_events"],
                    str(plan["fee_bps_per_side"]),
                    str(plan["slippage_bps"]),
                    str(plan["average_funding_rate_bps"]),
                    str(plan["latest_spread_bps"]),
                    str(plan["gross_horizon_carry_bps"]),
                    str(plan["estimated_cost_bps"]),
                    str(plan["net_carry_bps"]),
                    str(plan["break_even_funding_bps"]),
                    str(plan["funding_gap_to_break_even_bps"]),
                    plan["planning_reason"],
                    plan["live_trading"],
                    plan["live_order_sent"],
                    plan["capital_deployment"],
                    json.dumps(plan["metadata"], sort_keys=True),
                ),
            )

        conn.commit()


def summarize_planner(
    db_path: str | Path,
    plan_label: str,
    report_label: str,
    created_at: str,
    source_calibration_label: str | None,
    requested_symbols: list[str] | None,
    scenarios: list[sqlite3.Row],
    plans: list[dict[str, Any]],
) -> dict[str, Any]:
    positive_source_scenario_count = sum(
        1 for row in scenarios if row["scenario_status"] == SCENARIO_POSITIVE
    )

    source_symbols = sorted(set(str(row["symbol"]) for row in scenarios))
    planned_symbols = sorted(set(str(plan["symbol"]) for plan in plans))

    if requested_symbols is not None:
        excluded_symbols = sorted(set(requested_symbols) - set(planned_symbols))
    else:
        excluded_symbols = sorted(set(source_symbols) - set(planned_symbols))

    ready_plan_count = sum(1 for plan in plans if plan["plan_status"] == PLAN_STATUS_READY)
    blocked_plan_count = sum(1 for plan in plans if plan["plan_status"] == PLAN_STATUS_BLOCKED)

    safety_breach_count = sum(
        1
        for plan in plans
        if plan["live_trading"] != LIVE_TRADING_STATUS
        or int(plan["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or plan["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS
        or plan["plan_status"] == PLAN_STATUS_BLOCKED
    )

    safety_breach_count += sum(1 for row in scenarios if scenario_has_safety_breach(row))

    top_symbol = plans[0]["symbol"] if plans else None
    top_net = safe_float(plans[0]["net_carry_bps"]) if plans else 0.0

    status_counts = dict(Counter(plan["plan_status"] for plan in plans))

    if safety_breach_count > 0:
        global_verdict = SAFETY_BREACH_VERDICT
        recommended_action = RECOMMEND_REVIEW_SAFETY
    elif not scenarios:
        global_verdict = NO_MATCHING_SCENARIOS_VERDICT
        recommended_action = RECOMMEND_RUN_CALIBRATION
    elif not plans:
        global_verdict = NO_VIABLE_SCENARIOS_VERDICT
        recommended_action = RECOMMEND_CONTINUE_DATA_COLLECTION
    else:
        global_verdict = READY_VERDICT
        recommended_action = RECOMMEND_CREATE_SHADOW_LEDGER_ENTRIES

    return {
        "report_label": report_label,
        "plan_label": plan_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_calibration_label": source_calibration_label,
        "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
        "source_scenario_count": len(scenarios),
        "positive_source_scenario_count": positive_source_scenario_count,
        "plan_count": len(plans),
        "ready_plan_count": ready_plan_count,
        "blocked_plan_count": blocked_plan_count,
        "excluded_symbol_count": len(excluded_symbols),
        "excluded_symbols": excluded_symbols,
        "safety_breach_count": safety_breach_count,
        "top_symbol": top_symbol,
        "top_net_carry_bps": round(top_net, 8),
        "plan_status_counts": status_counts,
        "plans": plans,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    plan_lines = []

    for plan in summary["plans"]:
        plan_lines.append(
            "- "
            + f"priority={plan['observation_priority']} "
            + f"{plan['symbol']}: "
            + f"status={plan['plan_status']}, "
            + f"net_carry_bps={plan['net_carry_bps']}, "
            + f"holding_events={plan['holding_funding_events']}, "
            + f"fee_bps_per_side={plan['fee_bps_per_side']}, "
            + f"slippage_bps={plan['slippage_bps']}, "
            + f"planned_notional_usd={plan['planned_notional_usd']}"
        )

    plans_markdown = "\n".join(plan_lines) or "- None"

    return f"""# DeltaGrid Mission 53 Calibrated Shadow Observation Planner Report

Report label: {summary['report_label']}
Plan label: {summary['plan_label']}
Created at: {summary['created_at']}
Source calibration label: {summary['source_calibration_label']}

## Planner Summary

Source scenario count: {summary['source_scenario_count']}
Positive source scenario count: {summary['positive_source_scenario_count']}
Plan count: {summary['plan_count']}
Ready plan count: {summary['ready_plan_count']}
Blocked plan count: {summary['blocked_plan_count']}
Excluded symbol count: {summary['excluded_symbol_count']}
Excluded symbols: {summary['excluded_symbols']}
Safety breach count: {summary['safety_breach_count']}

Top symbol: {summary['top_symbol']}
Top net carry bps: {summary['top_net_carry_bps']}

## Planned Shadow Observations

{plans_markdown}

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
            INSERT OR REPLACE INTO calibrated_shadow_observation_plan_reports (
                report_label,
                plan_label,
                created_at,
                source_calibration_label,
                requested_symbol_count,
                source_scenario_count,
                positive_source_scenario_count,
                plan_count,
                ready_plan_count,
                blocked_plan_count,
                excluded_symbol_count,
                safety_breach_count,
                top_symbol,
                top_net_carry_bps,
                global_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["plan_label"],
                summary["created_at"],
                summary["source_calibration_label"],
                summary["requested_symbol_count"],
                summary["source_scenario_count"],
                summary["positive_source_scenario_count"],
                summary["plan_count"],
                summary["ready_plan_count"],
                summary["blocked_plan_count"],
                summary["excluded_symbol_count"],
                summary["safety_breach_count"],
                summary["top_symbol"],
                str(summary["top_net_carry_bps"]),
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def run_calibrated_shadow_observation_planner(
    db_path: str | Path = "offchain/deltagrid.db",
    plan_label: str | None = None,
    report_label: str | None = None,
    calibration_label: str | None = None,
    symbols: str | list[str] | tuple[str, ...] | None = None,
    max_plans: int = 2,
    min_net_carry_bps: float = 0.25,
    planned_notional_usd: float = 1000.0,
) -> dict[str, Any]:
    db = Path(db_path)
    label = plan_label or new_plan_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    if max_plans <= 0:
        raise ValueError("max_plans must be greater than 0")

    if planned_notional_usd <= 0:
        raise ValueError("planned_notional_usd must be greater than 0")

    requested_symbols = parse_symbols(symbols)

    if not db.exists():
        summary = {
            "report_label": report,
            "plan_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": False,
            "source_calibration_label": calibration_label,
            "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
            "source_scenario_count": 0,
            "positive_source_scenario_count": 0,
            "plan_count": 0,
            "ready_plan_count": 0,
            "blocked_plan_count": 0,
            "excluded_symbol_count": 0,
            "excluded_symbols": [],
            "safety_breach_count": 0,
            "top_symbol": None,
            "top_net_carry_bps": 0.0,
            "plan_status_counts": {},
            "plans": [],
            "global_verdict": NO_CALIBRATION_HISTORY_VERDICT,
            "recommended_action": RECOMMEND_RUN_CALIBRATION,
        }
        summary["markdown_report"] = build_markdown_report(summary)
        return summary

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        if not table_exists(conn, SOURCE_SCENARIOS_TABLE):
            summary = {
                "report_label": report,
                "plan_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "missing_tables": [SOURCE_SCENARIOS_TABLE],
                "source_calibration_label": calibration_label,
                "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
                "source_scenario_count": 0,
                "positive_source_scenario_count": 0,
                "plan_count": 0,
                "ready_plan_count": 0,
                "blocked_plan_count": 0,
                "excluded_symbol_count": 0,
                "excluded_symbols": [],
                "safety_breach_count": 0,
                "top_symbol": None,
                "top_net_carry_bps": 0.0,
                "plan_status_counts": {},
                "plans": [],
                "global_verdict": MISSING_CALIBRATION_TABLE_VERDICT,
                "recommended_action": RECOMMEND_RUN_CALIBRATION,
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        resolved_calibration_label = calibration_label or latest_calibration_label(conn)

        if resolved_calibration_label is None:
            summary = {
                "report_label": report,
                "plan_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "source_calibration_label": None,
                "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
                "source_scenario_count": 0,
                "positive_source_scenario_count": 0,
                "plan_count": 0,
                "ready_plan_count": 0,
                "blocked_plan_count": 0,
                "excluded_symbol_count": 0,
                "excluded_symbols": [],
                "safety_breach_count": 0,
                "top_symbol": None,
                "top_net_carry_bps": 0.0,
                "plan_status_counts": {},
                "plans": [],
                "global_verdict": NO_MATCHING_SCENARIOS_VERDICT,
                "recommended_action": RECOMMEND_RUN_CALIBRATION,
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        scenarios = load_source_scenarios(
            conn=conn,
            calibration_label=resolved_calibration_label,
            symbols=requested_symbols,
        )

    best_scenarios = choose_best_positive_scenarios(
        scenarios=scenarios,
        min_net_carry_bps=min_net_carry_bps,
    )[:max_plans]

    plans = [
        build_plan_from_scenario(
            plan_label=label,
            created_at=created_at,
            scenario=scenario,
            observation_priority=index,
            planned_notional_usd=planned_notional_usd,
        )
        for index, scenario in enumerate(best_scenarios, start=1)
    ]

    persist_plans(db, plans)

    summary = summarize_planner(
        db_path=db,
        plan_label=label,
        report_label=report,
        created_at=created_at,
        source_calibration_label=resolved_calibration_label,
        requested_symbols=requested_symbols,
        scenarios=scenarios,
        plans=plans,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_report(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid calibrated shadow observation planner."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--plan-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--calibration-label", default=None)
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--max-plans", type=int, default=2)
    parser.add_argument("--min-net-carry-bps", type=float, default=0.25)
    parser.add_argument("--planned-notional-usd", type=float, default=1000.0)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_calibrated_shadow_observation_planner(
        db_path=args.db,
        plan_label=args.plan_label,
        report_label=args.report_label,
        calibration_label=args.calibration_label,
        symbols=args.symbols,
        max_plans=args.max_plans,
        min_net_carry_bps=args.min_net_carry_bps,
        planned_notional_usd=args.planned_notional_usd,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

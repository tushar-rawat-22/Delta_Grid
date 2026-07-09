"""
Mission 64: Institutional Risk Control Layer.

This module reviews a paper sandbox session using institutional-style hard
risk controls.

It reads:
- paper_sandbox_sessions
- paper_sandbox_orders
- paper_sandbox_positions

It writes:
- institutional_risk_control_reviews
- institutional_risk_limit_checks
- institutional_risk_decision_records

It is risk governance only.

It never:
- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital
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


PAPER_SESSIONS_TABLE = "paper_sandbox_sessions"
PAPER_ORDERS_TABLE = "paper_sandbox_orders"
PAPER_POSITIONS_TABLE = "paper_sandbox_positions"

RISK_REVIEWS_TABLE = "institutional_risk_control_reviews"
RISK_LIMIT_CHECKS_TABLE = "institutional_risk_limit_checks"
RISK_DECISIONS_TABLE = "institutional_risk_decision_records"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

PAPER_SANDBOX_READY = "PAPER_SANDBOX_READY_SHADOW_ONLY"

LIMIT_PASS = "RISK_LIMIT_PASS"
LIMIT_FAIL = "RISK_LIMIT_FAIL"

RISK_DECISION_APPROVED = "INSTITUTIONAL_RISK_APPROVED_FOR_CONTROLLED_PAPER_OBSERVATION"
RISK_DECISION_BLOCK_LIMITS = "INSTITUTIONAL_RISK_BLOCKED_BY_LIMITS"
RISK_DECISION_BLOCK_SAFETY = "INSTITUTIONAL_RISK_BLOCKED_BY_SAFETY_POLICY"
RISK_DECISION_REJECT_MISSING = "INSTITUTIONAL_RISK_REJECTED_MISSING_SESSION"

RISK_READY = "INSTITUTIONAL_RISK_CONTROL_READY_SHADOW_ONLY"
RISK_BLOCKED = "INSTITUTIONAL_RISK_CONTROL_BLOCKED_SHADOW_ONLY"
RISK_MISSING = "INSTITUTIONAL_RISK_CONTROL_MISSING_EVIDENCE"

ACTION_RUN_OBSERVATION = "RUN_RISK_CONTROLLED_PAPER_OBSERVATION_CYCLE"
ACTION_REDUCE_RISK = "REDUCE_RISK_AND_RERUN_PAPER_SANDBOX"
ACTION_STOP_SAFETY = "STOP_AND_REVIEW_RISK_SAFETY_STATE"
ACTION_REFRESH_SESSION = "REFRESH_PAPER_SANDBOX_SESSION"

RISK_LEVEL_LOW = "INSTITUTIONAL_RISK_LEVEL_LOW"
RISK_LEVEL_MODERATE = "INSTITUTIONAL_RISK_LEVEL_MODERATE"
RISK_LEVEL_HIGH = "INSTITUTIONAL_RISK_LEVEL_HIGH"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_review_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission64-risk-review-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission64-risk-report-{stamp}-{uuid.uuid4().hex[:8]}"


def safe_float(value: Any) -> float:
    try:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return 0.0
        return number
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def round8(value: float) -> float:
    return round(float(value), 8)


def row_get(row: sqlite3.Row | dict[str, Any] | None, key: str, default: Any = None) -> Any:
    if row is None:
        return default

    if isinstance(row, dict):
        return row.get(key, default)

    try:
        if key in row.keys():
            return row[key]
        return default
    except (AttributeError, IndexError, KeyError):
        try:
            return row[key]
        except (IndexError, KeyError, TypeError):
            return default


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
            raise ValueError(f"Only USDT symbols are supported for Mission 64: {symbol}")

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
            CREATE TABLE IF NOT EXISTS institutional_risk_control_reviews (
                review_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_session_label TEXT NOT NULL,
                source_board_review_label TEXT,
                source_portfolio_label TEXT,
                paper_notional TEXT NOT NULL,
                limit_check_count INTEGER NOT NULL,
                pass_limit_count INTEGER NOT NULL,
                fail_limit_count INTEGER NOT NULL,
                position_count INTEGER NOT NULL,
                order_count INTEGER NOT NULL,
                filled_order_count INTEGER NOT NULL,
                blocked_order_count INTEGER NOT NULL,
                distinct_symbol_count INTEGER NOT NULL,
                distinct_strategy_count INTEGER NOT NULL,
                max_symbol_exposure_pct TEXT NOT NULL,
                max_strategy_exposure_pct TEXT NOT NULL,
                observed_max_symbol_exposure_pct TEXT NOT NULL,
                observed_max_strategy_exposure_pct TEXT NOT NULL,
                total_cost_bps TEXT NOT NULL,
                net_deployed_notional TEXT NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                institutional_risk_level TEXT NOT NULL,
                risk_decision TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                next_mission TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS institutional_risk_limit_checks (
                check_id TEXT PRIMARY KEY,
                review_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_session_label TEXT NOT NULL,
                limit_category TEXT NOT NULL,
                limit_name TEXT NOT NULL,
                limit_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                required_value TEXT NOT NULL,
                limit_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS institutional_risk_decision_records (
                decision_id TEXT PRIMARY KEY,
                review_label TEXT NOT NULL,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_session_label TEXT NOT NULL,
                risk_decision TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                approval_scope TEXT NOT NULL,
                explicit_non_approval_scope TEXT NOT NULL,
                decision_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.commit()


def safety_problem(row: sqlite3.Row | dict[str, Any] | None) -> bool:
    if row is None:
        return False

    return (
        str(row_get(row, "live_trading", LIVE_TRADING_STATUS)) != LIVE_TRADING_STATUS
        or safe_int(row_get(row, "live_order_sent", LIVE_ORDER_SENT_VALUE)) != LIVE_ORDER_SENT_VALUE
        or str(row_get(row, "capital_deployment", CAPITAL_DEPLOYMENT_STATUS)) != CAPITAL_DEPLOYMENT_STATUS
    )


def load_session(conn: sqlite3.Connection, session_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, PAPER_SESSIONS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM paper_sandbox_sessions
        WHERE session_label = ?
        """,
        (session_label,),
    ).fetchone()


def load_orders(conn: sqlite3.Connection, session_label: str, symbols: list[str] | None) -> list[sqlite3.Row]:
    if not table_exists(conn, PAPER_ORDERS_TABLE):
        return []

    params: list[Any] = [session_label]
    symbol_clause = ""

    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        symbol_clause = f" AND symbol IN ({placeholders})"
        params.extend(symbols)

    query = f"""
        SELECT *
        FROM paper_sandbox_orders
        WHERE session_label = ?
        {symbol_clause}
        ORDER BY CAST(requested_notional AS REAL) DESC
    """

    return conn.execute(query, params).fetchall()


def load_positions(conn: sqlite3.Connection, session_label: str, symbols: list[str] | None) -> list[sqlite3.Row]:
    if not table_exists(conn, PAPER_POSITIONS_TABLE):
        return []

    params: list[Any] = [session_label]
    symbol_clause = ""

    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        symbol_clause = f" AND symbol IN ({placeholders})"
        params.extend(symbols)

    query = f"""
        SELECT *
        FROM paper_sandbox_positions
        WHERE session_label = ?
        {symbol_clause}
        ORDER BY CAST(entry_notional AS REAL) DESC
    """

    return conn.execute(query, params).fetchall()


def limit_check(
    review_label: str,
    created_at: str,
    session_label: str,
    category: str,
    name: str,
    status: str,
    observed_value: Any,
    required_value: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{review_label}-{category}-{name}".replace(" ", "_"),
        "review_label": review_label,
        "created_at": created_at,
        "source_session_label": session_label,
        "limit_category": category,
        "limit_name": name,
        "limit_status": status,
        "observed_value": str(observed_value),
        "required_value": str(required_value),
        "limit_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "risk_role": "INSTITUTIONAL_RISK_LIMIT_CHECK_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def exposure_by_key(positions: list[sqlite3.Row], key: str) -> dict[str, float]:
    exposure: dict[str, float] = defaultdict(float)

    for position in positions:
        exposure[str(row_get(position, key, "UNKNOWN"))] += safe_float(row_get(position, "entry_notional", 0.0))

    return {name: round8(value) for name, value in sorted(exposure.items())}


def exposure_pct(exposure: dict[str, float], paper_notional: float) -> dict[str, float]:
    if paper_notional <= 0:
        return {name: 0.0 for name in exposure}

    return {name: round8((value / paper_notional) * 100.0) for name, value in exposure.items()}


def build_missing_checks(
    review_label: str,
    created_at: str,
    session_label: str,
) -> list[dict[str, Any]]:
    return [
        limit_check(
            review_label,
            created_at,
            session_label,
            "availability",
            "paper sandbox session exists",
            LIMIT_FAIL,
            "missing",
            "paper_sandbox_sessions record",
            "No paper sandbox session exists for this session label.",
        )
    ]


def build_limit_checks(
    review_label: str,
    created_at: str,
    session: sqlite3.Row,
    orders: list[sqlite3.Row],
    positions: list[sqlite3.Row],
    max_symbol_exposure_pct: float,
    max_strategy_exposure_pct: float,
    max_total_cost_bps: float,
    min_distinct_symbols: int,
    min_position_count: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    session_label = str(row_get(session, "session_label"))
    paper_notional = safe_float(row_get(session, "paper_notional", 0.0))
    total_fees = safe_float(row_get(session, "total_simulated_fees", 0.0))
    total_slippage = safe_float(row_get(session, "total_simulated_slippage", 0.0))
    total_cost_bps = round8(((total_fees + total_slippage) / paper_notional) * 10000.0) if paper_notional > 0 else 0.0
    net_deployed = safe_float(row_get(session, "net_paper_deployed_notional", 0.0))

    symbol_exposure_notional = exposure_by_key(positions, "symbol")
    strategy_exposure_notional = exposure_by_key(positions, "strategy_id")
    symbol_exposure_pct = exposure_pct(symbol_exposure_notional, paper_notional)
    strategy_exposure_pct = exposure_pct(strategy_exposure_notional, paper_notional)

    observed_max_symbol = round8(max(symbol_exposure_pct.values()) if symbol_exposure_pct else 0.0)
    observed_max_strategy = round8(max(strategy_exposure_pct.values()) if strategy_exposure_pct else 0.0)

    distinct_symbols = len(symbol_exposure_notional)
    distinct_strategies = len(strategy_exposure_notional)

    blocked_orders = safe_int(row_get(session, "blocked_order_count", 0))
    submitted_orders = safe_int(row_get(session, "submitted_order_count", len(orders)))
    filled_orders = safe_int(row_get(session, "filled_order_count", 0))
    position_count = len(positions)

    session_safety_count = safe_int(row_get(session, "safety_breach_count", 0))
    row_safety_count = sum(1 for row in [session, *orders, *positions] if safety_problem(row))
    total_safety_count = session_safety_count + row_safety_count

    cost_cap_notional = round8(paper_notional * (1.0 + max_total_cost_bps / 10000.0))

    checks = [
        limit_check(
            review_label,
            created_at,
            session_label,
            "safety",
            "safety invariants",
            LIMIT_PASS if total_safety_count == 0 else LIMIT_FAIL,
            total_safety_count,
            0,
            "No row may require live trading, capital deployment, or live order transmission.",
        ),
        limit_check(
            review_label,
            created_at,
            session_label,
            "session",
            "paper sandbox verdict",
            LIMIT_PASS if str(row_get(session, "global_verdict", "")) == PAPER_SANDBOX_READY else LIMIT_FAIL,
            str(row_get(session, "global_verdict", "")),
            PAPER_SANDBOX_READY,
            "Risk control can only approve a ready paper sandbox session.",
        ),
        limit_check(
            review_label,
            created_at,
            session_label,
            "execution",
            "order fill integrity",
            LIMIT_PASS if submitted_orders == filled_orders and blocked_orders == 0 else LIMIT_FAIL,
            f"submitted={submitted_orders}, filled={filled_orders}, blocked={blocked_orders}",
            "submitted == filled and blocked == 0",
            "All paper orders must be filled locally and none may be blocked.",
        ),
        limit_check(
            review_label,
            created_at,
            session_label,
            "portfolio",
            "position count",
            LIMIT_PASS if position_count >= min_position_count else LIMIT_FAIL,
            position_count,
            f">= {min_position_count}",
            "Paper session must contain enough positions for controlled observation.",
        ),
        limit_check(
            review_label,
            created_at,
            session_label,
            "cost",
            "total cost bps",
            LIMIT_PASS if total_cost_bps <= max_total_cost_bps else LIMIT_FAIL,
            total_cost_bps,
            f"<= {max_total_cost_bps}",
            "Total simulated fees plus slippage must stay inside the institutional cost cap.",
        ),
        limit_check(
            review_label,
            created_at,
            session_label,
            "cost",
            "net deployed notional",
            LIMIT_PASS if net_deployed <= cost_cap_notional else LIMIT_FAIL,
            round8(net_deployed),
            f"<= {cost_cap_notional}",
            "Net paper deployed notional cannot exceed notional plus allowed cost cap.",
        ),
        limit_check(
            review_label,
            created_at,
            session_label,
            "exposure",
            "max symbol exposure pct",
            LIMIT_PASS if observed_max_symbol <= max_symbol_exposure_pct else LIMIT_FAIL,
            observed_max_symbol,
            f"<= {max_symbol_exposure_pct}",
            "No single symbol may exceed the institutional symbol exposure cap.",
        ),
        limit_check(
            review_label,
            created_at,
            session_label,
            "exposure",
            "max strategy exposure pct",
            LIMIT_PASS if observed_max_strategy <= max_strategy_exposure_pct else LIMIT_FAIL,
            observed_max_strategy,
            f"<= {max_strategy_exposure_pct}",
            "No single strategy may exceed the institutional strategy exposure cap.",
        ),
        limit_check(
            review_label,
            created_at,
            session_label,
            "diversification",
            "distinct symbol count",
            LIMIT_PASS if distinct_symbols >= min_distinct_symbols else LIMIT_FAIL,
            distinct_symbols,
            f">= {min_distinct_symbols}",
            "Paper session must keep minimum symbol diversification.",
        ),
    ]

    metrics = {
        "paper_notional": round8(paper_notional),
        "total_fees": round8(total_fees),
        "total_slippage": round8(total_slippage),
        "total_cost_bps": total_cost_bps,
        "net_deployed_notional": round8(net_deployed),
        "symbol_exposure_notional": symbol_exposure_notional,
        "strategy_exposure_notional": strategy_exposure_notional,
        "symbol_exposure_pct": symbol_exposure_pct,
        "strategy_exposure_pct": strategy_exposure_pct,
        "observed_max_symbol_exposure_pct": observed_max_symbol,
        "observed_max_strategy_exposure_pct": observed_max_strategy,
        "distinct_symbol_count": distinct_symbols,
        "distinct_strategy_count": distinct_strategies,
        "position_count": position_count,
        "order_count": len(orders),
        "filled_order_count": filled_orders,
        "blocked_order_count": blocked_orders,
        "safety_breach_count": total_safety_count,
    }

    return checks, metrics


def decide_risk_outcome(
    session: sqlite3.Row | None,
    checks: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> tuple[str, str, str, str, str, str]:
    if session is None:
        return (
            RISK_DECISION_REJECT_MISSING,
            RISK_MISSING,
            ACTION_REFRESH_SESSION,
            "Mission 63 Paper Trading Sandbox",
            RISK_LEVEL_HIGH,
            "Paper sandbox session evidence is missing.",
        )

    fail_checks = [check for check in checks if check["limit_status"] == LIMIT_FAIL]

    safety_failed = any(
        check["limit_category"] == "safety" and check["limit_status"] == LIMIT_FAIL
        for check in checks
    )

    if safety_failed:
        return (
            RISK_DECISION_BLOCK_SAFETY,
            RISK_BLOCKED,
            ACTION_STOP_SAFETY,
            "Mission 64 safety remediation",
            RISK_LEVEL_HIGH,
            "Safety invariant failed.",
        )

    if fail_checks:
        return (
            RISK_DECISION_BLOCK_LIMITS,
            RISK_BLOCKED,
            ACTION_REDUCE_RISK,
            "Mission 63/64 risk remediation",
            RISK_LEVEL_HIGH,
            "One or more institutional risk limits failed.",
        )

    observed_max_symbol = safe_float(metrics.get("observed_max_symbol_exposure_pct", 0.0))
    observed_max_strategy = safe_float(metrics.get("observed_max_strategy_exposure_pct", 0.0))
    total_cost_bps = safe_float(metrics.get("total_cost_bps", 0.0))

    if observed_max_symbol >= 55 or observed_max_strategy >= 45 or total_cost_bps >= 7:
        level = RISK_LEVEL_MODERATE
    else:
        level = RISK_LEVEL_LOW

    return (
        RISK_DECISION_APPROVED,
        RISK_READY,
        ACTION_RUN_OBSERVATION,
        "Mission 65 Capital Readiness Review",
        level,
        "Paper sandbox session passes institutional risk controls for controlled paper observation only.",
    )


def build_summary(
    db_path: str | Path,
    review_label: str,
    report_label: str,
    created_at: str,
    session_label: str,
    session: sqlite3.Row | None,
    orders: list[sqlite3.Row],
    positions: list[sqlite3.Row],
    checks: list[dict[str, Any]],
    metrics: dict[str, Any],
    max_symbol_exposure_pct: float,
    max_strategy_exposure_pct: float,
    risk_decision: str,
    global_verdict: str,
    recommended_action: str,
    next_mission: str,
    risk_level: str,
    decision_reason: str,
) -> dict[str, Any]:
    counts = Counter(check["limit_status"] for check in checks)

    source_board_review_label = row_get(session, "source_board_review_label", None)
    source_portfolio_label = row_get(session, "source_portfolio_label", None)

    return {
        "review_label": review_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_session_label": session_label,
        "source_board_review_label": source_board_review_label,
        "source_portfolio_label": source_portfolio_label,
        "paper_notional": round8(safe_float(metrics.get("paper_notional", 0.0))),
        "limit_check_count": len(checks),
        "pass_limit_count": counts.get(LIMIT_PASS, 0),
        "fail_limit_count": counts.get(LIMIT_FAIL, 0),
        "position_count": safe_int(metrics.get("position_count", 0)),
        "order_count": safe_int(metrics.get("order_count", len(orders))),
        "filled_order_count": safe_int(metrics.get("filled_order_count", 0)),
        "blocked_order_count": safe_int(metrics.get("blocked_order_count", 0)),
        "distinct_symbol_count": safe_int(metrics.get("distinct_symbol_count", 0)),
        "distinct_strategy_count": safe_int(metrics.get("distinct_strategy_count", 0)),
        "max_symbol_exposure_pct": round8(max_symbol_exposure_pct),
        "max_strategy_exposure_pct": round8(max_strategy_exposure_pct),
        "observed_max_symbol_exposure_pct": round8(safe_float(metrics.get("observed_max_symbol_exposure_pct", 0.0))),
        "observed_max_strategy_exposure_pct": round8(safe_float(metrics.get("observed_max_strategy_exposure_pct", 0.0))),
        "total_cost_bps": round8(safe_float(metrics.get("total_cost_bps", 0.0))),
        "net_deployed_notional": round8(safe_float(metrics.get("net_deployed_notional", 0.0))),
        "symbol_exposure_pct": metrics.get("symbol_exposure_pct", {}),
        "strategy_exposure_pct": metrics.get("strategy_exposure_pct", {}),
        "safety_breach_count": safe_int(metrics.get("safety_breach_count", 0)),
        "limit_checks": checks,
        "institutional_risk_level": risk_level,
        "risk_decision": risk_decision,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
        "next_mission": next_mission,
        "decision_reason": decision_reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    check_lines = []

    for check in summary["limit_checks"]:
        check_lines.append(
            "- "
            + f"{check['limit_category']} / {check['limit_name']}: "
            + f"status={check['limit_status']}, "
            + f"observed={check['observed_value']}, "
            + f"required={check['required_value']}"
        )

    check_markdown = "\n".join(check_lines) or "- None"

    return f"""# DeltaGrid Mission 64 Institutional Risk Control Report

Report label: {summary['report_label']}
Review label: {summary['review_label']}
Created at: {summary['created_at']}
Source session label: {summary['source_session_label']}
Source board review label: {summary['source_board_review_label']}
Source portfolio label: {summary['source_portfolio_label']}

## Risk Control Summary

Paper notional: {summary['paper_notional']}
Limit check count: {summary['limit_check_count']}
Pass limit count: {summary['pass_limit_count']}
Fail limit count: {summary['fail_limit_count']}

Position count: {summary['position_count']}
Order count: {summary['order_count']}
Filled order count: {summary['filled_order_count']}
Blocked order count: {summary['blocked_order_count']}
Distinct symbol count: {summary['distinct_symbol_count']}
Distinct strategy count: {summary['distinct_strategy_count']}

Observed max symbol exposure pct: {summary['observed_max_symbol_exposure_pct']}
Observed max strategy exposure pct: {summary['observed_max_strategy_exposure_pct']}
Total cost bps: {summary['total_cost_bps']}
Net deployed notional: {summary['net_deployed_notional']}
Safety breach count: {summary['safety_breach_count']}
Institutional risk level: {summary['institutional_risk_level']}

## Limit Checks

{check_markdown}

## Decision

Risk decision: {summary['risk_decision']}
Global verdict: {summary['global_verdict']}
Recommended action: {summary['recommended_action']}
Decision reason: {summary['decision_reason']}
Next mission: {summary['next_mission']}

## Safety Statement

Live trading remains disabled.
Capital deployment remains blocked.
No private keys were read.
No signatures were produced.
No exchange orders were sent.
No real capital was used.
No paid APIs were used.

Approval scope, if approved, is controlled paper observation only.
It is not approval for live trading or real capital.
"""


def persist_review(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for check in summary["limit_checks"]:
            conn.execute(
                """
                INSERT OR REPLACE INTO institutional_risk_limit_checks (
                    check_id,
                    review_label,
                    created_at,
                    source_session_label,
                    limit_category,
                    limit_name,
                    limit_status,
                    observed_value,
                    required_value,
                    limit_reason,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    check["check_id"],
                    check["review_label"],
                    check["created_at"],
                    check["source_session_label"],
                    check["limit_category"],
                    check["limit_name"],
                    check["limit_status"],
                    check["observed_value"],
                    check["required_value"],
                    check["limit_reason"],
                    check["live_trading"],
                    check["live_order_sent"],
                    check["capital_deployment"],
                    json.dumps(check["metadata"], sort_keys=True),
                ),
            )

        conn.execute(
            """
            INSERT OR REPLACE INTO institutional_risk_control_reviews (
                review_label,
                report_label,
                created_at,
                source_session_label,
                source_board_review_label,
                source_portfolio_label,
                paper_notional,
                limit_check_count,
                pass_limit_count,
                fail_limit_count,
                position_count,
                order_count,
                filled_order_count,
                blocked_order_count,
                distinct_symbol_count,
                distinct_strategy_count,
                max_symbol_exposure_pct,
                max_strategy_exposure_pct,
                observed_max_symbol_exposure_pct,
                observed_max_strategy_exposure_pct,
                total_cost_bps,
                net_deployed_notional,
                safety_breach_count,
                institutional_risk_level,
                risk_decision,
                global_verdict,
                recommended_action,
                next_mission,
                live_trading,
                live_order_sent,
                capital_deployment,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["review_label"],
                summary["report_label"],
                summary["created_at"],
                summary["source_session_label"],
                summary["source_board_review_label"],
                summary["source_portfolio_label"],
                str(summary["paper_notional"]),
                summary["limit_check_count"],
                summary["pass_limit_count"],
                summary["fail_limit_count"],
                summary["position_count"],
                summary["order_count"],
                summary["filled_order_count"],
                summary["blocked_order_count"],
                summary["distinct_symbol_count"],
                summary["distinct_strategy_count"],
                str(summary["max_symbol_exposure_pct"]),
                str(summary["max_strategy_exposure_pct"]),
                str(summary["observed_max_symbol_exposure_pct"]),
                str(summary["observed_max_strategy_exposure_pct"]),
                str(summary["total_cost_bps"]),
                str(summary["net_deployed_notional"]),
                summary["safety_breach_count"],
                summary["institutional_risk_level"],
                summary["risk_decision"],
                summary["global_verdict"],
                summary["recommended_action"],
                summary["next_mission"],
                summary["live_trading"],
                summary["live_order_sent"],
                summary["capital_deployment"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.execute(
            """
            INSERT OR REPLACE INTO institutional_risk_decision_records (
                decision_id,
                review_label,
                report_label,
                created_at,
                source_session_label,
                risk_decision,
                global_verdict,
                recommended_action,
                approval_scope,
                explicit_non_approval_scope,
                decision_reason,
                live_trading,
                live_order_sent,
                capital_deployment,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{summary['review_label']}-decision",
                summary["review_label"],
                summary["report_label"],
                summary["created_at"],
                summary["source_session_label"],
                summary["risk_decision"],
                summary["global_verdict"],
                summary["recommended_action"],
                "CONTROLLED_PAPER_OBSERVATION_ONLY",
                "NOT_LIVE_TRADING_NOT_REAL_CAPITAL",
                summary["decision_reason"],
                LIVE_TRADING_STATUS,
                LIVE_ORDER_SENT_VALUE,
                CAPITAL_DEPLOYMENT_STATUS,
                json.dumps(
                    {
                        "risk_role": "INSTITUTIONAL_RISK_DECISION_ONLY",
                        "execution_role": "NONE",
                        "private_keys_used": False,
                        "orders_sent": False,
                        "paid_api_used": False,
                        "real_capital_used": False,
                    },
                    sort_keys=True,
                ),
            ),
        )

        conn.commit()


def run_institutional_risk_control(
    db_path: str | Path = "offchain/deltagrid.db",
    review_label: str | None = None,
    report_label: str | None = None,
    session_label: str = "mission63-final-check",
    symbols: str | list[str] | tuple[str, ...] | None = None,
    max_symbol_exposure_pct: float = 60.0,
    max_strategy_exposure_pct: float = 50.0,
    max_total_cost_bps: float = 10.0,
    min_distinct_symbols: int = 2,
    min_position_count: int = 3,
) -> dict[str, Any]:
    if max_symbol_exposure_pct <= 0 or max_symbol_exposure_pct > 100:
        raise ValueError("max_symbol_exposure_pct must be between 0 and 100")

    if max_strategy_exposure_pct <= 0 or max_strategy_exposure_pct > 100:
        raise ValueError("max_strategy_exposure_pct must be between 0 and 100")

    if max_total_cost_bps < 0:
        raise ValueError("max_total_cost_bps cannot be negative")

    if min_distinct_symbols <= 0:
        raise ValueError("min_distinct_symbols must be positive")

    if min_position_count <= 0:
        raise ValueError("min_position_count must be positive")

    db = Path(db_path)
    review = review_label or new_review_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    requested_symbols = parse_symbols(symbols)

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        session = load_session(conn, session_label)
        orders = load_orders(conn, session_label, requested_symbols)
        positions = load_positions(conn, session_label, requested_symbols)

    if session is None:
        checks = build_missing_checks(review, created_at, session_label)
        metrics: dict[str, Any] = {}
    else:
        checks, metrics = build_limit_checks(
            review_label=review,
            created_at=created_at,
            session=session,
            orders=orders,
            positions=positions,
            max_symbol_exposure_pct=max_symbol_exposure_pct,
            max_strategy_exposure_pct=max_strategy_exposure_pct,
            max_total_cost_bps=max_total_cost_bps,
            min_distinct_symbols=min_distinct_symbols,
            min_position_count=min_position_count,
        )

    risk_decision, global_verdict, recommended_action, next_mission, risk_level, decision_reason = decide_risk_outcome(
        session=session,
        checks=checks,
        metrics=metrics,
    )

    summary = build_summary(
        db_path=db,
        review_label=review,
        report_label=report,
        created_at=created_at,
        session_label=session_label,
        session=session,
        orders=orders,
        positions=positions,
        checks=checks,
        metrics=metrics,
        max_symbol_exposure_pct=max_symbol_exposure_pct,
        max_strategy_exposure_pct=max_strategy_exposure_pct,
        risk_decision=risk_decision,
        global_verdict=global_verdict,
        recommended_action=recommended_action,
        next_mission=next_mission,
        risk_level=risk_level,
        decision_reason=decision_reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_review(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid institutional risk control.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--review-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--session-label", default="mission63-final-check")
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--max-symbol-exposure-pct", type=float, default=60.0)
    parser.add_argument("--max-strategy-exposure-pct", type=float, default=50.0)
    parser.add_argument("--max-total-cost-bps", type=float, default=10.0)
    parser.add_argument("--min-distinct-symbols", type=int, default=2)
    parser.add_argument("--min-position-count", type=int, default=3)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_institutional_risk_control(
        db_path=args.db,
        review_label=args.review_label,
        report_label=args.report_label,
        session_label=args.session_label,
        symbols=args.symbols,
        max_symbol_exposure_pct=args.max_symbol_exposure_pct,
        max_strategy_exposure_pct=args.max_strategy_exposure_pct,
        max_total_cost_bps=args.max_total_cost_bps,
        min_distinct_symbols=args.min_distinct_symbols,
        min_position_count=args.min_position_count,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

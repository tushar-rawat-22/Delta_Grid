"""
Mission 63: Paper Trading Sandbox.

This module converts a board-approved shadow portfolio into a paper-only
execution sandbox.

It reads:
- research_promotion_board_reviews
- research_promotion_board_decision_records
- shadow_portfolio_allocations
- historical_public_basis_observations, when available for reference prices

It writes:
- paper_sandbox_sessions
- paper_sandbox_orders
- paper_sandbox_fills
- paper_sandbox_positions
- paper_sandbox_reports

It is paper simulation only.

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


BOARD_REVIEWS_TABLE = "research_promotion_board_reviews"
BOARD_DECISIONS_TABLE = "research_promotion_board_decision_records"
ALLOCATIONS_TABLE = "shadow_portfolio_allocations"
BASIS_TABLE = "historical_public_basis_observations"

SESSIONS_TABLE = "paper_sandbox_sessions"
ORDERS_TABLE = "paper_sandbox_orders"
FILLS_TABLE = "paper_sandbox_fills"
POSITIONS_TABLE = "paper_sandbox_positions"
REPORTS_TABLE = "paper_sandbox_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

BOARD_APPROVED = "RESEARCH_BOARD_APPROVED_FOR_PAPER_SANDBOX_SHADOW_ONLY"
BOARD_READY = "RESEARCH_PROMOTION_BOARD_REVIEW_READY"
BOARD_ACTION_OPEN = "OPEN_PAPER_SANDBOX_RESEARCH_ONLY"

ALLOC_INCLUDED = "PORTFOLIO_ALLOCATION_INCLUDED_SHADOW_ONLY"

ORDER_SUBMITTED = "PAPER_ORDER_SUBMITTED"
ORDER_FILLED = "PAPER_ORDER_FILLED"
ORDER_BLOCKED = "PAPER_ORDER_BLOCKED"

FILL_SIMULATED = "PAPER_FILL_SIMULATED"
POSITION_OPEN = "PAPER_POSITION_OPEN"

SESSION_READY = "PAPER_SANDBOX_READY_SHADOW_ONLY"
SESSION_BLOCKED_BOARD = "PAPER_SANDBOX_BLOCKED_BY_BOARD"
SESSION_BLOCKED_SAFETY = "PAPER_SANDBOX_BLOCKED_BY_SAFETY_POLICY"
SESSION_NO_ALLOCATIONS = "PAPER_SANDBOX_NO_INCLUDED_ALLOCATIONS"

ACTION_RUN_OBSERVATION = "RUN_PAPER_SANDBOX_OBSERVATION_CYCLE"
ACTION_REVIEW_BOARD = "RETURN_TO_RESEARCH_PROMOTION_BOARD"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_PAPER_SANDBOX_SAFETY_STATE"
ACTION_REFRESH_PORTFOLIO = "REFRESH_SHADOW_PORTFOLIO_AND_RERUN_BOARD"

PAPER_ORDER_SIDE = "PAPER_BUY"
PAPER_ORDER_TYPE = "PAPER_MARKET_SIMULATION"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_session_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission63-paper-session-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission63-paper-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
            raise ValueError(f"Only USDT symbols are supported for Mission 63: {symbol}")

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
            CREATE TABLE IF NOT EXISTS paper_sandbox_sessions (
                session_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_board_review_label TEXT NOT NULL,
                source_portfolio_label TEXT,
                paper_notional TEXT NOT NULL,
                requested_symbol_count INTEGER NOT NULL,
                source_allocation_count INTEGER NOT NULL,
                submitted_order_count INTEGER NOT NULL,
                filled_order_count INTEGER NOT NULL,
                blocked_order_count INTEGER NOT NULL,
                position_count INTEGER NOT NULL,
                total_paper_order_notional TEXT NOT NULL,
                total_simulated_fees TEXT NOT NULL,
                total_simulated_slippage TEXT NOT NULL,
                net_paper_deployed_notional TEXT NOT NULL,
                weighted_average_fill_price TEXT NOT NULL,
                safety_breach_count INTEGER NOT NULL,
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
            CREATE TABLE IF NOT EXISTS paper_sandbox_orders (
                order_id TEXT PRIMARY KEY,
                session_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_board_review_label TEXT NOT NULL,
                source_portfolio_label TEXT,
                source_allocation_id TEXT,
                strategy_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                paper_order_side TEXT NOT NULL,
                paper_order_type TEXT NOT NULL,
                paper_order_status TEXT NOT NULL,
                allocation_weight TEXT NOT NULL,
                requested_notional TEXT NOT NULL,
                reference_price TEXT NOT NULL,
                simulated_quantity TEXT NOT NULL,
                simulated_slippage_bps TEXT NOT NULL,
                simulated_fee_bps TEXT NOT NULL,
                simulated_fee_amount TEXT NOT NULL,
                paper_execution_venue TEXT NOT NULL,
                order_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_sandbox_fills (
                fill_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                session_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                fill_status TEXT NOT NULL,
                fill_price TEXT NOT NULL,
                fill_quantity TEXT NOT NULL,
                fill_notional TEXT NOT NULL,
                simulated_slippage_amount TEXT NOT NULL,
                simulated_fee_amount TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_sandbox_positions (
                position_id TEXT PRIMARY KEY,
                session_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                position_status TEXT NOT NULL,
                paper_side TEXT NOT NULL,
                quantity TEXT NOT NULL,
                entry_price TEXT NOT NULL,
                entry_notional TEXT NOT NULL,
                allocation_weight TEXT NOT NULL,
                simulated_fee_amount TEXT NOT NULL,
                unrealized_paper_pnl TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_sandbox_reports (
                report_label TEXT PRIMARY KEY,
                session_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_board_review_label TEXT NOT NULL,
                source_portfolio_label TEXT,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                report_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL
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


def load_board_review(conn: sqlite3.Connection, review_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, BOARD_REVIEWS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM research_promotion_board_reviews
        WHERE review_label = ?
        """,
        (review_label,),
    ).fetchone()


def load_board_decision(conn: sqlite3.Connection, review_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, BOARD_DECISIONS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM research_promotion_board_decision_records
        WHERE review_label = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (review_label,),
    ).fetchone()


def load_included_allocations(
    conn: sqlite3.Connection,
    portfolio_label: str | None,
    symbols: list[str] | None,
) -> list[sqlite3.Row]:
    if not portfolio_label:
        return []

    if not table_exists(conn, ALLOCATIONS_TABLE):
        return []

    params: list[Any] = [portfolio_label, ALLOC_INCLUDED]
    symbol_clause = ""

    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        symbol_clause = f" AND symbol IN ({placeholders})"
        params.extend(symbols)

    query = f"""
        SELECT *
        FROM shadow_portfolio_allocations
        WHERE portfolio_label = ?
        AND allocation_status = ?
        {symbol_clause}
        ORDER BY CAST(allocation_weight AS REAL) DESC
    """

    return conn.execute(query, params).fetchall()


def load_reference_prices(
    conn: sqlite3.Connection,
    dataset_label: str | None,
    symbols: list[str] | None,
) -> dict[str, float]:
    if not dataset_label:
        return {}

    if not table_exists(conn, BASIS_TABLE):
        return {}

    params: list[Any] = [dataset_label]
    symbol_clause = ""

    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        symbol_clause = f" AND symbol IN ({placeholders})"
        params.extend(symbols)

    query = f"""
        SELECT symbol, mark_price, created_at
        FROM historical_public_basis_observations
        WHERE dataset_label = ?
        {symbol_clause}
        ORDER BY symbol ASC, created_at DESC
    """

    prices: dict[str, float] = {}

    for row in conn.execute(query, params).fetchall():
        symbol = str(row["symbol"])
        price = safe_float(row["mark_price"])

        if symbol not in prices and price > 0:
            prices[symbol] = price

    return prices


def fallback_price(symbol: str) -> float:
    known = {
        "BTCUSDT": 100000.0,
        "ETHUSDT": 4000.0,
        "SOLUSDT": 200.0,
        "BNBUSDT": 700.0,
        "XRPUSDT": 2.0,
        "DOGEUSDT": 0.2,
    }
    return known.get(symbol.upper(), 100.0)


def board_is_approved(board: sqlite3.Row | None, decision: sqlite3.Row | None) -> bool:
    if board is None:
        return False

    decision_value = str(row_get(board, "board_decision", ""))
    verdict_value = str(row_get(board, "global_verdict", ""))
    action_value = str(row_get(board, "recommended_action", ""))

    if decision is not None:
        decision_value = str(row_get(decision, "board_decision", decision_value))
        verdict_value = str(row_get(decision, "global_verdict", verdict_value))
        action_value = str(row_get(decision, "recommended_action", action_value))

    return (
        decision_value == BOARD_APPROVED
        and verdict_value == BOARD_READY
        and action_value == BOARD_ACTION_OPEN
    )


def build_order(
    session_label: str,
    created_at: str,
    board_review_label: str,
    portfolio_label: str | None,
    allocation: sqlite3.Row,
    paper_notional: float,
    reference_price: float,
    slippage_bps: float,
    fee_bps: float,
) -> dict[str, Any]:
    allocation_weight = safe_float(row_get(allocation, "allocation_weight", 0.0))
    requested_notional = round8(allocation_weight * paper_notional)
    slippage_amount = round8(requested_notional * (slippage_bps / 10000.0))
    fee_amount = round8(requested_notional * (fee_bps / 10000.0))
    fill_price = round8(reference_price * (1.0 + slippage_bps / 10000.0))
    quantity = round8(requested_notional / fill_price) if fill_price > 0 else 0.0

    order_id = f"{session_label}-{row_get(allocation, 'allocation_id', uuid.uuid4().hex[:8])}"

    return {
        "order_id": order_id,
        "session_label": session_label,
        "created_at": created_at,
        "source_board_review_label": board_review_label,
        "source_portfolio_label": portfolio_label,
        "source_allocation_id": str(row_get(allocation, "allocation_id", "")),
        "strategy_id": str(row_get(allocation, "strategy_id", "UNKNOWN_STRATEGY")),
        "symbol": str(row_get(allocation, "symbol", "UNKNOWN")),
        "paper_order_side": PAPER_ORDER_SIDE,
        "paper_order_type": PAPER_ORDER_TYPE,
        "paper_order_status": ORDER_FILLED,
        "allocation_weight": round8(allocation_weight),
        "requested_notional": requested_notional,
        "reference_price": round8(reference_price),
        "simulated_quantity": quantity,
        "simulated_slippage_bps": round8(slippage_bps),
        "simulated_fee_bps": round8(fee_bps),
        "simulated_fee_amount": fee_amount,
        "simulated_slippage_amount": slippage_amount,
        "fill_price": fill_price,
        "paper_execution_venue": "LOCAL_PAPER_SANDBOX_ONLY",
        "order_reason": "Board-approved shadow allocation converted to paper-only simulated order.",
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "sandbox_role": "PAPER_EXECUTION_SIMULATION_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def build_orders(
    session_label: str,
    created_at: str,
    board_review_label: str,
    portfolio_label: str | None,
    allocations: list[sqlite3.Row],
    reference_prices: dict[str, float],
    paper_notional: float,
    slippage_bps: float,
    fee_bps: float,
) -> list[dict[str, Any]]:
    orders = []

    for allocation in allocations:
        symbol = str(row_get(allocation, "symbol", "")).upper()
        price = reference_prices.get(symbol, fallback_price(symbol))

        orders.append(
            build_order(
                session_label=session_label,
                created_at=created_at,
                board_review_label=board_review_label,
                portfolio_label=portfolio_label,
                allocation=allocation,
                paper_notional=paper_notional,
                reference_price=price,
                slippage_bps=slippage_bps,
                fee_bps=fee_bps,
            )
        )

    return orders


def build_fill(order: dict[str, Any]) -> dict[str, Any]:
    return {
        "fill_id": f"{order['order_id']}-fill",
        "order_id": order["order_id"],
        "session_label": order["session_label"],
        "created_at": order["created_at"],
        "symbol": order["symbol"],
        "strategy_id": order["strategy_id"],
        "fill_status": FILL_SIMULATED,
        "fill_price": order["fill_price"],
        "fill_quantity": order["simulated_quantity"],
        "fill_notional": order["requested_notional"],
        "simulated_slippage_amount": order["simulated_slippage_amount"],
        "simulated_fee_amount": order["simulated_fee_amount"],
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "sandbox_role": "PAPER_FILL_SIMULATION_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def build_position(order: dict[str, Any], fill: dict[str, Any]) -> dict[str, Any]:
    return {
        "position_id": f"{order['order_id']}-position",
        "session_label": order["session_label"],
        "created_at": order["created_at"],
        "symbol": order["symbol"],
        "strategy_id": order["strategy_id"],
        "position_status": POSITION_OPEN,
        "paper_side": order["paper_order_side"],
        "quantity": fill["fill_quantity"],
        "entry_price": fill["fill_price"],
        "entry_notional": fill["fill_notional"],
        "allocation_weight": order["allocation_weight"],
        "simulated_fee_amount": fill["simulated_fee_amount"],
        "unrealized_paper_pnl": 0.0,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "sandbox_role": "PAPER_POSITION_SIMULATION_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def summarize_session(
    db_path: str | Path,
    session_label: str,
    report_label: str,
    created_at: str,
    board_review_label: str,
    board: sqlite3.Row | None,
    decision: sqlite3.Row | None,
    portfolio_label: str | None,
    paper_notional: float,
    requested_symbols: list[str] | None,
    allocations: list[sqlite3.Row],
    orders: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    positions: list[dict[str, Any]],
    board_approved: bool,
) -> dict[str, Any]:
    safety_count = 0

    for row in [board, decision, *allocations, *orders, *fills, *positions]:
        if safety_problem(row):
            safety_count += 1

    submitted_order_count = len(orders)
    filled_order_count = sum(1 for order in orders if order["paper_order_status"] == ORDER_FILLED)
    blocked_order_count = sum(1 for order in orders if order["paper_order_status"] == ORDER_BLOCKED)
    total_paper_order_notional = round8(sum(order["requested_notional"] for order in orders))
    total_simulated_fees = round8(sum(order["simulated_fee_amount"] for order in orders))
    total_simulated_slippage = round8(sum(order["simulated_slippage_amount"] for order in orders))
    net_deployed = round8(total_paper_order_notional + total_simulated_fees + total_simulated_slippage)

    weighted_average_fill_price = 0.0
    total_quantity = sum(fill["fill_quantity"] for fill in fills)

    if total_quantity > 0:
        weighted_average_fill_price = round8(
            sum(fill["fill_price"] * fill["fill_quantity"] for fill in fills) / total_quantity
        )

    if safety_count > 0:
        verdict = SESSION_BLOCKED_SAFETY
        action = ACTION_REVIEW_SAFETY
        next_mission = "Mission 63 safety remediation"
    elif not board_approved:
        verdict = SESSION_BLOCKED_BOARD
        action = ACTION_REVIEW_BOARD
        next_mission = "Mission 62 Research Promotion Board"
    elif not allocations:
        verdict = SESSION_NO_ALLOCATIONS
        action = ACTION_REFRESH_PORTFOLIO
        next_mission = "Mission 61 Shadow Portfolio Simulator"
    else:
        verdict = SESSION_READY
        action = ACTION_RUN_OBSERVATION
        next_mission = "Mission 64 Institutional Risk Control Layer"

    return {
        "session_label": session_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_board_review_label": board_review_label,
        "source_portfolio_label": portfolio_label,
        "paper_notional": round8(paper_notional),
        "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
        "source_allocation_count": len(allocations),
        "submitted_order_count": submitted_order_count,
        "filled_order_count": filled_order_count,
        "blocked_order_count": blocked_order_count,
        "position_count": len(positions),
        "total_paper_order_notional": total_paper_order_notional,
        "total_simulated_fees": total_simulated_fees,
        "total_simulated_slippage": total_simulated_slippage,
        "net_paper_deployed_notional": net_deployed,
        "weighted_average_fill_price": weighted_average_fill_price,
        "symbol_order_counts": dict(Counter(order["symbol"] for order in orders)),
        "strategy_order_counts": dict(Counter(order["strategy_id"] for order in orders)),
        "orders": orders,
        "fills": fills,
        "positions": positions,
        "safety_breach_count": safety_count,
        "board_decision": str(row_get(board, "board_decision", "")) if board is not None else None,
        "board_global_verdict": str(row_get(board, "global_verdict", "")) if board is not None else None,
        "global_verdict": verdict,
        "recommended_action": action,
        "next_mission": next_mission,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    order_lines = []

    for order in summary["orders"]:
        order_lines.append(
            "- "
            + f"{order['symbol']} {order['strategy_id']}: "
            + f"notional={order['requested_notional']}, "
            + f"qty={order['simulated_quantity']}, "
            + f"fill_price={order['fill_price']}, "
            + f"fee={order['simulated_fee_amount']}"
        )

    order_markdown = "\n".join(order_lines) or "- None"

    return f"""# DeltaGrid Mission 63 Paper Trading Sandbox Report

Report label: {summary['report_label']}
Session label: {summary['session_label']}
Created at: {summary['created_at']}
Source board review label: {summary['source_board_review_label']}
Source portfolio label: {summary['source_portfolio_label']}

## Sandbox Summary

Paper notional: {summary['paper_notional']}
Source allocation count: {summary['source_allocation_count']}
Submitted order count: {summary['submitted_order_count']}
Filled order count: {summary['filled_order_count']}
Blocked order count: {summary['blocked_order_count']}
Position count: {summary['position_count']}

Total paper order notional: {summary['total_paper_order_notional']}
Total simulated fees: {summary['total_simulated_fees']}
Total simulated slippage: {summary['total_simulated_slippage']}
Net paper deployed notional: {summary['net_paper_deployed_notional']}
Weighted average fill price: {summary['weighted_average_fill_price']}

Safety breach count: {summary['safety_breach_count']}

## Paper Orders

{order_markdown}

## Verdict

Global verdict: {summary['global_verdict']}
Recommended action: {summary['recommended_action']}
Next mission: {summary['next_mission']}

## Safety Statement

Live trading remains disabled.
Capital deployment remains blocked.
No private keys were read.
No signatures were produced.
No exchange orders were sent.
No real capital was used.
No paid APIs were used.

All orders, fills, and positions are paper-only local simulations.
"""


def persist_session(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for order in summary["orders"]:
            conn.execute(
                """
                INSERT OR REPLACE INTO paper_sandbox_orders (
                    order_id,
                    session_label,
                    created_at,
                    source_board_review_label,
                    source_portfolio_label,
                    source_allocation_id,
                    strategy_id,
                    symbol,
                    paper_order_side,
                    paper_order_type,
                    paper_order_status,
                    allocation_weight,
                    requested_notional,
                    reference_price,
                    simulated_quantity,
                    simulated_slippage_bps,
                    simulated_fee_bps,
                    simulated_fee_amount,
                    paper_execution_venue,
                    order_reason,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order["order_id"],
                    order["session_label"],
                    order["created_at"],
                    order["source_board_review_label"],
                    order["source_portfolio_label"],
                    order["source_allocation_id"],
                    order["strategy_id"],
                    order["symbol"],
                    order["paper_order_side"],
                    order["paper_order_type"],
                    order["paper_order_status"],
                    str(order["allocation_weight"]),
                    str(order["requested_notional"]),
                    str(order["reference_price"]),
                    str(order["simulated_quantity"]),
                    str(order["simulated_slippage_bps"]),
                    str(order["simulated_fee_bps"]),
                    str(order["simulated_fee_amount"]),
                    order["paper_execution_venue"],
                    order["order_reason"],
                    order["live_trading"],
                    order["live_order_sent"],
                    order["capital_deployment"],
                    json.dumps(order["metadata"], sort_keys=True),
                ),
            )

        for fill in summary["fills"]:
            conn.execute(
                """
                INSERT OR REPLACE INTO paper_sandbox_fills (
                    fill_id,
                    order_id,
                    session_label,
                    created_at,
                    symbol,
                    strategy_id,
                    fill_status,
                    fill_price,
                    fill_quantity,
                    fill_notional,
                    simulated_slippage_amount,
                    simulated_fee_amount,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fill["fill_id"],
                    fill["order_id"],
                    fill["session_label"],
                    fill["created_at"],
                    fill["symbol"],
                    fill["strategy_id"],
                    fill["fill_status"],
                    str(fill["fill_price"]),
                    str(fill["fill_quantity"]),
                    str(fill["fill_notional"]),
                    str(fill["simulated_slippage_amount"]),
                    str(fill["simulated_fee_amount"]),
                    fill["live_trading"],
                    fill["live_order_sent"],
                    fill["capital_deployment"],
                    json.dumps(fill["metadata"], sort_keys=True),
                ),
            )

        for position in summary["positions"]:
            conn.execute(
                """
                INSERT OR REPLACE INTO paper_sandbox_positions (
                    position_id,
                    session_label,
                    created_at,
                    symbol,
                    strategy_id,
                    position_status,
                    paper_side,
                    quantity,
                    entry_price,
                    entry_notional,
                    allocation_weight,
                    simulated_fee_amount,
                    unrealized_paper_pnl,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position["position_id"],
                    position["session_label"],
                    position["created_at"],
                    position["symbol"],
                    position["strategy_id"],
                    position["position_status"],
                    position["paper_side"],
                    str(position["quantity"]),
                    str(position["entry_price"]),
                    str(position["entry_notional"]),
                    str(position["allocation_weight"]),
                    str(position["simulated_fee_amount"]),
                    str(position["unrealized_paper_pnl"]),
                    position["live_trading"],
                    position["live_order_sent"],
                    position["capital_deployment"],
                    json.dumps(position["metadata"], sort_keys=True),
                ),
            )

        conn.execute(
            """
            INSERT OR REPLACE INTO paper_sandbox_sessions (
                session_label,
                report_label,
                created_at,
                source_board_review_label,
                source_portfolio_label,
                paper_notional,
                requested_symbol_count,
                source_allocation_count,
                submitted_order_count,
                filled_order_count,
                blocked_order_count,
                position_count,
                total_paper_order_notional,
                total_simulated_fees,
                total_simulated_slippage,
                net_paper_deployed_notional,
                weighted_average_fill_price,
                safety_breach_count,
                global_verdict,
                recommended_action,
                next_mission,
                live_trading,
                live_order_sent,
                capital_deployment,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["session_label"],
                summary["report_label"],
                summary["created_at"],
                summary["source_board_review_label"],
                summary["source_portfolio_label"],
                str(summary["paper_notional"]),
                summary["requested_symbol_count"],
                summary["source_allocation_count"],
                summary["submitted_order_count"],
                summary["filled_order_count"],
                summary["blocked_order_count"],
                summary["position_count"],
                str(summary["total_paper_order_notional"]),
                str(summary["total_simulated_fees"]),
                str(summary["total_simulated_slippage"]),
                str(summary["net_paper_deployed_notional"]),
                str(summary["weighted_average_fill_price"]),
                summary["safety_breach_count"],
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
            INSERT OR REPLACE INTO paper_sandbox_reports (
                report_label,
                session_label,
                created_at,
                source_board_review_label,
                source_portfolio_label,
                global_verdict,
                recommended_action,
                report_json,
                markdown_report,
                live_trading,
                live_order_sent,
                capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["session_label"],
                summary["created_at"],
                summary["source_board_review_label"],
                summary["source_portfolio_label"],
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
                LIVE_TRADING_STATUS,
                LIVE_ORDER_SENT_VALUE,
                CAPITAL_DEPLOYMENT_STATUS,
            ),
        )

        conn.commit()


def run_paper_trading_sandbox(
    db_path: str | Path = "offchain/deltagrid.db",
    session_label: str | None = None,
    report_label: str | None = None,
    board_review_label: str = "mission62-final-confirm",
    symbols: str | list[str] | tuple[str, ...] | None = None,
    paper_notional: float = 100000.0,
    reference_dataset_label: str | None = "mission50-final-check",
    simulated_slippage_bps: float = 1.5,
    simulated_fee_bps: float = 2.0,
) -> dict[str, Any]:
    if paper_notional <= 0:
        raise ValueError("paper_notional must be positive")

    if simulated_slippage_bps < 0:
        raise ValueError("simulated_slippage_bps cannot be negative")

    if simulated_fee_bps < 0:
        raise ValueError("simulated_fee_bps cannot be negative")

    db = Path(db_path)
    session = session_label or new_session_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    requested_symbols = parse_symbols(symbols)

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        board = load_board_review(conn, board_review_label)
        decision = load_board_decision(conn, board_review_label)

        portfolio_label = row_get(board, "source_portfolio_label", None)

        allocations = load_included_allocations(
            conn=conn,
            portfolio_label=portfolio_label,
            symbols=requested_symbols,
        )

        allocation_symbols = sorted({str(row_get(row, "symbol", "")).upper() for row in allocations})
        price_symbols = requested_symbols or allocation_symbols

        reference_prices = load_reference_prices(
            conn=conn,
            dataset_label=reference_dataset_label,
            symbols=price_symbols,
        )

    approved = board_is_approved(board, decision)

    orders: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    positions: list[dict[str, Any]] = []

    if approved:
        orders = build_orders(
            session_label=session,
            created_at=created_at,
            board_review_label=board_review_label,
            portfolio_label=portfolio_label,
            allocations=allocations,
            reference_prices=reference_prices,
            paper_notional=paper_notional,
            slippage_bps=simulated_slippage_bps,
            fee_bps=simulated_fee_bps,
        )

        fills = [build_fill(order) for order in orders]
        positions = [build_position(order, fill) for order, fill in zip(orders, fills)]

    summary = summarize_session(
        db_path=db,
        session_label=session,
        report_label=report,
        created_at=created_at,
        board_review_label=board_review_label,
        board=board,
        decision=decision,
        portfolio_label=portfolio_label,
        paper_notional=paper_notional,
        requested_symbols=requested_symbols,
        allocations=allocations,
        orders=orders,
        fills=fills,
        positions=positions,
        board_approved=approved,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_session(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid paper trading sandbox.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--session-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--board-review-label", default="mission62-final-confirm")
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--paper-notional", type=float, default=100000.0)
    parser.add_argument("--reference-dataset-label", default="mission50-final-check")
    parser.add_argument("--simulated-slippage-bps", type=float, default=1.5)
    parser.add_argument("--simulated-fee-bps", type=float, default=2.0)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_paper_trading_sandbox(
        db_path=args.db,
        session_label=args.session_label,
        report_label=args.report_label,
        board_review_label=args.board_review_label,
        symbols=args.symbols,
        paper_notional=args.paper_notional,
        reference_dataset_label=args.reference_dataset_label,
        simulated_slippage_bps=args.simulated_slippage_bps,
        simulated_fee_bps=args.simulated_fee_bps,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

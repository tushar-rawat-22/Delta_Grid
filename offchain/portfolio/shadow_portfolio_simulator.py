"""
Mission 61: Shadow Portfolio Simulator.

This module converts regime-gated strategy candidates into a portfolio-level
shadow simulation.

It reads:
- data_quality_strategy_candidate_gates

It writes:
- shadow_portfolio_simulations
- shadow_portfolio_allocations
- shadow_portfolio_risk_reports

It is simulation-only.

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
import statistics
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GATES_TABLE = "data_quality_strategy_candidate_gates"

SIMULATIONS_TABLE = "shadow_portfolio_simulations"
ALLOCATIONS_TABLE = "shadow_portfolio_allocations"
RISK_REPORTS_TABLE = "shadow_portfolio_risk_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

GATE_PASS = "CANDIDATE_GATE_PASS_RESEARCH_REVIEW"
GATE_WATCH = "CANDIDATE_GATE_WATCHLIST_ONLY_BY_REGIME"
GATE_BLOCK = "CANDIDATE_GATE_BLOCK_PROMOTION_BY_REGIME"
GATE_SAFETY = "CANDIDATE_GATE_SAFETY_BLOCKED"

PORTFOLIO_READY = "SHADOW_PORTFOLIO_SIMULATION_READY"
PORTFOLIO_CONSTRAINED = "SHADOW_PORTFOLIO_SIMULATION_CONSTRAINED"
PORTFOLIO_NO_ELIGIBLE = "SHADOW_PORTFOLIO_NO_ELIGIBLE_CANDIDATES"
PORTFOLIO_SAFETY_BLOCKED = "SHADOW_PORTFOLIO_SAFETY_BLOCKED"

ACTION_REVIEW = "REVIEW_SHADOW_PORTFOLIO_FOR_RESEARCH_BOARD"
ACTION_CONTINUE = "CONTINUE_SHADOW_PORTFOLIO_SIMULATION"
ACTION_REFRESH = "REFRESH_CANDIDATES_AND_REGIME_GATES"
ACTION_STOP = "STOP_AND_REVIEW_PORTFOLIO_SAFETY_STATE"

ALLOC_INCLUDED = "PORTFOLIO_ALLOCATION_INCLUDED_SHADOW_ONLY"
ALLOC_EXCLUDED = "PORTFOLIO_ALLOCATION_EXCLUDED_SHADOW_ONLY"

RISK_LOW = "PORTFOLIO_RISK_LOW"
RISK_MODERATE = "PORTFOLIO_RISK_MODERATE"
RISK_HIGH = "PORTFOLIO_RISK_HIGH"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_portfolio_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission61-shadow-portfolio-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission61-shadow-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
            raise ValueError(f"Only USDT perpetual symbols are supported for Mission 61: {symbol}")

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
            CREATE TABLE IF NOT EXISTS shadow_portfolio_simulations (
                portfolio_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_regime_label TEXT NOT NULL,
                shadow_notional TEXT NOT NULL,
                requested_symbol_count INTEGER NOT NULL,
                source_gate_count INTEGER NOT NULL,
                eligible_candidate_count INTEGER NOT NULL,
                included_allocation_count INTEGER NOT NULL,
                excluded_candidate_count INTEGER NOT NULL,
                total_allocated_weight TEXT NOT NULL,
                unallocated_weight TEXT NOT NULL,
                allocated_notional TEXT NOT NULL,
                weighted_alpha_score TEXT NOT NULL,
                max_symbol_weight TEXT NOT NULL,
                max_strategy_weight TEXT NOT NULL,
                max_candidate_weight TEXT NOT NULL,
                concentration_score TEXT NOT NULL,
                estimated_shadow_drawdown_pct TEXT NOT NULL,
                portfolio_risk_rating TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS shadow_portfolio_allocations (
                allocation_id TEXT PRIMARY KEY,
                portfolio_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_regime_label TEXT NOT NULL,
                source_gate_id TEXT NOT NULL,
                source_candidate_id TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                candidate_status TEXT NOT NULL,
                candidate_gate_status TEXT NOT NULL,
                allocation_status TEXT NOT NULL,
                allocation_reason TEXT NOT NULL,
                promotion_eligible INTEGER NOT NULL,
                alpha_score TEXT NOT NULL,
                data_quality_score TEXT NOT NULL,
                market_risk_state TEXT NOT NULL,
                raw_score TEXT NOT NULL,
                allocation_weight TEXT NOT NULL,
                allocation_notional TEXT NOT NULL,
                expected_alpha_contribution TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_portfolio_risk_reports (
                risk_report_id TEXT PRIMARY KEY,
                portfolio_label TEXT NOT NULL,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                symbol_exposure_json TEXT NOT NULL,
                strategy_exposure_json TEXT NOT NULL,
                top_symbol TEXT,
                top_strategy_id TEXT,
                max_symbol_weight TEXT NOT NULL,
                max_strategy_weight TEXT NOT NULL,
                concentration_score TEXT NOT NULL,
                estimated_shadow_drawdown_pct TEXT NOT NULL,
                portfolio_risk_rating TEXT NOT NULL,
                risk_notes_json TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL
            )
            """
        )

        conn.commit()


def load_candidate_gates(
    conn: sqlite3.Connection,
    regime_label: str,
    symbols: list[str] | None,
) -> list[sqlite3.Row]:
    if not table_exists(conn, GATES_TABLE):
        return []

    params: list[Any] = [regime_label]
    symbol_clause = ""

    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        symbol_clause = f" AND symbol IN ({placeholders})"
        params.extend(symbols)

    query = f"""
        SELECT
            gate_id,
            regime_label,
            source_factory_label,
            source_candidate_id,
            strategy_id,
            symbol,
            candidate_status,
            promotion_eligible,
            alpha_score,
            market_risk_state,
            data_quality_score,
            candidate_gate_status,
            gate_reason,
            live_trading,
            live_order_sent,
            capital_deployment
        FROM data_quality_strategy_candidate_gates
        WHERE regime_label = ?
        {symbol_clause}
        ORDER BY CAST(alpha_score AS REAL) DESC
    """

    return conn.execute(query, params).fetchall()


def safety_problem(row: sqlite3.Row | dict[str, Any]) -> bool:
    return (
        str(row["live_trading"]) != LIVE_TRADING_STATUS
        or safe_int(row["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or str(row["capital_deployment"]) != CAPITAL_DEPLOYMENT_STATUS
    )


def gate_is_eligible(row: sqlite3.Row) -> bool:
    return (
        str(row["candidate_gate_status"]) == GATE_PASS
        and safe_int(row["promotion_eligible"]) == 1
        and safe_float(row["alpha_score"]) > 0
        and not safety_problem(row)
    )


def raw_candidate_score(row: sqlite3.Row) -> float:
    alpha = max(0.0, safe_float(row["alpha_score"]))
    quality_multiplier = max(0.0, min(1.0, safe_float(row["data_quality_score"]) / 100.0))

    risk_multiplier = 1.0
    if str(row["market_risk_state"]).endswith("CAUTION"):
        risk_multiplier = 0.5
    elif str(row["market_risk_state"]).endswith("DANGER"):
        risk_multiplier = 0.0

    return round8(alpha * quality_multiplier * risk_multiplier)


def build_base_allocation_record(
    portfolio_label: str,
    created_at: str,
    shadow_notional: float,
    gate: sqlite3.Row,
    allocation_status: str,
    reason: str,
    raw_score: float = 0.0,
    allocation_weight: float = 0.0,
) -> dict[str, Any]:
    allocation_notional = allocation_weight * shadow_notional
    expected_alpha_contribution = allocation_weight * safe_float(gate["alpha_score"])

    return {
        "allocation_id": f"{portfolio_label}-{gate['gate_id']}",
        "portfolio_label": portfolio_label,
        "created_at": created_at,
        "source_regime_label": str(gate["regime_label"]),
        "source_gate_id": str(gate["gate_id"]),
        "source_candidate_id": str(gate["source_candidate_id"]),
        "strategy_id": str(gate["strategy_id"]),
        "symbol": str(gate["symbol"]),
        "candidate_status": str(gate["candidate_status"]),
        "candidate_gate_status": str(gate["candidate_gate_status"]),
        "allocation_status": allocation_status,
        "allocation_reason": reason,
        "promotion_eligible": safe_int(gate["promotion_eligible"]),
        "alpha_score": round8(safe_float(gate["alpha_score"])),
        "data_quality_score": round8(safe_float(gate["data_quality_score"])),
        "market_risk_state": str(gate["market_risk_state"]),
        "raw_score": round8(raw_score),
        "allocation_weight": round8(allocation_weight),
        "allocation_notional": round8(allocation_notional),
        "expected_alpha_contribution": round8(expected_alpha_contribution),
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "simulation_role": "SHADOW_PORTFOLIO_ALLOCATION_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def exclusion_reason(gate: sqlite3.Row) -> str:
    if safety_problem(gate):
        return "Excluded because source gate violates safety invariants."

    if str(gate["candidate_gate_status"]) == GATE_SAFETY:
        return "Excluded because candidate gate is safety blocked."

    if str(gate["candidate_gate_status"]) == GATE_BLOCK:
        return "Excluded because candidate is blocked by regime gate."

    if str(gate["candidate_gate_status"]) == GATE_WATCH:
        return "Excluded from portfolio allocation because candidate is watchlist-only by regime."

    if safe_int(gate["promotion_eligible"]) != 1:
        return "Excluded because candidate is not promotion eligible."

    if safe_float(gate["alpha_score"]) <= 0:
        return "Excluded because alpha score is non-positive."

    return "Excluded by portfolio allocation rules."


def allocate_weights_with_caps(
    eligible: list[sqlite3.Row],
    max_symbol_weight: float,
    max_strategy_weight: float,
    max_candidate_weight: float,
) -> dict[str, float]:
    scores = {str(row["gate_id"]): raw_candidate_score(row) for row in eligible}
    weights = {str(row["gate_id"]): 0.0 for row in eligible}

    if not eligible or sum(scores.values()) <= 0:
        return weights

    by_gate = {str(row["gate_id"]): row for row in eligible}
    remaining = 1.0

    for _ in range(100):
        available_ids = []

        symbol_weights: dict[str, float] = defaultdict(float)
        strategy_weights: dict[str, float] = defaultdict(float)

        for gate_id, weight in weights.items():
            row = by_gate[gate_id]
            symbol_weights[str(row["symbol"])] += weight
            strategy_weights[str(row["strategy_id"])] += weight

        for gate_id, row in by_gate.items():
            symbol_capacity = max_symbol_weight - symbol_weights[str(row["symbol"])]
            strategy_capacity = max_strategy_weight - strategy_weights[str(row["strategy_id"])]
            candidate_capacity = max_candidate_weight - weights[gate_id]
            capacity = min(symbol_capacity, strategy_capacity, candidate_capacity)

            if capacity > 0.00000001 and scores[gate_id] > 0:
                available_ids.append(gate_id)

        if remaining <= 0.00000001 or not available_ids:
            break

        total_available_score = sum(scores[gate_id] for gate_id in available_ids)
        if total_available_score <= 0:
            break

        progress = 0.0

        for gate_id in available_ids:
            row = by_gate[gate_id]

            symbol_used = sum(
                weights[item_id]
                for item_id, item in by_gate.items()
                if str(item["symbol"]) == str(row["symbol"])
            )
            strategy_used = sum(
                weights[item_id]
                for item_id, item in by_gate.items()
                if str(item["strategy_id"]) == str(row["strategy_id"])
            )

            capacity = min(
                max_symbol_weight - symbol_used,
                max_strategy_weight - strategy_used,
                max_candidate_weight - weights[gate_id],
            )

            if capacity <= 0:
                continue

            proposed = remaining * (scores[gate_id] / total_available_score)
            addition = min(proposed, capacity)

            if addition > 0:
                weights[gate_id] += addition
                progress += addition

        remaining = max(0.0, 1.0 - sum(weights.values()))

        if progress <= 0.00000001:
            break

    return {gate_id: round8(weight) for gate_id, weight in weights.items()}


def build_allocations(
    portfolio_label: str,
    created_at: str,
    shadow_notional: float,
    gates: list[sqlite3.Row],
    max_symbol_weight: float,
    max_strategy_weight: float,
    max_candidate_weight: float,
) -> list[dict[str, Any]]:
    eligible = [gate for gate in gates if gate_is_eligible(gate)]
    weights = allocate_weights_with_caps(
        eligible,
        max_symbol_weight=max_symbol_weight,
        max_strategy_weight=max_strategy_weight,
        max_candidate_weight=max_candidate_weight,
    )

    allocations = []

    for gate in gates:
        gate_id = str(gate["gate_id"])

        if gate in eligible:
            weight = weights.get(gate_id, 0.0)
            status = ALLOC_INCLUDED if weight > 0 else ALLOC_EXCLUDED
            reason = "Included in shadow portfolio allocation." if weight > 0 else "Eligible but no remaining allocation capacity."
            allocations.append(
                build_base_allocation_record(
                    portfolio_label=portfolio_label,
                    created_at=created_at,
                    shadow_notional=shadow_notional,
                    gate=gate,
                    allocation_status=status,
                    reason=reason,
                    raw_score=raw_candidate_score(gate),
                    allocation_weight=weight,
                )
            )
        else:
            allocations.append(
                build_base_allocation_record(
                    portfolio_label=portfolio_label,
                    created_at=created_at,
                    shadow_notional=shadow_notional,
                    gate=gate,
                    allocation_status=ALLOC_EXCLUDED,
                    reason=exclusion_reason(gate),
                    raw_score=raw_candidate_score(gate),
                    allocation_weight=0.0,
                )
            )

    allocations.sort(
        key=lambda item: (
            item["allocation_status"] == ALLOC_INCLUDED,
            item["allocation_weight"],
            item["alpha_score"],
        ),
        reverse=True,
    )

    return allocations


def exposure_by_key(allocations: list[dict[str, Any]], key: str) -> dict[str, float]:
    exposures: dict[str, float] = defaultdict(float)

    for item in allocations:
        if item["allocation_status"] == ALLOC_INCLUDED:
            exposures[str(item[key])] += safe_float(item["allocation_weight"])

    return {name: round8(weight) for name, weight in sorted(exposures.items())}


def portfolio_risk_rating(
    max_symbol_observed: float,
    max_strategy_observed: float,
    unallocated_weight: float,
    estimated_drawdown_pct: float,
) -> str:
    if max_symbol_observed > 0.7 or max_strategy_observed > 0.7 or estimated_drawdown_pct > 8:
        return RISK_HIGH

    if max_symbol_observed > 0.55 or max_strategy_observed > 0.55 or unallocated_weight > 0.25:
        return RISK_MODERATE

    return RISK_LOW


def summarize_portfolio(
    db_path: str | Path,
    portfolio_label: str,
    report_label: str,
    created_at: str,
    regime_label: str,
    requested_symbols: list[str] | None,
    shadow_notional: float,
    max_symbol_weight: float,
    max_strategy_weight: float,
    max_candidate_weight: float,
    gates: list[sqlite3.Row],
    allocations: list[dict[str, Any]],
) -> dict[str, Any]:
    included = [item for item in allocations if item["allocation_status"] == ALLOC_INCLUDED]
    excluded = [item for item in allocations if item["allocation_status"] == ALLOC_EXCLUDED]

    symbol_exposure = exposure_by_key(allocations, "symbol")
    strategy_exposure = exposure_by_key(allocations, "strategy_id")

    total_allocated_weight = round8(sum(item["allocation_weight"] for item in included))
    unallocated_weight = round8(max(0.0, 1.0 - total_allocated_weight))
    allocated_notional = round8(total_allocated_weight * shadow_notional)
    weighted_alpha = round8(sum(item["expected_alpha_contribution"] for item in included))

    max_symbol_observed = round8(max(symbol_exposure.values()) if symbol_exposure else 0.0)
    max_strategy_observed = round8(max(strategy_exposure.values()) if strategy_exposure else 0.0)

    top_symbol = max(symbol_exposure, key=symbol_exposure.get) if symbol_exposure else None
    top_strategy = max(strategy_exposure, key=strategy_exposure.get) if strategy_exposure else None

    concentration_score = round8(max(max_symbol_observed, max_strategy_observed) * 100.0)
    estimated_drawdown_pct = round8(
        max(
            0.0,
            max_symbol_observed * 6.0
            + max_strategy_observed * 4.0
            + unallocated_weight * 1.5
        )
    )

    risk_rating = portfolio_risk_rating(
        max_symbol_observed=max_symbol_observed,
        max_strategy_observed=max_strategy_observed,
        unallocated_weight=unallocated_weight,
        estimated_drawdown_pct=estimated_drawdown_pct,
    )

    safety_count = sum(1 for item in allocations if safety_problem(item))

    if safety_count > 0:
        verdict = PORTFOLIO_SAFETY_BLOCKED
        action = ACTION_STOP
    elif not included:
        verdict = PORTFOLIO_NO_ELIGIBLE
        action = ACTION_REFRESH
    elif risk_rating == RISK_HIGH or unallocated_weight > 0.35:
        verdict = PORTFOLIO_CONSTRAINED
        action = ACTION_CONTINUE
    else:
        verdict = PORTFOLIO_READY
        action = ACTION_REVIEW

    candidate_gate_counts = Counter(str(gate["candidate_gate_status"]) for gate in gates)
    allocation_counts = Counter(item["allocation_status"] for item in allocations)

    return {
        "portfolio_label": portfolio_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_regime_label": regime_label,
        "requested_symbol_count": len(requested_symbols) if requested_symbols else 0,
        "shadow_notional": round8(shadow_notional),
        "source_gate_count": len(gates),
        "eligible_candidate_count": sum(1 for gate in gates if gate_is_eligible(gate)),
        "included_allocation_count": len(included),
        "excluded_candidate_count": len(excluded),
        "total_allocated_weight": total_allocated_weight,
        "unallocated_weight": unallocated_weight,
        "allocated_notional": allocated_notional,
        "weighted_alpha_score": weighted_alpha,
        "max_symbol_weight": round8(max_symbol_weight),
        "max_strategy_weight": round8(max_strategy_weight),
        "max_candidate_weight": round8(max_candidate_weight),
        "observed_max_symbol_weight": max_symbol_observed,
        "observed_max_strategy_weight": max_strategy_observed,
        "symbol_exposure": symbol_exposure,
        "strategy_exposure": strategy_exposure,
        "top_symbol": top_symbol,
        "top_strategy_id": top_strategy,
        "concentration_score": concentration_score,
        "estimated_shadow_drawdown_pct": estimated_drawdown_pct,
        "portfolio_risk_rating": risk_rating,
        "candidate_gate_counts": dict(candidate_gate_counts),
        "allocation_counts": dict(allocation_counts),
        "allocations": allocations,
        "included_allocations": included,
        "excluded_allocations": excluded[:20],
        "safety_breach_count": safety_count,
        "global_verdict": verdict,
        "recommended_action": action,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    included_lines = []

    for item in summary["included_allocations"]:
        included_lines.append(
            "- "
            + f"{item['strategy_id']} {item['symbol']}: "
            + f"weight={item['allocation_weight']}, "
            + f"notional={item['allocation_notional']}, "
            + f"alpha_contribution={item['expected_alpha_contribution']}, "
            + f"gate={item['candidate_gate_status']}"
        )

    excluded_lines = []

    for item in summary["excluded_allocations"][:10]:
        excluded_lines.append(
            "- "
            + f"{item['strategy_id']} {item['symbol']}: "
            + f"reason={item['allocation_reason']}"
        )

    included_markdown = "\n".join(included_lines) or "- None"
    excluded_markdown = "\n".join(excluded_lines) or "- None"

    return f"""# DeltaGrid Mission 61 Shadow Portfolio Simulator Report

Report label: {summary['report_label']}
Portfolio label: {summary['portfolio_label']}
Created at: {summary['created_at']}
Source regime label: {summary['source_regime_label']}

## Portfolio Summary

Shadow notional: {summary['shadow_notional']}
Source gate count: {summary['source_gate_count']}
Eligible candidate count: {summary['eligible_candidate_count']}
Included allocation count: {summary['included_allocation_count']}
Excluded candidate count: {summary['excluded_candidate_count']}

Total allocated weight: {summary['total_allocated_weight']}
Unallocated weight: {summary['unallocated_weight']}
Allocated notional: {summary['allocated_notional']}
Weighted alpha score: {summary['weighted_alpha_score']}

Observed max symbol weight: {summary['observed_max_symbol_weight']}
Observed max strategy weight: {summary['observed_max_strategy_weight']}
Concentration score: {summary['concentration_score']}
Estimated shadow drawdown pct: {summary['estimated_shadow_drawdown_pct']}
Portfolio risk rating: {summary['portfolio_risk_rating']}

Top symbol: {summary['top_symbol']}
Top strategy: {summary['top_strategy_id']}

## Included Allocations

{included_markdown}

## Excluded Candidates

{excluded_markdown}

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


def persist_allocations(db_path: str | Path, allocations: list[dict[str, Any]]) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for item in allocations:
            conn.execute(
                """
                INSERT OR REPLACE INTO shadow_portfolio_allocations (
                    allocation_id,
                    portfolio_label,
                    created_at,
                    source_regime_label,
                    source_gate_id,
                    source_candidate_id,
                    strategy_id,
                    symbol,
                    candidate_status,
                    candidate_gate_status,
                    allocation_status,
                    allocation_reason,
                    promotion_eligible,
                    alpha_score,
                    data_quality_score,
                    market_risk_state,
                    raw_score,
                    allocation_weight,
                    allocation_notional,
                    expected_alpha_contribution,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["allocation_id"],
                    item["portfolio_label"],
                    item["created_at"],
                    item["source_regime_label"],
                    item["source_gate_id"],
                    item["source_candidate_id"],
                    item["strategy_id"],
                    item["symbol"],
                    item["candidate_status"],
                    item["candidate_gate_status"],
                    item["allocation_status"],
                    item["allocation_reason"],
                    item["promotion_eligible"],
                    str(item["alpha_score"]),
                    str(item["data_quality_score"]),
                    item["market_risk_state"],
                    str(item["raw_score"]),
                    str(item["allocation_weight"]),
                    str(item["allocation_notional"]),
                    str(item["expected_alpha_contribution"]),
                    item["live_trading"],
                    item["live_order_sent"],
                    item["capital_deployment"],
                    json.dumps(item["metadata"], sort_keys=True),
                ),
            )

        conn.commit()


def persist_simulation_and_risk(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    risk_notes = []
    if summary["unallocated_weight"] > 0:
        risk_notes.append("Some shadow notional remains unallocated due exposure constraints.")
    if summary["portfolio_risk_rating"] != RISK_LOW:
        risk_notes.append("Portfolio concentration or allocation constraints require review.")
    if not risk_notes:
        risk_notes.append("Portfolio simulation remains inside configured shadow caps.")

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO shadow_portfolio_simulations (
                portfolio_label,
                report_label,
                created_at,
                source_regime_label,
                shadow_notional,
                requested_symbol_count,
                source_gate_count,
                eligible_candidate_count,
                included_allocation_count,
                excluded_candidate_count,
                total_allocated_weight,
                unallocated_weight,
                allocated_notional,
                weighted_alpha_score,
                max_symbol_weight,
                max_strategy_weight,
                max_candidate_weight,
                concentration_score,
                estimated_shadow_drawdown_pct,
                portfolio_risk_rating,
                global_verdict,
                recommended_action,
                live_trading,
                live_order_sent,
                capital_deployment,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["portfolio_label"],
                summary["report_label"],
                summary["created_at"],
                summary["source_regime_label"],
                str(summary["shadow_notional"]),
                summary["requested_symbol_count"],
                summary["source_gate_count"],
                summary["eligible_candidate_count"],
                summary["included_allocation_count"],
                summary["excluded_candidate_count"],
                str(summary["total_allocated_weight"]),
                str(summary["unallocated_weight"]),
                str(summary["allocated_notional"]),
                str(summary["weighted_alpha_score"]),
                str(summary["max_symbol_weight"]),
                str(summary["max_strategy_weight"]),
                str(summary["max_candidate_weight"]),
                str(summary["concentration_score"]),
                str(summary["estimated_shadow_drawdown_pct"]),
                summary["portfolio_risk_rating"],
                summary["global_verdict"],
                summary["recommended_action"],
                LIVE_TRADING_STATUS,
                LIVE_ORDER_SENT_VALUE,
                CAPITAL_DEPLOYMENT_STATUS,
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.execute(
            """
            INSERT OR REPLACE INTO shadow_portfolio_risk_reports (
                risk_report_id,
                portfolio_label,
                report_label,
                created_at,
                symbol_exposure_json,
                strategy_exposure_json,
                top_symbol,
                top_strategy_id,
                max_symbol_weight,
                max_strategy_weight,
                concentration_score,
                estimated_shadow_drawdown_pct,
                portfolio_risk_rating,
                risk_notes_json,
                live_trading,
                live_order_sent,
                capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{summary['portfolio_label']}-risk-report",
                summary["portfolio_label"],
                summary["report_label"],
                summary["created_at"],
                json.dumps(summary["symbol_exposure"], sort_keys=True),
                json.dumps(summary["strategy_exposure"], sort_keys=True),
                summary["top_symbol"],
                summary["top_strategy_id"],
                str(summary["observed_max_symbol_weight"]),
                str(summary["observed_max_strategy_weight"]),
                str(summary["concentration_score"]),
                str(summary["estimated_shadow_drawdown_pct"]),
                summary["portfolio_risk_rating"],
                json.dumps(risk_notes, sort_keys=True),
                LIVE_TRADING_STATUS,
                LIVE_ORDER_SENT_VALUE,
                CAPITAL_DEPLOYMENT_STATUS,
            ),
        )

        conn.commit()


def run_shadow_portfolio_simulator(
    db_path: str | Path = "offchain/deltagrid.db",
    portfolio_label: str | None = None,
    report_label: str | None = None,
    regime_label: str = "mission60-final-check",
    symbols: str | list[str] | tuple[str, ...] | None = None,
    shadow_notional: float = 100000.0,
    max_symbol_weight: float = 0.6,
    max_strategy_weight: float = 0.5,
    max_candidate_weight: float = 0.35,
) -> dict[str, Any]:
    if shadow_notional <= 0:
        raise ValueError("shadow_notional must be positive")

    for name, value in {
        "max_symbol_weight": max_symbol_weight,
        "max_strategy_weight": max_strategy_weight,
        "max_candidate_weight": max_candidate_weight,
    }.items():
        if value <= 0 or value > 1:
            raise ValueError(f"{name} must be between 0 and 1")

    db = Path(db_path)
    portfolio = portfolio_label or new_portfolio_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    requested_symbols = parse_symbols(symbols)

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        gates = load_candidate_gates(
            conn=conn,
            regime_label=regime_label,
            symbols=requested_symbols,
        )

    allocations = build_allocations(
        portfolio_label=portfolio,
        created_at=created_at,
        shadow_notional=shadow_notional,
        gates=gates,
        max_symbol_weight=max_symbol_weight,
        max_strategy_weight=max_strategy_weight,
        max_candidate_weight=max_candidate_weight,
    )

    summary = summarize_portfolio(
        db_path=db,
        portfolio_label=portfolio,
        report_label=report,
        created_at=created_at,
        regime_label=regime_label,
        requested_symbols=requested_symbols,
        shadow_notional=shadow_notional,
        max_symbol_weight=max_symbol_weight,
        max_strategy_weight=max_strategy_weight,
        max_candidate_weight=max_candidate_weight,
        gates=gates,
        allocations=allocations,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_allocations(db, allocations)
    persist_simulation_and_risk(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid shadow portfolio simulator."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--portfolio-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--regime-label", default="mission60-final-check")
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--shadow-notional", type=float, default=100000.0)
    parser.add_argument("--max-symbol-weight", type=float, default=0.6)
    parser.add_argument("--max-strategy-weight", type=float, default=0.5)
    parser.add_argument("--max-candidate-weight", type=float, default=0.35)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_shadow_portfolio_simulator(
        db_path=args.db,
        portfolio_label=args.portfolio_label,
        report_label=args.report_label,
        regime_label=args.regime_label,
        symbols=args.symbols,
        shadow_notional=args.shadow_notional,
        max_symbol_weight=args.max_symbol_weight,
        max_strategy_weight=args.max_strategy_weight,
        max_candidate_weight=args.max_candidate_weight,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

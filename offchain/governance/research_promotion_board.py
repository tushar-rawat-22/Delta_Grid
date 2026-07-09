"""
Mission 62: Research Promotion Board.

This module reviews a shadow portfolio simulation and makes a board-style
promotion decision.

It reads:
- shadow_portfolio_simulations
- shadow_portfolio_allocations
- shadow_portfolio_risk_reports

It writes:
- research_promotion_board_reviews
- research_promotion_board_evidence_items
- research_promotion_board_decision_records

It is governance and research review only.

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
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PORTFOLIO_TABLE = "shadow_portfolio_simulations"
ALLOCATIONS_TABLE = "shadow_portfolio_allocations"
RISK_REPORTS_TABLE = "shadow_portfolio_risk_reports"

BOARD_REVIEWS_TABLE = "research_promotion_board_reviews"
BOARD_EVIDENCE_TABLE = "research_promotion_board_evidence_items"
BOARD_DECISIONS_TABLE = "research_promotion_board_decision_records"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

PORTFOLIO_READY = "SHADOW_PORTFOLIO_SIMULATION_READY"
PORTFOLIO_CONSTRAINED = "SHADOW_PORTFOLIO_SIMULATION_CONSTRAINED"
PORTFOLIO_NO_ELIGIBLE = "SHADOW_PORTFOLIO_NO_ELIGIBLE_CANDIDATES"
PORTFOLIO_SAFETY_BLOCKED = "SHADOW_PORTFOLIO_SAFETY_BLOCKED"

RISK_LOW = "PORTFOLIO_RISK_LOW"
RISK_MODERATE = "PORTFOLIO_RISK_MODERATE"
RISK_HIGH = "PORTFOLIO_RISK_HIGH"

DECISION_APPROVE_PAPER = "RESEARCH_BOARD_APPROVED_FOR_PAPER_SANDBOX_SHADOW_ONLY"
DECISION_WATCHLIST = "RESEARCH_BOARD_WATCHLIST_MORE_SHADOW_DATA"
DECISION_BLOCK_RISK = "RESEARCH_BOARD_BLOCKED_BY_PORTFOLIO_RISK"
DECISION_BLOCK_SAFETY = "RESEARCH_BOARD_BLOCKED_BY_SAFETY_POLICY"
DECISION_REJECT_MISSING = "RESEARCH_BOARD_REJECTED_MISSING_EVIDENCE"

BOARD_READY = "RESEARCH_PROMOTION_BOARD_REVIEW_READY"
BOARD_WATCHLIST = "RESEARCH_PROMOTION_BOARD_REVIEW_WATCHLIST"
BOARD_BLOCKED = "RESEARCH_PROMOTION_BOARD_REVIEW_BLOCKED"
BOARD_MISSING = "RESEARCH_PROMOTION_BOARD_REVIEW_MISSING_EVIDENCE"

ACTION_OPEN_PAPER_SANDBOX = "OPEN_PAPER_SANDBOX_RESEARCH_ONLY"
ACTION_CONTINUE_SHADOW = "CONTINUE_SHADOW_OBSERVATION_AND_REVIEW"
ACTION_REDUCE_RISK = "REDUCE_PORTFOLIO_RISK_AND_RERUN_BOARD"
ACTION_STOP = "STOP_AND_REVIEW_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_PORTFOLIO_EVIDENCE_AND_RERUN_BOARD"

EVIDENCE_PASS = "EVIDENCE_PASS"
EVIDENCE_WARN = "EVIDENCE_WARN"
EVIDENCE_FAIL = "EVIDENCE_FAIL"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_review_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission62-board-review-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission62-board-report-{stamp}-{uuid.uuid4().hex[:8]}"


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


def row_get(row: sqlite3.Row | dict[str, Any], key: str, default: Any = None) -> Any:
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
            CREATE TABLE IF NOT EXISTS research_promotion_board_reviews (
                review_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_portfolio_label TEXT NOT NULL,
                source_regime_label TEXT,
                evidence_item_count INTEGER NOT NULL,
                pass_evidence_count INTEGER NOT NULL,
                warn_evidence_count INTEGER NOT NULL,
                fail_evidence_count INTEGER NOT NULL,
                included_allocation_count INTEGER NOT NULL,
                excluded_candidate_count INTEGER NOT NULL,
                weighted_alpha_score TEXT NOT NULL,
                concentration_score TEXT NOT NULL,
                estimated_shadow_drawdown_pct TEXT NOT NULL,
                portfolio_risk_rating TEXT NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                board_decision TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS research_promotion_board_evidence_items (
                evidence_id TEXT PRIMARY KEY,
                review_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_portfolio_label TEXT NOT NULL,
                evidence_category TEXT NOT NULL,
                evidence_name TEXT NOT NULL,
                evidence_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                required_value TEXT NOT NULL,
                evidence_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS research_promotion_board_decision_records (
                decision_id TEXT PRIMARY KEY,
                review_label TEXT NOT NULL,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_portfolio_label TEXT NOT NULL,
                board_decision TEXT NOT NULL,
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


def load_portfolio(conn: sqlite3.Connection, portfolio_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, PORTFOLIO_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM shadow_portfolio_simulations
        WHERE portfolio_label = ?
        """,
        (portfolio_label,),
    ).fetchone()


def load_allocations(conn: sqlite3.Connection, portfolio_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, ALLOCATIONS_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM shadow_portfolio_allocations
        WHERE portfolio_label = ?
        ORDER BY CAST(allocation_weight AS REAL) DESC
        """,
        (portfolio_label,),
    ).fetchall()


def load_risk_report(conn: sqlite3.Connection, portfolio_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, RISK_REPORTS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM shadow_portfolio_risk_reports
        WHERE portfolio_label = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (portfolio_label,),
    ).fetchone()


def safety_problem(row: sqlite3.Row | dict[str, Any]) -> bool:
    return (
        str(row["live_trading"]) != LIVE_TRADING_STATUS
        or safe_int(row["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or str(row["capital_deployment"]) != CAPITAL_DEPLOYMENT_STATUS
    )


def evidence_item(
    review_label: str,
    created_at: str,
    portfolio_label: str,
    category: str,
    name: str,
    status: str,
    observed_value: Any,
    required_value: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "evidence_id": f"{review_label}-{category}-{name}".replace(" ", "_"),
        "review_label": review_label,
        "created_at": created_at,
        "source_portfolio_label": portfolio_label,
        "evidence_category": category,
        "evidence_name": name,
        "evidence_status": status,
        "observed_value": str(observed_value),
        "required_value": str(required_value),
        "evidence_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "board_role": "RESEARCH_PROMOTION_EVIDENCE_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
        },
    }


def build_missing_evidence(
    review_label: str,
    created_at: str,
    portfolio_label: str,
) -> list[dict[str, Any]]:
    return [
        evidence_item(
            review_label,
            created_at,
            portfolio_label,
            "availability",
            "portfolio evidence exists",
            EVIDENCE_FAIL,
            "missing",
            "portfolio simulation record",
            "No portfolio simulation record exists for this portfolio label.",
        )
    ]


def build_evidence_items(
    review_label: str,
    created_at: str,
    portfolio: sqlite3.Row,
    allocations: list[sqlite3.Row],
    risk_report: sqlite3.Row | None,
    min_included_allocations: int,
    min_weighted_alpha_score: float,
    max_concentration_score: float,
    max_shadow_drawdown_pct: float,
) -> list[dict[str, Any]]:
    portfolio_label = str(portfolio["portfolio_label"])

    safety_count = safe_int(row_get(portfolio, "safety_breach_count", 0))
    allocation_safety_count = sum(1 for row in allocations if safety_problem(row))
    risk_safety_count = 1 if risk_report is not None and safety_problem(risk_report) else 0
    total_safety = safety_count + allocation_safety_count + risk_safety_count

    evidence = []

    evidence.append(
        evidence_item(
            review_label,
            created_at,
            portfolio_label,
            "safety",
            "safety invariants",
            EVIDENCE_PASS if total_safety == 0 and not safety_problem(portfolio) else EVIDENCE_FAIL,
            total_safety,
            0,
            "All safety invariants must remain clean.",
        )
    )

    evidence.append(
        evidence_item(
            review_label,
            created_at,
            portfolio_label,
            "portfolio",
            "portfolio verdict",
            EVIDENCE_PASS if str(portfolio["global_verdict"]) == PORTFOLIO_READY else EVIDENCE_WARN,
            str(portfolio["global_verdict"]),
            PORTFOLIO_READY,
            "Portfolio simulation should be ready before paper sandbox review.",
        )
    )

    included = safe_int(portfolio["included_allocation_count"])
    evidence.append(
        evidence_item(
            review_label,
            created_at,
            portfolio_label,
            "portfolio",
            "included allocation count",
            EVIDENCE_PASS if included >= min_included_allocations else EVIDENCE_FAIL,
            included,
            f">= {min_included_allocations}",
            "A portfolio needs enough included allocations to avoid single-candidate dependence.",
        )
    )

    weighted_alpha = safe_float(portfolio["weighted_alpha_score"])
    evidence.append(
        evidence_item(
            review_label,
            created_at,
            portfolio_label,
            "alpha",
            "weighted alpha score",
            EVIDENCE_PASS if weighted_alpha >= min_weighted_alpha_score else EVIDENCE_WARN,
            round8(weighted_alpha),
            f">= {min_weighted_alpha_score}",
            "Weighted alpha should clear the research board threshold.",
        )
    )

    concentration = safe_float(portfolio["concentration_score"])
    evidence.append(
        evidence_item(
            review_label,
            created_at,
            portfolio_label,
            "risk",
            "concentration score",
            EVIDENCE_PASS if concentration <= max_concentration_score else EVIDENCE_FAIL,
            round8(concentration),
            f"<= {max_concentration_score}",
            "Portfolio concentration must remain below board threshold.",
        )
    )

    drawdown = safe_float(portfolio["estimated_shadow_drawdown_pct"])
    evidence.append(
        evidence_item(
            review_label,
            created_at,
            portfolio_label,
            "risk",
            "estimated shadow drawdown pct",
            EVIDENCE_PASS if drawdown <= max_shadow_drawdown_pct else EVIDENCE_FAIL,
            round8(drawdown),
            f"<= {max_shadow_drawdown_pct}",
            "Estimated shadow drawdown must be acceptable for paper sandbox review.",
        )
    )

    risk_rating = str(portfolio["portfolio_risk_rating"])
    risk_status = EVIDENCE_PASS if risk_rating in {RISK_LOW, RISK_MODERATE} else EVIDENCE_FAIL
    evidence.append(
        evidence_item(
            review_label,
            created_at,
            portfolio_label,
            "risk",
            "portfolio risk rating",
            risk_status,
            risk_rating,
            f"{RISK_LOW} or {RISK_MODERATE}",
            "High-risk portfolios cannot advance to the paper sandbox.",
        )
    )

    total_allocated_weight = safe_float(portfolio["total_allocated_weight"])
    evidence.append(
        evidence_item(
            review_label,
            created_at,
            portfolio_label,
            "allocation",
            "total allocated weight",
            EVIDENCE_PASS if total_allocated_weight >= 0.95 else EVIDENCE_WARN,
            round8(total_allocated_weight),
            ">= 0.95",
            "Most shadow notional should be allocated unless caps intentionally constrain it.",
        )
    )

    if risk_report is None:
        evidence.append(
            evidence_item(
                review_label,
                created_at,
                portfolio_label,
                "risk",
                "risk report exists",
                EVIDENCE_WARN,
                "missing",
                "risk report",
                "Portfolio risk report is missing.",
            )
        )
    else:
        evidence.append(
            evidence_item(
                review_label,
                created_at,
                portfolio_label,
                "risk",
                "risk report exists",
                EVIDENCE_PASS,
                "present",
                "risk report",
                "Portfolio risk report exists.",
            )
        )

    return evidence


def decide_board_outcome(evidence: list[dict[str, Any]], portfolio: sqlite3.Row | None) -> tuple[str, str, str, str]:
    if portfolio is None:
        return (
            DECISION_REJECT_MISSING,
            BOARD_MISSING,
            ACTION_REFRESH,
            "Portfolio evidence is missing.",
        )

    status_counts = Counter(item["evidence_status"] for item in evidence)
    fail_count = status_counts.get(EVIDENCE_FAIL, 0)
    warn_count = status_counts.get(EVIDENCE_WARN, 0)

    if any(item["evidence_category"] == "safety" and item["evidence_status"] == EVIDENCE_FAIL for item in evidence):
        return (
            DECISION_BLOCK_SAFETY,
            BOARD_BLOCKED,
            ACTION_STOP,
            "Safety evidence failed.",
        )

    if fail_count > 0:
        return (
            DECISION_BLOCK_RISK,
            BOARD_BLOCKED,
            ACTION_REDUCE_RISK,
            "One or more risk or evidence requirements failed.",
        )

    if warn_count > 1:
        return (
            DECISION_WATCHLIST,
            BOARD_WATCHLIST,
            ACTION_CONTINUE_SHADOW,
            "Board review found warnings that require more shadow observation.",
        )

    return (
        DECISION_APPROVE_PAPER,
        BOARD_READY,
        ACTION_OPEN_PAPER_SANDBOX,
        "Portfolio evidence passes board thresholds for paper sandbox research only.",
    )


def build_summary(
    db_path: str | Path,
    review_label: str,
    report_label: str,
    created_at: str,
    portfolio_label: str,
    portfolio: sqlite3.Row | None,
    allocations: list[sqlite3.Row],
    risk_report: sqlite3.Row | None,
    evidence: list[dict[str, Any]],
    board_decision: str,
    global_verdict: str,
    recommended_action: str,
    decision_reason: str,
) -> dict[str, Any]:
    counts = Counter(item["evidence_status"] for item in evidence)

    if portfolio is None:
        source_regime_label = None
        included_allocation_count = 0
        excluded_candidate_count = 0
        weighted_alpha_score = 0.0
        concentration_score = 0.0
        estimated_shadow_drawdown_pct = 0.0
        portfolio_risk_rating = "UNKNOWN"
        safety_breach_count = 0
    else:
        source_regime_label = str(portfolio["source_regime_label"])
        included_allocation_count = safe_int(portfolio["included_allocation_count"])
        excluded_candidate_count = safe_int(portfolio["excluded_candidate_count"])
        weighted_alpha_score = round8(safe_float(portfolio["weighted_alpha_score"]))
        concentration_score = round8(safe_float(portfolio["concentration_score"]))
        estimated_shadow_drawdown_pct = round8(safe_float(portfolio["estimated_shadow_drawdown_pct"]))
        portfolio_risk_rating = str(portfolio["portfolio_risk_rating"])
        safety_breach_count = safe_int(row_get(portfolio, "safety_breach_count", 0))

    allocation_counts = Counter(str(row["allocation_status"]) for row in allocations)
    strategy_counts = Counter(str(row["strategy_id"]) for row in allocations if safe_float(row["allocation_weight"]) > 0)
    symbol_counts = Counter(str(row["symbol"]) for row in allocations if safe_float(row["allocation_weight"]) > 0)

    next_mission = "Mission 63: Paper Trading Sandbox" if board_decision == DECISION_APPROVE_PAPER else "Mission 61/62 remediation"

    return {
        "review_label": review_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_portfolio_label": portfolio_label,
        "source_regime_label": source_regime_label,
        "evidence_item_count": len(evidence),
        "pass_evidence_count": counts.get(EVIDENCE_PASS, 0),
        "warn_evidence_count": counts.get(EVIDENCE_WARN, 0),
        "fail_evidence_count": counts.get(EVIDENCE_FAIL, 0),
        "included_allocation_count": included_allocation_count,
        "excluded_candidate_count": excluded_candidate_count,
        "weighted_alpha_score": weighted_alpha_score,
        "concentration_score": concentration_score,
        "estimated_shadow_drawdown_pct": estimated_shadow_drawdown_pct,
        "portfolio_risk_rating": portfolio_risk_rating,
        "safety_breach_count": safety_breach_count,
        "allocation_status_counts": dict(allocation_counts),
        "included_strategy_counts": dict(strategy_counts),
        "included_symbol_counts": dict(symbol_counts),
        "evidence_items": evidence,
        "board_decision": board_decision,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
        "decision_reason": decision_reason,
        "next_mission": next_mission,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    evidence_lines = []

    for item in summary["evidence_items"]:
        evidence_lines.append(
            "- "
            + f"{item['evidence_category']} / {item['evidence_name']}: "
            + f"status={item['evidence_status']}, "
            + f"observed={item['observed_value']}, "
            + f"required={item['required_value']}"
        )

    evidence_markdown = "\n".join(evidence_lines) or "- None"

    return f"""# DeltaGrid Mission 62 Research Promotion Board Report

Report label: {summary['report_label']}
Review label: {summary['review_label']}
Created at: {summary['created_at']}
Source portfolio label: {summary['source_portfolio_label']}
Source regime label: {summary['source_regime_label']}

## Board Summary

Evidence item count: {summary['evidence_item_count']}
Pass evidence count: {summary['pass_evidence_count']}
Warn evidence count: {summary['warn_evidence_count']}
Fail evidence count: {summary['fail_evidence_count']}

Included allocation count: {summary['included_allocation_count']}
Excluded candidate count: {summary['excluded_candidate_count']}
Weighted alpha score: {summary['weighted_alpha_score']}
Concentration score: {summary['concentration_score']}
Estimated shadow drawdown pct: {summary['estimated_shadow_drawdown_pct']}
Portfolio risk rating: {summary['portfolio_risk_rating']}
Safety breach count: {summary['safety_breach_count']}

## Evidence

{evidence_markdown}

## Decision

Board decision: {summary['board_decision']}
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

Approval scope, if approved, is paper sandbox research only.
It is not approval for live trading or real capital.
"""


def persist_review(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for item in summary["evidence_items"]:
            conn.execute(
                """
                INSERT OR REPLACE INTO research_promotion_board_evidence_items (
                    evidence_id,
                    review_label,
                    created_at,
                    source_portfolio_label,
                    evidence_category,
                    evidence_name,
                    evidence_status,
                    observed_value,
                    required_value,
                    evidence_reason,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["evidence_id"],
                    item["review_label"],
                    item["created_at"],
                    item["source_portfolio_label"],
                    item["evidence_category"],
                    item["evidence_name"],
                    item["evidence_status"],
                    item["observed_value"],
                    item["required_value"],
                    item["evidence_reason"],
                    item["live_trading"],
                    item["live_order_sent"],
                    item["capital_deployment"],
                    json.dumps(item["metadata"], sort_keys=True),
                ),
            )

        conn.execute(
            """
            INSERT OR REPLACE INTO research_promotion_board_reviews (
                review_label,
                report_label,
                created_at,
                source_portfolio_label,
                source_regime_label,
                evidence_item_count,
                pass_evidence_count,
                warn_evidence_count,
                fail_evidence_count,
                included_allocation_count,
                excluded_candidate_count,
                weighted_alpha_score,
                concentration_score,
                estimated_shadow_drawdown_pct,
                portfolio_risk_rating,
                safety_breach_count,
                board_decision,
                global_verdict,
                recommended_action,
                next_mission,
                live_trading,
                live_order_sent,
                capital_deployment,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["review_label"],
                summary["report_label"],
                summary["created_at"],
                summary["source_portfolio_label"],
                summary["source_regime_label"],
                summary["evidence_item_count"],
                summary["pass_evidence_count"],
                summary["warn_evidence_count"],
                summary["fail_evidence_count"],
                summary["included_allocation_count"],
                summary["excluded_candidate_count"],
                str(summary["weighted_alpha_score"]),
                str(summary["concentration_score"]),
                str(summary["estimated_shadow_drawdown_pct"]),
                summary["portfolio_risk_rating"],
                summary["safety_breach_count"],
                summary["board_decision"],
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
            INSERT OR REPLACE INTO research_promotion_board_decision_records (
                decision_id,
                review_label,
                report_label,
                created_at,
                source_portfolio_label,
                board_decision,
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
                summary["source_portfolio_label"],
                summary["board_decision"],
                summary["global_verdict"],
                summary["recommended_action"],
                "PAPER_SANDBOX_RESEARCH_ONLY",
                "NOT_LIVE_TRADING_NOT_REAL_CAPITAL",
                summary["decision_reason"],
                LIVE_TRADING_STATUS,
                LIVE_ORDER_SENT_VALUE,
                CAPITAL_DEPLOYMENT_STATUS,
                json.dumps(
                    {
                        "board_role": "RESEARCH_PROMOTION_DECISION_ONLY",
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


def run_research_promotion_board(
    db_path: str | Path = "offchain/deltagrid.db",
    review_label: str | None = None,
    report_label: str | None = None,
    portfolio_label: str = "mission61-final-check",
    min_included_allocations: int = 3,
    min_weighted_alpha_score: float = 50.0,
    max_concentration_score: float = 65.0,
    max_shadow_drawdown_pct: float = 6.5,
) -> dict[str, Any]:
    if min_included_allocations <= 0:
        raise ValueError("min_included_allocations must be positive")

    if min_weighted_alpha_score < 0:
        raise ValueError("min_weighted_alpha_score cannot be negative")

    if max_concentration_score <= 0:
        raise ValueError("max_concentration_score must be positive")

    if max_shadow_drawdown_pct <= 0:
        raise ValueError("max_shadow_drawdown_pct must be positive")

    db = Path(db_path)
    review = review_label or new_review_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        portfolio = load_portfolio(conn, portfolio_label)
        allocations = load_allocations(conn, portfolio_label)
        risk_report = load_risk_report(conn, portfolio_label)

    if portfolio is None:
        evidence = build_missing_evidence(review, created_at, portfolio_label)
    else:
        evidence = build_evidence_items(
            review_label=review,
            created_at=created_at,
            portfolio=portfolio,
            allocations=allocations,
            risk_report=risk_report,
            min_included_allocations=min_included_allocations,
            min_weighted_alpha_score=min_weighted_alpha_score,
            max_concentration_score=max_concentration_score,
            max_shadow_drawdown_pct=max_shadow_drawdown_pct,
        )

    board_decision, global_verdict, recommended_action, decision_reason = decide_board_outcome(
        evidence=evidence,
        portfolio=portfolio,
    )

    summary = build_summary(
        db_path=db,
        review_label=review,
        report_label=report,
        created_at=created_at,
        portfolio_label=portfolio_label,
        portfolio=portfolio,
        allocations=allocations,
        risk_report=risk_report,
        evidence=evidence,
        board_decision=board_decision,
        global_verdict=global_verdict,
        recommended_action=recommended_action,
        decision_reason=decision_reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_review(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid research promotion board.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--review-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--portfolio-label", default="mission61-final-check")
    parser.add_argument("--min-included-allocations", type=int, default=3)
    parser.add_argument("--min-weighted-alpha-score", type=float, default=50.0)
    parser.add_argument("--max-concentration-score", type=float, default=65.0)
    parser.add_argument("--max-shadow-drawdown-pct", type=float, default=6.5)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_research_promotion_board(
        db_path=args.db,
        review_label=args.review_label,
        report_label=args.report_label,
        portfolio_label=args.portfolio_label,
        min_included_allocations=args.min_included_allocations,
        min_weighted_alpha_score=args.min_weighted_alpha_score,
        max_concentration_score=args.max_concentration_score,
        max_shadow_drawdown_pct=args.max_shadow_drawdown_pct,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

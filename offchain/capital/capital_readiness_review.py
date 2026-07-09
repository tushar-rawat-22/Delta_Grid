"""
Mission 65: Capital Readiness Review.

This module reviews institutional risk-control output and decides whether the
system is ready for extended paper observation.

It does not approve real capital.

It reads:
- institutional_risk_control_reviews
- institutional_risk_decision_records

It writes:
- capital_readiness_reviews
- capital_readiness_evidence_items
- capital_readiness_decision_records

It is governance only.

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


RISK_REVIEWS_TABLE = "institutional_risk_control_reviews"
RISK_DECISIONS_TABLE = "institutional_risk_decision_records"

CAPITAL_REVIEWS_TABLE = "capital_readiness_reviews"
CAPITAL_EVIDENCE_TABLE = "capital_readiness_evidence_items"
CAPITAL_DECISIONS_TABLE = "capital_readiness_decision_records"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

RISK_DECISION_APPROVED = "INSTITUTIONAL_RISK_APPROVED_FOR_CONTROLLED_PAPER_OBSERVATION"
RISK_READY = "INSTITUTIONAL_RISK_CONTROL_READY_SHADOW_ONLY"
RISK_LEVEL_LOW = "INSTITUTIONAL_RISK_LEVEL_LOW"
RISK_LEVEL_MODERATE = "INSTITUTIONAL_RISK_LEVEL_MODERATE"

EVIDENCE_PASS = "CAPITAL_EVIDENCE_PASS"
EVIDENCE_WARN = "CAPITAL_EVIDENCE_WARN"
EVIDENCE_FAIL = "CAPITAL_EVIDENCE_FAIL"

CAPITAL_DECISION_EXTENDED_PAPER = "CAPITAL_READINESS_APPROVED_FOR_EXTENDED_PAPER_OBSERVATION_ONLY"
CAPITAL_DECISION_BLOCK_RISK = "CAPITAL_READINESS_BLOCKED_BY_RISK_CONTROL"
CAPITAL_DECISION_BLOCK_SAFETY = "CAPITAL_READINESS_BLOCKED_BY_SAFETY_POLICY"
CAPITAL_DECISION_REJECT_MISSING = "CAPITAL_READINESS_REJECTED_MISSING_EVIDENCE"
CAPITAL_DECISION_BLOCK_CAPITAL = "CAPITAL_READINESS_BLOCKED_BY_CAPITAL_POLICY"

CAPITAL_READY_PAPER_ONLY = "CAPITAL_READINESS_REVIEW_PAPER_ONLY_READY"
CAPITAL_BLOCKED = "CAPITAL_READINESS_REVIEW_BLOCKED"
CAPITAL_MISSING = "CAPITAL_READINESS_REVIEW_MISSING_EVIDENCE"

ACTION_EXTENDED_PAPER = "CONTINUE_EXTENDED_PAPER_OBSERVATION_ONLY"
ACTION_REMEDIATE_RISK = "REMEDIATE_RISK_AND_RERUN_CONTROL_LAYER"
ACTION_STOP_SAFETY = "STOP_AND_REVIEW_CAPITAL_SAFETY_STATE"
ACTION_REFRESH_EVIDENCE = "REFRESH_RISK_CONTROL_EVIDENCE"
ACTION_KEEP_CAPITAL_BLOCKED = "KEEP_CAPITAL_DEPLOYMENT_BLOCKED"

READINESS_LEVEL_EARLY = "CAPITAL_READINESS_LEVEL_EARLY_PAPER_ONLY"
READINESS_LEVEL_DEVELOPING = "CAPITAL_READINESS_LEVEL_DEVELOPING_PAPER_ONLY"
READINESS_LEVEL_BLOCKED = "CAPITAL_READINESS_LEVEL_BLOCKED"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_review_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission65-capital-review-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission65-capital-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
            CREATE TABLE IF NOT EXISTS capital_readiness_reviews (
                review_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_risk_review_label TEXT NOT NULL,
                source_session_label TEXT,
                source_board_review_label TEXT,
                source_portfolio_label TEXT,
                evidence_item_count INTEGER NOT NULL,
                pass_evidence_count INTEGER NOT NULL,
                warn_evidence_count INTEGER NOT NULL,
                fail_evidence_count INTEGER NOT NULL,
                paper_notional TEXT NOT NULL,
                position_count INTEGER NOT NULL,
                order_count INTEGER NOT NULL,
                distinct_symbol_count INTEGER NOT NULL,
                distinct_strategy_count INTEGER NOT NULL,
                observed_max_symbol_exposure_pct TEXT NOT NULL,
                observed_max_strategy_exposure_pct TEXT NOT NULL,
                total_cost_bps TEXT NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                institutional_risk_level TEXT NOT NULL,
                capital_readiness_level TEXT NOT NULL,
                capital_decision TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS capital_readiness_evidence_items (
                evidence_id TEXT PRIMARY KEY,
                review_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_risk_review_label TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS capital_readiness_decision_records (
                decision_id TEXT PRIMARY KEY,
                review_label TEXT NOT NULL,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_risk_review_label TEXT NOT NULL,
                capital_decision TEXT NOT NULL,
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
    )


def load_risk_review(conn: sqlite3.Connection, risk_review_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, RISK_REVIEWS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM institutional_risk_control_reviews
        WHERE review_label = ?
        """,
        (risk_review_label,),
    ).fetchone()


def load_risk_decision(conn: sqlite3.Connection, risk_review_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, RISK_DECISIONS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM institutional_risk_decision_records
        WHERE review_label = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (risk_review_label,),
    ).fetchone()


def evidence_item(
    review_label: str,
    created_at: str,
    risk_review_label: str,
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
        "source_risk_review_label": risk_review_label,
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
            "capital_role": "CAPITAL_READINESS_EVIDENCE_ONLY",
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
    risk_review_label: str,
) -> list[dict[str, Any]]:
    return [
        evidence_item(
            review_label,
            created_at,
            risk_review_label,
            "availability",
            "institutional risk review exists",
            EVIDENCE_FAIL,
            "missing",
            "institutional_risk_control_reviews record",
            "No institutional risk-control review exists for this label.",
        )
    ]


def build_evidence_items(
    review_label: str,
    created_at: str,
    risk_review_label: str,
    risk_review: sqlite3.Row,
    risk_decision: sqlite3.Row | None,
    max_allowed_symbol_exposure_pct: float,
    max_allowed_strategy_exposure_pct: float,
    max_allowed_total_cost_bps: float,
    min_positions: int,
    min_distinct_symbols: int,
) -> list[dict[str, Any]]:
    safety_count = safe_int(row_get(risk_review, "safety_breach_count", 0))
    if safety_problem(risk_review):
        safety_count += 1
    if risk_decision is not None and safety_problem(risk_decision):
        safety_count += 1

    decision_value = str(row_get(risk_review, "risk_decision", ""))
    verdict_value = str(row_get(risk_review, "global_verdict", ""))
    action_value = str(row_get(risk_review, "recommended_action", ""))

    if risk_decision is not None:
        decision_value = str(row_get(risk_decision, "risk_decision", decision_value))
        verdict_value = str(row_get(risk_decision, "global_verdict", verdict_value))
        action_value = str(row_get(risk_decision, "recommended_action", action_value))

    fail_limit_count = safe_int(row_get(risk_review, "fail_limit_count", 0))
    risk_level = str(row_get(risk_review, "institutional_risk_level", ""))
    position_count = safe_int(row_get(risk_review, "position_count", 0))
    distinct_symbol_count = safe_int(row_get(risk_review, "distinct_symbol_count", 0))
    observed_symbol_exposure = safe_float(row_get(risk_review, "observed_max_symbol_exposure_pct", 0.0))
    observed_strategy_exposure = safe_float(row_get(risk_review, "observed_max_strategy_exposure_pct", 0.0))
    total_cost_bps = safe_float(row_get(risk_review, "total_cost_bps", 0.0))
    capital_status = str(row_get(risk_review, "capital_deployment", ""))

    return [
        evidence_item(
            review_label,
            created_at,
            risk_review_label,
            "safety",
            "safety invariants",
            EVIDENCE_PASS if safety_count == 0 else EVIDENCE_FAIL,
            safety_count,
            0,
            "Capital readiness requires zero live-trading, order-transmission, and capital-deployment breaches.",
        ),
        evidence_item(
            review_label,
            created_at,
            risk_review_label,
            "risk",
            "risk decision approved",
            EVIDENCE_PASS if decision_value == RISK_DECISION_APPROVED else EVIDENCE_FAIL,
            decision_value,
            RISK_DECISION_APPROVED,
            "Only an approved institutional risk-control decision may advance to extended paper observation.",
        ),
        evidence_item(
            review_label,
            created_at,
            risk_review_label,
            "risk",
            "risk global verdict",
            EVIDENCE_PASS if verdict_value == RISK_READY else EVIDENCE_FAIL,
            verdict_value,
            RISK_READY,
            "Institutional risk-control global verdict must be ready.",
        ),
        evidence_item(
            review_label,
            created_at,
            risk_review_label,
            "risk",
            "failed risk limits",
            EVIDENCE_PASS if fail_limit_count == 0 else EVIDENCE_FAIL,
            fail_limit_count,
            0,
            "No institutional risk limits may fail.",
        ),
        evidence_item(
            review_label,
            created_at,
            risk_review_label,
            "risk",
            "institutional risk level",
            EVIDENCE_PASS if risk_level in {RISK_LEVEL_LOW, RISK_LEVEL_MODERATE} else EVIDENCE_FAIL,
            risk_level,
            f"{RISK_LEVEL_LOW} or {RISK_LEVEL_MODERATE}",
            "High institutional risk cannot advance.",
        ),
        evidence_item(
            review_label,
            created_at,
            risk_review_label,
            "portfolio",
            "position count",
            EVIDENCE_PASS if position_count >= min_positions else EVIDENCE_FAIL,
            position_count,
            f">= {min_positions}",
            "Extended paper observation needs enough active paper positions.",
        ),
        evidence_item(
            review_label,
            created_at,
            risk_review_label,
            "portfolio",
            "distinct symbol count",
            EVIDENCE_PASS if distinct_symbol_count >= min_distinct_symbols else EVIDENCE_FAIL,
            distinct_symbol_count,
            f">= {min_distinct_symbols}",
            "Extended paper observation needs minimum symbol diversification.",
        ),
        evidence_item(
            review_label,
            created_at,
            risk_review_label,
            "exposure",
            "max symbol exposure",
            EVIDENCE_PASS if observed_symbol_exposure <= max_allowed_symbol_exposure_pct else EVIDENCE_FAIL,
            round8(observed_symbol_exposure),
            f"<= {max_allowed_symbol_exposure_pct}",
            "No symbol exposure may exceed capital-readiness threshold.",
        ),
        evidence_item(
            review_label,
            created_at,
            risk_review_label,
            "exposure",
            "max strategy exposure",
            EVIDENCE_PASS if observed_strategy_exposure <= max_allowed_strategy_exposure_pct else EVIDENCE_FAIL,
            round8(observed_strategy_exposure),
            f"<= {max_allowed_strategy_exposure_pct}",
            "No strategy exposure may exceed capital-readiness threshold.",
        ),
        evidence_item(
            review_label,
            created_at,
            risk_review_label,
            "cost",
            "total cost bps",
            EVIDENCE_PASS if total_cost_bps <= max_allowed_total_cost_bps else EVIDENCE_FAIL,
            round8(total_cost_bps),
            f"<= {max_allowed_total_cost_bps}",
            "Paper trading cost must remain inside the capital-readiness threshold.",
        ),
        evidence_item(
            review_label,
            created_at,
            risk_review_label,
            "capital",
            "capital deployment remains blocked",
            EVIDENCE_PASS if capital_status == CAPITAL_DEPLOYMENT_STATUS else EVIDENCE_FAIL,
            capital_status,
            CAPITAL_DEPLOYMENT_STATUS,
            "Capital readiness review must preserve blocked capital deployment.",
        ),
        evidence_item(
            review_label,
            created_at,
            risk_review_label,
            "scope",
            "recommended action remains paper only",
            EVIDENCE_PASS if "PAPER" in action_value else EVIDENCE_WARN,
            action_value,
            "paper-only continuation action",
            "Mission 65 may only advance to extended paper observation, not live capital.",
        ),
    ]


def decide_capital_outcome(
    risk_review: sqlite3.Row | None,
    evidence: list[dict[str, Any]],
) -> tuple[str, str, str, str, str, str]:
    if risk_review is None:
        return (
            CAPITAL_DECISION_REJECT_MISSING,
            CAPITAL_MISSING,
            ACTION_REFRESH_EVIDENCE,
            "Mission 64 Institutional Risk Control Layer",
            READINESS_LEVEL_BLOCKED,
            "Institutional risk-control evidence is missing.",
        )

    fail_count = sum(1 for item in evidence if item["evidence_status"] == EVIDENCE_FAIL)

    safety_failed = any(
        item["evidence_category"] == "safety" and item["evidence_status"] == EVIDENCE_FAIL
        for item in evidence
    )

    capital_failed = any(
        item["evidence_category"] == "capital" and item["evidence_status"] == EVIDENCE_FAIL
        for item in evidence
    )

    if safety_failed:
        return (
            CAPITAL_DECISION_BLOCK_SAFETY,
            CAPITAL_BLOCKED,
            ACTION_STOP_SAFETY,
            "Mission 65 safety remediation",
            READINESS_LEVEL_BLOCKED,
            "Safety evidence failed.",
        )

    if capital_failed:
        return (
            CAPITAL_DECISION_BLOCK_CAPITAL,
            CAPITAL_BLOCKED,
            ACTION_KEEP_CAPITAL_BLOCKED,
            "Mission 65 capital policy remediation",
            READINESS_LEVEL_BLOCKED,
            "Capital policy evidence failed.",
        )

    if fail_count > 0:
        return (
            CAPITAL_DECISION_BLOCK_RISK,
            CAPITAL_BLOCKED,
            ACTION_REMEDIATE_RISK,
            "Mission 64 risk remediation",
            READINESS_LEVEL_BLOCKED,
            "Risk or readiness evidence failed.",
        )

    risk_level = str(row_get(risk_review, "institutional_risk_level", ""))

    if risk_level == RISK_LEVEL_LOW:
        readiness_level = READINESS_LEVEL_DEVELOPING
    else:
        readiness_level = READINESS_LEVEL_EARLY

    return (
        CAPITAL_DECISION_EXTENDED_PAPER,
        CAPITAL_READY_PAPER_ONLY,
        ACTION_EXTENDED_PAPER,
        "Mission 66 Paper Observation Performance Monitor",
        readiness_level,
        "Evidence supports extended paper observation only. Real capital remains blocked.",
    )


def build_summary(
    db_path: str | Path,
    review_label: str,
    report_label: str,
    created_at: str,
    risk_review_label: str,
    risk_review: sqlite3.Row | None,
    evidence: list[dict[str, Any]],
    capital_decision: str,
    global_verdict: str,
    recommended_action: str,
    next_mission: str,
    readiness_level: str,
    decision_reason: str,
) -> dict[str, Any]:
    counts = Counter(item["evidence_status"] for item in evidence)

    if risk_review is None:
        source_session_label = None
        source_board_review_label = None
        source_portfolio_label = None
        paper_notional = 0.0
        position_count = 0
        order_count = 0
        distinct_symbol_count = 0
        distinct_strategy_count = 0
        observed_symbol = 0.0
        observed_strategy = 0.0
        total_cost_bps = 0.0
        safety_breach_count = 0
        institutional_risk_level = "UNKNOWN"
    else:
        source_session_label = row_get(risk_review, "source_session_label", None)
        source_board_review_label = row_get(risk_review, "source_board_review_label", None)
        source_portfolio_label = row_get(risk_review, "source_portfolio_label", None)
        paper_notional = round8(safe_float(row_get(risk_review, "paper_notional", 0.0)))
        position_count = safe_int(row_get(risk_review, "position_count", 0))
        order_count = safe_int(row_get(risk_review, "order_count", 0))
        distinct_symbol_count = safe_int(row_get(risk_review, "distinct_symbol_count", 0))
        distinct_strategy_count = safe_int(row_get(risk_review, "distinct_strategy_count", 0))
        observed_symbol = round8(safe_float(row_get(risk_review, "observed_max_symbol_exposure_pct", 0.0)))
        observed_strategy = round8(safe_float(row_get(risk_review, "observed_max_strategy_exposure_pct", 0.0)))
        total_cost_bps = round8(safe_float(row_get(risk_review, "total_cost_bps", 0.0)))
        safety_breach_count = safe_int(row_get(risk_review, "safety_breach_count", 0))
        institutional_risk_level = str(row_get(risk_review, "institutional_risk_level", "UNKNOWN"))

    return {
        "review_label": review_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_risk_review_label": risk_review_label,
        "source_session_label": source_session_label,
        "source_board_review_label": source_board_review_label,
        "source_portfolio_label": source_portfolio_label,
        "evidence_item_count": len(evidence),
        "pass_evidence_count": counts.get(EVIDENCE_PASS, 0),
        "warn_evidence_count": counts.get(EVIDENCE_WARN, 0),
        "fail_evidence_count": counts.get(EVIDENCE_FAIL, 0),
        "paper_notional": paper_notional,
        "position_count": position_count,
        "order_count": order_count,
        "distinct_symbol_count": distinct_symbol_count,
        "distinct_strategy_count": distinct_strategy_count,
        "observed_max_symbol_exposure_pct": observed_symbol,
        "observed_max_strategy_exposure_pct": observed_strategy,
        "total_cost_bps": total_cost_bps,
        "safety_breach_count": safety_breach_count,
        "institutional_risk_level": institutional_risk_level,
        "capital_readiness_level": readiness_level,
        "capital_decision": capital_decision,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
        "next_mission": next_mission,
        "decision_reason": decision_reason,
        "evidence_items": evidence,
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

    return f"""# DeltaGrid Mission 65 Capital Readiness Review Report

Report label: {summary['report_label']}
Review label: {summary['review_label']}
Created at: {summary['created_at']}
Source risk review label: {summary['source_risk_review_label']}
Source session label: {summary['source_session_label']}
Source board review label: {summary['source_board_review_label']}
Source portfolio label: {summary['source_portfolio_label']}

## Capital Readiness Summary

Evidence item count: {summary['evidence_item_count']}
Pass evidence count: {summary['pass_evidence_count']}
Warn evidence count: {summary['warn_evidence_count']}
Fail evidence count: {summary['fail_evidence_count']}

Paper notional: {summary['paper_notional']}
Position count: {summary['position_count']}
Order count: {summary['order_count']}
Distinct symbol count: {summary['distinct_symbol_count']}
Distinct strategy count: {summary['distinct_strategy_count']}

Observed max symbol exposure pct: {summary['observed_max_symbol_exposure_pct']}
Observed max strategy exposure pct: {summary['observed_max_strategy_exposure_pct']}
Total cost bps: {summary['total_cost_bps']}
Safety breach count: {summary['safety_breach_count']}
Institutional risk level: {summary['institutional_risk_level']}
Capital readiness level: {summary['capital_readiness_level']}

## Evidence

{evidence_markdown}

## Decision

Capital decision: {summary['capital_decision']}
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

Approval scope, if approved, is extended paper observation only.
It is not approval for live trading or real capital.
"""


def persist_review(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for item in summary["evidence_items"]:
            conn.execute(
                """
                INSERT OR REPLACE INTO capital_readiness_evidence_items (
                    evidence_id,
                    review_label,
                    created_at,
                    source_risk_review_label,
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
                    item["source_risk_review_label"],
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
            INSERT OR REPLACE INTO capital_readiness_reviews (
                review_label,
                report_label,
                created_at,
                source_risk_review_label,
                source_session_label,
                source_board_review_label,
                source_portfolio_label,
                evidence_item_count,
                pass_evidence_count,
                warn_evidence_count,
                fail_evidence_count,
                paper_notional,
                position_count,
                order_count,
                distinct_symbol_count,
                distinct_strategy_count,
                observed_max_symbol_exposure_pct,
                observed_max_strategy_exposure_pct,
                total_cost_bps,
                safety_breach_count,
                institutional_risk_level,
                capital_readiness_level,
                capital_decision,
                global_verdict,
                recommended_action,
                next_mission,
                live_trading,
                live_order_sent,
                capital_deployment,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["review_label"],
                summary["report_label"],
                summary["created_at"],
                summary["source_risk_review_label"],
                summary["source_session_label"],
                summary["source_board_review_label"],
                summary["source_portfolio_label"],
                summary["evidence_item_count"],
                summary["pass_evidence_count"],
                summary["warn_evidence_count"],
                summary["fail_evidence_count"],
                str(summary["paper_notional"]),
                summary["position_count"],
                summary["order_count"],
                summary["distinct_symbol_count"],
                summary["distinct_strategy_count"],
                str(summary["observed_max_symbol_exposure_pct"]),
                str(summary["observed_max_strategy_exposure_pct"]),
                str(summary["total_cost_bps"]),
                summary["safety_breach_count"],
                summary["institutional_risk_level"],
                summary["capital_readiness_level"],
                summary["capital_decision"],
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
            INSERT OR REPLACE INTO capital_readiness_decision_records (
                decision_id,
                review_label,
                report_label,
                created_at,
                source_risk_review_label,
                capital_decision,
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
                summary["source_risk_review_label"],
                summary["capital_decision"],
                summary["global_verdict"],
                summary["recommended_action"],
                "EXTENDED_PAPER_OBSERVATION_ONLY",
                "NOT_LIVE_TRADING_NOT_REAL_CAPITAL",
                summary["decision_reason"],
                LIVE_TRADING_STATUS,
                LIVE_ORDER_SENT_VALUE,
                CAPITAL_DEPLOYMENT_STATUS,
                json.dumps(
                    {
                        "capital_role": "CAPITAL_READINESS_DECISION_ONLY",
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


def run_capital_readiness_review(
    db_path: str | Path = "offchain/deltagrid.db",
    review_label: str | None = None,
    report_label: str | None = None,
    risk_review_label: str = "mission64-final-check",
    max_allowed_symbol_exposure_pct: float = 60.0,
    max_allowed_strategy_exposure_pct: float = 50.0,
    max_allowed_total_cost_bps: float = 10.0,
    min_positions: int = 3,
    min_distinct_symbols: int = 2,
) -> dict[str, Any]:
    if max_allowed_symbol_exposure_pct <= 0 or max_allowed_symbol_exposure_pct > 100:
        raise ValueError("max_allowed_symbol_exposure_pct must be between 0 and 100")

    if max_allowed_strategy_exposure_pct <= 0 or max_allowed_strategy_exposure_pct > 100:
        raise ValueError("max_allowed_strategy_exposure_pct must be between 0 and 100")

    if max_allowed_total_cost_bps < 0:
        raise ValueError("max_allowed_total_cost_bps cannot be negative")

    if min_positions <= 0:
        raise ValueError("min_positions must be positive")

    if min_distinct_symbols <= 0:
        raise ValueError("min_distinct_symbols must be positive")

    db = Path(db_path)
    review = review_label or new_review_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        risk_review = load_risk_review(conn, risk_review_label)
        risk_decision = load_risk_decision(conn, risk_review_label)

    if risk_review is None:
        evidence = build_missing_evidence(review, created_at, risk_review_label)
    else:
        evidence = build_evidence_items(
            review_label=review,
            created_at=created_at,
            risk_review_label=risk_review_label,
            risk_review=risk_review,
            risk_decision=risk_decision,
            max_allowed_symbol_exposure_pct=max_allowed_symbol_exposure_pct,
            max_allowed_strategy_exposure_pct=max_allowed_strategy_exposure_pct,
            max_allowed_total_cost_bps=max_allowed_total_cost_bps,
            min_positions=min_positions,
            min_distinct_symbols=min_distinct_symbols,
        )

    capital_decision, global_verdict, recommended_action, next_mission, readiness_level, decision_reason = decide_capital_outcome(
        risk_review=risk_review,
        evidence=evidence,
    )

    summary = build_summary(
        db_path=db,
        review_label=review,
        report_label=report,
        created_at=created_at,
        risk_review_label=risk_review_label,
        risk_review=risk_review,
        evidence=evidence,
        capital_decision=capital_decision,
        global_verdict=global_verdict,
        recommended_action=recommended_action,
        next_mission=next_mission,
        readiness_level=readiness_level,
        decision_reason=decision_reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_review(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid capital readiness review.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--review-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--risk-review-label", default="mission64-final-check")
    parser.add_argument("--max-allowed-symbol-exposure-pct", type=float, default=60.0)
    parser.add_argument("--max-allowed-strategy-exposure-pct", type=float, default=50.0)
    parser.add_argument("--max-allowed-total-cost-bps", type=float, default=10.0)
    parser.add_argument("--min-positions", type=int, default=3)
    parser.add_argument("--min-distinct-symbols", type=int, default=2)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_capital_readiness_review(
        db_path=args.db,
        review_label=args.review_label,
        report_label=args.report_label,
        risk_review_label=args.risk_review_label,
        max_allowed_symbol_exposure_pct=args.max_allowed_symbol_exposure_pct,
        max_allowed_strategy_exposure_pct=args.max_allowed_strategy_exposure_pct,
        max_allowed_total_cost_bps=args.max_allowed_total_cost_bps,
        min_positions=args.min_positions,
        min_distinct_symbols=args.min_distinct_symbols,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

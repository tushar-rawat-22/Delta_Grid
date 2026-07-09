"""
Mission 79: AI Research Recommendation Engine.

This module converts Mission 78 governance-approved offline evaluation evidence
into research-only recommendations.

Important boundary:
- This is research recommendation only.
- This does not train a model.
- This does not create live trading signals.
- This does not unlock capital.
- This does not trade.
- This does not adjust strategy weights.
- Every recommendation requires human review.

It reads:
- ai_offline_evaluation_governance_reviews
- ai_offline_evaluation_governance_evidence
- ai_offline_evaluation_governance_votes
- ai_offline_evaluation_governance_checks

It writes:
- ai_research_recommendation_runs
- ai_research_recommendation_items
- ai_research_recommendation_checks
- ai_research_recommendation_reports
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GOV_REVIEWS_TABLE = "ai_offline_evaluation_governance_reviews"
GOV_EVIDENCE_TABLE = "ai_offline_evaluation_governance_evidence"
GOV_VOTES_TABLE = "ai_offline_evaluation_governance_votes"
GOV_CHECKS_TABLE = "ai_offline_evaluation_governance_checks"

RUNS_TABLE = "ai_research_recommendation_runs"
ITEMS_TABLE = "ai_research_recommendation_items"
CHECKS_TABLE = "ai_research_recommendation_checks"
REPORTS_TABLE = "ai_research_recommendation_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

GOV_DECISION_READY = "AI_OFFLINE_EVALUATION_GOVERNANCE_APPROVED_FOR_RESEARCH_RECOMMENDATION_ONLY"
GOV_VERDICT_READY = "AI_OFFLINE_EVALUATION_GOVERNANCE_READY_SHADOW_ONLY"
GOV_STATE_READY = "AI_OFFLINE_EVALUATION_GOVERNANCE_READY_RESEARCH_ONLY"

CHECK_PASS = "AI_RESEARCH_RECOMMENDATION_CHECK_PASS"
CHECK_FAIL = "AI_RESEARCH_RECOMMENDATION_CHECK_FAIL"

RECOMMENDATION_STATUS_READY = "AI_RESEARCH_RECOMMENDATION_READY_FOR_HUMAN_REVIEW_ONLY"
RECOMMENDATION_STATUS_BLOCKED = "AI_RESEARCH_RECOMMENDATION_BLOCKED_REVIEW_REQUIRED"

RECOMMENDATION_MODE = "RESEARCH_ONLY_RECOMMENDATION_NO_TRAINING_NO_SIGNAL"
RECOMMENDATION_SCOPE = "RESEARCH_ONLY"
NO_LIVE_SIGNAL = "NO_LIVE_SIGNAL"
NO_EXECUTION = "NO_EXECUTION"
NO_CAPITAL_DEPLOYMENT = "NO_CAPITAL_DEPLOYMENT"
KEEP_TRAINING_DISABLED = "KEEP_MODEL_TRAINING_DISABLED"

ENGINE_STATE_READY = "AI_RESEARCH_RECOMMENDATION_ENGINE_READY_RESEARCH_ONLY"
ENGINE_STATE_UNSTABLE = "AI_RESEARCH_RECOMMENDATION_ENGINE_UNSTABLE"
ENGINE_STATE_BLOCKED = "AI_RESEARCH_RECOMMENDATION_ENGINE_BLOCKED"
ENGINE_STATE_MISSING = "AI_RESEARCH_RECOMMENDATION_ENGINE_MISSING"

DECISION_READY = "AI_RESEARCH_RECOMMENDATION_ENGINE_APPROVED_FOR_HUMAN_REVIEW_ONLY"
DECISION_UNSTABLE = "AI_RESEARCH_RECOMMENDATION_ENGINE_REVIEW_REQUIRED"
DECISION_BLOCK_SAFETY = "AI_RESEARCH_RECOMMENDATION_ENGINE_BLOCKED_BY_SAFETY_POLICY"
DECISION_REJECT_MISSING = "AI_RESEARCH_RECOMMENDATION_ENGINE_REJECTED_MISSING_EVIDENCE"

VERDICT_READY = "AI_RESEARCH_RECOMMENDATION_READY_SHADOW_ONLY"
VERDICT_UNSTABLE = "AI_RESEARCH_RECOMMENDATION_UNSTABLE_SHADOW_ONLY"
VERDICT_BLOCKED = "AI_RESEARCH_RECOMMENDATION_BLOCKED_SHADOW_ONLY"
VERDICT_MISSING = "AI_RESEARCH_RECOMMENDATION_MISSING_EVIDENCE"

ACTION_READY = "HAND_OFF_RESEARCH_RECOMMENDATIONS_TO_HUMAN_APPROVAL_GATE"
ACTION_REVIEW_UNSTABLE = "REVIEW_RESEARCH_RECOMMENDATION_EVIDENCE"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_RESEARCH_RECOMMENDATION_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_AI_OFFLINE_EVALUATION_GOVERNANCE_BOARD"

NEXT_READY = "Mission 80 Human Approval Gate"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_run_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission79-ai-research-recommendation-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission79-ai-research-recommendation-report-{stamp}-{uuid.uuid4().hex[:8]}"


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


def parse_labels(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return ["mission78-final-check"]

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    labels: list[str] = []

    for item in raw_items:
        label = str(item).strip()
        if not label:
            continue
        if any(ch.isspace() for ch in label):
            raise ValueError(f"Invalid governance review label: {label}")
        if label not in labels:
            labels.append(label)

    if not labels:
        raise ValueError("At least one governance review label is required")

    return labels


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


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not table_exists(conn, table_name):
        return set()

    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def order_clause(conn: sqlite3.Connection, table_name: str, fallback_column: str) -> str:
    columns = table_columns(conn, table_name)
    if "created_at" in columns and fallback_column in columns:
        return f"created_at ASC, {fallback_column} ASC"
    if fallback_column in columns:
        return f"{fallback_column} ASC"
    return "rowid ASC"


def ensure_schema(db_path: str | Path) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_research_recommendation_runs (
                recommendation_run_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_governance_review_label TEXT NOT NULL,
                source_evaluation_label TEXT,
                source_guard_review_label TEXT,
                source_collection_label TEXT,
                source_registry_label TEXT,
                source_build_label TEXT,
                source_schedule_label TEXT,
                source_learning_run_label TEXT,
                source_multi_cycle_track_label TEXT,
                source_session_label TEXT,
                source_portfolio_label TEXT,
                recommendation_count INTEGER NOT NULL,
                ready_recommendation_count INTEGER NOT NULL,
                blocked_recommendation_count INTEGER NOT NULL,
                human_review_required_count INTEGER NOT NULL,
                no_live_signal_count INTEGER NOT NULL,
                no_execution_count INTEGER NOT NULL,
                no_capital_deployment_count INTEGER NOT NULL,
                training_disabled_count INTEGER NOT NULL,
                source_evidence_count INTEGER NOT NULL,
                source_pass_evidence_count INTEGER NOT NULL,
                source_fail_evidence_count INTEGER NOT NULL,
                source_approve_vote_count INTEGER NOT NULL,
                source_review_vote_count INTEGER NOT NULL,
                source_block_vote_count INTEGER NOT NULL,
                recommendation_check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                leakage_breach_count INTEGER NOT NULL,
                training_eligible_count INTEGER NOT NULL,
                training_locked_count INTEGER NOT NULL,
                baseline_accuracy_pct TEXT NOT NULL,
                average_label_confidence TEXT NOT NULL,
                average_net_paper_outcome_bps TEXT NOT NULL,
                recommendation_mode TEXT NOT NULL,
                engine_state TEXT NOT NULL,
                engine_decision TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_research_recommendation_items (
                recommendation_id TEXT PRIMARY KEY,
                recommendation_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_governance_review_label TEXT NOT NULL,
                recommendation_rank INTEGER NOT NULL,
                recommendation_code TEXT NOT NULL,
                recommendation_title TEXT NOT NULL,
                recommendation_detail TEXT NOT NULL,
                recommendation_scope TEXT NOT NULL,
                recommendation_status TEXT NOT NULL,
                priority TEXT NOT NULL,
                rationale TEXT NOT NULL,
                human_review_required INTEGER NOT NULL,
                model_training_action TEXT NOT NULL,
                live_signal_action TEXT NOT NULL,
                execution_action TEXT NOT NULL,
                capital_action TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_research_recommendation_checks (
                check_id TEXT PRIMARY KEY,
                recommendation_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_governance_review_label TEXT NOT NULL,
                check_category TEXT NOT NULL,
                check_name TEXT NOT NULL,
                check_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                threshold_value TEXT NOT NULL,
                check_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_research_recommendation_reports (
                report_label TEXT PRIMARY KEY,
                recommendation_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_governance_review_label TEXT NOT NULL,
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


def load_governance_review(conn: sqlite3.Connection, review_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, GOV_REVIEWS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM ai_offline_evaluation_governance_reviews
        WHERE governance_review_label = ?
        """,
        (review_label,),
    ).fetchone()


def load_governance_evidence(conn: sqlite3.Connection, review_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, GOV_EVIDENCE_TABLE):
        return []

    order_by = order_clause(conn, GOV_EVIDENCE_TABLE, "evidence_id")
    return conn.execute(
        f"""
        SELECT *
        FROM ai_offline_evaluation_governance_evidence
        WHERE governance_review_label = ?
        ORDER BY {order_by}
        """,
        (review_label,),
    ).fetchall()


def load_governance_votes(conn: sqlite3.Connection, review_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, GOV_VOTES_TABLE):
        return []

    order_by = order_clause(conn, GOV_VOTES_TABLE, "vote_id")
    return conn.execute(
        f"""
        SELECT *
        FROM ai_offline_evaluation_governance_votes
        WHERE governance_review_label = ?
        ORDER BY {order_by}
        """,
        (review_label,),
    ).fetchall()


def load_governance_checks(conn: sqlite3.Connection, review_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, GOV_CHECKS_TABLE):
        return []

    order_by = order_clause(conn, GOV_CHECKS_TABLE, "check_id")
    return conn.execute(
        f"""
        SELECT *
        FROM ai_offline_evaluation_governance_checks
        WHERE governance_review_label = ?
        ORDER BY {order_by}
        """,
        (review_label,),
    ).fetchall()


def recommendation_item(
    run_label: str,
    created_at: str,
    governance_review_label: str,
    rank: int,
    code: str,
    title: str,
    detail: str,
    priority: str,
    rationale: str,
    status: str = RECOMMENDATION_STATUS_READY,
) -> dict[str, Any]:
    return {
        "recommendation_id": f"{run_label}-{rank}-{code}".replace(" ", "_"),
        "recommendation_run_label": run_label,
        "created_at": created_at,
        "source_governance_review_label": governance_review_label,
        "recommendation_rank": rank,
        "recommendation_code": code,
        "recommendation_title": title,
        "recommendation_detail": detail,
        "recommendation_scope": RECOMMENDATION_SCOPE,
        "recommendation_status": status,
        "priority": priority,
        "rationale": rationale,
        "human_review_required": 1,
        "model_training_action": KEEP_TRAINING_DISABLED,
        "live_signal_action": NO_LIVE_SIGNAL,
        "execution_action": NO_EXECUTION,
        "capital_action": NO_CAPITAL_DEPLOYMENT,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "recommendation_role": "RESEARCH_ONLY_RECOMMENDATION",
            "model_training_enabled": False,
            "live_signal_generation_enabled": False,
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
            "autonomous_trading_enabled": False,
            "automatic_strategy_reweighting_enabled": False,
            "requires_human_review": True,
            "not_profitability_claim": True,
        },
    }


def build_recommendations(
    run_label: str,
    created_at: str,
    governance_review_label: str,
    governance_review: sqlite3.Row | None,
) -> list[dict[str, Any]]:
    if governance_review is None:
        return []

    if row_get(governance_review, "governance_decision", "") != GOV_DECISION_READY:
        return []

    baseline_accuracy = round8(safe_float(row_get(governance_review, "baseline_accuracy_pct", 0.0)))
    average_net_bps = round8(safe_float(row_get(governance_review, "average_net_paper_outcome_bps", 0.0)))
    training_locked = safe_int(row_get(governance_review, "training_locked_count", 0))

    return [
        recommendation_item(
            run_label,
            created_at,
            governance_review_label,
            1,
            "CONTINUE_PAPER_OUTCOME_COLLECTION",
            "Continue paper outcome collection",
            "Continue collecting local paper-only outcomes before any model-training step.",
            "HIGH",
            f"Governance evidence passed while training remains locked for {training_locked} labels.",
        ),
        recommendation_item(
            run_label,
            created_at,
            governance_review_label,
            2,
            "EXPAND_CLASS_DIVERSITY_BEFORE_TRAINING",
            "Expand label class diversity",
            "Collect more cycles until positive, neutral, and negative classes are represented before training is reconsidered.",
            "HIGH",
            f"Current baseline accuracy is {baseline_accuracy}, but it is label agreement only and not profitability evidence.",
        ),
        recommendation_item(
            run_label,
            created_at,
            governance_review_label,
            3,
            "KEEP_MODEL_TRAINING_LOCKED",
            "Keep model training locked",
            "Do not train or retrain models from this dataset yet.",
            "CRITICAL",
            "The governance approval is research-only and explicitly does not approve model training.",
        ),
        recommendation_item(
            run_label,
            created_at,
            governance_review_label,
            4,
            "KEEP_LIVE_TRADING_DISABLED",
            "Keep live trading disabled",
            "Do not create live trading signals or send orders from these recommendations.",
            "CRITICAL",
            "The recommendation engine is research-only and execution permission remains denied.",
        ),
        recommendation_item(
            run_label,
            created_at,
            governance_review_label,
            5,
            "HAND_OFF_TO_HUMAN_APPROVAL_GATE",
            "Hand off to human approval gate",
            "Route research-only recommendations to the human approval gate before any future research action.",
            "HIGH",
            f"Average paper outcome remains {average_net_bps} bps, so recommendations must remain review-only.",
        ),
    ]


def research_check(
    run_label: str,
    created_at: str,
    governance_review_label: str,
    category: str,
    name: str,
    passed: bool,
    observed: Any,
    threshold: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{run_label}-{category}-{name}".replace(" ", "_"),
        "recommendation_run_label": run_label,
        "created_at": created_at,
        "source_governance_review_label": governance_review_label,
        "check_category": category,
        "check_name": name,
        "check_status": CHECK_PASS if passed else CHECK_FAIL,
        "observed_value": str(observed),
        "threshold_value": str(threshold),
        "check_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "recommendation_check_role": "RESEARCH_RECOMMENDATION_CHECK_ONLY",
            "model_training_enabled": False,
            "live_signal_generation_enabled": False,
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
            "autonomous_trading_enabled": False,
            "automatic_strategy_reweighting_enabled": False,
        },
    }


def build_recommendation_checks(
    run_label: str,
    created_at: str,
    governance_review_label: str,
    governance_review: sqlite3.Row | None,
    evidence: list[sqlite3.Row],
    votes: list[sqlite3.Row],
    checks: list[sqlite3.Row],
    recommendations: list[dict[str, Any]],
    min_recommendations: int,
    min_approve_votes: int,
) -> list[dict[str, Any]]:
    if governance_review is None:
        return [
            research_check(
                run_label,
                created_at,
                governance_review_label,
                "availability",
                "governance review exists",
                False,
                "missing",
                "present",
                "Governance review evidence is missing.",
            )
        ]

    safety_count = safe_int(row_get(governance_review, "safety_breach_count", 0))
    safety_count += sum(1 for row in [governance_review, *evidence, *votes, *checks] if safety_problem(row))

    source_fail_count = safe_int(row_get(governance_review, "fail_check_count", 0))
    fail_evidence_count = safe_int(row_get(governance_review, "fail_evidence_count", 0))
    approve_vote_count = safe_int(row_get(governance_review, "approve_vote_count", 0))
    review_vote_count = safe_int(row_get(governance_review, "review_vote_count", 0))
    block_vote_count = safe_int(row_get(governance_review, "block_vote_count", 0))
    leakage_breach_count = safe_int(row_get(governance_review, "leakage_breach_count", 0))
    training_eligible_count = safe_int(row_get(governance_review, "training_eligible_count", 0))

    recommendation_count = len(recommendations)
    no_live_signal_count = sum(1 for item in recommendations if item["live_signal_action"] == NO_LIVE_SIGNAL)
    no_execution_count = sum(1 for item in recommendations if item["execution_action"] == NO_EXECUTION)
    no_capital_count = sum(1 for item in recommendations if item["capital_action"] == NO_CAPITAL_DEPLOYMENT)
    training_disabled_count = sum(1 for item in recommendations if item["model_training_action"] == KEEP_TRAINING_DISABLED)
    human_review_count = sum(1 for item in recommendations if safe_int(item["human_review_required"]) == 1)

    return [
        research_check(run_label, created_at, governance_review_label, "availability", "governance review exists", True, "present", "present", "Governance review exists."),
        research_check(run_label, created_at, governance_review_label, "safety", "safety breach count", safety_count == 0, safety_count, 0, "Recommendation engine requires zero safety breaches."),
        research_check(run_label, created_at, governance_review_label, "governance", "governance decision ready", row_get(governance_review, "governance_decision", "") == GOV_DECISION_READY, row_get(governance_review, "governance_decision", ""), GOV_DECISION_READY, "Governance must approve research-only recommendations."),
        research_check(run_label, created_at, governance_review_label, "governance", "governance verdict ready", row_get(governance_review, "global_verdict", "") == GOV_VERDICT_READY, row_get(governance_review, "global_verdict", ""), GOV_VERDICT_READY, "Governance verdict must be ready and shadow-only."),
        research_check(run_label, created_at, governance_review_label, "governance", "governance state ready", row_get(governance_review, "governance_state", "") == GOV_STATE_READY, row_get(governance_review, "governance_state", ""), GOV_STATE_READY, "Governance state must be research-only ready."),
        research_check(run_label, created_at, governance_review_label, "governance", "source governance failed checks", source_fail_count == 0, source_fail_count, 0, "Source governance failed checks must remain zero."),
        research_check(run_label, created_at, governance_review_label, "evidence", "failed evidence count", fail_evidence_count == 0, fail_evidence_count, 0, "Governance evidence failures must remain zero."),
        research_check(run_label, created_at, governance_review_label, "votes", "board vote approval", approve_vote_count >= min_approve_votes and review_vote_count == 0 and block_vote_count == 0, f"approve={approve_vote_count}, review={review_vote_count}, block={block_vote_count}", f"approve>={min_approve_votes}, review=0, block=0", "Board votes must approve research-only handoff."),
        research_check(run_label, created_at, governance_review_label, "leakage", "leakage breach count", leakage_breach_count == 0, leakage_breach_count, 0, "No leakage breach may feed recommendations."),
        research_check(run_label, created_at, governance_review_label, "recommendations", "recommendation count", recommendation_count >= min_recommendations, recommendation_count, f">= {min_recommendations}", "Research recommendation set must be produced."),
        research_check(run_label, created_at, governance_review_label, "live_signal", "no live signal recommendations", no_live_signal_count == recommendation_count and recommendation_count > 0, no_live_signal_count, recommendation_count, "Recommendations must not create live signals."),
        research_check(run_label, created_at, governance_review_label, "execution", "no execution recommendations", no_execution_count == recommendation_count and recommendation_count > 0, no_execution_count, recommendation_count, "Recommendations must not permit execution."),
        research_check(run_label, created_at, governance_review_label, "capital", "no capital deployment recommendations", no_capital_count == recommendation_count and recommendation_count > 0, no_capital_count, recommendation_count, "Recommendations must not permit capital deployment."),
        research_check(run_label, created_at, governance_review_label, "training_lock", "model training remains disabled", training_eligible_count == 0 and training_disabled_count == recommendation_count and recommendation_count > 0, f"eligible={training_eligible_count}, disabled_recs={training_disabled_count}", f"eligible=0, disabled_recs={recommendation_count}", "Recommendations must keep model training disabled."),
        research_check(run_label, created_at, governance_review_label, "human_review", "human review required", human_review_count == recommendation_count and recommendation_count > 0, human_review_count, recommendation_count, "Every recommendation must require human review."),
        research_check(run_label, created_at, governance_review_label, "profitability", "no profitability claim", True, "baseline accuracy is label agreement only", "no profitability claim", "Recommendation report must not treat baseline accuracy as profitability."),
    ]


def decide_engine_outcome(
    governance_review: sqlite3.Row | None,
    checks: list[dict[str, Any]],
) -> tuple[str, str, str, str, str, str]:
    if governance_review is None:
        return (
            DECISION_REJECT_MISSING,
            VERDICT_MISSING,
            ACTION_REFRESH,
            "Mission 78 AI Offline Evaluation Governance Board",
            ENGINE_STATE_MISSING,
            "Governance review evidence is missing.",
        )

    failed = [check for check in checks if check["check_status"] == CHECK_FAIL]

    if any(check["check_category"] == "safety" for check in failed):
        return (
            DECISION_BLOCK_SAFETY,
            VERDICT_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 79 safety remediation",
            ENGINE_STATE_BLOCKED,
            "Safety invariant failed during research recommendation generation.",
        )

    if failed:
        return (
            DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 78 AI Offline Evaluation Governance Board",
            ENGINE_STATE_UNSTABLE,
            "Research recommendation engine failed one or more checks.",
        )

    return (
        DECISION_READY,
        VERDICT_READY,
        ACTION_READY,
        NEXT_READY,
        ENGINE_STATE_READY,
        "Research-only recommendations are ready for human approval gate. No model training, live signals, capital deployment, or trading are approved.",
    )


def build_summary(
    db_path: str | Path,
    run_label: str,
    report_label: str,
    created_at: str,
    governance_review_label: str,
    governance_review: sqlite3.Row | None,
    recommendations: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    decision: str,
    verdict: str,
    action: str,
    next_mission: str,
    state: str,
    reason: str,
) -> dict[str, Any]:
    recommendation_count = len(recommendations)
    ready_count = sum(1 for item in recommendations if item["recommendation_status"] == RECOMMENDATION_STATUS_READY)
    blocked_count = sum(1 for item in recommendations if item["recommendation_status"] == RECOMMENDATION_STATUS_BLOCKED)
    human_review_count = sum(1 for item in recommendations if safe_int(item["human_review_required"]) == 1)
    no_live_signal_count = sum(1 for item in recommendations if item["live_signal_action"] == NO_LIVE_SIGNAL)
    no_execution_count = sum(1 for item in recommendations if item["execution_action"] == NO_EXECUTION)
    no_capital_count = sum(1 for item in recommendations if item["capital_action"] == NO_CAPITAL_DEPLOYMENT)
    training_disabled_count = sum(1 for item in recommendations if item["model_training_action"] == KEEP_TRAINING_DISABLED)
    pass_check_count = sum(1 for check in checks if check["check_status"] == CHECK_PASS)
    fail_check_count = sum(1 for check in checks if check["check_status"] == CHECK_FAIL)

    return {
        "recommendation_run_label": run_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_governance_review_label": governance_review_label,
        "source_evaluation_label": row_get(governance_review, "source_evaluation_label", None),
        "source_guard_review_label": row_get(governance_review, "source_guard_review_label", None),
        "source_collection_label": row_get(governance_review, "source_collection_label", None),
        "source_registry_label": row_get(governance_review, "source_registry_label", None),
        "source_build_label": row_get(governance_review, "source_build_label", None),
        "source_schedule_label": row_get(governance_review, "source_schedule_label", None),
        "source_learning_run_label": row_get(governance_review, "source_learning_run_label", None),
        "source_multi_cycle_track_label": row_get(governance_review, "source_multi_cycle_track_label", None),
        "source_session_label": row_get(governance_review, "source_session_label", None),
        "source_portfolio_label": row_get(governance_review, "source_portfolio_label", None),
        "recommendation_count": recommendation_count,
        "ready_recommendation_count": ready_count,
        "blocked_recommendation_count": blocked_count,
        "human_review_required_count": human_review_count,
        "no_live_signal_count": no_live_signal_count,
        "no_execution_count": no_execution_count,
        "no_capital_deployment_count": no_capital_count,
        "training_disabled_count": training_disabled_count,
        "source_evidence_count": safe_int(row_get(governance_review, "evidence_count", 0)),
        "source_pass_evidence_count": safe_int(row_get(governance_review, "pass_evidence_count", 0)),
        "source_fail_evidence_count": safe_int(row_get(governance_review, "fail_evidence_count", 0)),
        "source_approve_vote_count": safe_int(row_get(governance_review, "approve_vote_count", 0)),
        "source_review_vote_count": safe_int(row_get(governance_review, "review_vote_count", 0)),
        "source_block_vote_count": safe_int(row_get(governance_review, "block_vote_count", 0)),
        "recommendation_check_count": len(checks),
        "pass_check_count": pass_check_count,
        "fail_check_count": fail_check_count,
        "safety_breach_count": safe_int(row_get(governance_review, "safety_breach_count", 0)),
        "leakage_breach_count": safe_int(row_get(governance_review, "leakage_breach_count", 0)),
        "training_eligible_count": safe_int(row_get(governance_review, "training_eligible_count", 0)),
        "training_locked_count": safe_int(row_get(governance_review, "training_locked_count", 0)),
        "baseline_accuracy_pct": round8(safe_float(row_get(governance_review, "baseline_accuracy_pct", 0.0))),
        "average_label_confidence": round8(safe_float(row_get(governance_review, "average_label_confidence", 0.0))),
        "average_net_paper_outcome_bps": round8(safe_float(row_get(governance_review, "average_net_paper_outcome_bps", 0.0))),
        "recommendation_mode": RECOMMENDATION_MODE,
        "research_recommendations": recommendations,
        "recommendation_checks": checks,
        "engine_state": state,
        "engine_decision": decision,
        "global_verdict": verdict,
        "recommended_action": action,
        "next_mission": next_mission,
        "decision_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    recommendation_lines = [
        f"- #{item['recommendation_rank']} {item['recommendation_code']}: {item['recommendation_title']} | status={item['recommendation_status']} | human_review={item['human_review_required']}"
        for item in summary["research_recommendations"]
    ]

    check_lines = [
        f"- {check['check_category']} / {check['check_name']}: status={check['check_status']}, observed={check['observed_value']}, threshold={check['threshold_value']}"
        for check in summary["recommendation_checks"]
    ]

    return f"""# DeltaGrid Mission 79 AI Research Recommendation Engine Report

Report label: {summary['report_label']}
Recommendation run label: {summary['recommendation_run_label']}
Created at: {summary['created_at']}
Source governance review label: {summary['source_governance_review_label']}
Source evaluation label: {summary['source_evaluation_label']}
Source guard review label: {summary['source_guard_review_label']}
Source collection label: {summary['source_collection_label']}
Source registry label: {summary['source_registry_label']}
Source build label: {summary['source_build_label']}
Source schedule label: {summary['source_schedule_label']}
Source learning run label: {summary['source_learning_run_label']}
Source multi-cycle track label: {summary['source_multi_cycle_track_label']}
Source session label: {summary['source_session_label']}
Source portfolio label: {summary['source_portfolio_label']}

## Research Recommendation Summary

Recommendation mode: {summary['recommendation_mode']}
Recommendation count: {summary['recommendation_count']}
Ready recommendation count: {summary['ready_recommendation_count']}
Blocked recommendation count: {summary['blocked_recommendation_count']}
Human review required count: {summary['human_review_required_count']}
No live signal count: {summary['no_live_signal_count']}
No execution count: {summary['no_execution_count']}
No capital deployment count: {summary['no_capital_deployment_count']}
Training disabled count: {summary['training_disabled_count']}

Source evidence count: {summary['source_evidence_count']}
Source pass evidence count: {summary['source_pass_evidence_count']}
Source fail evidence count: {summary['source_fail_evidence_count']}
Source approve vote count: {summary['source_approve_vote_count']}
Source review vote count: {summary['source_review_vote_count']}
Source block vote count: {summary['source_block_vote_count']}

Recommendation check count: {summary['recommendation_check_count']}
Pass check count: {summary['pass_check_count']}
Fail check count: {summary['fail_check_count']}
Safety breach count: {summary['safety_breach_count']}
Leakage breach count: {summary['leakage_breach_count']}
Training eligible count: {summary['training_eligible_count']}
Training locked count: {summary['training_locked_count']}

Baseline accuracy pct: {summary['baseline_accuracy_pct']}
Average label confidence: {summary['average_label_confidence']}
Average net paper outcome bps: {summary['average_net_paper_outcome_bps']}

## Recommendations

{chr(10).join(recommendation_lines) if recommendation_lines else "- None"}

## Checks

{chr(10).join(check_lines) if check_lines else "- None"}

## Decision

Engine state: {summary['engine_state']}
Engine decision: {summary['engine_decision']}
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

This recommendation engine does not train a model.
This recommendation engine does not create live trading signals.
This recommendation engine does not perform autonomous trading.
This recommendation engine does not adjust strategy weights automatically.
Every recommendation requires human review.

Baseline accuracy is offline label agreement only.
It is not profitability evidence.
"""


def insert_row(conn: sqlite3.Connection, table_name: str, row: dict[str, Any], columns: list[str]) -> None:
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    values = [row[column] for column in columns]
    conn.execute(f"INSERT OR REPLACE INTO {table_name} ({column_sql}) VALUES ({placeholders})", values)


def persist_recommendation_run(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM ai_research_recommendation_items WHERE recommendation_run_label = ?",
            (summary["recommendation_run_label"],),
        )
        conn.execute(
            "DELETE FROM ai_research_recommendation_checks WHERE recommendation_run_label = ?",
            (summary["recommendation_run_label"],),
        )
        conn.execute(
            "DELETE FROM ai_research_recommendation_runs WHERE recommendation_run_label = ?",
            (summary["recommendation_run_label"],),
        )
        conn.execute(
            "DELETE FROM ai_research_recommendation_reports WHERE recommendation_run_label = ? OR report_label = ?",
            (summary["recommendation_run_label"], summary["report_label"]),
        )

        for item in summary["research_recommendations"]:
            stored = dict(item)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                ITEMS_TABLE,
                stored,
                [
                    "recommendation_id", "recommendation_run_label", "created_at",
                    "source_governance_review_label", "recommendation_rank",
                    "recommendation_code", "recommendation_title",
                    "recommendation_detail", "recommendation_scope",
                    "recommendation_status", "priority", "rationale",
                    "human_review_required", "model_training_action",
                    "live_signal_action", "execution_action", "capital_action",
                    "live_trading", "live_order_sent", "capital_deployment",
                    "metadata_json",
                ],
            )

        for check in summary["recommendation_checks"]:
            stored_check = dict(check)
            stored_check["metadata_json"] = json.dumps(stored_check.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                CHECKS_TABLE,
                stored_check,
                [
                    "check_id", "recommendation_run_label", "created_at",
                    "source_governance_review_label", "check_category",
                    "check_name", "check_status", "observed_value",
                    "threshold_value", "check_reason", "live_trading",
                    "live_order_sent", "capital_deployment", "metadata_json",
                ],
            )

        run_row = {
            "recommendation_run_label": summary["recommendation_run_label"],
            "report_label": summary["report_label"],
            "created_at": summary["created_at"],
            "source_governance_review_label": summary["source_governance_review_label"],
            "source_evaluation_label": summary["source_evaluation_label"],
            "source_guard_review_label": summary["source_guard_review_label"],
            "source_collection_label": summary["source_collection_label"],
            "source_registry_label": summary["source_registry_label"],
            "source_build_label": summary["source_build_label"],
            "source_schedule_label": summary["source_schedule_label"],
            "source_learning_run_label": summary["source_learning_run_label"],
            "source_multi_cycle_track_label": summary["source_multi_cycle_track_label"],
            "source_session_label": summary["source_session_label"],
            "source_portfolio_label": summary["source_portfolio_label"],
            "recommendation_count": summary["recommendation_count"],
            "ready_recommendation_count": summary["ready_recommendation_count"],
            "blocked_recommendation_count": summary["blocked_recommendation_count"],
            "human_review_required_count": summary["human_review_required_count"],
            "no_live_signal_count": summary["no_live_signal_count"],
            "no_execution_count": summary["no_execution_count"],
            "no_capital_deployment_count": summary["no_capital_deployment_count"],
            "training_disabled_count": summary["training_disabled_count"],
            "source_evidence_count": summary["source_evidence_count"],
            "source_pass_evidence_count": summary["source_pass_evidence_count"],
            "source_fail_evidence_count": summary["source_fail_evidence_count"],
            "source_approve_vote_count": summary["source_approve_vote_count"],
            "source_review_vote_count": summary["source_review_vote_count"],
            "source_block_vote_count": summary["source_block_vote_count"],
            "recommendation_check_count": summary["recommendation_check_count"],
            "pass_check_count": summary["pass_check_count"],
            "fail_check_count": summary["fail_check_count"],
            "safety_breach_count": summary["safety_breach_count"],
            "leakage_breach_count": summary["leakage_breach_count"],
            "training_eligible_count": summary["training_eligible_count"],
            "training_locked_count": summary["training_locked_count"],
            "baseline_accuracy_pct": str(summary["baseline_accuracy_pct"]),
            "average_label_confidence": str(summary["average_label_confidence"]),
            "average_net_paper_outcome_bps": str(summary["average_net_paper_outcome_bps"]),
            "recommendation_mode": summary["recommendation_mode"],
            "engine_state": summary["engine_state"],
            "engine_decision": summary["engine_decision"],
            "global_verdict": summary["global_verdict"],
            "recommended_action": summary["recommended_action"],
            "next_mission": summary["next_mission"],
            "live_trading": summary["live_trading"],
            "live_order_sent": summary["live_order_sent"],
            "capital_deployment": summary["capital_deployment"],
            "summary_json": json.dumps(summary, sort_keys=True),
            "markdown_report": markdown_report,
        }

        insert_row(
            conn,
            RUNS_TABLE,
            run_row,
            [
                "recommendation_run_label", "report_label", "created_at",
                "source_governance_review_label", "source_evaluation_label",
                "source_guard_review_label", "source_collection_label",
                "source_registry_label", "source_build_label", "source_schedule_label",
                "source_learning_run_label", "source_multi_cycle_track_label",
                "source_session_label", "source_portfolio_label",
                "recommendation_count", "ready_recommendation_count",
                "blocked_recommendation_count", "human_review_required_count",
                "no_live_signal_count", "no_execution_count",
                "no_capital_deployment_count", "training_disabled_count",
                "source_evidence_count", "source_pass_evidence_count",
                "source_fail_evidence_count", "source_approve_vote_count",
                "source_review_vote_count", "source_block_vote_count",
                "recommendation_check_count", "pass_check_count",
                "fail_check_count", "safety_breach_count", "leakage_breach_count",
                "training_eligible_count", "training_locked_count",
                "baseline_accuracy_pct", "average_label_confidence",
                "average_net_paper_outcome_bps", "recommendation_mode",
                "engine_state", "engine_decision", "global_verdict",
                "recommended_action", "next_mission", "live_trading",
                "live_order_sent", "capital_deployment", "summary_json",
                "markdown_report",
            ],
        )

        report_row = {
            "report_label": summary["report_label"],
            "recommendation_run_label": summary["recommendation_run_label"],
            "created_at": summary["created_at"],
            "source_governance_review_label": summary["source_governance_review_label"],
            "global_verdict": summary["global_verdict"],
            "recommended_action": summary["recommended_action"],
            "report_json": json.dumps(summary, sort_keys=True),
            "markdown_report": markdown_report,
            "live_trading": LIVE_TRADING_STATUS,
            "live_order_sent": LIVE_ORDER_SENT_VALUE,
            "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        }

        insert_row(
            conn,
            REPORTS_TABLE,
            report_row,
            [
                "report_label", "recommendation_run_label", "created_at",
                "source_governance_review_label", "global_verdict",
                "recommended_action", "report_json", "markdown_report",
                "live_trading", "live_order_sent", "capital_deployment",
            ],
        )

        conn.commit()


def run_ai_research_recommendation_engine(
    db_path: str | Path = "offchain/deltagrid.db",
    recommendation_run_label: str | None = None,
    report_label: str | None = None,
    governance_review_label: str = "mission78-final-check",
    min_recommendations: int = 5,
    min_approve_votes: int = 5,
) -> dict[str, Any]:
    if min_recommendations <= 0:
        raise ValueError("min_recommendations must be positive")
    if min_approve_votes <= 0:
        raise ValueError("min_approve_votes must be positive")

    db = Path(db_path)
    run_label = recommendation_run_label or new_run_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    source_governance_review_label = parse_labels(governance_review_label)[0]

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        governance_review = load_governance_review(conn, source_governance_review_label)
        evidence = load_governance_evidence(conn, source_governance_review_label)
        votes = load_governance_votes(conn, source_governance_review_label)
        source_checks = load_governance_checks(conn, source_governance_review_label)

    recommendations = build_recommendations(
        run_label=run_label,
        created_at=created_at,
        governance_review_label=source_governance_review_label,
        governance_review=governance_review,
    )

    recommendation_checks = build_recommendation_checks(
        run_label=run_label,
        created_at=created_at,
        governance_review_label=source_governance_review_label,
        governance_review=governance_review,
        evidence=evidence,
        votes=votes,
        checks=source_checks,
        recommendations=recommendations,
        min_recommendations=min_recommendations,
        min_approve_votes=min_approve_votes,
    )

    decision, verdict, action, next_mission, state, reason = decide_engine_outcome(governance_review, recommendation_checks)

    summary = build_summary(
        db_path=db,
        run_label=run_label,
        report_label=report,
        created_at=created_at,
        governance_review_label=source_governance_review_label,
        governance_review=governance_review,
        recommendations=recommendations,
        checks=recommendation_checks,
        decision=decision,
        verdict=verdict,
        action=action,
        next_mission=next_mission,
        state=state,
        reason=reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_recommendation_run(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid AI research recommendation engine.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--recommendation-run-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--governance-review-label", default="mission78-final-check")
    parser.add_argument("--min-recommendations", type=int, default=5)
    parser.add_argument("--min-approve-votes", type=int, default=5)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_ai_research_recommendation_engine(
        db_path=args.db,
        recommendation_run_label=args.recommendation_run_label,
        report_label=args.report_label,
        governance_review_label=args.governance_review_label,
        min_recommendations=args.min_recommendations,
        min_approve_votes=args.min_approve_votes,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

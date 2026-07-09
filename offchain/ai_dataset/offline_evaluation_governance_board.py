"""
Mission 78: AI Offline Evaluation Governance Board.

This module reviews Mission 77 offline evaluation evidence and produces a
research-only governance decision.

Important boundary:
- This is governance review only.
- This does not train a model.
- This does not create live signals.
- This does not unlock capital.
- This does not trade.
- This does not adjust strategy weights.

It reads:
- ai_offline_evaluation_runs
- ai_offline_evaluation_cases
- ai_offline_evaluation_metrics
- ai_offline_evaluation_checks

It writes:
- ai_offline_evaluation_governance_reviews
- ai_offline_evaluation_governance_evidence
- ai_offline_evaluation_governance_votes
- ai_offline_evaluation_governance_checks
- ai_offline_evaluation_governance_reports
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


EVAL_RUNS_TABLE = "ai_offline_evaluation_runs"
EVAL_CASES_TABLE = "ai_offline_evaluation_cases"
EVAL_METRICS_TABLE = "ai_offline_evaluation_metrics"
EVAL_CHECKS_TABLE = "ai_offline_evaluation_checks"

REVIEWS_TABLE = "ai_offline_evaluation_governance_reviews"
EVIDENCE_TABLE = "ai_offline_evaluation_governance_evidence"
VOTES_TABLE = "ai_offline_evaluation_governance_votes"
CHECKS_TABLE = "ai_offline_evaluation_governance_checks"
REPORTS_TABLE = "ai_offline_evaluation_governance_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

EVAL_DECISION_READY = "AI_OFFLINE_EVALUATION_APPROVED_FOR_GOVERNANCE_REVIEW"
EVAL_VERDICT_READY = "AI_OFFLINE_EVALUATION_READY_SHADOW_ONLY"
EVAL_STATE_READY = "AI_OFFLINE_EVALUATION_HARNESS_READY"
EVAL_MODE_REQUIRED = "DETERMINISTIC_BASELINE_OFFLINE_EVALUATION_NO_MODEL_TRAINING"

CHECK_PASS = "AI_OFFLINE_EVALUATION_GOVERNANCE_CHECK_PASS"
CHECK_FAIL = "AI_OFFLINE_EVALUATION_GOVERNANCE_CHECK_FAIL"

EVIDENCE_PASS = "AI_OFFLINE_EVALUATION_GOVERNANCE_EVIDENCE_PASS"
EVIDENCE_FAIL = "AI_OFFLINE_EVALUATION_GOVERNANCE_EVIDENCE_FAIL"

VOTE_APPROVE = "AI_GOVERNANCE_BOARD_VOTE_APPROVE_RESEARCH_ONLY"
VOTE_REVIEW = "AI_GOVERNANCE_BOARD_VOTE_REVIEW_REQUIRED"
VOTE_BLOCK = "AI_GOVERNANCE_BOARD_VOTE_BLOCK"

GOVERNANCE_STATE_READY = "AI_OFFLINE_EVALUATION_GOVERNANCE_READY_RESEARCH_ONLY"
GOVERNANCE_STATE_UNSTABLE = "AI_OFFLINE_EVALUATION_GOVERNANCE_UNSTABLE"
GOVERNANCE_STATE_BLOCKED = "AI_OFFLINE_EVALUATION_GOVERNANCE_BLOCKED"
GOVERNANCE_STATE_MISSING = "AI_OFFLINE_EVALUATION_GOVERNANCE_MISSING"

DECISION_READY = "AI_OFFLINE_EVALUATION_GOVERNANCE_APPROVED_FOR_RESEARCH_RECOMMENDATION_ONLY"
DECISION_UNSTABLE = "AI_OFFLINE_EVALUATION_GOVERNANCE_REVIEW_REQUIRED"
DECISION_BLOCK_SAFETY = "AI_OFFLINE_EVALUATION_GOVERNANCE_BLOCKED_BY_SAFETY_POLICY"
DECISION_REJECT_MISSING = "AI_OFFLINE_EVALUATION_GOVERNANCE_REJECTED_MISSING_EVIDENCE"

VERDICT_READY = "AI_OFFLINE_EVALUATION_GOVERNANCE_READY_SHADOW_ONLY"
VERDICT_UNSTABLE = "AI_OFFLINE_EVALUATION_GOVERNANCE_UNSTABLE_SHADOW_ONLY"
VERDICT_BLOCKED = "AI_OFFLINE_EVALUATION_GOVERNANCE_BLOCKED_SHADOW_ONLY"
VERDICT_MISSING = "AI_OFFLINE_EVALUATION_GOVERNANCE_MISSING_EVIDENCE"

ACTION_READY = "HAND_OFF_TO_RESEARCH_RECOMMENDATION_ENGINE_NO_TRAINING"
ACTION_REVIEW_UNSTABLE = "REVIEW_OFFLINE_EVALUATION_GOVERNANCE_EVIDENCE"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_GOVERNANCE_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_AI_OFFLINE_EVALUATION_HARNESS"

NEXT_READY = "Mission 79 AI Research Recommendation Engine"

BOARD_ROLES = (
    "RESEARCH_CTO",
    "MODEL_RISK_OFFICER",
    "DATA_QUALITY_OFFICER",
    "SAFETY_OFFICER",
    "CAPITAL_CONTROL_OFFICER",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_review_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission78-ai-offline-evaluation-governance-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission78-ai-offline-evaluation-governance-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
        return ["mission77-final-check"]

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    labels: list[str] = []

    for item in raw_items:
        label = str(item).strip()
        if not label:
            continue
        if any(ch.isspace() for ch in label):
            raise ValueError(f"Invalid offline evaluation label: {label}")
        if label not in labels:
            labels.append(label)

    if not labels:
        raise ValueError("At least one offline evaluation label is required")

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
            CREATE TABLE IF NOT EXISTS ai_offline_evaluation_governance_reviews (
                governance_review_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_evaluation_label TEXT NOT NULL,
                source_guard_review_label TEXT,
                source_collection_label TEXT,
                source_registry_label TEXT,
                source_build_label TEXT,
                source_schedule_label TEXT,
                source_learning_run_label TEXT,
                source_multi_cycle_track_label TEXT,
                source_session_label TEXT,
                source_portfolio_label TEXT,
                final_label_count INTEGER NOT NULL,
                evaluation_case_count INTEGER NOT NULL,
                metric_count INTEGER NOT NULL,
                evidence_count INTEGER NOT NULL,
                pass_evidence_count INTEGER NOT NULL,
                fail_evidence_count INTEGER NOT NULL,
                board_vote_count INTEGER NOT NULL,
                approve_vote_count INTEGER NOT NULL,
                review_vote_count INTEGER NOT NULL,
                block_vote_count INTEGER NOT NULL,
                governance_check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                leakage_breach_count INTEGER NOT NULL,
                training_eligible_count INTEGER NOT NULL,
                training_locked_count INTEGER NOT NULL,
                baseline_accuracy_pct TEXT NOT NULL,
                average_label_confidence TEXT NOT NULL,
                average_net_paper_outcome_bps TEXT NOT NULL,
                governance_state TEXT NOT NULL,
                governance_decision TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_offline_evaluation_governance_evidence (
                evidence_id TEXT PRIMARY KEY,
                governance_review_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_evaluation_label TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_offline_evaluation_governance_votes (
                vote_id TEXT PRIMARY KEY,
                governance_review_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_evaluation_label TEXT NOT NULL,
                board_role TEXT NOT NULL,
                vote_status TEXT NOT NULL,
                vote_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_offline_evaluation_governance_checks (
                check_id TEXT PRIMARY KEY,
                governance_review_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_evaluation_label TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_offline_evaluation_governance_reports (
                report_label TEXT PRIMARY KEY,
                governance_review_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_evaluation_label TEXT NOT NULL,
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


def load_evaluation_run(conn: sqlite3.Connection, evaluation_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, EVAL_RUNS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM ai_offline_evaluation_runs
        WHERE evaluation_label = ?
        """,
        (evaluation_label,),
    ).fetchone()


def load_evaluation_cases(conn: sqlite3.Connection, evaluation_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, EVAL_CASES_TABLE):
        return []

    order_by = order_clause(conn, EVAL_CASES_TABLE, "evaluation_case_id")
    return conn.execute(
        f"""
        SELECT *
        FROM ai_offline_evaluation_cases
        WHERE evaluation_label = ?
        ORDER BY {order_by}
        """,
        (evaluation_label,),
    ).fetchall()


def load_evaluation_metrics(conn: sqlite3.Connection, evaluation_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, EVAL_METRICS_TABLE):
        return []

    order_by = order_clause(conn, EVAL_METRICS_TABLE, "metric_id")
    return conn.execute(
        f"""
        SELECT *
        FROM ai_offline_evaluation_metrics
        WHERE evaluation_label = ?
        ORDER BY {order_by}
        """,
        (evaluation_label,),
    ).fetchall()


def load_evaluation_checks(conn: sqlite3.Connection, evaluation_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, EVAL_CHECKS_TABLE):
        return []

    order_by = order_clause(conn, EVAL_CHECKS_TABLE, "check_id")
    return conn.execute(
        f"""
        SELECT *
        FROM ai_offline_evaluation_checks
        WHERE evaluation_label = ?
        ORDER BY {order_by}
        """,
        (evaluation_label,),
    ).fetchall()


def governance_evidence(
    governance_review_label: str,
    created_at: str,
    evaluation_label: str,
    category: str,
    name: str,
    passed: bool,
    observed: Any,
    required: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "evidence_id": f"{governance_review_label}-{category}-{name}".replace(" ", "_"),
        "governance_review_label": governance_review_label,
        "created_at": created_at,
        "source_evaluation_label": evaluation_label,
        "evidence_category": category,
        "evidence_name": name,
        "evidence_status": EVIDENCE_PASS if passed else EVIDENCE_FAIL,
        "observed_value": str(observed),
        "required_value": str(required),
        "evidence_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "governance_role": "OFFLINE_EVALUATION_EVIDENCE_ONLY",
            "model_training_enabled": False,
            "live_signal_generation_enabled": False,
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
            "autonomous_trading_enabled": False,
            "automatic_strategy_reweighting_enabled": False,
            "not_profitability_claim": True,
        },
    }


def build_missing_evidence(review_label: str, created_at: str, evaluation_label: str) -> list[dict[str, Any]]:
    return [
        governance_evidence(
            review_label,
            created_at,
            evaluation_label,
            "availability",
            "offline evaluation run exists",
            False,
            "missing",
            "ai_offline_evaluation_runs record",
            "No offline evaluation run exists for this label.",
        )
    ]


def build_governance_evidence(
    review_label: str,
    created_at: str,
    evaluation_label: str,
    evaluation_run: sqlite3.Row,
    cases: list[sqlite3.Row],
    metrics: list[sqlite3.Row],
    checks: list[sqlite3.Row],
    min_cases: int,
    min_metrics: int,
) -> list[dict[str, Any]]:
    safety_count = safe_int(row_get(evaluation_run, "safety_breach_count", 0))
    safety_count += sum(1 for row in [evaluation_run, *cases, *metrics, *checks] if safety_problem(row))

    source_fail_count = safe_int(row_get(evaluation_run, "fail_check_count", 0))
    leakage_breach_count = safe_int(row_get(evaluation_run, "leakage_breach_count", 0))
    training_eligible_count = safe_int(row_get(evaluation_run, "training_eligible_count", 0))
    training_locked_count = safe_int(row_get(evaluation_run, "training_locked_count", 0))
    case_count = len(cases)
    metric_count = len(metrics)
    check_count = len(checks)

    return [
        governance_evidence(review_label, created_at, evaluation_label, "availability", "offline evaluation run exists", True, "present", "present", "Offline evaluation run exists."),
        governance_evidence(review_label, created_at, evaluation_label, "safety", "safety breach count", safety_count == 0, safety_count, 0, "Governance requires zero safety breaches."),
        governance_evidence(review_label, created_at, evaluation_label, "evaluation", "evaluation decision ready", row_get(evaluation_run, "evaluation_decision", "") == EVAL_DECISION_READY, row_get(evaluation_run, "evaluation_decision", ""), EVAL_DECISION_READY, "Offline evaluation must be approved for governance review."),
        governance_evidence(review_label, created_at, evaluation_label, "evaluation", "evaluation verdict ready", row_get(evaluation_run, "global_verdict", "") == EVAL_VERDICT_READY, row_get(evaluation_run, "global_verdict", ""), EVAL_VERDICT_READY, "Offline evaluation verdict must be ready and shadow-only."),
        governance_evidence(review_label, created_at, evaluation_label, "evaluation", "evaluation state ready", row_get(evaluation_run, "evaluation_state", "") == EVAL_STATE_READY, row_get(evaluation_run, "evaluation_state", ""), EVAL_STATE_READY, "Offline evaluation state must be ready."),
        governance_evidence(review_label, created_at, evaluation_label, "evaluation", "source failed checks", source_fail_count == 0, source_fail_count, 0, "Offline evaluation failed checks must remain zero."),
        governance_evidence(review_label, created_at, evaluation_label, "leakage", "leakage breach count", leakage_breach_count == 0, leakage_breach_count, 0, "Governance cannot approve evidence with leakage breaches."),
        governance_evidence(review_label, created_at, evaluation_label, "coverage", "evaluation case count", case_count >= min_cases, case_count, f">= {min_cases}", "Enough offline evaluation cases must exist."),
        governance_evidence(review_label, created_at, evaluation_label, "metrics", "metric count", metric_count >= min_metrics, metric_count, f">= {min_metrics}", "Core offline evaluation metric set must exist."),
        governance_evidence(review_label, created_at, evaluation_label, "checks", "evaluation check count", check_count >= 16, check_count, ">= 16", "Offline evaluation checks must be available for governance review."),
        governance_evidence(review_label, created_at, evaluation_label, "training_lock", "training remains locked", training_eligible_count == 0 and training_locked_count >= min_cases, f"eligible={training_eligible_count}, locked={training_locked_count}", f"eligible=0, locked>={min_cases}", "Governance cannot unlock model training."),
        governance_evidence(review_label, created_at, evaluation_label, "mode", "evaluation mode no training", row_get(evaluation_run, "evaluation_mode", "") == EVAL_MODE_REQUIRED, row_get(evaluation_run, "evaluation_mode", ""), EVAL_MODE_REQUIRED, "Evaluation mode must be offline and no-training."),
        governance_evidence(review_label, created_at, evaluation_label, "profitability", "baseline accuracy not profitability", True, row_get(evaluation_run, "baseline_accuracy_pct", "0"), "governance note only", "Baseline accuracy is label agreement only, not profitability evidence."),
        governance_evidence(review_label, created_at, evaluation_label, "capital", "capital deployment blocked", str(row_get(evaluation_run, "capital_deployment", CAPITAL_DEPLOYMENT_STATUS)) == CAPITAL_DEPLOYMENT_STATUS, row_get(evaluation_run, "capital_deployment", ""), CAPITAL_DEPLOYMENT_STATUS, "Capital deployment must remain blocked."),
    ]


def governance_check(
    governance_review_label: str,
    created_at: str,
    evaluation_label: str,
    category: str,
    name: str,
    passed: bool,
    observed: Any,
    threshold: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{governance_review_label}-{category}-{name}".replace(" ", "_"),
        "governance_review_label": governance_review_label,
        "created_at": created_at,
        "source_evaluation_label": evaluation_label,
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
            "governance_role": "OFFLINE_EVALUATION_GOVERNANCE_CHECK_ONLY",
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


def build_governance_checks(
    review_label: str,
    created_at: str,
    evaluation_label: str,
    evaluation_run: sqlite3.Row | None,
    evidence: list[dict[str, Any]],
    votes: list[dict[str, Any]],
    min_approve_votes: int,
) -> list[dict[str, Any]]:
    if evaluation_run is None:
        return [
            governance_check(
                review_label,
                created_at,
                evaluation_label,
                "availability",
                "offline evaluation run exists",
                False,
                "missing",
                "present",
                "Offline evaluation evidence is missing.",
            )
        ]

    fail_evidence_count = sum(1 for item in evidence if item["evidence_status"] == EVIDENCE_FAIL)
    safety_evidence_failed = any(item["evidence_category"] == "safety" and item["evidence_status"] == EVIDENCE_FAIL for item in evidence)
    approve_votes = sum(1 for vote in votes if vote["vote_status"] == VOTE_APPROVE)
    review_votes = sum(1 for vote in votes if vote["vote_status"] == VOTE_REVIEW)
    block_votes = sum(1 for vote in votes if vote["vote_status"] == VOTE_BLOCK)

    return [
        governance_check(review_label, created_at, evaluation_label, "availability", "offline evaluation run exists", True, "present", "present", "Offline evaluation run exists."),
        governance_check(review_label, created_at, evaluation_label, "evidence", "evidence failure count", fail_evidence_count == 0, fail_evidence_count, 0, "Governance evidence must have zero failures."),
        governance_check(review_label, created_at, evaluation_label, "safety", "safety evidence status", not safety_evidence_failed, safety_evidence_failed, False, "Safety evidence must pass."),
        governance_check(review_label, created_at, evaluation_label, "votes", "approve vote count", approve_votes >= min_approve_votes, approve_votes, f">= {min_approve_votes}", "Enough board roles must approve research-only handoff."),
        governance_check(review_label, created_at, evaluation_label, "votes", "review vote count", review_votes == 0, review_votes, 0, "Review votes must be zero for approval."),
        governance_check(review_label, created_at, evaluation_label, "votes", "block vote count", block_votes == 0, block_votes, 0, "Block votes must be zero for approval."),
        governance_check(review_label, created_at, evaluation_label, "training_lock", "model training remains disabled", True, "disabled", "disabled", "Governance board does not train a model."),
        governance_check(review_label, created_at, evaluation_label, "live_trading", "live trading remains disabled", str(row_get(evaluation_run, "live_trading", LIVE_TRADING_STATUS)) == LIVE_TRADING_STATUS, row_get(evaluation_run, "live_trading", ""), LIVE_TRADING_STATUS, "Governance board cannot approve live trading."),
        governance_check(review_label, created_at, evaluation_label, "capital", "capital deployment remains blocked", str(row_get(evaluation_run, "capital_deployment", CAPITAL_DEPLOYMENT_STATUS)) == CAPITAL_DEPLOYMENT_STATUS, row_get(evaluation_run, "capital_deployment", ""), CAPITAL_DEPLOYMENT_STATUS, "Governance board cannot approve capital deployment."),
        governance_check(review_label, created_at, evaluation_label, "profitability", "no profitability claim", True, "baseline accuracy is label agreement only", "no profitability claim", "Governance report must not treat baseline accuracy as profitability."),
    ]


def build_votes(
    review_label: str,
    created_at: str,
    evaluation_label: str,
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    fail_count = sum(1 for item in evidence if item["evidence_status"] == EVIDENCE_FAIL)
    safety_fail = any(item["evidence_category"] == "safety" and item["evidence_status"] == EVIDENCE_FAIL for item in evidence)

    if safety_fail:
        status = VOTE_BLOCK
        reason = "Safety evidence failed. Governance board blocks handoff."
    elif fail_count:
        status = VOTE_REVIEW
        reason = "One or more evidence checks failed. Governance board requires review."
    else:
        status = VOTE_APPROVE
        reason = "Evidence passes for research-only recommendation handoff. No training or trading is approved."

    votes = []
    for role in BOARD_ROLES:
        votes.append(
            {
                "vote_id": f"{review_label}-{role}".replace(" ", "_"),
                "governance_review_label": review_label,
                "created_at": created_at,
                "source_evaluation_label": evaluation_label,
                "board_role": role,
                "vote_status": status,
                "vote_reason": reason,
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT_VALUE,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "metadata": {
                    "governance_role": "BOARD_VOTE_ONLY",
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
        )

    return votes


def decide_governance_outcome(
    evaluation_run: sqlite3.Row | None,
    checks: list[dict[str, Any]],
) -> tuple[str, str, str, str, str, str]:
    if evaluation_run is None:
        return (
            DECISION_REJECT_MISSING,
            VERDICT_MISSING,
            ACTION_REFRESH,
            "Mission 77 AI Offline Evaluation Harness",
            GOVERNANCE_STATE_MISSING,
            "Offline evaluation evidence is missing.",
        )

    failed = [check for check in checks if check["check_status"] == CHECK_FAIL]

    if any(check["check_category"] == "safety" for check in failed):
        return (
            DECISION_BLOCK_SAFETY,
            VERDICT_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 78 safety remediation",
            GOVERNANCE_STATE_BLOCKED,
            "Safety invariant failed during offline evaluation governance review.",
        )

    if failed:
        return (
            DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 77 AI Offline Evaluation Harness",
            GOVERNANCE_STATE_UNSTABLE,
            "Governance review failed one or more checks.",
        )

    return (
        DECISION_READY,
        VERDICT_READY,
        ACTION_READY,
        NEXT_READY,
        GOVERNANCE_STATE_READY,
        "Offline evaluation governance approved research-only recommendation handoff. No model training, live signals, or trading are approved.",
    )


def build_summary(
    db_path: str | Path,
    review_label: str,
    report_label: str,
    created_at: str,
    evaluation_label: str,
    evaluation_run: sqlite3.Row | None,
    cases: list[sqlite3.Row],
    metrics: list[sqlite3.Row],
    evidence: list[dict[str, Any]],
    votes: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    decision: str,
    verdict: str,
    action: str,
    next_mission: str,
    state: str,
    reason: str,
) -> dict[str, Any]:
    pass_evidence_count = sum(1 for item in evidence if item["evidence_status"] == EVIDENCE_PASS)
    fail_evidence_count = sum(1 for item in evidence if item["evidence_status"] == EVIDENCE_FAIL)
    approve_vote_count = sum(1 for vote in votes if vote["vote_status"] == VOTE_APPROVE)
    review_vote_count = sum(1 for vote in votes if vote["vote_status"] == VOTE_REVIEW)
    block_vote_count = sum(1 for vote in votes if vote["vote_status"] == VOTE_BLOCK)
    pass_check_count = sum(1 for check in checks if check["check_status"] == CHECK_PASS)
    fail_check_count = sum(1 for check in checks if check["check_status"] == CHECK_FAIL)

    return {
        "governance_review_label": review_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_evaluation_label": evaluation_label,
        "source_guard_review_label": row_get(evaluation_run, "source_guard_review_label", None),
        "source_collection_label": row_get(evaluation_run, "source_collection_label", None),
        "source_registry_label": row_get(evaluation_run, "source_registry_label", None),
        "source_build_label": row_get(evaluation_run, "source_build_label", None),
        "source_schedule_label": row_get(evaluation_run, "source_schedule_label", None),
        "source_learning_run_label": row_get(evaluation_run, "source_learning_run_label", None),
        "source_multi_cycle_track_label": row_get(evaluation_run, "source_multi_cycle_track_label", None),
        "source_session_label": row_get(evaluation_run, "source_session_label", None),
        "source_portfolio_label": row_get(evaluation_run, "source_portfolio_label", None),
        "final_label_count": safe_int(row_get(evaluation_run, "final_label_count", 0)),
        "evaluation_case_count": len(cases),
        "metric_count": len(metrics),
        "evidence_count": len(evidence),
        "pass_evidence_count": pass_evidence_count,
        "fail_evidence_count": fail_evidence_count,
        "board_vote_count": len(votes),
        "approve_vote_count": approve_vote_count,
        "review_vote_count": review_vote_count,
        "block_vote_count": block_vote_count,
        "governance_check_count": len(checks),
        "pass_check_count": pass_check_count,
        "fail_check_count": fail_check_count,
        "safety_breach_count": safe_int(row_get(evaluation_run, "safety_breach_count", 0)),
        "leakage_breach_count": safe_int(row_get(evaluation_run, "leakage_breach_count", 0)),
        "training_eligible_count": safe_int(row_get(evaluation_run, "training_eligible_count", 0)),
        "training_locked_count": safe_int(row_get(evaluation_run, "training_locked_count", 0)),
        "baseline_accuracy_pct": round8(safe_float(row_get(evaluation_run, "baseline_accuracy_pct", 0.0))),
        "average_label_confidence": round8(safe_float(row_get(evaluation_run, "average_label_confidence", 0.0))),
        "average_net_paper_outcome_bps": round8(safe_float(row_get(evaluation_run, "average_net_paper_outcome_bps", 0.0))),
        "governance_evidence": evidence,
        "board_votes": votes,
        "governance_checks": checks,
        "governance_state": state,
        "governance_decision": decision,
        "global_verdict": verdict,
        "recommended_action": action,
        "next_mission": next_mission,
        "decision_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    evidence_lines = [
        f"- {item['evidence_category']} / {item['evidence_name']}: status={item['evidence_status']}, observed={item['observed_value']}, required={item['required_value']}"
        for item in summary["governance_evidence"]
    ]

    vote_lines = [
        f"- {vote['board_role']}: {vote['vote_status']} — {vote['vote_reason']}"
        for vote in summary["board_votes"]
    ]

    check_lines = [
        f"- {check['check_category']} / {check['check_name']}: status={check['check_status']}, observed={check['observed_value']}, threshold={check['threshold_value']}"
        for check in summary["governance_checks"]
    ]

    return f"""# DeltaGrid Mission 78 AI Offline Evaluation Governance Board Report

Report label: {summary['report_label']}
Governance review label: {summary['governance_review_label']}
Created at: {summary['created_at']}
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

## Governance Summary

Final label count: {summary['final_label_count']}
Evaluation case count: {summary['evaluation_case_count']}
Metric count: {summary['metric_count']}
Evidence count: {summary['evidence_count']}
Pass evidence count: {summary['pass_evidence_count']}
Fail evidence count: {summary['fail_evidence_count']}

Board vote count: {summary['board_vote_count']}
Approve vote count: {summary['approve_vote_count']}
Review vote count: {summary['review_vote_count']}
Block vote count: {summary['block_vote_count']}

Governance check count: {summary['governance_check_count']}
Pass check count: {summary['pass_check_count']}
Fail check count: {summary['fail_check_count']}
Safety breach count: {summary['safety_breach_count']}
Leakage breach count: {summary['leakage_breach_count']}
Training eligible count: {summary['training_eligible_count']}
Training locked count: {summary['training_locked_count']}

Baseline accuracy pct: {summary['baseline_accuracy_pct']}
Average label confidence: {summary['average_label_confidence']}
Average net paper outcome bps: {summary['average_net_paper_outcome_bps']}

## Evidence

{chr(10).join(evidence_lines) if evidence_lines else "- None"}

## Board Votes

{chr(10).join(vote_lines) if vote_lines else "- None"}

## Checks

{chr(10).join(check_lines) if check_lines else "- None"}

## Decision

Governance state: {summary['governance_state']}
Governance decision: {summary['governance_decision']}
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

This governance board does not train a model.
This governance board does not create live trading signals.
This governance board does not perform autonomous trading.
This governance board does not adjust strategy weights automatically.

Baseline accuracy is offline label agreement only.
It is not profitability evidence.
"""


def insert_row(conn: sqlite3.Connection, table_name: str, row: dict[str, Any], columns: list[str]) -> None:
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    values = [row[column] for column in columns]
    conn.execute(f"INSERT OR REPLACE INTO {table_name} ({column_sql}) VALUES ({placeholders})", values)


def persist_governance_review(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM ai_offline_evaluation_governance_evidence WHERE governance_review_label = ?",
            (summary["governance_review_label"],),
        )
        conn.execute(
            "DELETE FROM ai_offline_evaluation_governance_votes WHERE governance_review_label = ?",
            (summary["governance_review_label"],),
        )
        conn.execute(
            "DELETE FROM ai_offline_evaluation_governance_checks WHERE governance_review_label = ?",
            (summary["governance_review_label"],),
        )
        conn.execute(
            "DELETE FROM ai_offline_evaluation_governance_reviews WHERE governance_review_label = ?",
            (summary["governance_review_label"],),
        )
        conn.execute(
            "DELETE FROM ai_offline_evaluation_governance_reports WHERE governance_review_label = ? OR report_label = ?",
            (summary["governance_review_label"], summary["report_label"]),
        )

        for item in summary["governance_evidence"]:
            stored = dict(item)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                EVIDENCE_TABLE,
                stored,
                [
                    "evidence_id", "governance_review_label", "created_at",
                    "source_evaluation_label", "evidence_category", "evidence_name",
                    "evidence_status", "observed_value", "required_value",
                    "evidence_reason", "live_trading", "live_order_sent",
                    "capital_deployment", "metadata_json",
                ],
            )

        for vote in summary["board_votes"]:
            stored_vote = dict(vote)
            stored_vote["metadata_json"] = json.dumps(stored_vote.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                VOTES_TABLE,
                stored_vote,
                [
                    "vote_id", "governance_review_label", "created_at",
                    "source_evaluation_label", "board_role", "vote_status",
                    "vote_reason", "live_trading", "live_order_sent",
                    "capital_deployment", "metadata_json",
                ],
            )

        for check in summary["governance_checks"]:
            stored_check = dict(check)
            stored_check["metadata_json"] = json.dumps(stored_check.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                CHECKS_TABLE,
                stored_check,
                [
                    "check_id", "governance_review_label", "created_at",
                    "source_evaluation_label", "check_category", "check_name",
                    "check_status", "observed_value", "threshold_value",
                    "check_reason", "live_trading", "live_order_sent",
                    "capital_deployment", "metadata_json",
                ],
            )

        review_row = {
            "governance_review_label": summary["governance_review_label"],
            "report_label": summary["report_label"],
            "created_at": summary["created_at"],
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
            "final_label_count": summary["final_label_count"],
            "evaluation_case_count": summary["evaluation_case_count"],
            "metric_count": summary["metric_count"],
            "evidence_count": summary["evidence_count"],
            "pass_evidence_count": summary["pass_evidence_count"],
            "fail_evidence_count": summary["fail_evidence_count"],
            "board_vote_count": summary["board_vote_count"],
            "approve_vote_count": summary["approve_vote_count"],
            "review_vote_count": summary["review_vote_count"],
            "block_vote_count": summary["block_vote_count"],
            "governance_check_count": summary["governance_check_count"],
            "pass_check_count": summary["pass_check_count"],
            "fail_check_count": summary["fail_check_count"],
            "safety_breach_count": summary["safety_breach_count"],
            "leakage_breach_count": summary["leakage_breach_count"],
            "training_eligible_count": summary["training_eligible_count"],
            "training_locked_count": summary["training_locked_count"],
            "baseline_accuracy_pct": str(summary["baseline_accuracy_pct"]),
            "average_label_confidence": str(summary["average_label_confidence"]),
            "average_net_paper_outcome_bps": str(summary["average_net_paper_outcome_bps"]),
            "governance_state": summary["governance_state"],
            "governance_decision": summary["governance_decision"],
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
            REVIEWS_TABLE,
            review_row,
            [
                "governance_review_label", "report_label", "created_at",
                "source_evaluation_label", "source_guard_review_label",
                "source_collection_label", "source_registry_label", "source_build_label",
                "source_schedule_label", "source_learning_run_label",
                "source_multi_cycle_track_label", "source_session_label",
                "source_portfolio_label", "final_label_count", "evaluation_case_count",
                "metric_count", "evidence_count", "pass_evidence_count",
                "fail_evidence_count", "board_vote_count", "approve_vote_count",
                "review_vote_count", "block_vote_count", "governance_check_count",
                "pass_check_count", "fail_check_count", "safety_breach_count",
                "leakage_breach_count", "training_eligible_count",
                "training_locked_count", "baseline_accuracy_pct",
                "average_label_confidence", "average_net_paper_outcome_bps",
                "governance_state", "governance_decision", "global_verdict",
                "recommended_action", "next_mission", "live_trading",
                "live_order_sent", "capital_deployment", "summary_json",
                "markdown_report",
            ],
        )

        report_row = {
            "report_label": summary["report_label"],
            "governance_review_label": summary["governance_review_label"],
            "created_at": summary["created_at"],
            "source_evaluation_label": summary["source_evaluation_label"],
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
                "report_label", "governance_review_label", "created_at",
                "source_evaluation_label", "global_verdict", "recommended_action",
                "report_json", "markdown_report", "live_trading",
                "live_order_sent", "capital_deployment",
            ],
        )

        conn.commit()


def run_ai_offline_evaluation_governance_board(
    db_path: str | Path = "offchain/deltagrid.db",
    governance_review_label: str | None = None,
    report_label: str | None = None,
    evaluation_label: str = "mission77-final-check",
    min_cases: int = 4,
    min_metrics: int = 10,
    min_approve_votes: int = 5,
) -> dict[str, Any]:
    if min_cases <= 0:
        raise ValueError("min_cases must be positive")
    if min_metrics <= 0:
        raise ValueError("min_metrics must be positive")
    if min_approve_votes <= 0:
        raise ValueError("min_approve_votes must be positive")

    db = Path(db_path)
    review = governance_review_label or new_review_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    source_evaluation_label = parse_labels(evaluation_label)[0]

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        evaluation_run = load_evaluation_run(conn, source_evaluation_label)
        cases = load_evaluation_cases(conn, source_evaluation_label)
        metrics = load_evaluation_metrics(conn, source_evaluation_label)
        source_checks = load_evaluation_checks(conn, source_evaluation_label)

    if evaluation_run is None:
        evidence = build_missing_evidence(review, created_at, source_evaluation_label)
        votes: list[dict[str, Any]] = []
    else:
        evidence = build_governance_evidence(
            review_label=review,
            created_at=created_at,
            evaluation_label=source_evaluation_label,
            evaluation_run=evaluation_run,
            cases=cases,
            metrics=metrics,
            checks=source_checks,
            min_cases=min_cases,
            min_metrics=min_metrics,
        )
        votes = build_votes(review, created_at, source_evaluation_label, evidence)

    checks = build_governance_checks(
        review_label=review,
        created_at=created_at,
        evaluation_label=source_evaluation_label,
        evaluation_run=evaluation_run,
        evidence=evidence,
        votes=votes,
        min_approve_votes=min_approve_votes,
    )

    decision, verdict, action, next_mission, state, reason = decide_governance_outcome(evaluation_run, checks)

    summary = build_summary(
        db_path=db,
        review_label=review,
        report_label=report,
        created_at=created_at,
        evaluation_label=source_evaluation_label,
        evaluation_run=evaluation_run,
        cases=cases,
        metrics=metrics,
        evidence=evidence,
        votes=votes,
        checks=checks,
        decision=decision,
        verdict=verdict,
        action=action,
        next_mission=next_mission,
        state=state,
        reason=reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_governance_review(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid AI offline evaluation governance board.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--governance-review-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--evaluation-label", default="mission77-final-check")
    parser.add_argument("--min-cases", type=int, default=4)
    parser.add_argument("--min-metrics", type=int, default=10)
    parser.add_argument("--min-approve-votes", type=int, default=5)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_ai_offline_evaluation_governance_board(
        db_path=args.db,
        governance_review_label=args.governance_review_label,
        report_label=args.report_label,
        evaluation_label=args.evaluation_label,
        min_cases=args.min_cases,
        min_metrics=args.min_metrics,
        min_approve_votes=args.min_approve_votes,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

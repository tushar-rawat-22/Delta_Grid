"""
Mission 80: Autonomous Policy Gate.

This replaces the earlier Human Approval Gate direction with a machine-checkable
autonomous policy gate.

Boundary:
- paper-only autonomous progression may be approved
- live trading remains disabled
- capital deployment remains blocked
- model training remains disabled
- live signals remain disabled
- execution remains disabled
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


SOURCE_RUNS_TABLE = "ai_research_recommendation_runs"
SOURCE_ITEMS_TABLE = "ai_research_recommendation_items"
SOURCE_CHECKS_TABLE = "ai_research_recommendation_checks"

RUNS_TABLE = "ai_autonomous_policy_gate_runs"
RULES_TABLE = "ai_autonomous_policy_gate_rules"
DECISIONS_TABLE = "ai_autonomous_policy_gate_decisions"
CHECKS_TABLE = "ai_autonomous_policy_gate_checks"
REPORTS_TABLE = "ai_autonomous_policy_gate_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

SOURCE_ENGINE_STATE_READY = "AI_RESEARCH_RECOMMENDATION_ENGINE_READY_RESEARCH_ONLY"
SOURCE_ENGINE_DECISION_READY = "AI_RESEARCH_RECOMMENDATION_ENGINE_APPROVED_FOR_HUMAN_REVIEW_ONLY"
SOURCE_VERDICT_READY = "AI_RESEARCH_RECOMMENDATION_READY_SHADOW_ONLY"

POLICY_SCOPE = "AUTONOMOUS_POLICY_GATE_PAPER_ONLY"
POLICY_MODE = "MACHINE_CHECKABLE_POLICY_GATE_NO_LIVE_TRADING"

RULE_PASS = "AI_AUTONOMOUS_POLICY_RULE_PASS"
RULE_FAIL = "AI_AUTONOMOUS_POLICY_RULE_FAIL"

DECISION_PASS = "AI_AUTONOMOUS_POLICY_DECISION_PASS"
DECISION_FAIL = "AI_AUTONOMOUS_POLICY_DECISION_FAIL"

CHECK_PASS = "AI_AUTONOMOUS_POLICY_GATE_CHECK_PASS"
CHECK_FAIL = "AI_AUTONOMOUS_POLICY_GATE_CHECK_FAIL"

POLICY_STATE_READY = "AI_AUTONOMOUS_POLICY_GATE_READY_PAPER_ONLY"
POLICY_STATE_UNSTABLE = "AI_AUTONOMOUS_POLICY_GATE_UNSTABLE"
POLICY_STATE_BLOCKED = "AI_AUTONOMOUS_POLICY_GATE_BLOCKED"
POLICY_STATE_MISSING = "AI_AUTONOMOUS_POLICY_GATE_MISSING"

POLICY_DECISION_READY = "AI_AUTONOMOUS_POLICY_GATE_APPROVED_FOR_AUTONOMOUS_PAPER_SIGNAL_ENGINE"
POLICY_DECISION_UNSTABLE = "AI_AUTONOMOUS_POLICY_GATE_REVIEW_REQUIRED"
POLICY_DECISION_BLOCK_SAFETY = "AI_AUTONOMOUS_POLICY_GATE_BLOCKED_BY_SAFETY_POLICY"
POLICY_DECISION_REJECT_MISSING = "AI_AUTONOMOUS_POLICY_GATE_REJECTED_MISSING_EVIDENCE"

VERDICT_READY = "AI_AUTONOMOUS_POLICY_GATE_READY_SHADOW_ONLY"
VERDICT_UNSTABLE = "AI_AUTONOMOUS_POLICY_GATE_UNSTABLE_SHADOW_ONLY"
VERDICT_BLOCKED = "AI_AUTONOMOUS_POLICY_GATE_BLOCKED_SHADOW_ONLY"
VERDICT_MISSING = "AI_AUTONOMOUS_POLICY_GATE_MISSING_EVIDENCE"

ACTION_READY = "HAND_OFF_TO_AUTONOMOUS_PAPER_SIGNAL_ENGINE"
ACTION_REVIEW_UNSTABLE = "REVIEW_AUTONOMOUS_POLICY_GATE_EVIDENCE"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_AUTONOMOUS_POLICY_GATE_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_AI_RESEARCH_RECOMMENDATION_ENGINE"

NEXT_READY = "Mission 81 Autonomous Paper Signal Engine"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_policy_run_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission80-autonomous-policy-gate-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission80-autonomous-policy-gate-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
    except Exception:
        pass
    return default


def parse_labels(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return ["mission79-final-check"]

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    labels: list[str] = []

    for item in raw_items:
        label = str(item).strip()
        if not label:
            continue
        if any(ch.isspace() for ch in label):
            raise ValueError(f"Invalid recommendation run label: {label}")
        if label not in labels:
            labels.append(label)

    if not labels:
        raise ValueError("At least one recommendation run label is required")

    return labels


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not table_exists(conn, table_name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def order_clause(conn: sqlite3.Connection, table_name: str, fallback_column: str) -> str:
    cols = table_columns(conn, table_name)
    if "created_at" in cols and fallback_column in cols:
        return f"created_at ASC, {fallback_column} ASC"
    if fallback_column in cols:
        return f"{fallback_column} ASC"
    return "rowid ASC"


def ensure_schema(db_path: str | Path) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_autonomous_policy_gate_runs (
                policy_run_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_recommendation_run_label TEXT NOT NULL,
                source_governance_review_label TEXT,
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
                policy_scope TEXT NOT NULL,
                policy_mode TEXT NOT NULL,
                policy_rule_count INTEGER NOT NULL,
                pass_rule_count INTEGER NOT NULL,
                fail_rule_count INTEGER NOT NULL,
                policy_decision_count INTEGER NOT NULL,
                pass_decision_count INTEGER NOT NULL,
                fail_decision_count INTEGER NOT NULL,
                policy_check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                source_recommendation_count INTEGER NOT NULL,
                source_ready_recommendation_count INTEGER NOT NULL,
                source_blocked_recommendation_count INTEGER NOT NULL,
                source_human_review_required_count INTEGER NOT NULL,
                source_no_live_signal_count INTEGER NOT NULL,
                source_no_execution_count INTEGER NOT NULL,
                source_no_capital_deployment_count INTEGER NOT NULL,
                source_training_disabled_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                leakage_breach_count INTEGER NOT NULL,
                training_eligible_count INTEGER NOT NULL,
                training_locked_count INTEGER NOT NULL,
                baseline_accuracy_pct TEXT NOT NULL,
                average_label_confidence TEXT NOT NULL,
                average_net_paper_outcome_bps TEXT NOT NULL,
                policy_state TEXT NOT NULL,
                policy_decision TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_autonomous_policy_gate_rules (
                rule_id TEXT PRIMARY KEY,
                policy_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_recommendation_run_label TEXT NOT NULL,
                rule_code TEXT NOT NULL,
                rule_category TEXT NOT NULL,
                rule_name TEXT NOT NULL,
                rule_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                required_value TEXT NOT NULL,
                rule_reason TEXT NOT NULL,
                policy_scope TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_autonomous_policy_gate_decisions (
                decision_id TEXT PRIMARY KEY,
                policy_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_recommendation_run_label TEXT NOT NULL,
                decision_category TEXT NOT NULL,
                decision_name TEXT NOT NULL,
                decision_status TEXT NOT NULL,
                decision_value TEXT NOT NULL,
                decision_reason TEXT NOT NULL,
                policy_scope TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_autonomous_policy_gate_checks (
                check_id TEXT PRIMARY KEY,
                policy_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_recommendation_run_label TEXT NOT NULL,
                check_category TEXT NOT NULL,
                check_name TEXT NOT NULL,
                check_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                threshold_value TEXT NOT NULL,
                check_reason TEXT NOT NULL,
                policy_scope TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_autonomous_policy_gate_reports (
                report_label TEXT PRIMARY KEY,
                policy_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_recommendation_run_label TEXT NOT NULL,
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


def load_recommendation_run(conn: sqlite3.Connection, run_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, SOURCE_RUNS_TABLE):
        return None
    return conn.execute(
        "SELECT * FROM ai_research_recommendation_runs WHERE recommendation_run_label = ?",
        (run_label,),
    ).fetchone()


def load_recommendation_items(conn: sqlite3.Connection, run_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, SOURCE_ITEMS_TABLE):
        return []
    order_by = order_clause(conn, SOURCE_ITEMS_TABLE, "recommendation_id")
    return conn.execute(
        f"SELECT * FROM ai_research_recommendation_items WHERE recommendation_run_label = ? ORDER BY {order_by}",
        (run_label,),
    ).fetchall()


def load_recommendation_checks(conn: sqlite3.Connection, run_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, SOURCE_CHECKS_TABLE):
        return []
    order_by = order_clause(conn, SOURCE_CHECKS_TABLE, "check_id")
    return conn.execute(
        f"SELECT * FROM ai_research_recommendation_checks WHERE recommendation_run_label = ? ORDER BY {order_by}",
        (run_label,),
    ).fetchall()


def base_metadata(role: str) -> dict[str, Any]:
    return {
        "policy_role": role,
        "policy_scope": POLICY_SCOPE,
        "paper_only": True,
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
    }


def make_rule(
    run_label: str,
    created_at: str,
    source_label: str,
    code: str,
    category: str,
    name: str,
    passed: bool,
    observed: Any,
    required: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "rule_id": f"{run_label}-{code}".replace(" ", "_"),
        "policy_run_label": run_label,
        "created_at": created_at,
        "source_recommendation_run_label": source_label,
        "rule_code": code,
        "rule_category": category,
        "rule_name": name,
        "rule_status": RULE_PASS if passed else RULE_FAIL,
        "observed_value": str(observed),
        "required_value": str(required),
        "rule_reason": reason,
        "policy_scope": POLICY_SCOPE,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": base_metadata("MACHINE_CHECKABLE_POLICY_RULE"),
    }


def build_missing_rules(run_label: str, created_at: str, source_label: str) -> list[dict[str, Any]]:
    return [
        make_rule(
            run_label,
            created_at,
            source_label,
            "R001",
            "availability",
            "source recommendation run exists",
            False,
            "missing",
            "present",
            "Source Mission 79 recommendation run is missing.",
        )
    ]


def build_policy_rules(
    run_label: str,
    created_at: str,
    source_label: str,
    source_run: sqlite3.Row,
    items: list[sqlite3.Row],
    source_checks: list[sqlite3.Row],
    min_recommendations: int,
) -> list[dict[str, Any]]:
    recommendation_count = safe_int(row_get(source_run, "recommendation_count", len(items)))
    ready_count = safe_int(row_get(source_run, "ready_recommendation_count", 0))
    blocked_count = safe_int(row_get(source_run, "blocked_recommendation_count", 0))
    failed_checks = safe_int(row_get(source_run, "fail_check_count", 0))
    safety_count = safe_int(row_get(source_run, "safety_breach_count", 0))
    safety_count += sum(1 for row in [source_run, *items, *source_checks] if safety_problem(row))
    leakage_count = safe_int(row_get(source_run, "leakage_breach_count", 0))
    training_eligible_count = safe_int(row_get(source_run, "training_eligible_count", 0))
    no_live_signal_count = safe_int(row_get(source_run, "no_live_signal_count", 0))
    no_execution_count = safe_int(row_get(source_run, "no_execution_count", 0))
    no_capital_count = safe_int(row_get(source_run, "no_capital_deployment_count", 0))
    training_disabled_count = safe_int(row_get(source_run, "training_disabled_count", 0))

    source_ready = (
        row_get(source_run, "engine_state", "") == SOURCE_ENGINE_STATE_READY
        and row_get(source_run, "engine_decision", "") == SOURCE_ENGINE_DECISION_READY
        and row_get(source_run, "global_verdict", "") == SOURCE_VERDICT_READY
    )

    return [
        make_rule(run_label, created_at, source_label, "R001", "availability", "source recommendation run exists", True, "present", "present", "Source Mission 79 recommendation run exists."),
        make_rule(run_label, created_at, source_label, "R002", "source", "source engine ready", source_ready, f"state={row_get(source_run, 'engine_state', '')}, decision={row_get(source_run, 'engine_decision', '')}, verdict={row_get(source_run, 'global_verdict', '')}", "ready research-only source", "Source recommendation engine must be ready."),
        make_rule(run_label, created_at, source_label, "R003", "source", "zero source failed checks", failed_checks == 0, failed_checks, 0, "Source recommendation failed checks must remain zero."),
        make_rule(run_label, created_at, source_label, "R004", "safety", "zero safety breaches", safety_count == 0, safety_count, 0, "Safety breach count must be zero."),
        make_rule(run_label, created_at, source_label, "R005", "leakage", "zero leakage breaches", leakage_count == 0, leakage_count, 0, "Leakage breach count must be zero."),
        make_rule(run_label, created_at, source_label, "R006", "training_lock", "no model training", training_eligible_count == 0 and training_disabled_count == recommendation_count and recommendation_count >= min_recommendations, f"eligible={training_eligible_count}, disabled={training_disabled_count}, recommendations={recommendation_count}", f"eligible=0, disabled={recommendation_count}, recommendations>={min_recommendations}", "Model training must remain disabled."),
        make_rule(run_label, created_at, source_label, "R007", "live_signal", "no live signals", no_live_signal_count == recommendation_count and recommendation_count >= min_recommendations, no_live_signal_count, recommendation_count, "Recommendations must not create live signals."),
        make_rule(run_label, created_at, source_label, "R008", "execution", "no execution", no_execution_count == recommendation_count and recommendation_count >= min_recommendations, no_execution_count, recommendation_count, "Recommendations must not permit execution."),
        make_rule(run_label, created_at, source_label, "R009", "capital", "no capital deployment", no_capital_count == recommendation_count and recommendation_count >= min_recommendations, no_capital_count, recommendation_count, "Recommendations must not permit capital deployment."),
        make_rule(run_label, created_at, source_label, "R010", "live_trading", "live trading disabled", str(row_get(source_run, "live_trading", "")) == LIVE_TRADING_STATUS and safe_int(row_get(source_run, "live_order_sent", 1)) == 0, f"live_trading={row_get(source_run, 'live_trading', '')}, live_order_sent={row_get(source_run, 'live_order_sent', '')}", f"live_trading={LIVE_TRADING_STATUS}, live_order_sent=0", "Live trading must remain disabled."),
        make_rule(run_label, created_at, source_label, "R011", "paper_only", "paper only autonomous progression", recommendation_count >= min_recommendations and ready_count == recommendation_count and blocked_count == 0, f"ready={ready_count}, blocked={blocked_count}, recommendations={recommendation_count}", f"ready={recommendation_count}, blocked=0, recommendations>={min_recommendations}", "Only autonomous paper-signal progression may be approved."),
        make_rule(run_label, created_at, source_label, "R012", "profitability", "no profitability claim", True, row_get(source_run, "baseline_accuracy_pct", "0"), "label agreement only", "Baseline accuracy is not profitability evidence."),
    ]


def make_decision(
    run_label: str,
    created_at: str,
    source_label: str,
    category: str,
    name: str,
    passed: bool,
    value: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "decision_id": f"{run_label}-{category}-{name}".replace(" ", "_"),
        "policy_run_label": run_label,
        "created_at": created_at,
        "source_recommendation_run_label": source_label,
        "decision_category": category,
        "decision_name": name,
        "decision_status": DECISION_PASS if passed else DECISION_FAIL,
        "decision_value": value,
        "decision_reason": reason,
        "policy_scope": POLICY_SCOPE,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": base_metadata("AUTONOMOUS_POLICY_DECISION"),
    }


def build_policy_decisions(
    run_label: str,
    created_at: str,
    source_label: str,
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    all_rules_passed = all(rule["rule_status"] == RULE_PASS for rule in rules)

    return [
        make_decision(run_label, created_at, source_label, "autonomy", "allow autonomous paper signal engine", all_rules_passed, "ALLOW_PAPER_ONLY" if all_rules_passed else "BLOCK", "Allow only autonomous paper-signal progression when all policy rules pass."),
        make_decision(run_label, created_at, source_label, "training", "keep model training disabled", True, "KEEP_MODEL_TRAINING_DISABLED", "Mission 80 does not approve model training."),
        make_decision(run_label, created_at, source_label, "live_trading", "keep live trading disabled", True, "KEEP_LIVE_TRADING_DISABLED", "Mission 80 does not approve live trading."),
        make_decision(run_label, created_at, source_label, "capital", "keep capital deployment blocked", True, "KEEP_CAPITAL_DEPLOYMENT_BLOCKED", "Mission 80 does not approve real capital."),
        make_decision(run_label, created_at, source_label, "execution", "keep execution disabled", True, "KEEP_EXECUTION_DISABLED", "Mission 80 does not approve exchange orders."),
    ]


def make_check(
    run_label: str,
    created_at: str,
    source_label: str,
    category: str,
    name: str,
    passed: bool,
    observed: Any,
    threshold: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{run_label}-{category}-{name}".replace(" ", "_"),
        "policy_run_label": run_label,
        "created_at": created_at,
        "source_recommendation_run_label": source_label,
        "check_category": category,
        "check_name": name,
        "check_status": CHECK_PASS if passed else CHECK_FAIL,
        "observed_value": str(observed),
        "threshold_value": str(threshold),
        "check_reason": reason,
        "policy_scope": POLICY_SCOPE,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": base_metadata("AUTONOMOUS_POLICY_GATE_CHECK"),
    }


def build_policy_checks(
    run_label: str,
    created_at: str,
    source_label: str,
    source_run: sqlite3.Row | None,
    rules: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    min_rules: int,
) -> list[dict[str, Any]]:
    if source_run is None:
        return [
            make_check(run_label, created_at, source_label, "availability", "source recommendation run exists", False, "missing", "present", "Source recommendation run is missing.")
        ]

    rule_count = len(rules)
    failed_rule_count = sum(1 for rule in rules if rule["rule_status"] == RULE_FAIL)
    failed_decision_count = sum(1 for decision in decisions if decision["decision_status"] == DECISION_FAIL)
    paper_allow_count = sum(1 for decision in decisions if decision["decision_value"] == "ALLOW_PAPER_ONLY")
    safety_count = safe_int(row_get(source_run, "safety_breach_count", 0))
    leakage_count = safe_int(row_get(source_run, "leakage_breach_count", 0))
    training_eligible_count = safe_int(row_get(source_run, "training_eligible_count", 0))
    recommendation_count = safe_int(row_get(source_run, "recommendation_count", 0))

    return [
        make_check(run_label, created_at, source_label, "availability", "source recommendation run exists", True, "present", "present", "Source recommendation run exists."),
        make_check(run_label, created_at, source_label, "rules", "policy rule count", rule_count >= min_rules, rule_count, f">= {min_rules}", "Policy gate must evaluate the full policy rule set."),
        make_check(run_label, created_at, source_label, "rules", "policy failed rule count", failed_rule_count == 0, failed_rule_count, 0, "No policy rule may fail."),
        make_check(run_label, created_at, source_label, "decisions", "policy failed decision count", failed_decision_count == 0, failed_decision_count, 0, "No policy decision may fail."),
        make_check(run_label, created_at, source_label, "autonomy", "paper-only autonomy approved", paper_allow_count == 1, paper_allow_count, 1, "Only paper-only autonomous progression may be approved."),
        make_check(run_label, created_at, source_label, "safety", "safety breach count", safety_count == 0, safety_count, 0, "Safety breach count must remain zero."),
        make_check(run_label, created_at, source_label, "leakage", "leakage breach count", leakage_count == 0, leakage_count, 0, "Leakage breach count must remain zero."),
        make_check(run_label, created_at, source_label, "training_lock", "training remains disabled", training_eligible_count == 0, training_eligible_count, 0, "Model training remains disabled."),
        make_check(run_label, created_at, source_label, "recommendations", "recommendations exist", recommendation_count > 0, recommendation_count, "> 0", "Research recommendations must exist before paper autonomy."),
        make_check(run_label, created_at, source_label, "live_trading", "live trading disabled", str(row_get(source_run, "live_trading", "")) == LIVE_TRADING_STATUS, row_get(source_run, "live_trading", ""), LIVE_TRADING_STATUS, "Live trading must remain disabled."),
        make_check(run_label, created_at, source_label, "capital", "capital deployment blocked", str(row_get(source_run, "capital_deployment", "")) == CAPITAL_DEPLOYMENT_STATUS, row_get(source_run, "capital_deployment", ""), CAPITAL_DEPLOYMENT_STATUS, "Capital deployment must remain blocked."),
        make_check(run_label, created_at, source_label, "profitability", "no profitability claim", True, "baseline accuracy is label agreement only", "no profitability claim", "Policy gate does not treat baseline accuracy as profit evidence."),
    ]


def decide_policy_outcome(
    source_run: sqlite3.Row | None,
    checks: list[dict[str, Any]],
) -> tuple[str, str, str, str, str, str]:
    if source_run is None:
        return (
            POLICY_DECISION_REJECT_MISSING,
            VERDICT_MISSING,
            ACTION_REFRESH,
            "Mission 79 AI Research Recommendation Engine",
            POLICY_STATE_MISSING,
            "Source recommendation run is missing.",
        )

    failed = [check for check in checks if check["check_status"] == CHECK_FAIL]

    if any(check["check_category"] == "safety" for check in failed):
        return (
            POLICY_DECISION_BLOCK_SAFETY,
            VERDICT_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 80 safety remediation",
            POLICY_STATE_BLOCKED,
            "Safety invariant failed during autonomous policy gate review.",
        )

    if failed:
        return (
            POLICY_DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 79 AI Research Recommendation Engine",
            POLICY_STATE_UNSTABLE,
            "Autonomous policy gate failed one or more checks.",
        )

    return (
        POLICY_DECISION_READY,
        VERDICT_READY,
        ACTION_READY,
        NEXT_READY,
        POLICY_STATE_READY,
        "Autonomous policy gate approved paper-only progression. No live trading, capital deployment, model training, or execution is approved.",
    )


def build_summary(
    db_path: str | Path,
    run_label: str,
    report_label: str,
    created_at: str,
    source_label: str,
    source_run: sqlite3.Row | None,
    rules: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    policy_decision: str,
    verdict: str,
    action: str,
    next_mission: str,
    state: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "policy_run_label": run_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_recommendation_run_label": source_label,
        "source_governance_review_label": row_get(source_run, "source_governance_review_label", None),
        "source_evaluation_label": row_get(source_run, "source_evaluation_label", None),
        "source_guard_review_label": row_get(source_run, "source_guard_review_label", None),
        "source_collection_label": row_get(source_run, "source_collection_label", None),
        "source_registry_label": row_get(source_run, "source_registry_label", None),
        "source_build_label": row_get(source_run, "source_build_label", None),
        "source_schedule_label": row_get(source_run, "source_schedule_label", None),
        "source_learning_run_label": row_get(source_run, "source_learning_run_label", None),
        "source_multi_cycle_track_label": row_get(source_run, "source_multi_cycle_track_label", None),
        "source_session_label": row_get(source_run, "source_session_label", None),
        "source_portfolio_label": row_get(source_run, "source_portfolio_label", None),
        "policy_scope": POLICY_SCOPE,
        "policy_mode": POLICY_MODE,
        "policy_rule_count": len(rules),
        "pass_rule_count": sum(1 for rule in rules if rule["rule_status"] == RULE_PASS),
        "fail_rule_count": sum(1 for rule in rules if rule["rule_status"] == RULE_FAIL),
        "policy_decision_count": len(decisions),
        "pass_decision_count": sum(1 for decision in decisions if decision["decision_status"] == DECISION_PASS),
        "fail_decision_count": sum(1 for decision in decisions if decision["decision_status"] == DECISION_FAIL),
        "policy_check_count": len(checks),
        "pass_check_count": sum(1 for check in checks if check["check_status"] == CHECK_PASS),
        "fail_check_count": sum(1 for check in checks if check["check_status"] == CHECK_FAIL),
        "source_recommendation_count": safe_int(row_get(source_run, "recommendation_count", 0)),
        "source_ready_recommendation_count": safe_int(row_get(source_run, "ready_recommendation_count", 0)),
        "source_blocked_recommendation_count": safe_int(row_get(source_run, "blocked_recommendation_count", 0)),
        "source_human_review_required_count": safe_int(row_get(source_run, "human_review_required_count", 0)),
        "source_no_live_signal_count": safe_int(row_get(source_run, "no_live_signal_count", 0)),
        "source_no_execution_count": safe_int(row_get(source_run, "no_execution_count", 0)),
        "source_no_capital_deployment_count": safe_int(row_get(source_run, "no_capital_deployment_count", 0)),
        "source_training_disabled_count": safe_int(row_get(source_run, "training_disabled_count", 0)),
        "safety_breach_count": safe_int(row_get(source_run, "safety_breach_count", 0)),
        "leakage_breach_count": safe_int(row_get(source_run, "leakage_breach_count", 0)),
        "training_eligible_count": safe_int(row_get(source_run, "training_eligible_count", 0)),
        "training_locked_count": safe_int(row_get(source_run, "training_locked_count", 0)),
        "baseline_accuracy_pct": round8(safe_float(row_get(source_run, "baseline_accuracy_pct", 0.0))),
        "average_label_confidence": round8(safe_float(row_get(source_run, "average_label_confidence", 0.0))),
        "average_net_paper_outcome_bps": round8(safe_float(row_get(source_run, "average_net_paper_outcome_bps", 0.0))),
        "policy_rules": rules,
        "policy_decisions": decisions,
        "policy_checks": checks,
        "policy_state": state,
        "policy_decision": policy_decision,
        "global_verdict": verdict,
        "recommended_action": action,
        "next_mission": next_mission,
        "decision_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    rule_lines = [
        f"- {rule['rule_code']} {rule['rule_category']} / {rule['rule_name']}: status={rule['rule_status']}, observed={rule['observed_value']}, required={rule['required_value']}"
        for rule in summary["policy_rules"]
    ]

    decision_lines = [
        f"- {decision['decision_category']} / {decision['decision_name']}: status={decision['decision_status']}, value={decision['decision_value']}"
        for decision in summary["policy_decisions"]
    ]

    check_lines = [
        f"- {check['check_category']} / {check['check_name']}: status={check['check_status']}, observed={check['observed_value']}, threshold={check['threshold_value']}"
        for check in summary["policy_checks"]
    ]

    return f"""# DeltaGrid Mission 80 Autonomous Policy Gate Report

Report label: {summary['report_label']}
Policy run label: {summary['policy_run_label']}
Created at: {summary['created_at']}
Source recommendation run label: {summary['source_recommendation_run_label']}
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

## Architecture Decision

Mission 80 replaces the earlier Human Approval Gate path with an Autonomous Policy Gate.

This does not mean live autonomous trading is approved.
It means DeltaGrid can progress from research recommendations to autonomous paper-only signal generation when machine-checkable policy rules pass.

## Policy Summary

Policy scope: {summary['policy_scope']}
Policy mode: {summary['policy_mode']}

Policy rule count: {summary['policy_rule_count']}
Pass rule count: {summary['pass_rule_count']}
Fail rule count: {summary['fail_rule_count']}

Policy decision count: {summary['policy_decision_count']}
Pass decision count: {summary['pass_decision_count']}
Fail decision count: {summary['fail_decision_count']}

Policy check count: {summary['policy_check_count']}
Pass check count: {summary['pass_check_count']}
Fail check count: {summary['fail_check_count']}

Source recommendation count: {summary['source_recommendation_count']}
Source ready recommendation count: {summary['source_ready_recommendation_count']}
Source blocked recommendation count: {summary['source_blocked_recommendation_count']}
Source human review required count: {summary['source_human_review_required_count']}
Source no live signal count: {summary['source_no_live_signal_count']}
Source no execution count: {summary['source_no_execution_count']}
Source no capital deployment count: {summary['source_no_capital_deployment_count']}
Source training disabled count: {summary['source_training_disabled_count']}

Safety breach count: {summary['safety_breach_count']}
Leakage breach count: {summary['leakage_breach_count']}
Training eligible count: {summary['training_eligible_count']}
Training locked count: {summary['training_locked_count']}

Baseline accuracy pct: {summary['baseline_accuracy_pct']}
Average label confidence: {summary['average_label_confidence']}
Average net paper outcome bps: {summary['average_net_paper_outcome_bps']}

## Policy Rules

{chr(10).join(rule_lines) if rule_lines else "- None"}

## Policy Decisions

{chr(10).join(decision_lines) if decision_lines else "- None"}

## Checks

{chr(10).join(check_lines) if check_lines else "- None"}

## Decision

Policy state: {summary['policy_state']}
Policy decision: {summary['policy_decision']}
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

This policy gate does not train a model.
This policy gate does not create live trading signals.
This policy gate does not perform autonomous live trading.
This policy gate does not adjust live strategy weights automatically.

Only autonomous paper-only progression may be approved.

Baseline accuracy is offline label agreement only.
It is not profitability evidence.
"""


def insert_row(conn: sqlite3.Connection, table_name: str, row: dict[str, Any], columns: list[str]) -> None:
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT OR REPLACE INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})",
        [row[column] for column in columns],
    )


def persist_policy_run(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for table in (RULES_TABLE, DECISIONS_TABLE, CHECKS_TABLE, RUNS_TABLE):
            conn.execute(f"DELETE FROM {table} WHERE policy_run_label = ?", (summary["policy_run_label"],))

        conn.execute(
            "DELETE FROM ai_autonomous_policy_gate_reports WHERE policy_run_label = ? OR report_label = ?",
            (summary["policy_run_label"], summary["report_label"]),
        )

        for rule in summary["policy_rules"]:
            stored = dict(rule)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                RULES_TABLE,
                stored,
                [
                    "rule_id", "policy_run_label", "created_at",
                    "source_recommendation_run_label", "rule_code", "rule_category",
                    "rule_name", "rule_status", "observed_value", "required_value",
                    "rule_reason", "policy_scope", "live_trading", "live_order_sent",
                    "capital_deployment", "metadata_json",
                ],
            )

        for decision in summary["policy_decisions"]:
            stored = dict(decision)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                DECISIONS_TABLE,
                stored,
                [
                    "decision_id", "policy_run_label", "created_at",
                    "source_recommendation_run_label", "decision_category",
                    "decision_name", "decision_status", "decision_value",
                    "decision_reason", "policy_scope", "live_trading",
                    "live_order_sent", "capital_deployment", "metadata_json",
                ],
            )

        for check in summary["policy_checks"]:
            stored = dict(check)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                CHECKS_TABLE,
                stored,
                [
                    "check_id", "policy_run_label", "created_at",
                    "source_recommendation_run_label", "check_category", "check_name",
                    "check_status", "observed_value", "threshold_value",
                    "check_reason", "policy_scope", "live_trading", "live_order_sent",
                    "capital_deployment", "metadata_json",
                ],
            )

        run_row = {
            **{key: summary[key] for key in [
                "policy_run_label", "report_label", "created_at",
                "source_recommendation_run_label", "source_governance_review_label",
                "source_evaluation_label", "source_guard_review_label",
                "source_collection_label", "source_registry_label", "source_build_label",
                "source_schedule_label", "source_learning_run_label",
                "source_multi_cycle_track_label", "source_session_label",
                "source_portfolio_label", "policy_scope", "policy_mode",
                "policy_rule_count", "pass_rule_count", "fail_rule_count",
                "policy_decision_count", "pass_decision_count", "fail_decision_count",
                "policy_check_count", "pass_check_count", "fail_check_count",
                "source_recommendation_count", "source_ready_recommendation_count",
                "source_blocked_recommendation_count",
                "source_human_review_required_count", "source_no_live_signal_count",
                "source_no_execution_count", "source_no_capital_deployment_count",
                "source_training_disabled_count", "safety_breach_count",
                "leakage_breach_count", "training_eligible_count",
                "training_locked_count", "baseline_accuracy_pct",
                "average_label_confidence", "average_net_paper_outcome_bps",
                "policy_state", "policy_decision", "global_verdict",
                "recommended_action", "next_mission", "live_trading",
                "live_order_sent", "capital_deployment",
            ]},
            "summary_json": json.dumps(summary, sort_keys=True),
            "markdown_report": markdown_report,
        }

        insert_row(
            conn,
            RUNS_TABLE,
            run_row,
            [
                "policy_run_label", "report_label", "created_at",
                "source_recommendation_run_label", "source_governance_review_label",
                "source_evaluation_label", "source_guard_review_label",
                "source_collection_label", "source_registry_label", "source_build_label",
                "source_schedule_label", "source_learning_run_label",
                "source_multi_cycle_track_label", "source_session_label",
                "source_portfolio_label", "policy_scope", "policy_mode",
                "policy_rule_count", "pass_rule_count", "fail_rule_count",
                "policy_decision_count", "pass_decision_count", "fail_decision_count",
                "policy_check_count", "pass_check_count", "fail_check_count",
                "source_recommendation_count", "source_ready_recommendation_count",
                "source_blocked_recommendation_count", "source_human_review_required_count",
                "source_no_live_signal_count", "source_no_execution_count",
                "source_no_capital_deployment_count", "source_training_disabled_count",
                "safety_breach_count", "leakage_breach_count", "training_eligible_count",
                "training_locked_count", "baseline_accuracy_pct", "average_label_confidence",
                "average_net_paper_outcome_bps", "policy_state", "policy_decision",
                "global_verdict", "recommended_action", "next_mission", "live_trading",
                "live_order_sent", "capital_deployment", "summary_json", "markdown_report",
            ],
        )

        report_row = {
            "report_label": summary["report_label"],
            "policy_run_label": summary["policy_run_label"],
            "created_at": summary["created_at"],
            "source_recommendation_run_label": summary["source_recommendation_run_label"],
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
                "report_label", "policy_run_label", "created_at",
                "source_recommendation_run_label", "global_verdict",
                "recommended_action", "report_json", "markdown_report",
                "live_trading", "live_order_sent", "capital_deployment",
            ],
        )

        conn.commit()


def run_autonomous_policy_gate(
    db_path: str | Path = "offchain/deltagrid.db",
    policy_run_label: str | None = None,
    report_label: str | None = None,
    recommendation_run_label: str = "mission79-final-check",
    min_recommendations: int = 5,
    min_policy_rules: int = 12,
) -> dict[str, Any]:
    if min_recommendations <= 0:
        raise ValueError("min_recommendations must be positive")
    if min_policy_rules <= 0:
        raise ValueError("min_policy_rules must be positive")

    db = Path(db_path)
    run_label = policy_run_label or new_policy_run_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    source_label = parse_labels(recommendation_run_label)[0]

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        source_run = load_recommendation_run(conn, source_label)
        items = load_recommendation_items(conn, source_label)
        source_checks = load_recommendation_checks(conn, source_label)

    if source_run is None:
        rules = build_missing_rules(run_label, created_at, source_label)
    else:
        rules = build_policy_rules(
            run_label,
            created_at,
            source_label,
            source_run,
            items,
            source_checks,
            min_recommendations,
        )

    decisions = build_policy_decisions(run_label, created_at, source_label, rules)
    checks = build_policy_checks(run_label, created_at, source_label, source_run, rules, decisions, min_policy_rules)

    policy_decision, verdict, action, next_mission, state, reason = decide_policy_outcome(source_run, checks)

    summary = build_summary(
        db,
        run_label,
        report,
        created_at,
        source_label,
        source_run,
        rules,
        decisions,
        checks,
        policy_decision,
        verdict,
        action,
        next_mission,
        state,
        reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_policy_run(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid autonomous policy gate.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--policy-run-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--recommendation-run-label", default="mission79-final-check")
    parser.add_argument("--min-recommendations", type=int, default=5)
    parser.add_argument("--min-policy-rules", type=int, default=12)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_autonomous_policy_gate(
        db_path=args.db,
        policy_run_label=args.policy_run_label,
        report_label=args.report_label,
        recommendation_run_label=args.recommendation_run_label,
        min_recommendations=args.min_recommendations,
        min_policy_rules=args.min_policy_rules,
    )

    print(result["markdown_report"] if args.markdown else json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

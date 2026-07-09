"""
Mission 81: Autonomous Paper Signal Engine.

This module converts Mission 80 autonomous policy approval into paper-only
signal records.

Boundary:
- paper-only signals may be generated
- live trading remains disabled
- capital deployment remains blocked
- model training remains disabled
- exchange execution remains disabled
- private keys are not used
- no live trading signals are produced
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


POLICY_RUNS_TABLE = "ai_autonomous_policy_gate_runs"
POLICY_RULES_TABLE = "ai_autonomous_policy_gate_rules"
POLICY_DECISIONS_TABLE = "ai_autonomous_policy_gate_decisions"
POLICY_CHECKS_TABLE = "ai_autonomous_policy_gate_checks"
RECOMMENDATION_ITEMS_TABLE = "ai_research_recommendation_items"

RUNS_TABLE = "ai_autonomous_paper_signal_runs"
SIGNALS_TABLE = "ai_autonomous_paper_signals"
CHECKS_TABLE = "ai_autonomous_paper_signal_checks"
REPORTS_TABLE = "ai_autonomous_paper_signal_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

SOURCE_POLICY_STATE_READY = "AI_AUTONOMOUS_POLICY_GATE_READY_PAPER_ONLY"
SOURCE_POLICY_DECISION_READY = "AI_AUTONOMOUS_POLICY_GATE_APPROVED_FOR_AUTONOMOUS_PAPER_SIGNAL_ENGINE"
SOURCE_VERDICT_READY = "AI_AUTONOMOUS_POLICY_GATE_READY_SHADOW_ONLY"

PAPER_SIGNAL_SCOPE = "AUTONOMOUS_PAPER_SIGNAL_ONLY"
PAPER_SIGNAL_MODE = "AUTONOMOUS_PAPER_SIGNAL_NO_LIVE_SIGNAL_NO_EXECUTION"
PAPER_SIGNAL_STATUS_READY = "AI_AUTONOMOUS_PAPER_SIGNAL_READY_PAPER_ONLY"
PAPER_SIGNAL_STATUS_BLOCKED = "AI_AUTONOMOUS_PAPER_SIGNAL_BLOCKED"
PAPER_SIGNAL_ACTION = "PAPER_OBSERVE_ONLY_NO_ORDER"

NO_LIVE_SIGNAL = "NO_LIVE_SIGNAL"
NO_EXECUTION = "NO_EXECUTION"
NO_CAPITAL_DEPLOYMENT = "NO_CAPITAL_DEPLOYMENT"
KEEP_MODEL_TRAINING_DISABLED = "KEEP_MODEL_TRAINING_DISABLED"

CHECK_PASS = "AI_AUTONOMOUS_PAPER_SIGNAL_CHECK_PASS"
CHECK_FAIL = "AI_AUTONOMOUS_PAPER_SIGNAL_CHECK_FAIL"

ENGINE_STATE_READY = "AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_READY_PAPER_ONLY"
ENGINE_STATE_UNSTABLE = "AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_UNSTABLE"
ENGINE_STATE_BLOCKED = "AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_BLOCKED"
ENGINE_STATE_MISSING = "AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_MISSING"

ENGINE_DECISION_READY = "AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_APPROVED_FOR_PAPER_EXECUTION_AGENT"
ENGINE_DECISION_UNSTABLE = "AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_REVIEW_REQUIRED"
ENGINE_DECISION_BLOCK_SAFETY = "AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_BLOCKED_BY_SAFETY_POLICY"
ENGINE_DECISION_REJECT_MISSING = "AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_REJECTED_MISSING_POLICY"

VERDICT_READY = "AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_READY_SHADOW_ONLY"
VERDICT_UNSTABLE = "AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_UNSTABLE_SHADOW_ONLY"
VERDICT_BLOCKED = "AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_BLOCKED_SHADOW_ONLY"
VERDICT_MISSING = "AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_MISSING_EVIDENCE"

ACTION_READY = "HAND_OFF_AUTONOMOUS_PAPER_SIGNALS_TO_PAPER_EXECUTION_AGENT"
ACTION_REVIEW_UNSTABLE = "REVIEW_AUTONOMOUS_PAPER_SIGNAL_EVIDENCE"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_AUTONOMOUS_PAPER_SIGNAL_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_AUTONOMOUS_POLICY_GATE"

NEXT_READY = "Mission 82 Paper Execution Agent"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_signal_run_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission81-autonomous-paper-signal-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission81-autonomous-paper-signal-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
        return ["mission80-final-check"]

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    labels: list[str] = []

    for item in raw_items:
        label = str(item).strip()
        if not label:
            continue
        if any(ch.isspace() for ch in label):
            raise ValueError(f"Invalid policy run label: {label}")
        if label not in labels:
            labels.append(label)

    if not labels:
        raise ValueError("At least one policy run label is required")

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
            CREATE TABLE IF NOT EXISTS ai_autonomous_paper_signal_runs (
                signal_run_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_policy_run_label TEXT NOT NULL,
                source_recommendation_run_label TEXT,
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
                paper_signal_scope TEXT NOT NULL,
                paper_signal_mode TEXT NOT NULL,
                paper_signal_count INTEGER NOT NULL,
                ready_signal_count INTEGER NOT NULL,
                blocked_signal_count INTEGER NOT NULL,
                observe_only_signal_count INTEGER NOT NULL,
                no_live_signal_count INTEGER NOT NULL,
                no_execution_count INTEGER NOT NULL,
                no_capital_deployment_count INTEGER NOT NULL,
                training_disabled_count INTEGER NOT NULL,
                source_policy_rule_count INTEGER NOT NULL,
                source_pass_rule_count INTEGER NOT NULL,
                source_fail_rule_count INTEGER NOT NULL,
                source_policy_decision_count INTEGER NOT NULL,
                source_pass_decision_count INTEGER NOT NULL,
                source_fail_decision_count INTEGER NOT NULL,
                source_policy_check_count INTEGER NOT NULL,
                source_pass_check_count INTEGER NOT NULL,
                source_fail_check_count INTEGER NOT NULL,
                signal_check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                leakage_breach_count INTEGER NOT NULL,
                training_eligible_count INTEGER NOT NULL,
                training_locked_count INTEGER NOT NULL,
                baseline_accuracy_pct TEXT NOT NULL,
                average_label_confidence TEXT NOT NULL,
                average_net_paper_outcome_bps TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_autonomous_paper_signals (
                paper_signal_id TEXT PRIMARY KEY,
                signal_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_policy_run_label TEXT NOT NULL,
                source_recommendation_run_label TEXT,
                source_recommendation_id TEXT,
                source_recommendation_code TEXT,
                source_recommendation_title TEXT,
                signal_rank INTEGER NOT NULL,
                paper_signal_code TEXT NOT NULL,
                paper_signal_title TEXT NOT NULL,
                paper_signal_detail TEXT NOT NULL,
                paper_signal_scope TEXT NOT NULL,
                paper_signal_mode TEXT NOT NULL,
                paper_signal_status TEXT NOT NULL,
                paper_signal_action TEXT NOT NULL,
                paper_signal_side TEXT NOT NULL,
                paper_signal_strength TEXT NOT NULL,
                paper_signal_confidence TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_autonomous_paper_signal_checks (
                check_id TEXT PRIMARY KEY,
                signal_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_policy_run_label TEXT NOT NULL,
                check_category TEXT NOT NULL,
                check_name TEXT NOT NULL,
                check_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                threshold_value TEXT NOT NULL,
                check_reason TEXT NOT NULL,
                paper_signal_scope TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_autonomous_paper_signal_reports (
                report_label TEXT PRIMARY KEY,
                signal_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_policy_run_label TEXT NOT NULL,
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


def load_policy_run(conn: sqlite3.Connection, label: str) -> sqlite3.Row | None:
    if not table_exists(conn, POLICY_RUNS_TABLE):
        return None
    return conn.execute(
        "SELECT * FROM ai_autonomous_policy_gate_runs WHERE policy_run_label = ?",
        (label,),
    ).fetchone()


def load_policy_rules(conn: sqlite3.Connection, label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, POLICY_RULES_TABLE):
        return []
    order_by = order_clause(conn, POLICY_RULES_TABLE, "rule_id")
    return conn.execute(
        f"SELECT * FROM ai_autonomous_policy_gate_rules WHERE policy_run_label = ? ORDER BY {order_by}",
        (label,),
    ).fetchall()


def load_policy_decisions(conn: sqlite3.Connection, label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, POLICY_DECISIONS_TABLE):
        return []
    order_by = order_clause(conn, POLICY_DECISIONS_TABLE, "decision_id")
    return conn.execute(
        f"SELECT * FROM ai_autonomous_policy_gate_decisions WHERE policy_run_label = ? ORDER BY {order_by}",
        (label,),
    ).fetchall()


def load_policy_checks(conn: sqlite3.Connection, label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, POLICY_CHECKS_TABLE):
        return []
    order_by = order_clause(conn, POLICY_CHECKS_TABLE, "check_id")
    return conn.execute(
        f"SELECT * FROM ai_autonomous_policy_gate_checks WHERE policy_run_label = ? ORDER BY {order_by}",
        (label,),
    ).fetchall()


def load_recommendation_items(conn: sqlite3.Connection, recommendation_run_label: str | None) -> list[sqlite3.Row]:
    if not recommendation_run_label:
        return []
    if not table_exists(conn, RECOMMENDATION_ITEMS_TABLE):
        return []
    order_by = order_clause(conn, RECOMMENDATION_ITEMS_TABLE, "recommendation_rank")
    return conn.execute(
        f"SELECT * FROM ai_research_recommendation_items WHERE recommendation_run_label = ? ORDER BY {order_by}",
        (recommendation_run_label,),
    ).fetchall()


def base_metadata(role: str) -> dict[str, Any]:
    return {
        "paper_signal_role": role,
        "paper_signal_scope": PAPER_SIGNAL_SCOPE,
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


def build_paper_signals(
    signal_run_label: str,
    created_at: str,
    source_policy_label: str,
    source_run: sqlite3.Row | None,
    recommendation_items: list[sqlite3.Row],
) -> list[dict[str, Any]]:
    if source_run is None:
        return []

    if row_get(source_run, "policy_decision", "") != SOURCE_POLICY_DECISION_READY:
        return []

    signals: list[dict[str, Any]] = []
    source_recommendation_run_label = row_get(source_run, "source_recommendation_run_label", None)

    for index, item in enumerate(recommendation_items, start=1):
        rec_code = str(row_get(item, "recommendation_code", f"RECOMMENDATION_{index}"))
        rec_title = str(row_get(item, "recommendation_title", f"Research recommendation {index}"))
        rec_id = str(row_get(item, "recommendation_id", f"{source_recommendation_run_label}-item-{index}"))

        signals.append(
            {
                "paper_signal_id": f"{signal_run_label}-signal-{index}".replace(" ", "_"),
                "signal_run_label": signal_run_label,
                "created_at": created_at,
                "source_policy_run_label": source_policy_label,
                "source_recommendation_run_label": source_recommendation_run_label,
                "source_recommendation_id": rec_id,
                "source_recommendation_code": rec_code,
                "source_recommendation_title": rec_title,
                "signal_rank": index,
                "paper_signal_code": f"PAPER_ONLY_{rec_code}",
                "paper_signal_title": f"Paper-only signal for {rec_title}",
                "paper_signal_detail": "Autonomous paper-only observe signal. No order, no live signal, no capital, no execution.",
                "paper_signal_scope": PAPER_SIGNAL_SCOPE,
                "paper_signal_mode": PAPER_SIGNAL_MODE,
                "paper_signal_status": PAPER_SIGNAL_STATUS_READY,
                "paper_signal_action": PAPER_SIGNAL_ACTION,
                "paper_signal_side": "NO_TRADE",
                "paper_signal_strength": "0.0",
                "paper_signal_confidence": "0.0",
                "model_training_action": KEEP_MODEL_TRAINING_DISABLED,
                "live_signal_action": NO_LIVE_SIGNAL,
                "execution_action": NO_EXECUTION,
                "capital_action": NO_CAPITAL_DEPLOYMENT,
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT_VALUE,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "metadata": base_metadata("AUTONOMOUS_PAPER_SIGNAL_OBSERVE_ONLY"),
            }
        )

    return signals


def make_check(
    signal_run_label: str,
    created_at: str,
    source_policy_label: str,
    category: str,
    name: str,
    passed: bool,
    observed: Any,
    threshold: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{signal_run_label}-{category}-{name}".replace(" ", "_"),
        "signal_run_label": signal_run_label,
        "created_at": created_at,
        "source_policy_run_label": source_policy_label,
        "check_category": category,
        "check_name": name,
        "check_status": CHECK_PASS if passed else CHECK_FAIL,
        "observed_value": str(observed),
        "threshold_value": str(threshold),
        "check_reason": reason,
        "paper_signal_scope": PAPER_SIGNAL_SCOPE,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": base_metadata("AUTONOMOUS_PAPER_SIGNAL_CHECK"),
    }


def build_missing_checks(signal_run_label: str, created_at: str, source_policy_label: str) -> list[dict[str, Any]]:
    return [
        make_check(
            signal_run_label,
            created_at,
            source_policy_label,
            "availability",
            "source policy run exists",
            False,
            "missing",
            "present",
            "Source Mission 80 policy run is missing.",
        )
    ]


def build_signal_checks(
    signal_run_label: str,
    created_at: str,
    source_policy_label: str,
    source_run: sqlite3.Row,
    rules: list[sqlite3.Row],
    decisions: list[sqlite3.Row],
    policy_checks: list[sqlite3.Row],
    signals: list[dict[str, Any]],
    min_signals: int,
) -> list[dict[str, Any]]:
    signal_count = len(signals)
    ready_count = sum(1 for signal in signals if signal["paper_signal_status"] == PAPER_SIGNAL_STATUS_READY)
    observe_only_count = sum(1 for signal in signals if signal["paper_signal_action"] == PAPER_SIGNAL_ACTION)
    no_live_signal_count = sum(1 for signal in signals if signal["live_signal_action"] == NO_LIVE_SIGNAL)
    no_execution_count = sum(1 for signal in signals if signal["execution_action"] == NO_EXECUTION)
    no_capital_count = sum(1 for signal in signals if signal["capital_action"] == NO_CAPITAL_DEPLOYMENT)
    training_disabled_count = sum(1 for signal in signals if signal["model_training_action"] == KEEP_MODEL_TRAINING_DISABLED)

    source_fail_rules = safe_int(row_get(source_run, "fail_rule_count", 0))
    source_fail_decisions = safe_int(row_get(source_run, "fail_decision_count", 0))
    source_fail_checks = safe_int(row_get(source_run, "fail_check_count", 0))
    safety_count = safe_int(row_get(source_run, "safety_breach_count", 0))
    safety_count += sum(1 for row in [source_run, *rules, *decisions, *policy_checks] if safety_problem(row))
    leakage_count = safe_int(row_get(source_run, "leakage_breach_count", 0))
    training_eligible_count = safe_int(row_get(source_run, "training_eligible_count", 0))

    source_ready = (
        row_get(source_run, "policy_state", "") == SOURCE_POLICY_STATE_READY
        and row_get(source_run, "policy_decision", "") == SOURCE_POLICY_DECISION_READY
        and row_get(source_run, "global_verdict", "") == SOURCE_VERDICT_READY
    )

    return [
        make_check(signal_run_label, created_at, source_policy_label, "availability", "source policy run exists", True, "present", "present", "Source policy run exists."),
        make_check(signal_run_label, created_at, source_policy_label, "policy", "source policy ready", source_ready, f"state={row_get(source_run, 'policy_state', '')}, decision={row_get(source_run, 'policy_decision', '')}, verdict={row_get(source_run, 'global_verdict', '')}", "ready paper-only policy", "Source policy gate must approve paper-only progression."),
        make_check(signal_run_label, created_at, source_policy_label, "rules", "source failed rules", source_fail_rules == 0, source_fail_rules, 0, "Source policy failed rules must remain zero."),
        make_check(signal_run_label, created_at, source_policy_label, "decisions", "source failed decisions", source_fail_decisions == 0, source_fail_decisions, 0, "Source policy failed decisions must remain zero."),
        make_check(signal_run_label, created_at, source_policy_label, "checks", "source failed checks", source_fail_checks == 0, source_fail_checks, 0, "Source policy failed checks must remain zero."),
        make_check(signal_run_label, created_at, source_policy_label, "safety", "safety breach count", safety_count == 0, safety_count, 0, "Safety breach count must be zero."),
        make_check(signal_run_label, created_at, source_policy_label, "leakage", "leakage breach count", leakage_count == 0, leakage_count, 0, "Leakage breach count must be zero."),
        make_check(signal_run_label, created_at, source_policy_label, "signals", "paper signal count", signal_count >= min_signals, signal_count, f">= {min_signals}", "Paper signal engine must produce the minimum paper signal set."),
        make_check(signal_run_label, created_at, source_policy_label, "signals", "ready paper signals", ready_count == signal_count and signal_count > 0, ready_count, signal_count, "Every signal must be ready for paper-only handling."),
        make_check(signal_run_label, created_at, source_policy_label, "paper_only", "observe only signals", observe_only_count == signal_count and signal_count > 0, observe_only_count, signal_count, "Every signal must be observe-only and no-order."),
        make_check(signal_run_label, created_at, source_policy_label, "live_signal", "no live signal generation", no_live_signal_count == signal_count and signal_count > 0, no_live_signal_count, signal_count, "Paper signals must not become live signals."),
        make_check(signal_run_label, created_at, source_policy_label, "execution", "no execution", no_execution_count == signal_count and signal_count > 0, no_execution_count, signal_count, "Paper signals must not permit execution."),
        make_check(signal_run_label, created_at, source_policy_label, "capital", "no capital deployment", no_capital_count == signal_count and signal_count > 0, no_capital_count, signal_count, "Paper signals must not permit capital deployment."),
        make_check(signal_run_label, created_at, source_policy_label, "training_lock", "model training remains disabled", training_eligible_count == 0 and training_disabled_count == signal_count and signal_count > 0, f"eligible={training_eligible_count}, disabled_signals={training_disabled_count}", f"eligible=0, disabled_signals={signal_count}", "Paper signal generation must not unlock model training."),
        make_check(signal_run_label, created_at, source_policy_label, "live_trading", "live trading disabled", str(row_get(source_run, "live_trading", "")) == LIVE_TRADING_STATUS, row_get(source_run, "live_trading", ""), LIVE_TRADING_STATUS, "Live trading must remain disabled."),
        make_check(signal_run_label, created_at, source_policy_label, "profitability", "no profitability claim", True, "paper signals are observe-only", "no profitability claim", "Paper signals are not profitability evidence."),
    ]


def decide_engine_outcome(
    source_run: sqlite3.Row | None,
    checks: list[dict[str, Any]],
) -> tuple[str, str, str, str, str, str]:
    if source_run is None:
        return (
            ENGINE_DECISION_REJECT_MISSING,
            VERDICT_MISSING,
            ACTION_REFRESH,
            "Mission 80 Autonomous Policy Gate",
            ENGINE_STATE_MISSING,
            "Source autonomous policy gate evidence is missing.",
        )

    failed = [check for check in checks if check["check_status"] == CHECK_FAIL]

    if any(check["check_category"] == "safety" for check in failed):
        return (
            ENGINE_DECISION_BLOCK_SAFETY,
            VERDICT_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 81 safety remediation",
            ENGINE_STATE_BLOCKED,
            "Safety invariant failed during autonomous paper signal generation.",
        )

    if failed:
        return (
            ENGINE_DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 80 Autonomous Policy Gate",
            ENGINE_STATE_UNSTABLE,
            "Autonomous paper signal engine failed one or more checks.",
        )

    return (
        ENGINE_DECISION_READY,
        VERDICT_READY,
        ACTION_READY,
        NEXT_READY,
        ENGINE_STATE_READY,
        "Autonomous paper signal engine generated paper-only observe signals. No live trading, capital deployment, model training, or execution is approved.",
    )


def build_summary(
    db_path: str | Path,
    signal_run_label: str,
    report_label: str,
    created_at: str,
    source_policy_label: str,
    source_run: sqlite3.Row | None,
    signals: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    decision: str,
    verdict: str,
    action: str,
    next_mission: str,
    state: str,
    reason: str,
) -> dict[str, Any]:
    signal_count = len(signals)

    return {
        "signal_run_label": signal_run_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_policy_run_label": source_policy_label,
        "source_recommendation_run_label": row_get(source_run, "source_recommendation_run_label", None),
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
        "paper_signal_scope": PAPER_SIGNAL_SCOPE,
        "paper_signal_mode": PAPER_SIGNAL_MODE,
        "paper_signal_count": signal_count,
        "ready_signal_count": sum(1 for signal in signals if signal["paper_signal_status"] == PAPER_SIGNAL_STATUS_READY),
        "blocked_signal_count": sum(1 for signal in signals if signal["paper_signal_status"] == PAPER_SIGNAL_STATUS_BLOCKED),
        "observe_only_signal_count": sum(1 for signal in signals if signal["paper_signal_action"] == PAPER_SIGNAL_ACTION),
        "no_live_signal_count": sum(1 for signal in signals if signal["live_signal_action"] == NO_LIVE_SIGNAL),
        "no_execution_count": sum(1 for signal in signals if signal["execution_action"] == NO_EXECUTION),
        "no_capital_deployment_count": sum(1 for signal in signals if signal["capital_action"] == NO_CAPITAL_DEPLOYMENT),
        "training_disabled_count": sum(1 for signal in signals if signal["model_training_action"] == KEEP_MODEL_TRAINING_DISABLED),
        "source_policy_rule_count": safe_int(row_get(source_run, "policy_rule_count", 0)),
        "source_pass_rule_count": safe_int(row_get(source_run, "pass_rule_count", 0)),
        "source_fail_rule_count": safe_int(row_get(source_run, "fail_rule_count", 0)),
        "source_policy_decision_count": safe_int(row_get(source_run, "policy_decision_count", 0)),
        "source_pass_decision_count": safe_int(row_get(source_run, "pass_decision_count", 0)),
        "source_fail_decision_count": safe_int(row_get(source_run, "fail_decision_count", 0)),
        "source_policy_check_count": safe_int(row_get(source_run, "policy_check_count", 0)),
        "source_pass_check_count": safe_int(row_get(source_run, "pass_check_count", 0)),
        "source_fail_check_count": safe_int(row_get(source_run, "fail_check_count", 0)),
        "signal_check_count": len(checks),
        "pass_check_count": sum(1 for check in checks if check["check_status"] == CHECK_PASS),
        "fail_check_count": sum(1 for check in checks if check["check_status"] == CHECK_FAIL),
        "safety_breach_count": safe_int(row_get(source_run, "safety_breach_count", 0)),
        "leakage_breach_count": safe_int(row_get(source_run, "leakage_breach_count", 0)),
        "training_eligible_count": safe_int(row_get(source_run, "training_eligible_count", 0)),
        "training_locked_count": safe_int(row_get(source_run, "training_locked_count", 0)),
        "baseline_accuracy_pct": round8(safe_float(row_get(source_run, "baseline_accuracy_pct", 0.0))),
        "average_label_confidence": round8(safe_float(row_get(source_run, "average_label_confidence", 0.0))),
        "average_net_paper_outcome_bps": round8(safe_float(row_get(source_run, "average_net_paper_outcome_bps", 0.0))),
        "paper_signals": signals,
        "signal_checks": checks,
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
    signal_lines = [
        f"- #{signal['signal_rank']} {signal['paper_signal_code']}: action={signal['paper_signal_action']}, side={signal['paper_signal_side']}, status={signal['paper_signal_status']}"
        for signal in summary["paper_signals"]
    ]

    check_lines = [
        f"- {check['check_category']} / {check['check_name']}: status={check['check_status']}, observed={check['observed_value']}, threshold={check['threshold_value']}"
        for check in summary["signal_checks"]
    ]

    return f"""# DeltaGrid Mission 81 Autonomous Paper Signal Engine Report

Report label: {summary['report_label']}
Signal run label: {summary['signal_run_label']}
Created at: {summary['created_at']}
Source policy run label: {summary['source_policy_run_label']}
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

## Paper Signal Summary

Paper signal scope: {summary['paper_signal_scope']}
Paper signal mode: {summary['paper_signal_mode']}

Paper signal count: {summary['paper_signal_count']}
Ready signal count: {summary['ready_signal_count']}
Blocked signal count: {summary['blocked_signal_count']}
Observe-only signal count: {summary['observe_only_signal_count']}
No live signal count: {summary['no_live_signal_count']}
No execution count: {summary['no_execution_count']}
No capital deployment count: {summary['no_capital_deployment_count']}
Training disabled count: {summary['training_disabled_count']}

Source policy rule count: {summary['source_policy_rule_count']}
Source pass rule count: {summary['source_pass_rule_count']}
Source fail rule count: {summary['source_fail_rule_count']}
Source policy decision count: {summary['source_policy_decision_count']}
Source pass decision count: {summary['source_pass_decision_count']}
Source fail decision count: {summary['source_fail_decision_count']}
Source policy check count: {summary['source_policy_check_count']}
Source pass check count: {summary['source_pass_check_count']}
Source fail check count: {summary['source_fail_check_count']}

Signal check count: {summary['signal_check_count']}
Pass check count: {summary['pass_check_count']}
Fail check count: {summary['fail_check_count']}
Safety breach count: {summary['safety_breach_count']}
Leakage breach count: {summary['leakage_breach_count']}
Training eligible count: {summary['training_eligible_count']}
Training locked count: {summary['training_locked_count']}

Baseline accuracy pct: {summary['baseline_accuracy_pct']}
Average label confidence: {summary['average_label_confidence']}
Average net paper outcome bps: {summary['average_net_paper_outcome_bps']}

## Paper Signals

{chr(10).join(signal_lines) if signal_lines else "- None"}

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

This engine creates paper-only observe signals.
It does not train a model.
It does not create live trading signals.
It does not perform execution.
It does not deploy capital.
It does not perform autonomous live trading.

Paper signals are not profitability evidence.
"""


def insert_row(conn: sqlite3.Connection, table_name: str, row: dict[str, Any], columns: list[str]) -> None:
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT OR REPLACE INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})",
        [row[column] for column in columns],
    )


def persist_signal_run(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for table in (SIGNALS_TABLE, CHECKS_TABLE, RUNS_TABLE):
            conn.execute(f"DELETE FROM {table} WHERE signal_run_label = ?", (summary["signal_run_label"],))

        conn.execute(
            "DELETE FROM ai_autonomous_paper_signal_reports WHERE signal_run_label = ? OR report_label = ?",
            (summary["signal_run_label"], summary["report_label"]),
        )

        for signal in summary["paper_signals"]:
            stored = dict(signal)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                SIGNALS_TABLE,
                stored,
                [
                    "paper_signal_id", "signal_run_label", "created_at",
                    "source_policy_run_label", "source_recommendation_run_label",
                    "source_recommendation_id", "source_recommendation_code",
                    "source_recommendation_title", "signal_rank",
                    "paper_signal_code", "paper_signal_title",
                    "paper_signal_detail", "paper_signal_scope",
                    "paper_signal_mode", "paper_signal_status",
                    "paper_signal_action", "paper_signal_side",
                    "paper_signal_strength", "paper_signal_confidence",
                    "model_training_action", "live_signal_action",
                    "execution_action", "capital_action", "live_trading",
                    "live_order_sent", "capital_deployment", "metadata_json",
                ],
            )

        for check in summary["signal_checks"]:
            stored = dict(check)
            stored["metadata_json"] = json.dumps(stored.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                CHECKS_TABLE,
                stored,
                [
                    "check_id", "signal_run_label", "created_at",
                    "source_policy_run_label", "check_category", "check_name",
                    "check_status", "observed_value", "threshold_value",
                    "check_reason", "paper_signal_scope", "live_trading",
                    "live_order_sent", "capital_deployment", "metadata_json",
                ],
            )

        run_row = {
            **{key: summary[key] for key in [
                "signal_run_label", "report_label", "created_at",
                "source_policy_run_label", "source_recommendation_run_label",
                "source_governance_review_label", "source_evaluation_label",
                "source_guard_review_label", "source_collection_label",
                "source_registry_label", "source_build_label", "source_schedule_label",
                "source_learning_run_label", "source_multi_cycle_track_label",
                "source_session_label", "source_portfolio_label",
                "paper_signal_scope", "paper_signal_mode",
                "paper_signal_count", "ready_signal_count", "blocked_signal_count",
                "observe_only_signal_count", "no_live_signal_count",
                "no_execution_count", "no_capital_deployment_count",
                "training_disabled_count", "source_policy_rule_count",
                "source_pass_rule_count", "source_fail_rule_count",
                "source_policy_decision_count", "source_pass_decision_count",
                "source_fail_decision_count", "source_policy_check_count",
                "source_pass_check_count", "source_fail_check_count",
                "signal_check_count", "pass_check_count", "fail_check_count",
                "safety_breach_count", "leakage_breach_count",
                "training_eligible_count", "training_locked_count",
                "baseline_accuracy_pct", "average_label_confidence",
                "average_net_paper_outcome_bps", "engine_state",
                "engine_decision", "global_verdict", "recommended_action",
                "next_mission", "live_trading", "live_order_sent",
                "capital_deployment",
            ]},
            "summary_json": json.dumps(summary, sort_keys=True),
            "markdown_report": markdown_report,
        }

        insert_row(
            conn,
            RUNS_TABLE,
            run_row,
            [
                "signal_run_label", "report_label", "created_at",
                "source_policy_run_label", "source_recommendation_run_label",
                "source_governance_review_label", "source_evaluation_label",
                "source_guard_review_label", "source_collection_label",
                "source_registry_label", "source_build_label",
                "source_schedule_label", "source_learning_run_label",
                "source_multi_cycle_track_label", "source_session_label",
                "source_portfolio_label", "paper_signal_scope",
                "paper_signal_mode", "paper_signal_count",
                "ready_signal_count", "blocked_signal_count",
                "observe_only_signal_count", "no_live_signal_count",
                "no_execution_count", "no_capital_deployment_count",
                "training_disabled_count", "source_policy_rule_count",
                "source_pass_rule_count", "source_fail_rule_count",
                "source_policy_decision_count", "source_pass_decision_count",
                "source_fail_decision_count", "source_policy_check_count",
                "source_pass_check_count", "source_fail_check_count",
                "signal_check_count", "pass_check_count", "fail_check_count",
                "safety_breach_count", "leakage_breach_count",
                "training_eligible_count", "training_locked_count",
                "baseline_accuracy_pct", "average_label_confidence",
                "average_net_paper_outcome_bps", "engine_state",
                "engine_decision", "global_verdict", "recommended_action",
                "next_mission", "live_trading", "live_order_sent",
                "capital_deployment", "summary_json", "markdown_report",
            ],
        )

        report_row = {
            "report_label": summary["report_label"],
            "signal_run_label": summary["signal_run_label"],
            "created_at": summary["created_at"],
            "source_policy_run_label": summary["source_policy_run_label"],
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
                "report_label", "signal_run_label", "created_at",
                "source_policy_run_label", "global_verdict",
                "recommended_action", "report_json", "markdown_report",
                "live_trading", "live_order_sent", "capital_deployment",
            ],
        )

        conn.commit()


def run_autonomous_paper_signal_engine(
    db_path: str | Path = "offchain/deltagrid.db",
    signal_run_label: str | None = None,
    report_label: str | None = None,
    policy_run_label: str = "mission80-final-check",
    min_signals: int = 5,
) -> dict[str, Any]:
    if min_signals <= 0:
        raise ValueError("min_signals must be positive")

    db = Path(db_path)
    run_label = signal_run_label or new_signal_run_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    source_policy_label = parse_labels(policy_run_label)[0]

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        source_run = load_policy_run(conn, source_policy_label)
        rules = load_policy_rules(conn, source_policy_label)
        decisions = load_policy_decisions(conn, source_policy_label)
        policy_checks = load_policy_checks(conn, source_policy_label)
        recommendation_items = load_recommendation_items(
            conn,
            row_get(source_run, "source_recommendation_run_label", None),
        )

    signals = build_paper_signals(
        signal_run_label=run_label,
        created_at=created_at,
        source_policy_label=source_policy_label,
        source_run=source_run,
        recommendation_items=recommendation_items,
    )

    if source_run is None:
        signal_checks = build_missing_checks(run_label, created_at, source_policy_label)
    else:
        signal_checks = build_signal_checks(
            signal_run_label=run_label,
            created_at=created_at,
            source_policy_label=source_policy_label,
            source_run=source_run,
            rules=rules,
            decisions=decisions,
            policy_checks=policy_checks,
            signals=signals,
            min_signals=min_signals,
        )

    decision, verdict, action, next_mission, state, reason = decide_engine_outcome(
        source_run=source_run,
        checks=signal_checks,
    )

    summary = build_summary(
        db_path=db,
        signal_run_label=run_label,
        report_label=report,
        created_at=created_at,
        source_policy_label=source_policy_label,
        source_run=source_run,
        signals=signals,
        checks=signal_checks,
        decision=decision,
        verdict=verdict,
        action=action,
        next_mission=next_mission,
        state=state,
        reason=reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_signal_run(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid autonomous paper signal engine.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--signal-run-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--policy-run-label", default="mission80-final-check")
    parser.add_argument("--min-signals", type=int, default=5)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_autonomous_paper_signal_engine(
        db_path=args.db,
        signal_run_label=args.signal_run_label,
        report_label=args.report_label,
        policy_run_label=args.policy_run_label,
        min_signals=args.min_signals,
    )

    print(result["markdown_report"] if args.markdown else json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

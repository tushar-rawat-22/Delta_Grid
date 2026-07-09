"""
Mission 70: AI Paper Outcome Learning Engine.

This module converts multi-cycle paper observation evidence into local,
deterministic AI-learning features, labels, and recommendation-only outputs.

It reads:
- paper_multi_cycle_observation_tracks
- paper_multi_cycle_observation_cycles
- paper_multi_cycle_observation_checks

It writes:
- ai_paper_outcome_learning_runs
- ai_paper_outcome_learning_features
- ai_paper_outcome_learning_labels
- ai_paper_outcome_learning_recommendations
- ai_paper_outcome_learning_reports

It is local AI-learning preparation only.

It never:
- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital
- performs autonomous strategy reweighting
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


TRACKS_TABLE = "paper_multi_cycle_observation_tracks"
CYCLES_TABLE = "paper_multi_cycle_observation_cycles"
CHECKS_TABLE = "paper_multi_cycle_observation_checks"

LEARNING_RUNS_TABLE = "ai_paper_outcome_learning_runs"
FEATURES_TABLE = "ai_paper_outcome_learning_features"
LABELS_TABLE = "ai_paper_outcome_learning_labels"
RECOMMENDATIONS_TABLE = "ai_paper_outcome_learning_recommendations"
REPORTS_TABLE = "ai_paper_outcome_learning_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

MULTI_CYCLE_DECISION_CONFIRMED = "MULTI_CYCLE_OBSERVATION_CONFIRMED_CONTINUE_TRACKING"
MULTI_CYCLE_VERDICT_READY = "MULTI_CYCLE_OBSERVATION_TRACK_READY_SHADOW_ONLY"
MULTI_CYCLE_STATE_CONFIRMED = "MULTI_CYCLE_STATE_CONFIRMED"

MODEL_MODE = "DETERMINISTIC_LOCAL_RULE_BASED_RECOMMENDATION_ONLY"

OUTCOME_LABEL_STABLE = "AI_PAPER_OUTCOME_LABEL_STABLE_MULTI_CYCLE"
OUTCOME_LABEL_EARLY_STABLE = "AI_PAPER_OUTCOME_LABEL_EARLY_STABLE_NEEDS_MORE_CYCLES"
OUTCOME_LABEL_UNSTABLE = "AI_PAPER_OUTCOME_LABEL_UNSTABLE"
OUTCOME_LABEL_BLOCKED = "AI_PAPER_OUTCOME_LABEL_BLOCKED_BY_SAFETY"
OUTCOME_LABEL_MISSING = "AI_PAPER_OUTCOME_LABEL_MISSING_EVIDENCE"

DATA_LABEL_SUFFICIENT = "AI_DATA_SUFFICIENCY_LABEL_MULTI_CYCLE_READY"
DATA_LABEL_EARLY = "AI_DATA_SUFFICIENCY_LABEL_EARLY_NEEDS_MORE_CYCLES"
DATA_LABEL_MISSING = "AI_DATA_SUFFICIENCY_LABEL_MISSING"

RISK_LABEL_CLEAN = "AI_RISK_LABEL_NO_ALERTS_NO_TRIGGERED_EVENTS"
RISK_LABEL_CAUTION = "AI_RISK_LABEL_ALERTS_OR_TRIGGERED_EVENTS_PRESENT"
RISK_LABEL_BLOCKED = "AI_RISK_LABEL_SAFETY_BLOCKED"

AUTONOMY_LABEL_RECOMMENDATION_ONLY = "AI_AUTONOMY_LABEL_RECOMMENDATION_ONLY_NO_TRADING"

DECISION_READY = "AI_PAPER_OUTCOME_LEARNING_READY_FOR_DATASET_EXPANSION"
DECISION_UNSTABLE = "AI_PAPER_OUTCOME_LEARNING_UNSTABLE_REVIEW_REQUIRED"
DECISION_BLOCK_SAFETY = "AI_PAPER_OUTCOME_LEARNING_BLOCKED_BY_SAFETY_POLICY"
DECISION_REJECT_MISSING = "AI_PAPER_OUTCOME_LEARNING_REJECTED_MISSING_EVIDENCE"

VERDICT_READY = "AI_PAPER_OUTCOME_LEARNING_READY_SHADOW_ONLY"
VERDICT_UNSTABLE = "AI_PAPER_OUTCOME_LEARNING_UNSTABLE_SHADOW_ONLY"
VERDICT_BLOCKED = "AI_PAPER_OUTCOME_LEARNING_BLOCKED_SHADOW_ONLY"
VERDICT_MISSING = "AI_PAPER_OUTCOME_LEARNING_MISSING_EVIDENCE"

ACTION_EXPAND_DATASET = "CONTINUE_PAPER_DATASET_EXPANSION_NO_AUTONOMOUS_TRADING"
ACTION_REVIEW_UNSTABLE = "REVIEW_MULTI_CYCLE_EVIDENCE_BEFORE_AI_EXPANSION"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_AI_LEARNING_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_MULTI_CYCLE_PAPER_TRACKING_EVIDENCE"

NEXT_READY = "Mission 71 AI Feature Quality and Drift Guard"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_learning_run_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission70-ai-paper-learning-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission70-ai-paper-learning-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
        return ["mission69-final-check"]

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    labels: list[str] = []

    for item in raw_items:
        label = str(item).strip()

        if not label:
            continue

        if any(ch.isspace() for ch in label):
            raise ValueError(f"Invalid multi-cycle track label: {label}")

        if label not in labels:
            labels.append(label)

    if not labels:
        raise ValueError("At least one multi-cycle track label is required")

    return labels


def normalize_positive(value: float, target: float) -> float:
    if target <= 0:
        return 1.0

    return round8(max(0.0, min(value / target, 1.0)))


def normalize_lower_is_better(value: float, bad_at: float) -> float:
    if bad_at <= 0:
        return 1.0 if value <= 0 else 0.0

    return round8(max(0.0, 1.0 - min(max(value, 0.0) / bad_at, 1.0)))


def normalize_floor(value: float, floor: float) -> float:
    if floor >= 0:
        return 1.0 if value >= floor else 0.0

    if value >= 0:
        return 1.0

    if value <= floor:
        return 0.0

    return round8(1.0 - (abs(value) / abs(floor)))


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
            CREATE TABLE IF NOT EXISTS ai_paper_outcome_learning_runs (
                learning_run_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_multi_cycle_track_label TEXT NOT NULL,
                source_session_label TEXT,
                source_portfolio_label TEXT,
                cycle_count INTEGER NOT NULL,
                feature_count INTEGER NOT NULL,
                label_count INTEGER NOT NULL,
                recommendation_count INTEGER NOT NULL,
                paper_notional TEXT NOT NULL,
                cumulative_net_paper_pnl TEXT NOT NULL,
                cumulative_net_pnl_bps TEXT NOT NULL,
                average_cycle_net_pnl_bps TEXT NOT NULL,
                worst_cycle_net_pnl_bps TEXT NOT NULL,
                worst_position_loss_bps TEXT NOT NULL,
                average_fee_drag_bps TEXT NOT NULL,
                total_alert_count INTEGER NOT NULL,
                total_triggered_event_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                learning_score TEXT NOT NULL,
                outcome_label TEXT NOT NULL,
                data_sufficiency_label TEXT NOT NULL,
                risk_label TEXT NOT NULL,
                autonomy_label TEXT NOT NULL,
                model_mode TEXT NOT NULL,
                learning_decision TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_paper_outcome_learning_features (
                feature_id TEXT PRIMARY KEY,
                learning_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_multi_cycle_track_label TEXT NOT NULL,
                feature_group TEXT NOT NULL,
                feature_name TEXT NOT NULL,
                feature_value TEXT NOT NULL,
                normalized_value TEXT NOT NULL,
                feature_weight TEXT NOT NULL,
                feature_direction TEXT NOT NULL,
                feature_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_paper_outcome_learning_labels (
                label_id TEXT PRIMARY KEY,
                learning_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_multi_cycle_track_label TEXT NOT NULL,
                label_group TEXT NOT NULL,
                label_name TEXT NOT NULL,
                label_value TEXT NOT NULL,
                label_confidence TEXT NOT NULL,
                label_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_paper_outcome_learning_recommendations (
                recommendation_id TEXT PRIMARY KEY,
                learning_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_multi_cycle_track_label TEXT NOT NULL,
                recommendation_type TEXT NOT NULL,
                recommendation_status TEXT NOT NULL,
                recommendation_priority INTEGER NOT NULL,
                recommendation_text TEXT NOT NULL,
                expected_effect TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_paper_outcome_learning_reports (
                report_label TEXT PRIMARY KEY,
                learning_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_multi_cycle_track_label TEXT NOT NULL,
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


def load_multi_cycle_track(conn: sqlite3.Connection, track_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, TRACKS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM paper_multi_cycle_observation_tracks
        WHERE track_label = ?
        """,
        (track_label,),
    ).fetchone()


def load_multi_cycle_cycles(conn: sqlite3.Connection, track_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, CYCLES_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM paper_multi_cycle_observation_cycles
        WHERE track_label = ?
        ORDER BY cycle_index ASC
        """,
        (track_label,),
    ).fetchall()


def load_multi_cycle_checks(conn: sqlite3.Connection, track_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, CHECKS_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM paper_multi_cycle_observation_checks
        WHERE track_label = ?
        ORDER BY created_at ASC, check_id ASC
        """,
        (track_label,),
    ).fetchall()


def feature_row(
    learning_run_label: str,
    created_at: str,
    track_label: str,
    group: str,
    name: str,
    value: Any,
    normalized_value: float,
    weight: float,
    direction: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "feature_id": f"{learning_run_label}-{group}-{name}".replace(" ", "_"),
        "learning_run_label": learning_run_label,
        "created_at": created_at,
        "source_multi_cycle_track_label": track_label,
        "feature_group": group,
        "feature_name": name,
        "feature_value": str(value),
        "normalized_value": str(round8(normalized_value)),
        "feature_weight": str(round8(weight)),
        "feature_direction": direction,
        "feature_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "ai_learning_role": "LOCAL_FEATURE_EXTRACTION_ONLY",
            "model_mode": MODEL_MODE,
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
            "autonomous_trading_enabled": False,
        },
    }


def build_metrics(track: sqlite3.Row | None, cycles: list[sqlite3.Row], checks: list[sqlite3.Row]) -> dict[str, Any]:
    if track is None:
        return {
            "cycle_count": 0,
            "paper_notional": 0.0,
            "cumulative_net_paper_pnl": 0.0,
            "cumulative_net_pnl_bps": 0.0,
            "average_cycle_net_pnl_bps": 0.0,
            "worst_cycle_net_pnl_bps": 0.0,
            "worst_position_loss_bps": 0.0,
            "average_fee_drag_bps": 0.0,
            "total_alert_count": 0,
            "total_triggered_event_count": 0,
            "safety_breach_count": 0,
            "check_count": 0,
            "pass_check_count": 0,
            "fail_check_count": 0,
            "source_session_label": None,
            "source_portfolio_label": None,
        }

    row_safety = sum(1 for row in [track, *cycles, *checks] if safety_problem(row))
    safety_breach_count = safe_int(row_get(track, "safety_breach_count", 0)) + row_safety

    return {
        "cycle_count": safe_int(row_get(track, "cycle_count", len(cycles))),
        "paper_notional": round8(safe_float(row_get(track, "paper_notional", 0.0))),
        "cumulative_net_paper_pnl": round8(safe_float(row_get(track, "cumulative_net_paper_pnl", 0.0))),
        "cumulative_net_pnl_bps": round8(safe_float(row_get(track, "cumulative_net_pnl_bps", 0.0))),
        "average_cycle_net_pnl_bps": round8(safe_float(row_get(track, "average_cycle_net_pnl_bps", 0.0))),
        "worst_cycle_net_pnl_bps": round8(safe_float(row_get(track, "worst_cycle_net_pnl_bps", 0.0))),
        "worst_position_loss_bps": round8(safe_float(row_get(track, "worst_position_loss_bps", 0.0))),
        "average_fee_drag_bps": round8(safe_float(row_get(track, "average_fee_drag_bps", 0.0))),
        "total_alert_count": safe_int(row_get(track, "total_alert_count", 0)),
        "total_triggered_event_count": safe_int(row_get(track, "total_triggered_event_count", 0)),
        "safety_breach_count": safety_breach_count,
        "check_count": safe_int(row_get(track, "check_count", len(checks))),
        "pass_check_count": safe_int(row_get(track, "pass_check_count", 0)),
        "fail_check_count": safe_int(row_get(track, "fail_check_count", 0)),
        "multi_cycle_state": str(row_get(track, "multi_cycle_state", "")),
        "multi_cycle_decision": str(row_get(track, "multi_cycle_decision", "")),
        "global_verdict": str(row_get(track, "global_verdict", "")),
        "source_session_label": row_get(track, "source_session_label", None),
        "source_portfolio_label": row_get(track, "source_portfolio_label", None),
    }


def build_features(
    learning_run_label: str,
    created_at: str,
    track_label: str,
    metrics: dict[str, Any],
    min_recommended_cycles: int,
    max_allowed_learning_loss_bps: float,
    max_allowed_cycle_loss_bps: float,
    max_allowed_position_loss_bps: float,
    max_allowed_fee_drag_bps: float,
) -> list[dict[str, Any]]:
    check_count = safe_float(metrics.get("check_count", 0))
    pass_ratio = safe_float(metrics.get("pass_check_count", 0)) / check_count if check_count > 0 else 0.0

    return [
        feature_row(
            learning_run_label,
            created_at,
            track_label,
            "data",
            "cycle_count",
            metrics["cycle_count"],
            normalize_positive(safe_float(metrics["cycle_count"]), float(min_recommended_cycles)),
            0.10,
            "HIGHER_IS_BETTER",
            "More paper cycles improve AI learning reliability.",
        ),
        feature_row(
            learning_run_label,
            created_at,
            track_label,
            "quality",
            "pass_check_ratio",
            round8(pass_ratio),
            round8(pass_ratio),
            0.12,
            "HIGHER_IS_BETTER",
            "A high pass-check ratio improves dataset trust.",
        ),
        feature_row(
            learning_run_label,
            created_at,
            track_label,
            "performance",
            "cumulative_net_pnl_bps",
            metrics["cumulative_net_pnl_bps"],
            normalize_floor(safe_float(metrics["cumulative_net_pnl_bps"]), -abs(max_allowed_learning_loss_bps)),
            0.12,
            "HIGHER_IS_BETTER",
            "Cumulative paper outcome should avoid severe drawdown.",
        ),
        feature_row(
            learning_run_label,
            created_at,
            track_label,
            "performance",
            "average_cycle_net_pnl_bps",
            metrics["average_cycle_net_pnl_bps"],
            normalize_floor(safe_float(metrics["average_cycle_net_pnl_bps"]), -abs(max_allowed_cycle_loss_bps)),
            0.10,
            "HIGHER_IS_BETTER",
            "Average cycle outcome should remain above the cycle-loss floor.",
        ),
        feature_row(
            learning_run_label,
            created_at,
            track_label,
            "risk",
            "worst_cycle_net_pnl_bps",
            metrics["worst_cycle_net_pnl_bps"],
            normalize_floor(safe_float(metrics["worst_cycle_net_pnl_bps"]), -abs(max_allowed_cycle_loss_bps)),
            0.10,
            "HIGHER_IS_BETTER",
            "Worst cycle outcome should remain controlled.",
        ),
        feature_row(
            learning_run_label,
            created_at,
            track_label,
            "risk",
            "worst_position_loss_bps",
            metrics["worst_position_loss_bps"],
            normalize_floor(safe_float(metrics["worst_position_loss_bps"]), -abs(max_allowed_position_loss_bps)),
            0.10,
            "HIGHER_IS_BETTER",
            "Worst position loss should remain controlled.",
        ),
        feature_row(
            learning_run_label,
            created_at,
            track_label,
            "cost",
            "average_fee_drag_bps",
            metrics["average_fee_drag_bps"],
            normalize_lower_is_better(safe_float(metrics["average_fee_drag_bps"]), max_allowed_fee_drag_bps),
            0.08,
            "LOWER_IS_BETTER",
            "Lower fee drag improves paper outcome quality.",
        ),
        feature_row(
            learning_run_label,
            created_at,
            track_label,
            "alerts",
            "total_alert_count",
            metrics["total_alert_count"],
            normalize_lower_is_better(safe_float(metrics["total_alert_count"]), 1.0),
            0.08,
            "LOWER_IS_BETTER",
            "Fewer alerts improve learning stability.",
        ),
        feature_row(
            learning_run_label,
            created_at,
            track_label,
            "events",
            "total_triggered_event_count",
            metrics["total_triggered_event_count"],
            normalize_lower_is_better(safe_float(metrics["total_triggered_event_count"]), 1.0),
            0.08,
            "LOWER_IS_BETTER",
            "Triggered risk events reduce learning readiness.",
        ),
        feature_row(
            learning_run_label,
            created_at,
            track_label,
            "safety",
            "safety_breach_count",
            metrics["safety_breach_count"],
            normalize_lower_is_better(safe_float(metrics["safety_breach_count"]), 1.0),
            0.08,
            "LOWER_IS_BETTER",
            "Safety breaches block AI learning expansion.",
        ),
        feature_row(
            learning_run_label,
            created_at,
            track_label,
            "state",
            "multi_cycle_state_confirmed",
            metrics.get("multi_cycle_state", ""),
            1.0 if metrics.get("multi_cycle_state") == MULTI_CYCLE_STATE_CONFIRMED else 0.0,
            0.06,
            "BINARY_CONFIRMED_IS_BETTER",
            "Multi-cycle state must be confirmed.",
        ),
        feature_row(
            learning_run_label,
            created_at,
            track_label,
            "state",
            "multi_cycle_verdict_ready",
            metrics.get("global_verdict", ""),
            1.0 if metrics.get("global_verdict") == MULTI_CYCLE_VERDICT_READY else 0.0,
            0.06,
            "BINARY_READY_IS_BETTER",
            "Multi-cycle verdict must be ready.",
        ),
    ]


def compute_learning_score(features: list[dict[str, Any]]) -> float:
    total_weight = sum(safe_float(feature["feature_weight"]) for feature in features)

    if total_weight <= 0:
        return 0.0

    weighted = sum(
        safe_float(feature["normalized_value"]) * safe_float(feature["feature_weight"])
        for feature in features
    )

    return round8((weighted / total_weight) * 100.0)


def label_row(
    learning_run_label: str,
    created_at: str,
    track_label: str,
    group: str,
    name: str,
    value: str,
    confidence: float,
    reason: str,
) -> dict[str, Any]:
    return {
        "label_id": f"{learning_run_label}-{group}-{name}".replace(" ", "_"),
        "learning_run_label": learning_run_label,
        "created_at": created_at,
        "source_multi_cycle_track_label": track_label,
        "label_group": group,
        "label_name": name,
        "label_value": value,
        "label_confidence": str(round8(confidence)),
        "label_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "ai_learning_role": "LOCAL_LABEL_GENERATION_ONLY",
            "model_mode": MODEL_MODE,
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
            "autonomous_trading_enabled": False,
        },
    }


def build_labels(
    learning_run_label: str,
    created_at: str,
    track_label: str,
    metrics: dict[str, Any],
    learning_score: float,
    min_recommended_cycles: int,
    track_missing: bool,
) -> list[dict[str, Any]]:
    if track_missing:
        outcome = OUTCOME_LABEL_MISSING
        data_label = DATA_LABEL_MISSING
        risk_label = RISK_LABEL_CAUTION
        confidence = 0.0
        outcome_reason = "No multi-cycle paper observation track was available."
    elif safe_int(metrics.get("safety_breach_count", 0)) > 0:
        outcome = OUTCOME_LABEL_BLOCKED
        data_label = DATA_LABEL_EARLY
        risk_label = RISK_LABEL_BLOCKED
        confidence = 1.0
        outcome_reason = "Safety breach blocks AI paper outcome expansion."
    else:
        cycle_count = safe_int(metrics.get("cycle_count", 0))
        data_label = DATA_LABEL_SUFFICIENT if cycle_count >= min_recommended_cycles else DATA_LABEL_EARLY
        risk_label = (
            RISK_LABEL_CLEAN
            if safe_int(metrics.get("total_alert_count", 0)) == 0
            and safe_int(metrics.get("total_triggered_event_count", 0)) == 0
            else RISK_LABEL_CAUTION
        )

        if learning_score >= 85.0 and cycle_count >= min_recommended_cycles:
            outcome = OUTCOME_LABEL_STABLE
            confidence = 0.85
            outcome_reason = "Learning score and cycle count support stable multi-cycle outcome labeling."
        elif learning_score >= 75.0:
            outcome = OUTCOME_LABEL_EARLY_STABLE
            confidence = 0.70
            outcome_reason = "Learning score is stable, but more cycles are needed before stronger labeling."
        else:
            outcome = OUTCOME_LABEL_UNSTABLE
            confidence = 0.65
            outcome_reason = "Learning score is below the stability threshold."

    return [
        label_row(
            learning_run_label,
            created_at,
            track_label,
            "outcome",
            "paper_outcome_label",
            outcome,
            confidence,
            outcome_reason,
        ),
        label_row(
            learning_run_label,
            created_at,
            track_label,
            "data",
            "data_sufficiency_label",
            data_label,
            0.80 if data_label != DATA_LABEL_MISSING else 0.0,
            "Labels whether paper data volume is sufficient for deeper AI learning.",
        ),
        label_row(
            learning_run_label,
            created_at,
            track_label,
            "risk",
            "risk_cleanliness_label",
            risk_label,
            0.90 if risk_label == RISK_LABEL_CLEAN else 0.60,
            "Labels whether alerts, triggered events, or safety issues are present.",
        ),
        label_row(
            learning_run_label,
            created_at,
            track_label,
            "autonomy",
            "autonomy_scope_label",
            AUTONOMY_LABEL_RECOMMENDATION_ONLY,
            1.0,
            "AI output is recommendation-only and cannot trade.",
        ),
    ]


def recommendation_row(
    learning_run_label: str,
    created_at: str,
    track_label: str,
    recommendation_type: str,
    status: str,
    priority: int,
    text: str,
    effect: str,
) -> dict[str, Any]:
    return {
        "recommendation_id": f"{learning_run_label}-{recommendation_type}".replace(" ", "_"),
        "learning_run_label": learning_run_label,
        "created_at": created_at,
        "source_multi_cycle_track_label": track_label,
        "recommendation_type": recommendation_type,
        "recommendation_status": status,
        "recommendation_priority": priority,
        "recommendation_text": text,
        "expected_effect": effect,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "ai_learning_role": "LOCAL_RECOMMENDATION_ONLY",
            "model_mode": MODEL_MODE,
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
            "autonomous_trading_enabled": False,
        },
    }


def build_recommendations(
    learning_run_label: str,
    created_at: str,
    track_label: str,
    metrics: dict[str, Any],
    min_recommended_cycles: int,
) -> list[dict[str, Any]]:
    cycle_count = safe_int(metrics.get("cycle_count", 0))

    more_cycles_text = (
        f"Collect at least {max(min_recommended_cycles - cycle_count, 0)} additional paper cycle(s) before stronger AI conclusions."
        if cycle_count < min_recommended_cycles
        else "Continue collecting paper cycles to improve AI learning confidence."
    )

    return [
        recommendation_row(
            learning_run_label,
            created_at,
            track_label,
            "collect_more_paper_cycles",
            "RECOMMENDATION_ACTIVE",
            1,
            more_cycles_text,
            "Improves dataset sufficiency and reduces overfitting risk.",
        ),
        recommendation_row(
            learning_run_label,
            created_at,
            track_label,
            "keep_autonomous_trading_disabled",
            "RECOMMENDATION_MANDATORY",
            1,
            "Keep all AI outputs recommendation-only with live trading disabled.",
            "Preserves safety boundary while learning infrastructure matures.",
        ),
        recommendation_row(
            learning_run_label,
            created_at,
            track_label,
            "defer_strategy_weight_changes",
            "RECOMMENDATION_ACTIVE",
            2,
            "Do not auto-adjust strategy weights from this dataset yet.",
            "Prevents premature self-learning behavior from limited paper history.",
        ),
    ]


def decide_learning_outcome(
    track: sqlite3.Row | None,
    metrics: dict[str, Any],
    learning_score: float,
    min_learning_score: float,
    max_allowed_learning_loss_bps: float,
) -> tuple[str, str, str, str, str]:
    if track is None:
        return (
            DECISION_REJECT_MISSING,
            VERDICT_MISSING,
            ACTION_REFRESH,
            "Mission 69 Multi-Cycle Paper Observation Tracker",
            "Multi-cycle paper observation track is missing.",
        )

    if safe_int(metrics.get("safety_breach_count", 0)) > 0:
        return (
            DECISION_BLOCK_SAFETY,
            VERDICT_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 70 safety remediation",
            "Safety invariant failed during AI paper outcome learning.",
        )

    if (
        metrics.get("multi_cycle_decision") != MULTI_CYCLE_DECISION_CONFIRMED
        or metrics.get("global_verdict") != MULTI_CYCLE_VERDICT_READY
        or metrics.get("multi_cycle_state") != MULTI_CYCLE_STATE_CONFIRMED
        or safe_int(metrics.get("fail_check_count", 0)) > 0
        or safe_float(metrics.get("cumulative_net_pnl_bps", 0.0)) < -abs(max_allowed_learning_loss_bps)
    ):
        return (
            DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 69 Multi-Cycle Paper Observation Tracker",
            "Multi-cycle paper evidence is not stable enough for AI learning expansion.",
        )

    if learning_score < min_learning_score:
        return (
            DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 69 Multi-Cycle Paper Observation Tracker",
            "AI learning score is below the minimum threshold.",
        )

    return (
        DECISION_READY,
        VERDICT_READY,
        ACTION_EXPAND_DATASET,
        NEXT_READY,
        "AI paper outcome learning is ready for dataset expansion only. No autonomous trading is approved.",
    )


def build_summary(
    db_path: str | Path,
    learning_run_label: str,
    report_label: str,
    created_at: str,
    track_label: str,
    metrics: dict[str, Any],
    features: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    learning_score: float,
    learning_decision: str,
    global_verdict: str,
    recommended_action: str,
    next_mission: str,
    decision_reason: str,
) -> dict[str, Any]:
    label_values = {label["label_name"]: label["label_value"] for label in labels}

    return {
        "learning_run_label": learning_run_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_multi_cycle_track_label": track_label,
        "source_session_label": metrics.get("source_session_label"),
        "source_portfolio_label": metrics.get("source_portfolio_label"),
        "cycle_count": safe_int(metrics.get("cycle_count", 0)),
        "feature_count": len(features),
        "label_count": len(labels),
        "recommendation_count": len(recommendations),
        "paper_notional": round8(safe_float(metrics.get("paper_notional", 0.0))),
        "cumulative_net_paper_pnl": round8(safe_float(metrics.get("cumulative_net_paper_pnl", 0.0))),
        "cumulative_net_pnl_bps": round8(safe_float(metrics.get("cumulative_net_pnl_bps", 0.0))),
        "average_cycle_net_pnl_bps": round8(safe_float(metrics.get("average_cycle_net_pnl_bps", 0.0))),
        "worst_cycle_net_pnl_bps": round8(safe_float(metrics.get("worst_cycle_net_pnl_bps", 0.0))),
        "worst_position_loss_bps": round8(safe_float(metrics.get("worst_position_loss_bps", 0.0))),
        "average_fee_drag_bps": round8(safe_float(metrics.get("average_fee_drag_bps", 0.0))),
        "total_alert_count": safe_int(metrics.get("total_alert_count", 0)),
        "total_triggered_event_count": safe_int(metrics.get("total_triggered_event_count", 0)),
        "safety_breach_count": safe_int(metrics.get("safety_breach_count", 0)),
        "learning_score": round8(learning_score),
        "outcome_label": label_values.get("paper_outcome_label", OUTCOME_LABEL_MISSING),
        "data_sufficiency_label": label_values.get("data_sufficiency_label", DATA_LABEL_MISSING),
        "risk_label": label_values.get("risk_cleanliness_label", RISK_LABEL_CAUTION),
        "autonomy_label": AUTONOMY_LABEL_RECOMMENDATION_ONLY,
        "model_mode": MODEL_MODE,
        "learning_features": features,
        "learning_labels": labels,
        "learning_recommendations": recommendations,
        "learning_decision": learning_decision,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
        "next_mission": next_mission,
        "decision_reason": decision_reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    feature_lines = []
    for feature in summary["learning_features"]:
        feature_lines.append(
            "- "
            + f"{feature['feature_group']} / {feature['feature_name']}: "
            + f"value={feature['feature_value']}, "
            + f"normalized={feature['normalized_value']}, "
            + f"weight={feature['feature_weight']}"
        )

    label_lines = []
    for label in summary["learning_labels"]:
        label_lines.append(
            "- "
            + f"{label['label_group']} / {label['label_name']}: "
            + f"value={label['label_value']}, "
            + f"confidence={label['label_confidence']}"
        )

    recommendation_lines = []
    for recommendation in summary["learning_recommendations"]:
        recommendation_lines.append(
            "- "
            + f"{recommendation['recommendation_type']}: "
            + f"{recommendation['recommendation_text']}"
        )

    features_markdown = "\n".join(feature_lines) or "- None"
    labels_markdown = "\n".join(label_lines) or "- None"
    recommendations_markdown = "\n".join(recommendation_lines) or "- None"

    return f"""# DeltaGrid Mission 70 AI Paper Outcome Learning Engine Report

Report label: {summary['report_label']}
Learning run label: {summary['learning_run_label']}
Created at: {summary['created_at']}
Source multi-cycle track label: {summary['source_multi_cycle_track_label']}
Source session label: {summary['source_session_label']}
Source portfolio label: {summary['source_portfolio_label']}

## Learning Summary

Model mode: {summary['model_mode']}
Cycle count: {summary['cycle_count']}
Feature count: {summary['feature_count']}
Label count: {summary['label_count']}
Recommendation count: {summary['recommendation_count']}

Learning score: {summary['learning_score']}
Outcome label: {summary['outcome_label']}
Data sufficiency label: {summary['data_sufficiency_label']}
Risk label: {summary['risk_label']}
Autonomy label: {summary['autonomy_label']}

Paper notional: {summary['paper_notional']}
Cumulative net paper PnL: {summary['cumulative_net_paper_pnl']}
Cumulative net PnL bps: {summary['cumulative_net_pnl_bps']}
Average cycle net PnL bps: {summary['average_cycle_net_pnl_bps']}
Worst cycle net PnL bps: {summary['worst_cycle_net_pnl_bps']}
Worst position loss bps: {summary['worst_position_loss_bps']}
Average fee drag bps: {summary['average_fee_drag_bps']}
Total alert count: {summary['total_alert_count']}
Total triggered event count: {summary['total_triggered_event_count']}
Safety breach count: {summary['safety_breach_count']}

## Features

{features_markdown}

## Labels

{labels_markdown}

## Recommendations

{recommendations_markdown}

## Decision

Learning decision: {summary['learning_decision']}
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

AI output is recommendation-only.
This mission does not perform autonomous trading.
This mission does not adjust strategy weights automatically.
"""


def insert_row(conn: sqlite3.Connection, table_name: str, row: dict[str, Any], columns: list[str]) -> None:
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    values = [row[column] for column in columns]

    conn.execute(
        f"""
        INSERT OR REPLACE INTO {table_name} (
            {column_sql}
        )
        VALUES ({placeholders})
        """,
        values,
    )


def persist_learning_run(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for feature in summary["learning_features"]:
            row = dict(feature)
            row["metadata_json"] = json.dumps(row.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                FEATURES_TABLE,
                row,
                [
                    "feature_id",
                    "learning_run_label",
                    "created_at",
                    "source_multi_cycle_track_label",
                    "feature_group",
                    "feature_name",
                    "feature_value",
                    "normalized_value",
                    "feature_weight",
                    "feature_direction",
                    "feature_reason",
                    "live_trading",
                    "live_order_sent",
                    "capital_deployment",
                    "metadata_json",
                ],
            )

        for label in summary["learning_labels"]:
            row = dict(label)
            row["metadata_json"] = json.dumps(row.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                LABELS_TABLE,
                row,
                [
                    "label_id",
                    "learning_run_label",
                    "created_at",
                    "source_multi_cycle_track_label",
                    "label_group",
                    "label_name",
                    "label_value",
                    "label_confidence",
                    "label_reason",
                    "live_trading",
                    "live_order_sent",
                    "capital_deployment",
                    "metadata_json",
                ],
            )

        for recommendation in summary["learning_recommendations"]:
            row = dict(recommendation)
            row["metadata_json"] = json.dumps(row.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                RECOMMENDATIONS_TABLE,
                row,
                [
                    "recommendation_id",
                    "learning_run_label",
                    "created_at",
                    "source_multi_cycle_track_label",
                    "recommendation_type",
                    "recommendation_status",
                    "recommendation_priority",
                    "recommendation_text",
                    "expected_effect",
                    "live_trading",
                    "live_order_sent",
                    "capital_deployment",
                    "metadata_json",
                ],
            )

        run_row = {
            "learning_run_label": summary["learning_run_label"],
            "report_label": summary["report_label"],
            "created_at": summary["created_at"],
            "source_multi_cycle_track_label": summary["source_multi_cycle_track_label"],
            "source_session_label": summary["source_session_label"],
            "source_portfolio_label": summary["source_portfolio_label"],
            "cycle_count": summary["cycle_count"],
            "feature_count": summary["feature_count"],
            "label_count": summary["label_count"],
            "recommendation_count": summary["recommendation_count"],
            "paper_notional": str(summary["paper_notional"]),
            "cumulative_net_paper_pnl": str(summary["cumulative_net_paper_pnl"]),
            "cumulative_net_pnl_bps": str(summary["cumulative_net_pnl_bps"]),
            "average_cycle_net_pnl_bps": str(summary["average_cycle_net_pnl_bps"]),
            "worst_cycle_net_pnl_bps": str(summary["worst_cycle_net_pnl_bps"]),
            "worst_position_loss_bps": str(summary["worst_position_loss_bps"]),
            "average_fee_drag_bps": str(summary["average_fee_drag_bps"]),
            "total_alert_count": summary["total_alert_count"],
            "total_triggered_event_count": summary["total_triggered_event_count"],
            "safety_breach_count": summary["safety_breach_count"],
            "learning_score": str(summary["learning_score"]),
            "outcome_label": summary["outcome_label"],
            "data_sufficiency_label": summary["data_sufficiency_label"],
            "risk_label": summary["risk_label"],
            "autonomy_label": summary["autonomy_label"],
            "model_mode": summary["model_mode"],
            "learning_decision": summary["learning_decision"],
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
            LEARNING_RUNS_TABLE,
            run_row,
            [
                "learning_run_label",
                "report_label",
                "created_at",
                "source_multi_cycle_track_label",
                "source_session_label",
                "source_portfolio_label",
                "cycle_count",
                "feature_count",
                "label_count",
                "recommendation_count",
                "paper_notional",
                "cumulative_net_paper_pnl",
                "cumulative_net_pnl_bps",
                "average_cycle_net_pnl_bps",
                "worst_cycle_net_pnl_bps",
                "worst_position_loss_bps",
                "average_fee_drag_bps",
                "total_alert_count",
                "total_triggered_event_count",
                "safety_breach_count",
                "learning_score",
                "outcome_label",
                "data_sufficiency_label",
                "risk_label",
                "autonomy_label",
                "model_mode",
                "learning_decision",
                "global_verdict",
                "recommended_action",
                "next_mission",
                "live_trading",
                "live_order_sent",
                "capital_deployment",
                "summary_json",
                "markdown_report",
            ],
        )

        report_row = {
            "report_label": summary["report_label"],
            "learning_run_label": summary["learning_run_label"],
            "created_at": summary["created_at"],
            "source_multi_cycle_track_label": summary["source_multi_cycle_track_label"],
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
                "report_label",
                "learning_run_label",
                "created_at",
                "source_multi_cycle_track_label",
                "global_verdict",
                "recommended_action",
                "report_json",
                "markdown_report",
                "live_trading",
                "live_order_sent",
                "capital_deployment",
            ],
        )

        conn.commit()


def run_ai_paper_outcome_learning_engine(
    db_path: str | Path = "offchain/deltagrid.db",
    learning_run_label: str | None = None,
    report_label: str | None = None,
    multi_cycle_track_label: str = "mission69-final-check",
    min_recommended_cycles: int = 3,
    min_learning_score: float = 70.0,
    max_allowed_learning_loss_bps: float = 50.0,
    max_allowed_cycle_loss_bps: float = 10.0,
    max_allowed_position_loss_bps: float = 10.0,
    max_allowed_fee_drag_bps: float = 5.0,
) -> dict[str, Any]:
    if min_recommended_cycles <= 0:
        raise ValueError("min_recommended_cycles must be positive")

    if min_learning_score < 0:
        raise ValueError("min_learning_score cannot be negative")

    if max_allowed_learning_loss_bps < 0:
        raise ValueError("max_allowed_learning_loss_bps cannot be negative")

    if max_allowed_cycle_loss_bps < 0:
        raise ValueError("max_allowed_cycle_loss_bps cannot be negative")

    if max_allowed_position_loss_bps < 0:
        raise ValueError("max_allowed_position_loss_bps cannot be negative")

    if max_allowed_fee_drag_bps < 0:
        raise ValueError("max_allowed_fee_drag_bps cannot be negative")

    db = Path(db_path)
    learning_run = learning_run_label or new_learning_run_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    track_label = parse_labels(multi_cycle_track_label)[0]

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        track = load_multi_cycle_track(conn, track_label)
        cycles = load_multi_cycle_cycles(conn, track_label)
        checks = load_multi_cycle_checks(conn, track_label)

    metrics = build_metrics(track, cycles, checks)

    features = build_features(
        learning_run_label=learning_run,
        created_at=created_at,
        track_label=track_label,
        metrics=metrics,
        min_recommended_cycles=min_recommended_cycles,
        max_allowed_learning_loss_bps=max_allowed_learning_loss_bps,
        max_allowed_cycle_loss_bps=max_allowed_cycle_loss_bps,
        max_allowed_position_loss_bps=max_allowed_position_loss_bps,
        max_allowed_fee_drag_bps=max_allowed_fee_drag_bps,
    )

    learning_score = compute_learning_score(features)

    labels = build_labels(
        learning_run_label=learning_run,
        created_at=created_at,
        track_label=track_label,
        metrics=metrics,
        learning_score=learning_score,
        min_recommended_cycles=min_recommended_cycles,
        track_missing=track is None,
    )

    recommendations = build_recommendations(
        learning_run_label=learning_run,
        created_at=created_at,
        track_label=track_label,
        metrics=metrics,
        min_recommended_cycles=min_recommended_cycles,
    )

    learning_decision, global_verdict, recommended_action, next_mission, decision_reason = decide_learning_outcome(
        track=track,
        metrics=metrics,
        learning_score=learning_score,
        min_learning_score=min_learning_score,
        max_allowed_learning_loss_bps=max_allowed_learning_loss_bps,
    )

    summary = build_summary(
        db_path=db,
        learning_run_label=learning_run,
        report_label=report,
        created_at=created_at,
        track_label=track_label,
        metrics=metrics,
        features=features,
        labels=labels,
        recommendations=recommendations,
        learning_score=learning_score,
        learning_decision=learning_decision,
        global_verdict=global_verdict,
        recommended_action=recommended_action,
        next_mission=next_mission,
        decision_reason=decision_reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_learning_run(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid AI paper outcome learning engine.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--learning-run-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--multi-cycle-track-label", default="mission69-final-check")
    parser.add_argument("--min-recommended-cycles", type=int, default=3)
    parser.add_argument("--min-learning-score", type=float, default=70.0)
    parser.add_argument("--max-allowed-learning-loss-bps", type=float, default=50.0)
    parser.add_argument("--max-allowed-cycle-loss-bps", type=float, default=10.0)
    parser.add_argument("--max-allowed-position-loss-bps", type=float, default=10.0)
    parser.add_argument("--max-allowed-fee-drag-bps", type=float, default=5.0)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_ai_paper_outcome_learning_engine(
        db_path=args.db,
        learning_run_label=args.learning_run_label,
        report_label=args.report_label,
        multi_cycle_track_label=args.multi_cycle_track_label,
        min_recommended_cycles=args.min_recommended_cycles,
        min_learning_score=args.min_learning_score,
        max_allowed_learning_loss_bps=args.max_allowed_learning_loss_bps,
        max_allowed_cycle_loss_bps=args.max_allowed_cycle_loss_bps,
        max_allowed_position_loss_bps=args.max_allowed_position_loss_bps,
        max_allowed_fee_drag_bps=args.max_allowed_fee_drag_bps,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

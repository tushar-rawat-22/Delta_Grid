"""
Mission 71: AI Feature Quality and Drift Guard.

This module validates local AI paper-outcome learning features before dataset
expansion continues.

It reads:
- ai_paper_outcome_learning_runs
- ai_paper_outcome_learning_features
- ai_paper_outcome_learning_labels
- ai_paper_outcome_learning_recommendations

It writes:
- ai_feature_quality_drift_guard_reviews
- ai_feature_quality_drift_guard_checks
- ai_feature_quality_drift_guard_feature_drifts
- ai_feature_quality_drift_guard_reports

It is AI feature quality control only.

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


LEARNING_RUNS_TABLE = "ai_paper_outcome_learning_runs"
FEATURES_TABLE = "ai_paper_outcome_learning_features"
LABELS_TABLE = "ai_paper_outcome_learning_labels"
RECOMMENDATIONS_TABLE = "ai_paper_outcome_learning_recommendations"

GUARD_REVIEWS_TABLE = "ai_feature_quality_drift_guard_reviews"
GUARD_CHECKS_TABLE = "ai_feature_quality_drift_guard_checks"
GUARD_DRIFTS_TABLE = "ai_feature_quality_drift_guard_feature_drifts"
GUARD_REPORTS_TABLE = "ai_feature_quality_drift_guard_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

MODEL_MODE_REQUIRED = "DETERMINISTIC_LOCAL_RULE_BASED_RECOMMENDATION_ONLY"
AUTONOMY_LABEL_REQUIRED = "AI_AUTONOMY_LABEL_RECOMMENDATION_ONLY_NO_TRADING"

LEARNING_DECISION_READY = "AI_PAPER_OUTCOME_LEARNING_READY_FOR_DATASET_EXPANSION"
LEARNING_VERDICT_READY = "AI_PAPER_OUTCOME_LEARNING_READY_SHADOW_ONLY"

DATA_LABEL_EARLY = "AI_DATA_SUFFICIENCY_LABEL_EARLY_NEEDS_MORE_CYCLES"
DATA_LABEL_SUFFICIENT = "AI_DATA_SUFFICIENCY_LABEL_MULTI_CYCLE_READY"

CHECK_PASS = "AI_FEATURE_QUALITY_CHECK_PASS"
CHECK_FAIL = "AI_FEATURE_QUALITY_CHECK_FAIL"

DRIFT_BASELINE_UNAVAILABLE = "AI_FEATURE_DRIFT_BASELINE_UNAVAILABLE"
DRIFT_WITHIN_LIMIT = "AI_FEATURE_DRIFT_WITHIN_LIMIT"
DRIFT_BREACHED = "AI_FEATURE_DRIFT_BREACHED"
DRIFT_MISSING_BASELINE_FEATURE = "AI_FEATURE_DRIFT_MISSING_BASELINE_FEATURE"

QUALITY_STATE_READY = "AI_FEATURE_QUALITY_STATE_READY"
QUALITY_STATE_UNSTABLE = "AI_FEATURE_QUALITY_STATE_UNSTABLE"
QUALITY_STATE_BLOCKED = "AI_FEATURE_QUALITY_STATE_BLOCKED"
QUALITY_STATE_MISSING = "AI_FEATURE_QUALITY_STATE_MISSING"

DECISION_READY = "AI_FEATURE_QUALITY_DRIFT_GUARD_APPROVED_FOR_DATASET_EXPANSION"
DECISION_UNSTABLE = "AI_FEATURE_QUALITY_DRIFT_GUARD_UNSTABLE_REVIEW_REQUIRED"
DECISION_BLOCK_SAFETY = "AI_FEATURE_QUALITY_DRIFT_GUARD_BLOCKED_BY_SAFETY_POLICY"
DECISION_REJECT_MISSING = "AI_FEATURE_QUALITY_DRIFT_GUARD_REJECTED_MISSING_EVIDENCE"

VERDICT_READY = "AI_FEATURE_QUALITY_DRIFT_GUARD_READY_SHADOW_ONLY"
VERDICT_UNSTABLE = "AI_FEATURE_QUALITY_DRIFT_GUARD_UNSTABLE_SHADOW_ONLY"
VERDICT_BLOCKED = "AI_FEATURE_QUALITY_DRIFT_GUARD_BLOCKED_SHADOW_ONLY"
VERDICT_MISSING = "AI_FEATURE_QUALITY_DRIFT_GUARD_MISSING_EVIDENCE"

ACTION_CONTINUE = "CONTINUE_AI_DATASET_EXPANSION_WITH_DRIFT_MONITORING"
ACTION_REVIEW_UNSTABLE = "REVIEW_AI_FEATURE_QUALITY_BEFORE_DATASET_EXPANSION"
ACTION_REVIEW_SAFETY = "STOP_AND_REVIEW_AI_FEATURE_SAFETY_STATE"
ACTION_REFRESH = "REFRESH_AI_PAPER_OUTCOME_LEARNING_EVIDENCE"

NEXT_READY = "Mission 72 AI Paper Dataset Expansion Scheduler"

REQUIRED_FEATURE_GROUPS = (
    "data",
    "quality",
    "performance",
    "risk",
    "cost",
    "alerts",
    "events",
    "safety",
    "state",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_review_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission71-ai-feature-guard-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission71-ai-feature-guard-report-{stamp}-{uuid.uuid4().hex[:8]}"


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
        return ["mission70-final-check"]

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    labels: list[str] = []

    for item in raw_items:
        label = str(item).strip()

        if not label:
            continue

        if any(ch.isspace() for ch in label):
            raise ValueError(f"Invalid AI learning run label: {label}")

        if label not in labels:
            labels.append(label)

    if not labels:
        raise ValueError("At least one AI learning run label is required")

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


def ensure_schema(db_path: str | Path) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_feature_quality_drift_guard_reviews (
                review_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_learning_run_label TEXT NOT NULL,
                baseline_learning_run_label TEXT,
                source_multi_cycle_track_label TEXT,
                source_session_label TEXT,
                source_portfolio_label TEXT,
                cycle_count INTEGER NOT NULL,
                feature_count INTEGER NOT NULL,
                label_count INTEGER NOT NULL,
                recommendation_count INTEGER NOT NULL,
                required_feature_group_count INTEGER NOT NULL,
                observed_feature_group_count INTEGER NOT NULL,
                missing_required_group_count INTEGER NOT NULL,
                invalid_normalized_feature_count INTEGER NOT NULL,
                invalid_feature_weight_count INTEGER NOT NULL,
                feature_weight_total TEXT NOT NULL,
                learning_score TEXT NOT NULL,
                max_feature_drift TEXT NOT NULL,
                average_feature_drift TEXT NOT NULL,
                drift_check_count INTEGER NOT NULL,
                quality_check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                drift_status TEXT NOT NULL,
                quality_state TEXT NOT NULL,
                guard_decision TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_feature_quality_drift_guard_checks (
                check_id TEXT PRIMARY KEY,
                review_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_learning_run_label TEXT NOT NULL,
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
            CREATE TABLE IF NOT EXISTS ai_feature_quality_drift_guard_feature_drifts (
                drift_id TEXT PRIMARY KEY,
                review_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_learning_run_label TEXT NOT NULL,
                baseline_learning_run_label TEXT,
                feature_group TEXT NOT NULL,
                feature_name TEXT NOT NULL,
                current_normalized_value TEXT NOT NULL,
                baseline_normalized_value TEXT,
                absolute_drift TEXT NOT NULL,
                drift_status TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_feature_quality_drift_guard_reports (
                report_label TEXT PRIMARY KEY,
                review_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_learning_run_label TEXT NOT NULL,
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


def load_learning_run(conn: sqlite3.Connection, learning_run_label: str) -> sqlite3.Row | None:
    if not table_exists(conn, LEARNING_RUNS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM ai_paper_outcome_learning_runs
        WHERE learning_run_label = ?
        """,
        (learning_run_label,),
    ).fetchone()


def load_features(conn: sqlite3.Connection, learning_run_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, FEATURES_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM ai_paper_outcome_learning_features
        WHERE learning_run_label = ?
        ORDER BY feature_group ASC, feature_name ASC
        """,
        (learning_run_label,),
    ).fetchall()


def load_labels(conn: sqlite3.Connection, learning_run_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, LABELS_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM ai_paper_outcome_learning_labels
        WHERE learning_run_label = ?
        ORDER BY label_group ASC, label_name ASC
        """,
        (learning_run_label,),
    ).fetchall()


def load_recommendations(conn: sqlite3.Connection, learning_run_label: str) -> list[sqlite3.Row]:
    if not table_exists(conn, RECOMMENDATIONS_TABLE):
        return []

    return conn.execute(
        """
        SELECT *
        FROM ai_paper_outcome_learning_recommendations
        WHERE learning_run_label = ?
        ORDER BY recommendation_priority ASC, recommendation_type ASC
        """,
        (learning_run_label,),
    ).fetchall()


def load_baseline_learning_run(
    conn: sqlite3.Connection,
    current_learning_run_label: str,
    source_multi_cycle_track_label: str | None,
) -> sqlite3.Row | None:
    if not source_multi_cycle_track_label:
        return None

    if not table_exists(conn, LEARNING_RUNS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM ai_paper_outcome_learning_runs
        WHERE source_multi_cycle_track_label = ?
        AND learning_run_label != ?
        ORDER BY created_at DESC, learning_run_label DESC
        LIMIT 1
        """,
        (source_multi_cycle_track_label, current_learning_run_label),
    ).fetchone()


def label_value(labels: list[sqlite3.Row], label_name: str, fallback: str = "") -> str:
    for label in labels:
        if str(row_get(label, "label_name", "")) == label_name:
            return str(row_get(label, "label_value", fallback))

    return fallback


def feature_key(feature: sqlite3.Row | dict[str, Any]) -> tuple[str, str]:
    return (str(row_get(feature, "feature_group", "")), str(row_get(feature, "feature_name", "")))


def invalid_normalized_count(features: list[sqlite3.Row]) -> int:
    bad = 0

    for feature in features:
        raw = row_get(feature, "normalized_value", None)

        try:
            value = float(raw)
        except (TypeError, ValueError):
            bad += 1
            continue

        if math.isnan(value) or math.isinf(value) or value < 0.0 or value > 1.0:
            bad += 1

    return bad


def invalid_weight_count(features: list[sqlite3.Row]) -> int:
    bad = 0

    for feature in features:
        raw = row_get(feature, "feature_weight", None)

        try:
            value = float(raw)
        except (TypeError, ValueError):
            bad += 1
            continue

        if math.isnan(value) or math.isinf(value) or value <= 0.0:
            bad += 1

    return bad


def feature_weight_total(features: list[sqlite3.Row]) -> float:
    return round8(sum(safe_float(row_get(feature, "feature_weight", 0.0)) for feature in features))


def observed_feature_groups(features: list[sqlite3.Row]) -> set[str]:
    return {str(row_get(feature, "feature_group", "")) for feature in features if str(row_get(feature, "feature_group", ""))}


def missing_required_groups(features: list[sqlite3.Row]) -> list[str]:
    groups = observed_feature_groups(features)
    return [group for group in REQUIRED_FEATURE_GROUPS if group not in groups]


def guard_check(
    review_label: str,
    created_at: str,
    learning_run_label: str,
    category: str,
    name: str,
    status: str,
    observed_value: Any,
    threshold_value: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{review_label}-{category}-{name}".replace(" ", "_"),
        "review_label": review_label,
        "created_at": created_at,
        "source_learning_run_label": learning_run_label,
        "check_category": category,
        "check_name": name,
        "check_status": status,
        "observed_value": str(observed_value),
        "threshold_value": str(threshold_value),
        "check_reason": reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "ai_guard_role": "FEATURE_QUALITY_DRIFT_CHECK_ONLY",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
            "real_capital_used": False,
            "autonomous_trading_enabled": False,
            "automatic_strategy_reweighting_enabled": False,
        },
    }


def build_missing_checks(review_label: str, created_at: str, learning_run_label: str) -> list[dict[str, Any]]:
    return [
        guard_check(
            review_label,
            created_at,
            learning_run_label,
            "availability",
            "AI learning run exists",
            CHECK_FAIL,
            "missing",
            "ai_paper_outcome_learning_runs record",
            "No AI paper outcome learning run exists for this label.",
        )
    ]


def build_drift_rows(
    review_label: str,
    created_at: str,
    learning_run_label: str,
    baseline_learning_run_label: str | None,
    current_features: list[sqlite3.Row],
    baseline_features: list[sqlite3.Row],
    max_allowed_feature_drift: float,
) -> list[dict[str, Any]]:
    baseline_by_key = {feature_key(feature): feature for feature in baseline_features}
    drifts: list[dict[str, Any]] = []

    for feature in current_features:
        group, name = feature_key(feature)
        current_value = safe_float(row_get(feature, "normalized_value", 0.0))

        if baseline_learning_run_label is None:
            baseline_value = None
            absolute_drift = 0.0
            status = DRIFT_BASELINE_UNAVAILABLE
        else:
            baseline_feature = baseline_by_key.get((group, name))

            if baseline_feature is None:
                baseline_value = None
                absolute_drift = 0.0
                status = DRIFT_MISSING_BASELINE_FEATURE
            else:
                baseline_value = safe_float(row_get(baseline_feature, "normalized_value", 0.0))
                absolute_drift = round8(abs(current_value - baseline_value))
                status = DRIFT_WITHIN_LIMIT if absolute_drift <= max_allowed_feature_drift else DRIFT_BREACHED

        drifts.append(
            {
                "drift_id": f"{review_label}-{group}-{name}-drift".replace(" ", "_"),
                "review_label": review_label,
                "created_at": created_at,
                "source_learning_run_label": learning_run_label,
                "baseline_learning_run_label": baseline_learning_run_label,
                "feature_group": group,
                "feature_name": name,
                "current_normalized_value": str(round8(current_value)),
                "baseline_normalized_value": None if baseline_value is None else str(round8(baseline_value)),
                "absolute_drift": str(round8(absolute_drift)),
                "drift_status": status,
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT_VALUE,
                "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
                "metadata": {
                    "ai_guard_role": "FEATURE_DRIFT_CHECK_ONLY",
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

    return drifts


def aggregate_drift(drifts: list[dict[str, Any]]) -> tuple[float, float, str]:
    numeric_drifts = [safe_float(drift["absolute_drift"]) for drift in drifts]
    max_drift = round8(max(numeric_drifts, default=0.0))
    avg_drift = round8(sum(numeric_drifts) / len(numeric_drifts)) if numeric_drifts else 0.0

    if not drifts:
        return max_drift, avg_drift, DRIFT_BASELINE_UNAVAILABLE

    statuses = {drift["drift_status"] for drift in drifts}

    if DRIFT_BREACHED in statuses:
        status = DRIFT_BREACHED
    elif DRIFT_MISSING_BASELINE_FEATURE in statuses:
        status = DRIFT_MISSING_BASELINE_FEATURE
    elif statuses == {DRIFT_BASELINE_UNAVAILABLE}:
        status = DRIFT_BASELINE_UNAVAILABLE
    else:
        status = DRIFT_WITHIN_LIMIT

    return max_drift, avg_drift, status


def build_metrics(
    learning_run: sqlite3.Row | None,
    features: list[sqlite3.Row],
    labels: list[sqlite3.Row],
    recommendations: list[sqlite3.Row],
    baseline_learning_run: sqlite3.Row | None,
    drifts: list[dict[str, Any]],
) -> dict[str, Any]:
    if learning_run is None:
        return {
            "source_multi_cycle_track_label": None,
            "source_session_label": None,
            "source_portfolio_label": None,
            "cycle_count": 0,
            "feature_count": len(features),
            "label_count": len(labels),
            "recommendation_count": len(recommendations),
            "observed_feature_group_count": 0,
            "missing_required_group_count": len(REQUIRED_FEATURE_GROUPS),
            "missing_required_groups": list(REQUIRED_FEATURE_GROUPS),
            "invalid_normalized_feature_count": 0,
            "invalid_feature_weight_count": 0,
            "feature_weight_total": 0.0,
            "learning_score": 0.0,
            "safety_breach_count": 0,
            "baseline_learning_run_label": None,
            "max_feature_drift": 0.0,
            "average_feature_drift": 0.0,
            "drift_status": DRIFT_BASELINE_UNAVAILABLE,
        }

    max_drift, avg_drift, drift_status = aggregate_drift(drifts)

    safety_count = safe_int(row_get(learning_run, "safety_breach_count", 0))
    safety_count += sum(1 for row in [learning_run, *features, *labels, *recommendations] if safety_problem(row))

    groups = observed_feature_groups(features)
    missing_groups = missing_required_groups(features)

    return {
        "source_multi_cycle_track_label": row_get(learning_run, "source_multi_cycle_track_label", None),
        "source_session_label": row_get(learning_run, "source_session_label", None),
        "source_portfolio_label": row_get(learning_run, "source_portfolio_label", None),
        "cycle_count": safe_int(row_get(learning_run, "cycle_count", 0)),
        "feature_count": len(features),
        "label_count": len(labels),
        "recommendation_count": len(recommendations),
        "required_feature_group_count": len(REQUIRED_FEATURE_GROUPS),
        "observed_feature_group_count": len(groups),
        "missing_required_group_count": len(missing_groups),
        "missing_required_groups": missing_groups,
        "invalid_normalized_feature_count": invalid_normalized_count(features),
        "invalid_feature_weight_count": invalid_weight_count(features),
        "feature_weight_total": feature_weight_total(features),
        "learning_score": round8(safe_float(row_get(learning_run, "learning_score", 0.0))),
        "safety_breach_count": safety_count,
        "baseline_learning_run_label": row_get(baseline_learning_run, "learning_run_label", None),
        "max_feature_drift": max_drift,
        "average_feature_drift": avg_drift,
        "drift_status": drift_status,
        "model_mode": str(row_get(learning_run, "model_mode", "")),
        "learning_decision": str(row_get(learning_run, "learning_decision", "")),
        "global_verdict": str(row_get(learning_run, "global_verdict", "")),
        "autonomy_label": str(row_get(learning_run, "autonomy_label", label_value(labels, "autonomy_scope_label", ""))),
        "data_sufficiency_label": str(row_get(learning_run, "data_sufficiency_label", label_value(labels, "data_sufficiency_label", ""))),
        "risk_label": str(row_get(learning_run, "risk_label", label_value(labels, "risk_cleanliness_label", ""))),
    }


def build_checks(
    review_label: str,
    created_at: str,
    learning_run_label: str,
    learning_run: sqlite3.Row,
    features: list[sqlite3.Row],
    labels: list[sqlite3.Row],
    recommendations: list[sqlite3.Row],
    metrics: dict[str, Any],
    min_feature_count: int,
    min_label_count: int,
    min_recommendation_count: int,
    min_learning_score: float,
    min_feature_weight_total: float,
    max_feature_weight_total: float,
    max_allowed_feature_drift: float,
) -> list[dict[str, Any]]:
    return [
        guard_check(
            review_label,
            created_at,
            learning_run_label,
            "availability",
            "AI learning run exists",
            CHECK_PASS,
            "present",
            "present",
            "AI paper outcome learning run exists.",
        ),
        guard_check(
            review_label,
            created_at,
            learning_run_label,
            "safety",
            "safety breach count",
            CHECK_PASS if safe_int(metrics["safety_breach_count"]) == 0 else CHECK_FAIL,
            metrics["safety_breach_count"],
            0,
            "AI feature guard requires zero live-trading, order-transmission, and capital-deployment breaches.",
        ),
        guard_check(
            review_label,
            created_at,
            learning_run_label,
            "model",
            "model mode recommendation only",
            CHECK_PASS if metrics["model_mode"] == MODEL_MODE_REQUIRED else CHECK_FAIL,
            metrics["model_mode"],
            MODEL_MODE_REQUIRED,
            "AI feature guard only accepts deterministic local recommendation-only model mode.",
        ),
        guard_check(
            review_label,
            created_at,
            learning_run_label,
            "autonomy",
            "autonomy label no trading",
            CHECK_PASS if metrics["autonomy_label"] == AUTONOMY_LABEL_REQUIRED else CHECK_FAIL,
            metrics["autonomy_label"],
            AUTONOMY_LABEL_REQUIRED,
            "AI output must remain recommendation-only with no trading authority.",
        ),
        guard_check(
            review_label,
            created_at,
            learning_run_label,
            "learning",
            "learning decision ready",
            CHECK_PASS if metrics["learning_decision"] == LEARNING_DECISION_READY else CHECK_FAIL,
            metrics["learning_decision"],
            LEARNING_DECISION_READY,
            "The AI paper outcome learning run must be ready for dataset expansion.",
        ),
        guard_check(
            review_label,
            created_at,
            learning_run_label,
            "learning",
            "learning verdict ready",
            CHECK_PASS if metrics["global_verdict"] == LEARNING_VERDICT_READY else CHECK_FAIL,
            metrics["global_verdict"],
            LEARNING_VERDICT_READY,
            "The AI learning verdict must remain ready and shadow-only.",
        ),
        guard_check(
            review_label,
            created_at,
            learning_run_label,
            "features",
            "feature count",
            CHECK_PASS if len(features) >= min_feature_count else CHECK_FAIL,
            len(features),
            f">= {min_feature_count}",
            "Feature count must be sufficient for guard validation.",
        ),
        guard_check(
            review_label,
            created_at,
            learning_run_label,
            "labels",
            "label count",
            CHECK_PASS if len(labels) >= min_label_count else CHECK_FAIL,
            len(labels),
            f">= {min_label_count}",
            "Label count must be sufficient for guard validation.",
        ),
        guard_check(
            review_label,
            created_at,
            learning_run_label,
            "recommendations",
            "recommendation count",
            CHECK_PASS if len(recommendations) >= min_recommendation_count else CHECK_FAIL,
            len(recommendations),
            f">= {min_recommendation_count}",
            "Recommendation count must be sufficient for guard validation.",
        ),
        guard_check(
            review_label,
            created_at,
            learning_run_label,
            "features",
            "required feature groups",
            CHECK_PASS if safe_int(metrics["missing_required_group_count"]) == 0 else CHECK_FAIL,
            ",".join(metrics["missing_required_groups"]) or "none",
            "none missing",
            "All required AI feature groups must be present.",
        ),
        guard_check(
            review_label,
            created_at,
            learning_run_label,
            "features",
            "normalized feature values",
            CHECK_PASS if safe_int(metrics["invalid_normalized_feature_count"]) == 0 else CHECK_FAIL,
            metrics["invalid_normalized_feature_count"],
            0,
            "All normalized feature values must be numeric values between 0 and 1.",
        ),
        guard_check(
            review_label,
            created_at,
            learning_run_label,
            "features",
            "feature weights",
            CHECK_PASS if safe_int(metrics["invalid_feature_weight_count"]) == 0 else CHECK_FAIL,
            metrics["invalid_feature_weight_count"],
            0,
            "All feature weights must be positive finite values.",
        ),
        guard_check(
            review_label,
            created_at,
            learning_run_label,
            "features",
            "feature weight total",
            CHECK_PASS
            if min_feature_weight_total <= safe_float(metrics["feature_weight_total"]) <= max_feature_weight_total
            else CHECK_FAIL,
            metrics["feature_weight_total"],
            f"{min_feature_weight_total} <= total <= {max_feature_weight_total}",
            "Feature weight total must remain in a sane range.",
        ),
        guard_check(
            review_label,
            created_at,
            learning_run_label,
            "learning",
            "learning score",
            CHECK_PASS if safe_float(metrics["learning_score"]) >= min_learning_score else CHECK_FAIL,
            metrics["learning_score"],
            f">= {min_learning_score}",
            "Learning score must clear the feature-quality guard threshold.",
        ),
        guard_check(
            review_label,
            created_at,
            learning_run_label,
            "data",
            "data sufficiency label allowed",
            CHECK_PASS
            if metrics["data_sufficiency_label"] in {DATA_LABEL_EARLY, DATA_LABEL_SUFFICIENT}
            else CHECK_FAIL,
            metrics["data_sufficiency_label"],
            f"{DATA_LABEL_EARLY} or {DATA_LABEL_SUFFICIENT}",
            "The AI run may be early, but its data sufficiency label must be recognized.",
        ),
        guard_check(
            review_label,
            created_at,
            learning_run_label,
            "drift",
            "max feature drift",
            CHECK_PASS
            if metrics["drift_status"] in {DRIFT_BASELINE_UNAVAILABLE, DRIFT_WITHIN_LIMIT}
            and safe_float(metrics["max_feature_drift"]) <= max_allowed_feature_drift
            else CHECK_FAIL,
            metrics["max_feature_drift"],
            f"<= {max_allowed_feature_drift}",
            "Feature drift must remain inside the guard threshold when a baseline exists.",
        ),
    ]


def decide_guard_outcome(
    learning_run: sqlite3.Row | None,
    checks: list[dict[str, Any]],
) -> tuple[str, str, str, str, str, str]:
    if learning_run is None:
        return (
            DECISION_REJECT_MISSING,
            VERDICT_MISSING,
            ACTION_REFRESH,
            "Mission 70 AI Paper Outcome Learning Engine",
            QUALITY_STATE_MISSING,
            "AI paper outcome learning evidence is missing.",
        )

    failed = [check for check in checks if check["check_status"] == CHECK_FAIL]

    if any(check["check_category"] == "safety" for check in failed):
        return (
            DECISION_BLOCK_SAFETY,
            VERDICT_BLOCKED,
            ACTION_REVIEW_SAFETY,
            "Mission 71 safety remediation",
            QUALITY_STATE_BLOCKED,
            "Safety invariant failed during AI feature quality and drift guarding.",
        )

    if failed:
        return (
            DECISION_UNSTABLE,
            VERDICT_UNSTABLE,
            ACTION_REVIEW_UNSTABLE,
            "Mission 70 AI Paper Outcome Learning Engine",
            QUALITY_STATE_UNSTABLE,
            "AI feature quality or drift guard failed one or more checks.",
        )

    return (
        DECISION_READY,
        VERDICT_READY,
        ACTION_CONTINUE,
        NEXT_READY,
        QUALITY_STATE_READY,
        "AI feature quality and drift guard is ready for dataset expansion. No autonomous trading is approved.",
    )


def build_summary(
    db_path: str | Path,
    review_label: str,
    report_label: str,
    created_at: str,
    learning_run_label: str,
    metrics: dict[str, Any],
    checks: list[dict[str, Any]],
    drifts: list[dict[str, Any]],
    guard_decision: str,
    global_verdict: str,
    recommended_action: str,
    next_mission: str,
    quality_state: str,
    decision_reason: str,
) -> dict[str, Any]:
    pass_count = sum(1 for check in checks if check["check_status"] == CHECK_PASS)
    fail_count = sum(1 for check in checks if check["check_status"] == CHECK_FAIL)

    return {
        "review_label": review_label,
        "report_label": report_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_learning_run_label": learning_run_label,
        "baseline_learning_run_label": metrics.get("baseline_learning_run_label"),
        "source_multi_cycle_track_label": metrics.get("source_multi_cycle_track_label"),
        "source_session_label": metrics.get("source_session_label"),
        "source_portfolio_label": metrics.get("source_portfolio_label"),
        "cycle_count": safe_int(metrics.get("cycle_count", 0)),
        "feature_count": safe_int(metrics.get("feature_count", 0)),
        "label_count": safe_int(metrics.get("label_count", 0)),
        "recommendation_count": safe_int(metrics.get("recommendation_count", 0)),
        "required_feature_group_count": len(REQUIRED_FEATURE_GROUPS),
        "observed_feature_group_count": safe_int(metrics.get("observed_feature_group_count", 0)),
        "missing_required_group_count": safe_int(metrics.get("missing_required_group_count", 0)),
        "invalid_normalized_feature_count": safe_int(metrics.get("invalid_normalized_feature_count", 0)),
        "invalid_feature_weight_count": safe_int(metrics.get("invalid_feature_weight_count", 0)),
        "feature_weight_total": round8(safe_float(metrics.get("feature_weight_total", 0.0))),
        "learning_score": round8(safe_float(metrics.get("learning_score", 0.0))),
        "max_feature_drift": round8(safe_float(metrics.get("max_feature_drift", 0.0))),
        "average_feature_drift": round8(safe_float(metrics.get("average_feature_drift", 0.0))),
        "drift_check_count": len(drifts),
        "quality_check_count": len(checks),
        "pass_check_count": pass_count,
        "fail_check_count": fail_count,
        "safety_breach_count": safe_int(metrics.get("safety_breach_count", 0)),
        "drift_status": metrics.get("drift_status", DRIFT_BASELINE_UNAVAILABLE),
        "quality_state": quality_state,
        "guard_decision": guard_decision,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
        "next_mission": next_mission,
        "decision_reason": decision_reason,
        "guard_checks": checks,
        "feature_drifts": drifts,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    check_lines = []

    for check in summary["guard_checks"]:
        check_lines.append(
            "- "
            + f"{check['check_category']} / {check['check_name']}: "
            + f"status={check['check_status']}, "
            + f"observed={check['observed_value']}, "
            + f"threshold={check['threshold_value']}"
        )

    drift_lines = []

    for drift in summary["feature_drifts"]:
        drift_lines.append(
            "- "
            + f"{drift['feature_group']} / {drift['feature_name']}: "
            + f"current={drift['current_normalized_value']}, "
            + f"baseline={drift['baseline_normalized_value']}, "
            + f"drift={drift['absolute_drift']}, "
            + f"status={drift['drift_status']}"
        )

    checks_markdown = "\n".join(check_lines) or "- None"
    drifts_markdown = "\n".join(drift_lines) or "- None"

    return f"""# DeltaGrid Mission 71 AI Feature Quality and Drift Guard Report

Report label: {summary['report_label']}
Review label: {summary['review_label']}
Created at: {summary['created_at']}
Source learning run label: {summary['source_learning_run_label']}
Baseline learning run label: {summary['baseline_learning_run_label']}
Source multi-cycle track label: {summary['source_multi_cycle_track_label']}
Source session label: {summary['source_session_label']}
Source portfolio label: {summary['source_portfolio_label']}

## Feature Quality Summary

Cycle count: {summary['cycle_count']}
Feature count: {summary['feature_count']}
Label count: {summary['label_count']}
Recommendation count: {summary['recommendation_count']}
Required feature group count: {summary['required_feature_group_count']}
Observed feature group count: {summary['observed_feature_group_count']}
Missing required group count: {summary['missing_required_group_count']}
Invalid normalized feature count: {summary['invalid_normalized_feature_count']}
Invalid feature weight count: {summary['invalid_feature_weight_count']}
Feature weight total: {summary['feature_weight_total']}
Learning score: {summary['learning_score']}

## Drift Summary

Drift status: {summary['drift_status']}
Drift check count: {summary['drift_check_count']}
Max feature drift: {summary['max_feature_drift']}
Average feature drift: {summary['average_feature_drift']}

## Guard Summary

Quality check count: {summary['quality_check_count']}
Pass check count: {summary['pass_check_count']}
Fail check count: {summary['fail_check_count']}
Safety breach count: {summary['safety_breach_count']}
Quality state: {summary['quality_state']}

## Checks

{checks_markdown}

## Feature Drifts

{drifts_markdown}

## Decision

Guard decision: {summary['guard_decision']}
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

AI feature quality output is recommendation-only.
This guard does not perform autonomous trading.
This guard does not adjust strategy weights automatically.
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


def persist_guard_review(db_path: str | Path, summary: dict[str, Any], markdown_report: str) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for check in summary["guard_checks"]:
            row = dict(check)
            row["metadata_json"] = json.dumps(row.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                GUARD_CHECKS_TABLE,
                row,
                [
                    "check_id",
                    "review_label",
                    "created_at",
                    "source_learning_run_label",
                    "check_category",
                    "check_name",
                    "check_status",
                    "observed_value",
                    "threshold_value",
                    "check_reason",
                    "live_trading",
                    "live_order_sent",
                    "capital_deployment",
                    "metadata_json",
                ],
            )

        for drift in summary["feature_drifts"]:
            row = dict(drift)
            row["metadata_json"] = json.dumps(row.pop("metadata"), sort_keys=True)
            insert_row(
                conn,
                GUARD_DRIFTS_TABLE,
                row,
                [
                    "drift_id",
                    "review_label",
                    "created_at",
                    "source_learning_run_label",
                    "baseline_learning_run_label",
                    "feature_group",
                    "feature_name",
                    "current_normalized_value",
                    "baseline_normalized_value",
                    "absolute_drift",
                    "drift_status",
                    "live_trading",
                    "live_order_sent",
                    "capital_deployment",
                    "metadata_json",
                ],
            )

        review_row = {
            "review_label": summary["review_label"],
            "report_label": summary["report_label"],
            "created_at": summary["created_at"],
            "source_learning_run_label": summary["source_learning_run_label"],
            "baseline_learning_run_label": summary["baseline_learning_run_label"],
            "source_multi_cycle_track_label": summary["source_multi_cycle_track_label"],
            "source_session_label": summary["source_session_label"],
            "source_portfolio_label": summary["source_portfolio_label"],
            "cycle_count": summary["cycle_count"],
            "feature_count": summary["feature_count"],
            "label_count": summary["label_count"],
            "recommendation_count": summary["recommendation_count"],
            "required_feature_group_count": summary["required_feature_group_count"],
            "observed_feature_group_count": summary["observed_feature_group_count"],
            "missing_required_group_count": summary["missing_required_group_count"],
            "invalid_normalized_feature_count": summary["invalid_normalized_feature_count"],
            "invalid_feature_weight_count": summary["invalid_feature_weight_count"],
            "feature_weight_total": str(summary["feature_weight_total"]),
            "learning_score": str(summary["learning_score"]),
            "max_feature_drift": str(summary["max_feature_drift"]),
            "average_feature_drift": str(summary["average_feature_drift"]),
            "drift_check_count": summary["drift_check_count"],
            "quality_check_count": summary["quality_check_count"],
            "pass_check_count": summary["pass_check_count"],
            "fail_check_count": summary["fail_check_count"],
            "safety_breach_count": summary["safety_breach_count"],
            "drift_status": summary["drift_status"],
            "quality_state": summary["quality_state"],
            "guard_decision": summary["guard_decision"],
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
            GUARD_REVIEWS_TABLE,
            review_row,
            [
                "review_label",
                "report_label",
                "created_at",
                "source_learning_run_label",
                "baseline_learning_run_label",
                "source_multi_cycle_track_label",
                "source_session_label",
                "source_portfolio_label",
                "cycle_count",
                "feature_count",
                "label_count",
                "recommendation_count",
                "required_feature_group_count",
                "observed_feature_group_count",
                "missing_required_group_count",
                "invalid_normalized_feature_count",
                "invalid_feature_weight_count",
                "feature_weight_total",
                "learning_score",
                "max_feature_drift",
                "average_feature_drift",
                "drift_check_count",
                "quality_check_count",
                "pass_check_count",
                "fail_check_count",
                "safety_breach_count",
                "drift_status",
                "quality_state",
                "guard_decision",
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
            "review_label": summary["review_label"],
            "created_at": summary["created_at"],
            "source_learning_run_label": summary["source_learning_run_label"],
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
            GUARD_REPORTS_TABLE,
            report_row,
            [
                "report_label",
                "review_label",
                "created_at",
                "source_learning_run_label",
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


def run_ai_feature_quality_drift_guard(
    db_path: str | Path = "offchain/deltagrid.db",
    review_label: str | None = None,
    report_label: str | None = None,
    learning_run_label: str = "mission70-final-check",
    min_feature_count: int = 12,
    min_label_count: int = 4,
    min_recommendation_count: int = 3,
    min_learning_score: float = 70.0,
    min_feature_weight_total: float = 0.90,
    max_feature_weight_total: float = 1.20,
    max_allowed_feature_drift: float = 0.10,
) -> dict[str, Any]:
    if min_feature_count <= 0:
        raise ValueError("min_feature_count must be positive")

    if min_label_count <= 0:
        raise ValueError("min_label_count must be positive")

    if min_recommendation_count <= 0:
        raise ValueError("min_recommendation_count must be positive")

    if min_learning_score < 0:
        raise ValueError("min_learning_score cannot be negative")

    if min_feature_weight_total < 0 or max_feature_weight_total < 0:
        raise ValueError("feature weight total bounds cannot be negative")

    if min_feature_weight_total > max_feature_weight_total:
        raise ValueError("min_feature_weight_total cannot exceed max_feature_weight_total")

    if max_allowed_feature_drift < 0:
        raise ValueError("max_allowed_feature_drift cannot be negative")

    db = Path(db_path)
    review = review_label or new_review_label()
    report = report_label or new_report_label()
    created_at = utc_now()
    source_label = parse_labels(learning_run_label)[0]

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        learning_run = load_learning_run(conn, source_label)
        features = load_features(conn, source_label)
        labels = load_labels(conn, source_label)
        recommendations = load_recommendations(conn, source_label)

        source_track = row_get(learning_run, "source_multi_cycle_track_label", None)
        baseline_learning_run = load_baseline_learning_run(conn, source_label, source_track)
        baseline_label = row_get(baseline_learning_run, "learning_run_label", None)
        baseline_features = load_features(conn, baseline_label) if baseline_label else []

    drifts = build_drift_rows(
        review_label=review,
        created_at=created_at,
        learning_run_label=source_label,
        baseline_learning_run_label=baseline_label,
        current_features=features,
        baseline_features=baseline_features,
        max_allowed_feature_drift=max_allowed_feature_drift,
    )

    metrics = build_metrics(
        learning_run=learning_run,
        features=features,
        labels=labels,
        recommendations=recommendations,
        baseline_learning_run=baseline_learning_run,
        drifts=drifts,
    )

    if learning_run is None:
        checks = build_missing_checks(review, created_at, source_label)
    else:
        checks = build_checks(
            review_label=review,
            created_at=created_at,
            learning_run_label=source_label,
            learning_run=learning_run,
            features=features,
            labels=labels,
            recommendations=recommendations,
            metrics=metrics,
            min_feature_count=min_feature_count,
            min_label_count=min_label_count,
            min_recommendation_count=min_recommendation_count,
            min_learning_score=min_learning_score,
            min_feature_weight_total=min_feature_weight_total,
            max_feature_weight_total=max_feature_weight_total,
            max_allowed_feature_drift=max_allowed_feature_drift,
        )

    guard_decision, global_verdict, recommended_action, next_mission, quality_state, decision_reason = decide_guard_outcome(
        learning_run,
        checks,
    )

    summary = build_summary(
        db_path=db,
        review_label=review,
        report_label=report,
        created_at=created_at,
        learning_run_label=source_label,
        metrics=metrics,
        checks=checks,
        drifts=drifts,
        guard_decision=guard_decision,
        global_verdict=global_verdict,
        recommended_action=recommended_action,
        next_mission=next_mission,
        quality_state=quality_state,
        decision_reason=decision_reason,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_guard_review(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid AI feature quality and drift guard.")
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--review-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--learning-run-label", default="mission70-final-check")
    parser.add_argument("--min-feature-count", type=int, default=12)
    parser.add_argument("--min-label-count", type=int, default=4)
    parser.add_argument("--min-recommendation-count", type=int, default=3)
    parser.add_argument("--min-learning-score", type=float, default=70.0)
    parser.add_argument("--min-feature-weight-total", type=float, default=0.90)
    parser.add_argument("--max-feature-weight-total", type=float, default=1.20)
    parser.add_argument("--max-allowed-feature-drift", type=float, default=0.10)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_ai_feature_quality_drift_guard(
        db_path=args.db,
        review_label=args.review_label,
        report_label=args.report_label,
        learning_run_label=args.learning_run_label,
        min_feature_count=args.min_feature_count,
        min_label_count=args.min_label_count,
        min_recommendation_count=args.min_recommendation_count,
        min_learning_score=args.min_learning_score,
        min_feature_weight_total=args.min_feature_weight_total,
        max_feature_weight_total=args.max_feature_weight_total,
        max_allowed_feature_drift=args.max_allowed_feature_drift,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

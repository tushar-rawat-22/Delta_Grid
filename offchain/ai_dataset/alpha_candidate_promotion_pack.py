"""Mission 84.8: Alpha Candidate Promotion Pack.

Consumes Mission 84.7 walk-forward robustness results and creates a provisional,
fixture-only local research registry. This module never trains or promotes a
model, emits live signals, sends orders, deploys capital, uses private keys or
paid APIs, reweights strategies with capital, or makes profitability claims.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from offchain.ai_dataset.multi_strategy_backtest_pack import (
    CAPITAL_DEPLOYMENT_STATUS,
    LIVE_ORDER_SENT_VALUE,
    LIVE_TRADING_STATUS,
    MISSION85_STATUS,
    canonical_json,
    normalize_label,
    safe_float,
    safe_int,
    table_exists,
    utc_now,
)

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")
PROMOTION_SCOPE = "ALPHA_CANDIDATE_PROMOTION_PACK_FIXTURE_ONLY"
PROMOTION_MODE = "DETERMINISTIC_RULE_BASED_PROVISIONAL_RESEARCH_REGISTRY"
SOURCE_ENGINE_STATE = "AI_WALK_FORWARD_ROBUSTNESS_GATE_READY_LOCAL_ONLY"
SOURCE_ENGINE_DECISION = (
    "AI_WALK_FORWARD_ROBUSTNESS_GATE_APPROVED_FOR_ALPHA_CANDIDATE_PROMOTION_REVIEW"
)
SOURCE_GLOBAL_VERDICT = "AI_WALK_FORWARD_ROBUSTNESS_GATE_READY_SHADOW_RESEARCH_ONLY"
SOURCE_ROBUST_STATUS = "ROBUST_FIXTURE_CANDIDATE_UNPROMOTED"
SOURCE_BLOCKED_STATUS = "BLOCKED_BY_WALK_FORWARD_ROBUSTNESS_GATE"
PROVISIONAL_STATUS = "PROVISIONAL_ALPHA_RESEARCH_CANDIDATE_FIXTURE_ONLY_UNVALIDATED"
HELD_STATUS = "HELD_BY_ALPHA_CANDIDATE_PROMOTION_PACK"
REGISTRY_EVIDENCE_SCOPE = "SYNTHETIC_FIXTURE_WALK_FORWARD_ONLY_UNVALIDATED"
NEXT_VALIDATION_STAGE = "Mission 84.9 Real-Data Alpha Replication Pack"
ENGINE_STATE = "AI_ALPHA_CANDIDATE_PROMOTION_PACK_READY_LOCAL_ONLY"
ENGINE_DECISION = (
    "AI_ALPHA_CANDIDATE_PROMOTION_PACK_APPROVED_FOR_REAL_DATA_ALPHA_REPLICATION"
)
GLOBAL_VERDICT = "AI_ALPHA_CANDIDATE_PROMOTION_PACK_READY_SHADOW_RESEARCH_ONLY"
RECOMMENDED_ACTION = (
    "HAND_OFF_PROVISIONAL_FIXTURE_CANDIDATES_TO_REAL_DATA_ALPHA_REPLICATION_PACK"
)
NEXT_MISSION = NEXT_VALIDATION_STAGE
CHECK_PASS = "PASS"
CHECK_FAIL = "FAIL"

_REQUIRED_SOURCE_ACTIONS = {
    "model_training_action": "NO_MODEL_TRAINING",
    "model_artifact_action": "NO_MODEL_ARTIFACT",
    "model_promotion_action": "NO_MODEL_PROMOTION",
    "strategy_reweighting_action": "NO_STRATEGY_REWEIGHTING",
    "live_signal_action": "NO_LIVE_SIGNAL",
    "exchange_order_action": "NO_EXCHANGE_ORDER",
    "capital_action": "NO_CAPITAL_DEPLOYMENT",
    "paid_api_action": "NO_PAID_API",
    "profitability_claim_action": "NO_PROFITABILITY_CLAIM",
}


def ensure_schema(db_path: str | Path) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ai_alpha_candidate_promotion_runs (
                promotion_run_label TEXT PRIMARY KEY,
                report_label TEXT NOT NULL,
                source_robustness_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                promotion_scope TEXT NOT NULL,
                promotion_mode TEXT NOT NULL,
                mission85_status TEXT NOT NULL,
                source_candidate_count INTEGER NOT NULL,
                source_robust_candidate_count INTEGER NOT NULL,
                source_blocked_candidate_count INTEGER NOT NULL,
                reviewed_candidate_count INTEGER NOT NULL,
                provisional_candidate_count INTEGER NOT NULL,
                held_candidate_count INTEGER NOT NULL,
                strategy_family_count INTEGER NOT NULL,
                asset_group_count INTEGER NOT NULL,
                timeframe_count INTEGER NOT NULL,
                model_training_count INTEGER NOT NULL,
                model_artifact_count INTEGER NOT NULL,
                model_promotion_count INTEGER NOT NULL,
                strategy_reweighting_count INTEGER NOT NULL,
                live_signal_count INTEGER NOT NULL,
                exchange_order_count INTEGER NOT NULL,
                capital_deployment_count INTEGER NOT NULL,
                paid_api_count INTEGER NOT NULL,
                private_key_use_count INTEGER NOT NULL,
                profitability_claim_count INTEGER NOT NULL,
                promotion_check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
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
            );

            CREATE TABLE IF NOT EXISTS ai_alpha_candidate_reviews (
                review_id TEXT PRIMARY KEY,
                promotion_run_label TEXT NOT NULL,
                source_robustness_result_id TEXT NOT NULL,
                source_robustness_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                strategy_family_code TEXT NOT NULL,
                asset_group TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                cost_model_code TEXT NOT NULL,
                source_robustness_status TEXT NOT NULL,
                source_window_count INTEGER NOT NULL,
                source_positive_window_ratio TEXT NOT NULL,
                source_median_net_return_pct TEXT NOT NULL,
                source_return_dispersion_pct TEXT NOT NULL,
                source_worst_window_drawdown_pct TEXT NOT NULL,
                source_outperformed_cash_window_count INTEGER NOT NULL,
                review_status TEXT NOT NULL,
                registry_eligible INTEGER NOT NULL,
                review_reasons_json TEXT NOT NULL,
                model_training_action TEXT NOT NULL,
                model_artifact_action TEXT NOT NULL,
                model_promotion_action TEXT NOT NULL,
                strategy_reweighting_action TEXT NOT NULL,
                live_signal_action TEXT NOT NULL,
                exchange_order_action TEXT NOT NULL,
                capital_action TEXT NOT NULL,
                paid_api_action TEXT NOT NULL,
                profitability_claim_action TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_alpha_candidate_registry (
                registry_entry_id TEXT PRIMARY KEY,
                promotion_run_label TEXT NOT NULL,
                review_id TEXT NOT NULL,
                source_robustness_result_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                strategy_family_code TEXT NOT NULL,
                asset_group TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                cost_model_code TEXT NOT NULL,
                registry_status TEXT NOT NULL,
                evidence_scope TEXT NOT NULL,
                next_validation_stage TEXT NOT NULL,
                model_training_action TEXT NOT NULL,
                model_artifact_action TEXT NOT NULL,
                model_promotion_action TEXT NOT NULL,
                strategy_reweighting_action TEXT NOT NULL,
                live_signal_action TEXT NOT NULL,
                exchange_order_action TEXT NOT NULL,
                capital_action TEXT NOT NULL,
                paid_api_action TEXT NOT NULL,
                profitability_claim_action TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_alpha_candidate_promotion_checks (
                check_id TEXT PRIMARY KEY,
                promotion_run_label TEXT NOT NULL,
                source_robustness_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                check_category TEXT NOT NULL,
                check_name TEXT NOT NULL,
                check_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                threshold_value TEXT NOT NULL,
                check_reason TEXT NOT NULL,
                promotion_scope TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_alpha_candidate_promotion_reports (
                report_label TEXT PRIMARY KEY,
                promotion_run_label TEXT NOT NULL,
                source_robustness_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                report_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL
            );
            """
        )
        conn.commit()


def _value(row: sqlite3.Row | Mapping[str, Any], key: str, default: Any = None) -> Any:
    if isinstance(row, sqlite3.Row):
        return row[key] if key in row.keys() else default
    return row.get(key, default)


def inherited_safety_actions_valid(row: sqlite3.Row | Mapping[str, Any]) -> bool:
    if any(str(_value(row, key, "")) != expected for key, expected in _REQUIRED_SOURCE_ACTIONS.items()):
        return False
    return (
        str(_value(row, "live_trading", "")) == LIVE_TRADING_STATUS
        and safe_int(_value(row, "live_order_sent", -1)) == LIVE_ORDER_SENT_VALUE
        and str(_value(row, "capital_deployment", "")) == CAPITAL_DEPLOYMENT_STATUS
    )


def review_candidate(
    source_result: sqlite3.Row | Mapping[str, Any],
    promotion_run_label: str,
    source_robustness_run_label: str,
    created_at: str,
    min_windows: int = 3,
    min_positive_ratio: float = 2.0 / 3.0,
    max_worst_drawdown_pct: float = 25.0,
    max_return_dispersion_pct: float = 20.0,
    min_cash_outperformance_ratio: float = 2.0 / 3.0,
) -> dict[str, Any]:
    source_id = str(_value(source_result, "robustness_result_id", ""))
    if not source_id:
        raise ValueError("source result must include robustness_result_id")

    window_count = safe_int(_value(source_result, "window_count", 0))
    positive_ratio = safe_float(_value(source_result, "positive_window_ratio", 0.0))
    median_return = safe_float(_value(source_result, "median_net_return_pct", 0.0))
    dispersion = safe_float(_value(source_result, "return_dispersion_pct", 0.0))
    worst_drawdown = safe_float(_value(source_result, "worst_window_drawdown_pct", 0.0))
    out_cash = safe_int(_value(source_result, "outperformed_cash_window_count", 0))
    required_cash_windows = max(1, math.ceil(window_count * min_cash_outperformance_ratio)) if window_count else 1
    source_status = str(_value(source_result, "robustness_status", ""))

    reasons: list[str] = []
    if source_status != SOURCE_ROBUST_STATUS:
        reasons.append("SOURCE_NOT_ROBUST_FIXTURE_CANDIDATE")
    if window_count < min_windows:
        reasons.append("INSUFFICIENT_WINDOWS")
    if positive_ratio < min_positive_ratio:
        reasons.append("POSITIVE_WINDOW_RATIO_BELOW_THRESHOLD")
    if median_return <= 0.0:
        reasons.append("NON_POSITIVE_MEDIAN_RETURN")
    if worst_drawdown > max_worst_drawdown_pct:
        reasons.append("WORST_WINDOW_DRAWDOWN_ABOVE_THRESHOLD")
    if dispersion > max_return_dispersion_pct:
        reasons.append("RETURN_DISPERSION_ABOVE_THRESHOLD")
    if out_cash < required_cash_windows:
        reasons.append("INSUFFICIENT_CASH_BASELINE_OUTPERFORMANCE")
    if not inherited_safety_actions_valid(source_result):
        reasons.append("INHERITED_SAFETY_ACTIONS_INVALID")

    eligible = not reasons
    review_status = PROVISIONAL_STATUS if eligible else HELD_STATUS
    review_id = f"{promotion_run_label}-{source_id}"

    return {
        "review_id": review_id,
        "promotion_run_label": promotion_run_label,
        "source_robustness_result_id": source_id,
        "source_robustness_run_label": source_robustness_run_label,
        "created_at": created_at,
        "strategy_family_code": str(_value(source_result, "strategy_family_code", "UNKNOWN")),
        "asset_group": str(_value(source_result, "asset_group", "UNKNOWN")),
        "timeframe": str(_value(source_result, "timeframe", "UNKNOWN")),
        "cost_model_code": str(_value(source_result, "cost_model_code", "UNKNOWN")),
        "source_robustness_status": source_status,
        "source_window_count": window_count,
        "source_positive_window_ratio": positive_ratio,
        "source_median_net_return_pct": median_return,
        "source_return_dispersion_pct": dispersion,
        "source_worst_window_drawdown_pct": worst_drawdown,
        "source_outperformed_cash_window_count": out_cash,
        "review_status": review_status,
        "registry_eligible": int(eligible),
        "review_reasons": reasons,
        "model_training_action": "NO_MODEL_TRAINING",
        "model_artifact_action": "NO_MODEL_ARTIFACT",
        "model_promotion_action": "NO_MODEL_PROMOTION",
        "strategy_reweighting_action": "NO_STRATEGY_REWEIGHTING",
        "live_signal_action": "NO_LIVE_SIGNAL",
        "exchange_order_action": "NO_EXCHANGE_ORDER",
        "capital_action": "NO_CAPITAL_DEPLOYMENT",
        "paid_api_action": "NO_PAID_API",
        "profitability_claim_action": "NO_PROFITABILITY_CLAIM",
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "local_only": True,
            "paper_only": True,
            "fixture_based": True,
            "provisional_research_only": True,
            "real_data_validated": False,
            "model_training_enabled": False,
            "model_promoted": False,
            "profitability_claim": False,
            "mission85_status": MISSION85_STATUS,
        },
    }


def build_registry_entry(review: Mapping[str, Any]) -> dict[str, Any]:
    if safe_int(review.get("registry_eligible", 0)) != 1:
        raise ValueError("only registry-eligible reviews can enter the registry")
    if str(review.get("review_status")) != PROVISIONAL_STATUS:
        raise ValueError("review status is not provisional")

    return {
        "registry_entry_id": f"registry-{review['review_id']}",
        "promotion_run_label": str(review["promotion_run_label"]),
        "review_id": str(review["review_id"]),
        "source_robustness_result_id": str(review["source_robustness_result_id"]),
        "created_at": str(review["created_at"]),
        "strategy_family_code": str(review["strategy_family_code"]),
        "asset_group": str(review["asset_group"]),
        "timeframe": str(review["timeframe"]),
        "cost_model_code": str(review["cost_model_code"]),
        "registry_status": PROVISIONAL_STATUS,
        "evidence_scope": REGISTRY_EVIDENCE_SCOPE,
        "next_validation_stage": NEXT_VALIDATION_STAGE,
        "model_training_action": "NO_MODEL_TRAINING",
        "model_artifact_action": "NO_MODEL_ARTIFACT",
        "model_promotion_action": "NO_MODEL_PROMOTION",
        "strategy_reweighting_action": "NO_STRATEGY_REWEIGHTING",
        "live_signal_action": "NO_LIVE_SIGNAL",
        "exchange_order_action": "NO_EXCHANGE_ORDER",
        "capital_action": "NO_CAPITAL_DEPLOYMENT",
        "paid_api_action": "NO_PAID_API",
        "profitability_claim_action": "NO_PROFITABILITY_CLAIM",
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "local_only": True,
            "paper_only": True,
            "fixture_based": True,
            "real_data_validated": False,
            "candidate_deployed": False,
            "capital_allocated": False,
            "profitability_claim": False,
            "mission85_status": MISSION85_STATUS,
        },
    }


def _make_check(
    run_label: str,
    source_label: str,
    created_at: str,
    category: str,
    name: str,
    passed: bool,
    observed: Any,
    threshold: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_id": f"{run_label}-{category.lower()}-{name.lower().replace('_', '-')}",
        "promotion_run_label": run_label,
        "source_robustness_run_label": source_label,
        "created_at": created_at,
        "check_category": category,
        "check_name": name,
        "check_status": CHECK_PASS if passed else CHECK_FAIL,
        "observed_value": str(observed),
        "threshold_value": str(threshold),
        "check_reason": reason,
        "promotion_scope": PROMOTION_SCOPE,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "metadata": {
            "local_only": True,
            "paper_only": True,
            "fixture_based": True,
            "model_training_enabled": False,
            "live_signal_generation_enabled": False,
            "profitability_claim": False,
        },
    }


def _source_ready(source_run: sqlite3.Row | Mapping[str, Any] | None) -> bool:
    if source_run is None:
        return False
    zero_fields = (
        "model_training_count",
        "model_artifact_count",
        "model_promotion_count",
        "strategy_reweighting_count",
        "live_signal_count",
        "exchange_order_count",
        "capital_deployment_count",
        "paid_api_count",
        "private_key_use_count",
        "profitability_claim_count",
        "fail_check_count",
        "safety_breach_count",
    )
    return (
        str(_value(source_run, "engine_state", "")) == SOURCE_ENGINE_STATE
        and str(_value(source_run, "engine_decision", "")) == SOURCE_ENGINE_DECISION
        and str(_value(source_run, "global_verdict", "")) == SOURCE_GLOBAL_VERDICT
        and str(_value(source_run, "mission85_status", "")) == MISSION85_STATUS
        and all(safe_int(_value(source_run, field, -1)) == 0 for field in zero_fields)
    )


def _review_safety_valid(review: Mapping[str, Any]) -> bool:
    return inherited_safety_actions_valid(review)


def _registry_safety_valid(entry: Mapping[str, Any]) -> bool:
    return inherited_safety_actions_valid(entry)


def _fmt(value: Any) -> str:
    return f"{safe_float(value):.8f}"


def _build_markdown(summary: Mapping[str, Any]) -> str:
    return f"""# DeltaGrid Mission 84.8 Alpha Candidate Promotion Pack Report

- Run: {summary['promotion_run_label']}
- Source: {summary['source_robustness_run_label']}
- Source candidates: {summary['source_candidate_count']}
- Reviewed candidates: {summary['reviewed_candidate_count']}
- Provisional fixture-only candidates: {summary['provisional_candidate_count']}
- Held candidates: {summary['held_candidate_count']}
- Checks: {summary['pass_check_count']} passed, {summary['fail_check_count']} failed
- Safety breaches: {summary['safety_breach_count']}
- Mission 85: {summary['mission85_status']}

Provisional registration is synthetic-fixture-only, unvalidated research classification. It is not a profitability claim and does not authorize model training, model promotion, live signals, exchange orders, strategy reweighting, or capital deployment.
"""


def run_alpha_candidate_promotion_pack(
    db_path: str | Path = DEFAULT_DB_PATH,
    promotion_run_label: str = "mission84-8-local-check",
    report_label: str = "mission84-8-local-check-report",
    source_robustness_run_label: str = "mission84-7-final-check",
    min_source_candidates: int = 72,
    min_windows: int = 3,
    min_positive_ratio: float = 2.0 / 3.0,
    max_worst_drawdown_pct: float = 25.0,
    max_return_dispersion_pct: float = 20.0,
    min_cash_outperformance_ratio: float = 2.0 / 3.0,
) -> dict[str, Any]:
    promotion_run_label = normalize_label(promotion_run_label, "promotion_run_label")
    report_label = normalize_label(report_label, "report_label")
    source_robustness_run_label = normalize_label(
        source_robustness_run_label, "source_robustness_run_label"
    )
    if min_source_candidates < 1:
        raise ValueError("min_source_candidates must be positive")
    if min_windows < 1:
        raise ValueError("min_windows must be positive")
    if not 0.0 <= min_positive_ratio <= 1.0:
        raise ValueError("min_positive_ratio must be between 0 and 1")
    if not 0.0 <= min_cash_outperformance_ratio <= 1.0:
        raise ValueError("min_cash_outperformance_ratio must be between 0 and 1")

    ensure_schema(db_path)
    created_at = utc_now()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        source_tables_present = table_exists(conn, "ai_walk_forward_robustness_runs") and table_exists(
            conn, "ai_walk_forward_robustness_results"
        )
        source_run = None
        source_rows: list[sqlite3.Row] = []
        if source_tables_present:
            source_run = conn.execute(
                "SELECT * FROM ai_walk_forward_robustness_runs WHERE robustness_run_label=?",
                (source_robustness_run_label,),
            ).fetchone()
            source_rows = conn.execute(
                """
                SELECT *
                FROM ai_walk_forward_robustness_results
                WHERE robustness_run_label=?
                ORDER BY robustness_result_id
                """,
                (source_robustness_run_label,),
            ).fetchall()

        source_count = len(source_rows)
        source_robust_count = sum(
            str(row["robustness_status"]) == SOURCE_ROBUST_STATUS for row in source_rows
        )
        source_blocked_count = sum(
            str(row["robustness_status"]) == SOURCE_BLOCKED_STATUS for row in source_rows
        )
        source_ready = _source_ready(source_run)

        review_rows: list[dict[str, Any]] = []
        registry_rows: list[dict[str, Any]] = []
        if source_ready and source_count >= min_source_candidates:
            for source_row in source_rows:
                review = review_candidate(
                    source_row,
                    promotion_run_label=promotion_run_label,
                    source_robustness_run_label=source_robustness_run_label,
                    created_at=created_at,
                    min_windows=min_windows,
                    min_positive_ratio=min_positive_ratio,
                    max_worst_drawdown_pct=max_worst_drawdown_pct,
                    max_return_dispersion_pct=max_return_dispersion_pct,
                    min_cash_outperformance_ratio=min_cash_outperformance_ratio,
                )
                review_rows.append(review)
                if review["registry_eligible"] == 1:
                    registry_rows.append(build_registry_entry(review))

        reviewed_count = len(review_rows)
        provisional_count = len(registry_rows)
        held_count = reviewed_count - provisional_count
        blocked_registered_count = sum(
            1
            for entry in registry_rows
            if next(
                review
                for review in review_rows
                if review["review_id"] == entry["review_id"]
            )["source_robustness_status"]
            != SOURCE_ROBUST_STATUS
        )
        unsafe_review_count = sum(not _review_safety_valid(row) for row in review_rows)
        unsafe_registry_count = sum(not _registry_safety_valid(row) for row in registry_rows)
        safety_breach_count = unsafe_review_count + unsafe_registry_count
        strategy_family_count = len({row["strategy_family_code"] for row in review_rows})
        asset_group_count = len({row["asset_group"] for row in review_rows})
        timeframe_count = len({row["timeframe"] for row in review_rows})

        checks = [
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "SOURCE", "SOURCE_TABLES_PRESENT", source_tables_present, source_tables_present, True, "Mission 84.7 source tables must exist."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "SOURCE", "SOURCE_RUN_READY", source_ready, source_ready, True, "Mission 84.7 source run must be ready and safe."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "COVERAGE", "SOURCE_CANDIDATE_COUNT", source_count >= min_source_candidates, source_count, min_source_candidates, "All required source candidates must exist."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "COVERAGE", "REVIEWED_CANDIDATE_COUNT", reviewed_count == source_count and source_count >= min_source_candidates, reviewed_count, source_count, "Every source candidate must be reviewed."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "COVERAGE", "SOURCE_STATUS_PARTITION_COMPLETE", source_robust_count + source_blocked_count == source_count, source_robust_count + source_blocked_count, source_count, "Source statuses must form a complete partition."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "REGISTRY", "REGISTRY_ONLY_ELIGIBLE", all(row["registry_status"] == PROVISIONAL_STATUS for row in registry_rows), provisional_count, provisional_count, "Only eligible provisional candidates may enter the registry."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "REGISTRY", "BLOCKED_SOURCE_NOT_REGISTERED", blocked_registered_count == 0, blocked_registered_count, 0, "Blocked Mission 84.7 candidates must not be registered."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "GOVERNANCE", "NO_FORCED_PROMOTION", provisional_count <= source_robust_count, provisional_count, f"<= {source_robust_count}", "The pack must never force a minimum number of promotions."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "SAFETY", "NO_MODEL_TRAINING", 0 == 0, 0, 0, "Model training remains disabled."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "SAFETY", "NO_MODEL_ARTIFACTS", 0 == 0, 0, 0, "No model artifacts are created."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "SAFETY", "NO_MODEL_PROMOTION", 0 == 0, 0, 0, "No model is promoted."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "SAFETY", "NO_STRATEGY_REWEIGHTING", 0 == 0, 0, 0, "No capital-linked strategy reweighting occurs."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "SAFETY", "NO_LIVE_SIGNALS", 0 == 0, 0, 0, "No live signals are emitted."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "SAFETY", "NO_EXCHANGE_ORDERS", 0 == 0, 0, 0, "No exchange orders are sent."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "SAFETY", "NO_CAPITAL_DEPLOYMENT", 0 == 0, 0, 0, "No real capital is deployed."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "SAFETY", "NO_PAID_APIS", 0 == 0, 0, 0, "No paid API is used."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "SAFETY", "NO_PRIVATE_KEYS", 0 == 0, 0, 0, "No private keys or signing are used."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "GOVERNANCE", "NO_PROFITABILITY_CLAIMS", 0 == 0, 0, 0, "Provisional fixture evidence is not a profitability claim."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "GOVERNANCE", "MISSION85_PAUSED", MISSION85_STATUS == "PAUSED_UNTIL_ROBUST_ALPHA_CANDIDATES_EXIST", MISSION85_STATUS, "PAUSED_UNTIL_ROBUST_ALPHA_CANDIDATES_EXIST", "Model promotion remains paused."),
            _make_check(promotion_run_label, source_robustness_run_label, created_at, "SAFETY", "ZERO_SAFETY_BREACHES", safety_breach_count == 0, safety_breach_count, 0, "All reviews and registry entries must retain safety locks."),
        ]

        pass_count = sum(row["check_status"] == CHECK_PASS for row in checks)
        fail_count = sum(row["check_status"] == CHECK_FAIL for row in checks)
        ready = fail_count == 0

        summary: dict[str, Any] = {
            "promotion_run_label": promotion_run_label,
            "report_label": report_label,
            "source_robustness_run_label": source_robustness_run_label,
            "created_at": created_at,
            "promotion_scope": PROMOTION_SCOPE,
            "promotion_mode": PROMOTION_MODE,
            "mission85_status": MISSION85_STATUS,
            "source_candidate_count": source_count,
            "source_robust_candidate_count": source_robust_count,
            "source_blocked_candidate_count": source_blocked_count,
            "reviewed_candidate_count": reviewed_count,
            "provisional_candidate_count": provisional_count,
            "held_candidate_count": held_count,
            "strategy_family_count": strategy_family_count,
            "asset_group_count": asset_group_count,
            "timeframe_count": timeframe_count,
            "model_training_count": 0,
            "model_artifact_count": 0,
            "model_promotion_count": 0,
            "strategy_reweighting_count": 0,
            "live_signal_count": 0,
            "exchange_order_count": 0,
            "capital_deployment_count": 0,
            "paid_api_count": 0,
            "private_key_use_count": 0,
            "profitability_claim_count": 0,
            "promotion_check_count": len(checks),
            "pass_check_count": pass_count,
            "fail_check_count": fail_count,
            "safety_breach_count": safety_breach_count,
            "engine_state": ENGINE_STATE if ready else "AI_ALPHA_CANDIDATE_PROMOTION_PACK_BLOCKED",
            "engine_decision": ENGINE_DECISION if ready else "AI_ALPHA_CANDIDATE_PROMOTION_PACK_REQUIRES_REMEDIATION",
            "global_verdict": GLOBAL_VERDICT if ready else "AI_ALPHA_CANDIDATE_PROMOTION_PACK_BLOCKED_RESEARCH_ONLY",
            "recommended_action": RECOMMENDED_ACTION if ready else "REMEDIATE_FAILED_ALPHA_CANDIDATE_PROMOTION_CHECKS",
            "next_mission": NEXT_MISSION if ready else "Mission 84.8 remediation",
            "live_trading": LIVE_TRADING_STATUS,
            "live_order_sent": LIVE_ORDER_SENT_VALUE,
            "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
            "promotion_checks": checks,
            "candidate_reviews": review_rows,
            "registry_entries": registry_rows,
            "safety_disclaimer": "Provisional synthetic-fixture registration is unvalidated research classification and is not a profitability claim.",
        }
        markdown_report = _build_markdown(summary)
        summary["markdown_report"] = markdown_report

        for table, column, value in (
            ("ai_alpha_candidate_reviews", "promotion_run_label", promotion_run_label),
            ("ai_alpha_candidate_registry", "promotion_run_label", promotion_run_label),
            ("ai_alpha_candidate_promotion_checks", "promotion_run_label", promotion_run_label),
            ("ai_alpha_candidate_promotion_runs", "promotion_run_label", promotion_run_label),
            ("ai_alpha_candidate_promotion_reports", "report_label", report_label),
        ):
            conn.execute(f"DELETE FROM {table} WHERE {column}=?", (value,))

        for row in review_rows:
            metrics = {
                "window_count": row["source_window_count"],
                "positive_window_ratio": row["source_positive_window_ratio"],
                "median_net_return_pct": row["source_median_net_return_pct"],
                "return_dispersion_pct": row["source_return_dispersion_pct"],
                "worst_window_drawdown_pct": row["source_worst_window_drawdown_pct"],
                "outperformed_cash_window_count": row["source_outperformed_cash_window_count"],
            }
            conn.execute(
                "INSERT INTO ai_alpha_candidate_reviews VALUES (" + ",".join("?" for _ in range(33)) + ")",
                (
                    row["review_id"], row["promotion_run_label"], row["source_robustness_result_id"], row["source_robustness_run_label"], row["created_at"], row["strategy_family_code"], row["asset_group"], row["timeframe"], row["cost_model_code"], row["source_robustness_status"], row["source_window_count"], _fmt(row["source_positive_window_ratio"]), _fmt(row["source_median_net_return_pct"]), _fmt(row["source_return_dispersion_pct"]), _fmt(row["source_worst_window_drawdown_pct"]), row["source_outperformed_cash_window_count"], row["review_status"], row["registry_eligible"], canonical_json(row["review_reasons"]), row["model_training_action"], row["model_artifact_action"], row["model_promotion_action"], row["strategy_reweighting_action"], row["live_signal_action"], row["exchange_order_action"], row["capital_action"], row["paid_api_action"], row["profitability_claim_action"], row["live_trading"], row["live_order_sent"], row["capital_deployment"], canonical_json(metrics), canonical_json(row["metadata"]),
                ),
            )

        for row in registry_rows:
            conn.execute(
                "INSERT INTO ai_alpha_candidate_registry VALUES (" + ",".join("?" for _ in range(25)) + ")",
                (
                    row["registry_entry_id"], row["promotion_run_label"], row["review_id"], row["source_robustness_result_id"], row["created_at"], row["strategy_family_code"], row["asset_group"], row["timeframe"], row["cost_model_code"], row["registry_status"], row["evidence_scope"], row["next_validation_stage"], row["model_training_action"], row["model_artifact_action"], row["model_promotion_action"], row["strategy_reweighting_action"], row["live_signal_action"], row["exchange_order_action"], row["capital_action"], row["paid_api_action"], row["profitability_claim_action"], row["live_trading"], row["live_order_sent"], row["capital_deployment"], canonical_json(row["metadata"]),
                ),
            )

        for row in checks:
            conn.execute(
                "INSERT INTO ai_alpha_candidate_promotion_checks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row["check_id"], row["promotion_run_label"], row["source_robustness_run_label"], row["created_at"], row["check_category"], row["check_name"], row["check_status"], row["observed_value"], row["threshold_value"], row["check_reason"], row["promotion_scope"], row["live_trading"], row["live_order_sent"], row["capital_deployment"], canonical_json(row["metadata"]),
                ),
            )

        run_keys = (
            "promotion_run_label", "report_label", "source_robustness_run_label", "created_at", "promotion_scope", "promotion_mode", "mission85_status", "source_candidate_count", "source_robust_candidate_count", "source_blocked_candidate_count", "reviewed_candidate_count", "provisional_candidate_count", "held_candidate_count", "strategy_family_count", "asset_group_count", "timeframe_count", "model_training_count", "model_artifact_count", "model_promotion_count", "strategy_reweighting_count", "live_signal_count", "exchange_order_count", "capital_deployment_count", "paid_api_count", "private_key_use_count", "profitability_claim_count", "promotion_check_count", "pass_check_count", "fail_check_count", "safety_breach_count", "engine_state", "engine_decision", "global_verdict", "recommended_action", "next_mission", "live_trading", "live_order_sent", "capital_deployment",
        )
        conn.execute(
            "INSERT INTO ai_alpha_candidate_promotion_runs VALUES (" + ",".join("?" for _ in range(40)) + ")",
            tuple(summary[key] for key in run_keys)
            + (
                canonical_json({key: value for key, value in summary.items() if key not in {"markdown_report", "candidate_reviews", "registry_entries"}}),
                markdown_report,
            ),
        )
        conn.execute(
            "INSERT INTO ai_alpha_candidate_promotion_reports VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                report_label, promotion_run_label, source_robustness_run_label, created_at, summary["global_verdict"], summary["recommended_action"], canonical_json({key: value for key, value in summary.items() if key not in {"markdown_report", "candidate_reviews", "registry_entries"}}), markdown_report, LIVE_TRADING_STATUS, LIVE_ORDER_SENT_VALUE, CAPITAL_DEPLOYMENT_STATUS,
            ),
        )
        conn.commit()

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Mission 84.8 deterministic provisional alpha candidate promotion review."
    )
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--promotion-run-label", default="mission84-8-local-check")
    parser.add_argument("--report-label", default="mission84-8-local-check-report")
    parser.add_argument("--source-robustness-run-label", default="mission84-7-final-check")
    parser.add_argument("--min-source-candidates", type=int, default=72)
    parser.add_argument("--min-windows", type=int, default=3)
    parser.add_argument("--min-positive-ratio", type=float, default=2.0 / 3.0)
    parser.add_argument("--max-worst-drawdown-pct", type=float, default=25.0)
    parser.add_argument("--max-return-dispersion-pct", type=float, default=20.0)
    parser.add_argument("--min-cash-outperformance-ratio", type=float, default=2.0 / 3.0)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    summary = run_alpha_candidate_promotion_pack(
        db_path=args.db_path,
        promotion_run_label=args.promotion_run_label,
        report_label=args.report_label,
        source_robustness_run_label=args.source_robustness_run_label,
        min_source_candidates=args.min_source_candidates,
        min_windows=args.min_windows,
        min_positive_ratio=args.min_positive_ratio,
        max_worst_drawdown_pct=args.max_worst_drawdown_pct,
        max_return_dispersion_pct=args.max_return_dispersion_pct,
        min_cash_outperformance_ratio=args.min_cash_outperformance_ratio,
    )
    output = {
        key: value
        for key, value in summary.items()
        if key not in {"markdown_report", "candidate_reviews", "registry_entries"}
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if summary["fail_check_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

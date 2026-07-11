import json
import sqlite3
from pathlib import Path

import pytest

from offchain.ai_dataset.alpha_candidate_promotion_pack import (
    ENGINE_DECISION,
    ENGINE_STATE,
    GLOBAL_VERDICT,
    HELD_STATUS,
    MISSION85_STATUS,
    NEXT_MISSION,
    PROVISIONAL_STATUS,
    SOURCE_BLOCKED_STATUS,
    SOURCE_ROBUST_STATUS,
    build_parser,
    build_registry_entry,
    ensure_schema,
    inherited_safety_actions_valid,
    review_candidate,
    run_alpha_candidate_promotion_pack,
)


ACTIONS = {
    "model_training_action": "NO_MODEL_TRAINING",
    "model_artifact_action": "NO_MODEL_ARTIFACT",
    "model_promotion_action": "NO_MODEL_PROMOTION",
    "strategy_reweighting_action": "NO_STRATEGY_REWEIGHTING",
    "live_signal_action": "NO_LIVE_SIGNAL",
    "exchange_order_action": "NO_EXCHANGE_ORDER",
    "capital_action": "NO_CAPITAL_DEPLOYMENT",
    "paid_api_action": "NO_PAID_API",
    "profitability_claim_action": "NO_PROFITABILITY_CLAIM",
    "live_trading": "DISABLED",
    "live_order_sent": 0,
    "capital_deployment": "BLOCKED",
}


def candidate(result_id="r1", status=SOURCE_ROBUST_STATUS, **overrides):
    row = {
        "robustness_result_id": result_id,
        "robustness_run_label": "mission84-7-final-check",
        "strategy_family_code": "TIME_SERIES_MOMENTUM",
        "asset_group": "CRYPTO",
        "timeframe": "1D",
        "cost_model_code": "CRYPTO_PAPER_CONSERVATIVE",
        "window_count": 3,
        "positive_window_ratio": "0.66666667",
        "median_net_return_pct": "1.25000000",
        "return_dispersion_pct": "2.00000000",
        "worst_window_drawdown_pct": "8.00000000",
        "outperformed_cash_window_count": 2,
        "robustness_status": status,
        **ACTIONS,
    }
    row.update(overrides)
    return row


def create_source_tables(db_path: Path, rows):
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE ai_walk_forward_robustness_runs (
                robustness_run_label TEXT PRIMARY KEY,
                engine_state TEXT,
                engine_decision TEXT,
                global_verdict TEXT,
                mission85_status TEXT,
                evaluated_candidate_count INTEGER,
                robust_candidate_count INTEGER,
                blocked_candidate_count INTEGER,
                model_training_count INTEGER,
                model_artifact_count INTEGER,
                model_promotion_count INTEGER,
                strategy_reweighting_count INTEGER,
                live_signal_count INTEGER,
                exchange_order_count INTEGER,
                capital_deployment_count INTEGER,
                paid_api_count INTEGER,
                private_key_use_count INTEGER,
                profitability_claim_count INTEGER,
                fail_check_count INTEGER,
                safety_breach_count INTEGER
            );

            CREATE TABLE ai_walk_forward_robustness_results (
                robustness_result_id TEXT PRIMARY KEY,
                robustness_run_label TEXT,
                strategy_family_code TEXT,
                asset_group TEXT,
                timeframe TEXT,
                cost_model_code TEXT,
                window_count INTEGER,
                positive_window_ratio TEXT,
                median_net_return_pct TEXT,
                return_dispersion_pct TEXT,
                worst_window_drawdown_pct TEXT,
                outperformed_cash_window_count INTEGER,
                robustness_status TEXT,
                model_training_action TEXT,
                model_artifact_action TEXT,
                model_promotion_action TEXT,
                strategy_reweighting_action TEXT,
                live_signal_action TEXT,
                exchange_order_action TEXT,
                capital_action TEXT,
                paid_api_action TEXT,
                profitability_claim_action TEXT,
                live_trading TEXT,
                live_order_sent INTEGER,
                capital_deployment TEXT
            );
            """
        )
        robust = sum(row["robustness_status"] == SOURCE_ROBUST_STATUS for row in rows)
        blocked = sum(row["robustness_status"] == SOURCE_BLOCKED_STATUS for row in rows)
        conn.execute(
            "INSERT INTO ai_walk_forward_robustness_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "mission84-7-final-check",
                "AI_WALK_FORWARD_ROBUSTNESS_GATE_READY_LOCAL_ONLY",
                "AI_WALK_FORWARD_ROBUSTNESS_GATE_APPROVED_FOR_ALPHA_CANDIDATE_PROMOTION_REVIEW",
                "AI_WALK_FORWARD_ROBUSTNESS_GATE_READY_SHADOW_RESEARCH_ONLY",
                MISSION85_STATUS,
                len(rows),
                robust,
                blocked,
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            ),
        )
        columns = (
            "robustness_result_id", "robustness_run_label", "strategy_family_code",
            "asset_group", "timeframe", "cost_model_code", "window_count",
            "positive_window_ratio", "median_net_return_pct", "return_dispersion_pct",
            "worst_window_drawdown_pct", "outperformed_cash_window_count",
            "robustness_status", "model_training_action", "model_artifact_action",
            "model_promotion_action", "strategy_reweighting_action", "live_signal_action",
            "exchange_order_action", "capital_action", "paid_api_action",
            "profitability_claim_action", "live_trading", "live_order_sent",
            "capital_deployment",
        )
        for row in rows:
            conn.execute(
                "INSERT INTO ai_walk_forward_robustness_results VALUES (" + ",".join("?" for _ in columns) + ")",
                tuple(row[column] for column in columns),
            )
        conn.commit()


def test_ensure_schema_creates_all_tables(tmp_path):
    db = tmp_path / "schema.db"
    ensure_schema(db)
    with sqlite3.connect(db) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "ai_alpha_candidate_promotion_runs",
        "ai_alpha_candidate_reviews",
        "ai_alpha_candidate_registry",
        "ai_alpha_candidate_promotion_checks",
        "ai_alpha_candidate_promotion_reports",
    } <= tables


def test_inherited_safety_actions_accepts_locked_candidate():
    assert inherited_safety_actions_valid(candidate())


def test_inherited_safety_actions_rejects_live_signal_action():
    assert not inherited_safety_actions_valid(candidate(live_signal_action="EMIT_LIVE_SIGNAL"))


def test_robust_candidate_becomes_provisional():
    review = review_candidate(candidate(), "run", "source", "2026-07-11T00:00:00+00:00")
    assert review["registry_eligible"] == 1
    assert review["review_status"] == PROVISIONAL_STATUS
    assert review["review_reasons"] == []


def test_blocked_source_candidate_is_held():
    review = review_candidate(
        candidate(status=SOURCE_BLOCKED_STATUS), "run", "source", "2026-07-11T00:00:00+00:00"
    )
    assert review["registry_eligible"] == 0
    assert review["review_status"] == HELD_STATUS
    assert "SOURCE_NOT_ROBUST_FIXTURE_CANDIDATE" in review["review_reasons"]


def test_extra_evidence_failure_holds_candidate():
    review = review_candidate(
        candidate(median_net_return_pct="0.00000000"),
        "run", "source", "2026-07-11T00:00:00+00:00",
    )
    assert review["registry_eligible"] == 0
    assert "NON_POSITIVE_MEDIAN_RETURN" in review["review_reasons"]


def test_registry_builder_rejects_ineligible_review():
    review = review_candidate(
        candidate(status=SOURCE_BLOCKED_STATUS), "run", "source", "2026-07-11T00:00:00+00:00"
    )
    with pytest.raises(ValueError):
        build_registry_entry(review)


def test_run_reviews_and_registers_only_eligible_candidates(tmp_path):
    db = tmp_path / "integration.db"
    rows = [candidate("r1"), candidate("r2", status=SOURCE_BLOCKED_STATUS)]
    create_source_tables(db, rows)
    summary = run_alpha_candidate_promotion_pack(
        db_path=db,
        promotion_run_label="mission84-8-test",
        report_label="mission84-8-test-report",
        min_source_candidates=2,
    )
    assert summary["source_candidate_count"] == 2
    assert summary["reviewed_candidate_count"] == 2
    assert summary["provisional_candidate_count"] == 1
    assert summary["held_candidate_count"] == 1
    assert summary["fail_check_count"] == 0
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ai_alpha_candidate_reviews").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM ai_alpha_candidate_registry").fetchone()[0] == 1


def test_run_is_idempotent_for_same_labels(tmp_path):
    db = tmp_path / "idempotent.db"
    create_source_tables(db, [candidate("r1")])
    kwargs = dict(
        db_path=db,
        promotion_run_label="mission84-8-repeat",
        report_label="mission84-8-repeat-report",
        min_source_candidates=1,
    )
    run_alpha_candidate_promotion_pack(**kwargs)
    run_alpha_candidate_promotion_pack(**kwargs)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM ai_alpha_candidate_promotion_runs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM ai_alpha_candidate_reviews").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM ai_alpha_candidate_registry").fetchone()[0] == 1


def test_missing_source_fails_closed(tmp_path):
    db = tmp_path / "missing.db"
    summary = run_alpha_candidate_promotion_pack(
        db_path=db,
        promotion_run_label="mission84-8-missing",
        report_label="mission84-8-missing-report",
        min_source_candidates=1,
    )
    assert summary["reviewed_candidate_count"] == 0
    assert summary["provisional_candidate_count"] == 0
    assert summary["fail_check_count"] > 0
    assert summary["engine_state"] == "AI_ALPHA_CANDIDATE_PROMOTION_PACK_BLOCKED"


def test_ready_summary_preserves_safety_and_next_mission(tmp_path):
    db = tmp_path / "summary.db"
    create_source_tables(db, [candidate("r1")])
    summary = run_alpha_candidate_promotion_pack(
        db_path=db,
        promotion_run_label="mission84-8-summary",
        report_label="mission84-8-summary-report",
        min_source_candidates=1,
    )
    assert summary["engine_state"] == ENGINE_STATE
    assert summary["engine_decision"] == ENGINE_DECISION
    assert summary["global_verdict"] == GLOBAL_VERDICT
    assert summary["next_mission"] == NEXT_MISSION
    assert summary["mission85_status"] == MISSION85_STATUS
    for field in (
        "model_training_count", "model_artifact_count", "model_promotion_count",
        "strategy_reweighting_count", "live_signal_count", "exchange_order_count",
        "capital_deployment_count", "paid_api_count", "private_key_use_count",
        "profitability_claim_count", "safety_breach_count",
    ):
        assert summary[field] == 0


def test_parser_defaults_preserve_expected_source_and_coverage():
    args = build_parser().parse_args([])
    assert args.source_robustness_run_label == "mission84-7-final-check"
    assert args.min_source_candidates == 72
    assert args.min_windows == 3

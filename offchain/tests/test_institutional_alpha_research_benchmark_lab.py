import sqlite3

from offchain.ai_dataset.institutional_alpha_research_benchmark_lab import (
    ENGINE_DECISION_BLOCK_SAFETY,
    ENGINE_DECISION_READY,
    ENGINE_DECISION_REJECT_MISSING,
    ENGINE_DECISION_UNSTABLE,
    MISSION85_STATUS,
    VERDICT_BLOCKED,
    VERDICT_MISSING,
    VERDICT_READY,
    VERDICT_UNSTABLE,
    parse_labels,
    run_institutional_alpha_research_benchmark_lab,
)


def create_source_table(conn):
    conn.execute(
        """
        CREATE TABLE ai_offline_model_training_harness_runs (
            training_run_label TEXT PRIMARY KEY,
            source_feedback_run_label TEXT,
            source_execution_run_label TEXT,
            source_signal_run_label TEXT,
            source_policy_run_label TEXT,
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
            training_candidate_count INTEGER,
            training_ready_candidate_count INTEGER,
            training_blocked_candidate_count INTEGER,
            actual_model_training_count INTEGER,
            model_artifact_count INTEGER,
            fail_check_count INTEGER,
            safety_breach_count INTEGER,
            leakage_breach_count INTEGER,
            baseline_accuracy_pct TEXT,
            average_label_confidence TEXT,
            average_net_paper_outcome_bps TEXT,
            engine_state TEXT,
            engine_decision TEXT,
            global_verdict TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )


def insert_source_run(
    conn,
    label="training-1",
    engine_state="AI_OFFLINE_MODEL_TRAINING_HARNESS_READY_LOCAL_ONLY",
    engine_decision="AI_OFFLINE_MODEL_TRAINING_HARNESS_APPROVED_FOR_MODEL_PROMOTION_ENGINE_REVIEW",
    verdict="AI_OFFLINE_MODEL_TRAINING_HARNESS_READY_SHADOW_ONLY",
    training_candidate_count=5,
    ready_candidate_count=0,
    blocked_candidate_count=5,
    actual_training_count=0,
    artifact_count=0,
    fail_check_count=0,
    safety_breach_count=0,
    leakage_breach_count=0,
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO ai_offline_model_training_harness_runs (
            training_run_label, source_feedback_run_label, source_execution_run_label,
            source_signal_run_label, source_policy_run_label,
            source_recommendation_run_label, source_governance_review_label,
            source_evaluation_label, source_guard_review_label,
            source_collection_label, source_registry_label, source_build_label,
            source_schedule_label, source_learning_run_label,
            source_multi_cycle_track_label, source_session_label,
            source_portfolio_label, training_candidate_count,
            training_ready_candidate_count, training_blocked_candidate_count,
            actual_model_training_count, model_artifact_count, fail_check_count,
            safety_breach_count, leakage_breach_count, baseline_accuracy_pct,
            average_label_confidence, average_net_paper_outcome_bps,
            engine_state, engine_decision, global_verdict,
            live_trading, live_order_sent, capital_deployment
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            label,
            "feedback-1",
            "execution-1",
            "signal-1",
            "policy-1",
            "rec-1",
            "gov-1",
            "eval-1",
            "guard-1",
            "collection-1",
            "registry-1",
            "build-1",
            "schedule-1",
            "learning-1",
            "track-1",
            "session-1",
            "portfolio-1",
            training_candidate_count,
            ready_candidate_count,
            blocked_candidate_count,
            actual_training_count,
            artifact_count,
            fail_check_count,
            safety_breach_count,
            leakage_breach_count,
            "100.0",
            "0.65",
            "-2.0",
            engine_state,
            engine_decision,
            verdict,
            live_trading,
            live_order_sent,
            capital_deployment,
        ),
    )


def seed_good(conn):
    create_source_table(conn)
    insert_source_run(conn)


def test_parse_labels_deduplicates():
    assert parse_labels("training-1,training-2,training-1") == ["training-1", "training-2"]


def test_alpha_benchmark_lab_registers_varied_research_plan_and_persists(tmp_path):
    db_path = tmp_path / "mission84_5.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_institutional_alpha_research_benchmark_lab(
        db_path=db_path,
        benchmark_run_label="benchmark-1",
        report_label="report-1",
        training_run_label="training-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_READY
    assert result["global_verdict"] == VERDICT_READY
    assert result["mission85_status"] == MISSION85_STATUS
    assert result["strategy_family_count"] == 8
    assert result["asset_count"] == 21
    assert result["asset_group_count"] == 3
    assert result["timeframe_count"] == 3
    assert result["cost_model_count"] == 3
    assert result["benchmark_plan_entry_count"] == 72
    assert result["actual_backtest_count"] == 0
    assert result["model_training_count"] == 0
    assert result["model_artifact_count"] == 0
    assert result["model_promotion_count"] == 0
    assert result["no_live_signal_count"] == 72
    assert result["no_exchange_order_count"] == 72
    assert result["no_capital_deployment_count"] == 72
    assert result["benchmark_check_count"] == 27
    assert result["pass_check_count"] == 27
    assert result["fail_check_count"] == 0
    assert result["next_mission"] == "Mission 84.6 Multi-Strategy Backtest Pack"

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT benchmark_run_label, engine_decision, global_verdict
            FROM ai_institutional_alpha_benchmark_runs
            WHERE benchmark_run_label = ?
            """,
            ("benchmark-1",),
        ).fetchone()

    assert row == ("benchmark-1", ENGINE_DECISION_READY, VERDICT_READY)


def test_alpha_benchmark_lab_rejects_missing_training_harness(tmp_path):
    result = run_institutional_alpha_research_benchmark_lab(
        db_path=tmp_path / "missing.db",
        benchmark_run_label="missing-benchmark",
        report_label="missing-report",
        training_run_label="missing-training",
    )

    assert result["engine_decision"] == ENGINE_DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["fail_check_count"] == 1


def test_alpha_benchmark_lab_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "safety.db"
    with sqlite3.connect(db_path) as conn:
        create_source_table(conn)
        insert_source_run(conn, safety_breach_count=1, live_trading="ENABLED")
        conn.commit()

    result = run_institutional_alpha_research_benchmark_lab(
        db_path=db_path,
        benchmark_run_label="safety-benchmark",
        report_label="safety-report",
        training_run_label="training-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED


def test_alpha_benchmark_lab_flags_unapproved_training_harness(tmp_path):
    db_path = tmp_path / "unapproved.db"
    with sqlite3.connect(db_path) as conn:
        create_source_table(conn)
        insert_source_run(
            conn,
            engine_state="AI_OFFLINE_MODEL_TRAINING_HARNESS_UNSTABLE",
            engine_decision="AI_OFFLINE_MODEL_TRAINING_HARNESS_REVIEW_REQUIRED",
            verdict="AI_OFFLINE_MODEL_TRAINING_HARNESS_UNSTABLE_SHADOW_ONLY",
        )
        conn.commit()

    result = run_institutional_alpha_research_benchmark_lab(
        db_path=db_path,
        benchmark_run_label="unapproved-benchmark",
        report_label="unapproved-report",
        training_run_label="training-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE


def test_alpha_benchmark_lab_flags_source_failed_checks(tmp_path):
    db_path = tmp_path / "failed-checks.db"
    with sqlite3.connect(db_path) as conn:
        create_source_table(conn)
        insert_source_run(conn, fail_check_count=1)
        conn.commit()

    result = run_institutional_alpha_research_benchmark_lab(
        db_path=db_path,
        benchmark_run_label="failed-benchmark",
        report_label="failed-report",
        training_run_label="training-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["source_fail_check_count"] == 1


def test_alpha_benchmark_lab_flags_leakage_breach(tmp_path):
    db_path = tmp_path / "leakage.db"
    with sqlite3.connect(db_path) as conn:
        create_source_table(conn)
        insert_source_run(conn, leakage_breach_count=1)
        conn.commit()

    result = run_institutional_alpha_research_benchmark_lab(
        db_path=db_path,
        benchmark_run_label="leakage-benchmark",
        report_label="leakage-report",
        training_run_label="training-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["leakage_breach_count"] == 1


def test_alpha_benchmark_lab_flags_unlocked_source_candidates(tmp_path):
    db_path = tmp_path / "unlocked-source.db"
    with sqlite3.connect(db_path) as conn:
        create_source_table(conn)
        insert_source_run(conn, ready_candidate_count=1, blocked_candidate_count=4)
        conn.commit()

    result = run_institutional_alpha_research_benchmark_lab(
        db_path=db_path,
        benchmark_run_label="unlocked-benchmark",
        report_label="unlocked-report",
        training_run_label="training-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["source_training_ready_candidate_count"] == 1


def test_alpha_benchmark_lab_flags_too_high_plan_requirement(tmp_path):
    db_path = tmp_path / "high-min.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_institutional_alpha_research_benchmark_lab(
        db_path=db_path,
        benchmark_run_label="high-min-benchmark",
        report_label="high-min-report",
        training_run_label="training-1",
        min_plan_entries=100,
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["benchmark_plan_entry_count"] == 72


def test_alpha_benchmark_lab_registry_contains_required_strategy_families_and_assets(tmp_path):
    db_path = tmp_path / "registry.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_institutional_alpha_research_benchmark_lab(
        db_path=db_path,
        benchmark_run_label="registry-benchmark",
        report_label="registry-report",
        training_run_label="training-1",
    )

    strategies = {row["strategy_family_code"] for row in result["strategy_families"]}
    assets = {row["symbol"] for row in result["asset_universe"]}
    cost_models = {row["asset_group"] for row in result["cost_models"]}

    assert "TIME_SERIES_MOMENTUM" in strategies
    assert "PAIRS_STAT_ARB_RESIDUAL" in strategies
    assert "FUNDING_BASIS_CARRY" in strategies
    assert "HYBRID_ENSEMBLE" in strategies
    assert {"BTC", "ETH", "EURUSD", "USDJPY", "SPY", "QQQ", "TLT", "GLD"}.issubset(assets)
    assert cost_models == {"CRYPTO", "FX", "ETF_MACRO"}


def test_markdown_report_documents_mission85_pause_and_no_backtests(tmp_path):
    db_path = tmp_path / "markdown.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_institutional_alpha_research_benchmark_lab(
        db_path=db_path,
        benchmark_run_label="markdown-benchmark",
        report_label="markdown-report",
        training_run_label="training-1",
    )

    assert "# DeltaGrid Mission 84.5" in result["markdown_report"]
    assert "Mission 85 remains paused" in result["markdown_report"]
    assert "does not run backtests" in result["markdown_report"]
    assert "does not train models" in result["markdown_report"]
    assert "does not promote models" in result["markdown_report"]
    assert "Benchmark plans are not profitability evidence" in result["markdown_report"]

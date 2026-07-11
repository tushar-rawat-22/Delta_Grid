import sqlite3

from offchain.ai_dataset.offline_model_training_harness import (
    ENGINE_DECISION_BLOCK_SAFETY,
    ENGINE_DECISION_READY,
    ENGINE_DECISION_REJECT_MISSING,
    ENGINE_DECISION_UNSTABLE,
    VERDICT_BLOCKED,
    VERDICT_MISSING,
    VERDICT_READY,
    VERDICT_UNSTABLE,
    parse_labels,
    run_offline_model_training_harness,
)


def create_input_tables(conn):
    conn.execute(
        """
        CREATE TABLE ai_self_learning_feedback_runs (
            feedback_run_label TEXT PRIMARY KEY,
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
            feedback_item_count INTEGER,
            recorded_feedback_count INTEGER,
            blocked_feedback_count INTEGER,
            feedback_only_count INTEGER,
            no_model_training_count INTEGER,
            no_strategy_reweighting_count INTEGER,
            no_live_signal_count INTEGER,
            no_exchange_order_count INTEGER,
            no_capital_deployment_count INTEGER,
            no_profitability_claim_count INTEGER,
            feedback_check_count INTEGER,
            pass_check_count INTEGER,
            fail_check_count INTEGER,
            safety_breach_count INTEGER,
            leakage_breach_count INTEGER,
            training_eligible_count INTEGER,
            training_locked_count INTEGER,
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

    conn.execute(
        """
        CREATE TABLE ai_self_learning_feedback_items (
            feedback_item_id TEXT PRIMARY KEY,
            feedback_run_label TEXT,
            source_paper_signal_code TEXT,
            feedback_rank INTEGER,
            feedback_status TEXT,
            paper_outcome_quality TEXT,
            model_training_action TEXT,
            strategy_reweighting_action TEXT,
            live_signal_action TEXT,
            exchange_order_action TEXT,
            capital_action TEXT,
            not_profitability_claim INTEGER,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_self_learning_feedback_checks (
            check_id TEXT PRIMARY KEY,
            feedback_run_label TEXT,
            check_status TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )


def insert_feedback_run(
    conn,
    label="feedback-1",
    engine_state="AI_SELF_LEARNING_FEEDBACK_LOOP_READY_PAPER_ONLY",
    engine_decision="AI_SELF_LEARNING_FEEDBACK_LOOP_APPROVED_FOR_OFFLINE_MODEL_TRAINING_HARNESS",
    verdict="AI_SELF_LEARNING_FEEDBACK_LOOP_READY_SHADOW_ONLY",
    feedback_item_count=5,
    recorded_feedback_count=5,
    blocked_feedback_count=0,
    feedback_only_count=5,
    no_model_training_count=5,
    no_strategy_reweighting_count=5,
    no_live_signal_count=5,
    no_exchange_order_count=5,
    no_capital_count=5,
    no_profitability_count=5,
    fail_check_count=0,
    safety_breach_count=0,
    leakage_breach_count=0,
    training_eligible_count=0,
    training_locked_count=4,
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO ai_self_learning_feedback_runs (
            feedback_run_label, source_execution_run_label, source_signal_run_label,
            source_policy_run_label, source_recommendation_run_label,
            source_governance_review_label, source_evaluation_label,
            source_guard_review_label, source_collection_label, source_registry_label,
            source_build_label, source_schedule_label, source_learning_run_label,
            source_multi_cycle_track_label, source_session_label, source_portfolio_label,
            feedback_item_count, recorded_feedback_count, blocked_feedback_count,
            feedback_only_count, no_model_training_count, no_strategy_reweighting_count,
            no_live_signal_count, no_exchange_order_count, no_capital_deployment_count,
            no_profitability_claim_count, feedback_check_count, pass_check_count,
            fail_check_count, safety_breach_count, leakage_breach_count,
            training_eligible_count, training_locked_count, baseline_accuracy_pct,
            average_label_confidence, average_net_paper_outcome_bps,
            engine_state, engine_decision, global_verdict, live_trading,
            live_order_sent, capital_deployment
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            label,
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
            feedback_item_count,
            recorded_feedback_count,
            blocked_feedback_count,
            feedback_only_count,
            no_model_training_count,
            no_strategy_reweighting_count,
            no_live_signal_count,
            no_exchange_order_count,
            no_capital_count,
            no_profitability_count,
            19,
            19 - fail_check_count,
            fail_check_count,
            safety_breach_count,
            leakage_breach_count,
            training_eligible_count,
            training_locked_count,
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


def insert_feedback_items(conn, label="feedback-1", count=5, quality="INSUFFICIENT_FOR_TRAINING"):
    for index in range(1, count + 1):
        conn.execute(
            """
            INSERT INTO ai_self_learning_feedback_items (
                feedback_item_id, feedback_run_label, source_paper_signal_code,
                feedback_rank, feedback_status, paper_outcome_quality,
                model_training_action, strategy_reweighting_action,
                live_signal_action, exchange_order_action, capital_action,
                not_profitability_claim, live_trading, live_order_sent,
                capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{label}-feedback-item-{index}",
                label,
                f"PAPER_ONLY_RECOMMENDATION_{index}",
                index,
                "AI_SELF_LEARNING_FEEDBACK_RECORDED_PAPER_ONLY",
                quality,
                "KEEP_MODEL_TRAINING_DISABLED",
                "NO_STRATEGY_REWEIGHTING",
                "NO_LIVE_SIGNAL",
                "NO_EXCHANGE_ORDER",
                "NO_CAPITAL_DEPLOYMENT",
                1,
                "DISABLED",
                0,
                "BLOCKED",
            ),
        )


def insert_feedback_checks(conn, label="feedback-1", count=19):
    for index in range(1, count + 1):
        conn.execute(
            """
            INSERT INTO ai_self_learning_feedback_checks (
                check_id, feedback_run_label, check_status,
                live_trading, live_order_sent, capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"{label}-check-{index}",
                label,
                "AI_SELF_LEARNING_FEEDBACK_CHECK_PASS",
                "DISABLED",
                0,
                "BLOCKED",
            ),
        )


def seed_good(conn):
    create_input_tables(conn)
    insert_feedback_run(conn)
    insert_feedback_items(conn)
    insert_feedback_checks(conn)


def test_parse_labels_deduplicates():
    assert parse_labels("feedback-1,feedback-2,feedback-1") == ["feedback-1", "feedback-2"]


def test_training_harness_records_locked_candidates_and_persists(tmp_path):
    db_path = tmp_path / "mission84.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_offline_model_training_harness(
        db_path=db_path,
        training_run_label="training-1",
        report_label="report-1",
        feedback_run_label="feedback-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_READY
    assert result["global_verdict"] == VERDICT_READY
    assert result["training_candidate_count"] == 5
    assert result["training_ready_candidate_count"] == 0
    assert result["training_blocked_candidate_count"] == 5
    assert result["actual_model_training_count"] == 0
    assert result["model_artifact_count"] == 0
    assert result["no_model_deployment_count"] == 5
    assert result["no_live_deployment_count"] == 5
    assert result["no_strategy_reweighting_count"] == 5
    assert result["no_live_signal_count"] == 5
    assert result["no_exchange_order_count"] == 5
    assert result["no_capital_deployment_count"] == 5
    assert result["no_profitability_claim_count"] == 5
    assert result["training_check_count"] == 22
    assert result["pass_check_count"] == 22
    assert result["fail_check_count"] == 0
    assert result["next_mission"] == "Mission 85 Model Promotion Engine"

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT training_run_label, engine_decision, global_verdict
            FROM ai_offline_model_training_harness_runs
            WHERE training_run_label = ?
            """,
            ("training-1",),
        ).fetchone()

    assert row == ("training-1", ENGINE_DECISION_READY, VERDICT_READY)


def test_training_harness_rejects_missing_feedback_run(tmp_path):
    result = run_offline_model_training_harness(
        db_path=tmp_path / "missing.db",
        training_run_label="missing-training",
        report_label="missing-report",
        feedback_run_label="missing-feedback",
    )

    assert result["engine_decision"] == ENGINE_DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["fail_check_count"] == 1


def test_training_harness_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "safety.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_feedback_run(conn, safety_breach_count=1, live_trading="ENABLED")
        insert_feedback_items(conn)
        insert_feedback_checks(conn)
        conn.commit()

    result = run_offline_model_training_harness(
        db_path=db_path,
        training_run_label="safety-training",
        report_label="safety-report",
        feedback_run_label="feedback-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED


def test_training_harness_flags_unapproved_feedback_loop(tmp_path):
    db_path = tmp_path / "unapproved.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_feedback_run(
            conn,
            engine_state="AI_SELF_LEARNING_FEEDBACK_LOOP_UNSTABLE",
            engine_decision="AI_SELF_LEARNING_FEEDBACK_LOOP_REVIEW_REQUIRED",
            verdict="AI_SELF_LEARNING_FEEDBACK_LOOP_UNSTABLE_SHADOW_ONLY",
        )
        insert_feedback_items(conn)
        insert_feedback_checks(conn)
        conn.commit()

    result = run_offline_model_training_harness(
        db_path=db_path,
        training_run_label="unapproved-training",
        report_label="unapproved-report",
        feedback_run_label="feedback-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["training_candidate_count"] == 0


def test_training_harness_flags_source_failed_checks(tmp_path):
    db_path = tmp_path / "failed-checks.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_feedback_run(conn, fail_check_count=1)
        insert_feedback_items(conn)
        insert_feedback_checks(conn)
        conn.commit()

    result = run_offline_model_training_harness(
        db_path=db_path,
        training_run_label="failed-training",
        report_label="failed-report",
        feedback_run_label="feedback-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["source_fail_check_count"] == 1


def test_training_harness_flags_leakage_breach(tmp_path):
    db_path = tmp_path / "leakage.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_feedback_run(conn, leakage_breach_count=1)
        insert_feedback_items(conn)
        insert_feedback_checks(conn)
        conn.commit()

    result = run_offline_model_training_harness(
        db_path=db_path,
        training_run_label="leakage-training",
        report_label="leakage-report",
        feedback_run_label="feedback-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["leakage_breach_count"] == 1


def test_training_harness_flags_missing_feedback_items(tmp_path):
    db_path = tmp_path / "missing-items.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_feedback_run(conn)
        insert_feedback_checks(conn)
        conn.commit()

    result = run_offline_model_training_harness(
        db_path=db_path,
        training_run_label="missing-items-training",
        report_label="missing-items-report",
        feedback_run_label="feedback-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["training_candidate_count"] == 0


def test_training_harness_flags_unexpected_training_ready_data(tmp_path):
    db_path = tmp_path / "ready-data.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_feedback_run(conn)
        insert_feedback_items(conn, quality="SUFFICIENT_FOR_OFFLINE_TRAINING")
        insert_feedback_checks(conn)
        conn.commit()

    result = run_offline_model_training_harness(
        db_path=db_path,
        training_run_label="ready-data-training",
        report_label="ready-data-report",
        feedback_run_label="feedback-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["training_ready_candidate_count"] == 5
    assert result["training_blocked_candidate_count"] == 0


def test_markdown_report_documents_no_actual_training(tmp_path):
    db_path = tmp_path / "markdown.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_offline_model_training_harness(
        db_path=db_path,
        training_run_label="markdown-training",
        report_label="markdown-report",
        feedback_run_label="feedback-1",
    )

    assert "# DeltaGrid Mission 84" in result["markdown_report"]
    assert "offline training candidate records only" in result["markdown_report"]
    assert "does not run actual model training" in result["markdown_report"]
    assert "does not create model artifacts" in result["markdown_report"]
    assert "does not deploy models" in result["markdown_report"]
    assert "Training harness records are not profitability evidence" in result["markdown_report"]

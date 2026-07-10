import sqlite3

from offchain.ai_dataset.self_learning_feedback_loop import (
    ENGINE_DECISION_BLOCK_SAFETY,
    ENGINE_DECISION_READY,
    ENGINE_DECISION_REJECT_MISSING,
    ENGINE_DECISION_UNSTABLE,
    VERDICT_BLOCKED,
    VERDICT_MISSING,
    VERDICT_READY,
    VERDICT_UNSTABLE,
    parse_labels,
    run_self_learning_feedback_loop,
)


def create_input_tables(conn):
    conn.execute(
        """
        CREATE TABLE ai_paper_execution_agent_runs (
            execution_run_label TEXT PRIMARY KEY,
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
            paper_execution_count INTEGER,
            recorded_execution_count INTEGER,
            blocked_execution_count INTEGER,
            paper_only_execution_count INTEGER,
            no_live_signal_count INTEGER,
            no_exchange_order_count INTEGER,
            no_capital_deployment_count INTEGER,
            no_model_training_count INTEGER,
            zero_quantity_execution_count INTEGER,
            zero_notional_execution_count INTEGER,
            execution_check_count INTEGER,
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
        CREATE TABLE ai_paper_execution_records (
            paper_execution_id TEXT PRIMARY KEY,
            execution_run_label TEXT,
            source_paper_signal_code TEXT,
            execution_rank INTEGER,
            paper_execution_status TEXT,
            exchange_order_action TEXT,
            capital_action TEXT,
            live_signal_action TEXT,
            filled_quantity TEXT,
            paper_notional_value TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_paper_execution_agent_checks (
            check_id TEXT PRIMARY KEY,
            execution_run_label TEXT,
            check_status TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )


def insert_execution_run(
    conn,
    label="execution-1",
    engine_state="AI_PAPER_EXECUTION_AGENT_READY_PAPER_ONLY",
    engine_decision="AI_PAPER_EXECUTION_AGENT_APPROVED_FOR_SELF_LEARNING_FEEDBACK_LOOP",
    verdict="AI_PAPER_EXECUTION_AGENT_READY_SHADOW_ONLY",
    paper_execution_count=5,
    recorded_execution_count=5,
    blocked_execution_count=0,
    paper_only_execution_count=5,
    no_live_signal_count=5,
    no_exchange_order_count=5,
    no_capital_count=5,
    no_model_training_count=5,
    zero_quantity_count=5,
    zero_notional_count=5,
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
        INSERT INTO ai_paper_execution_agent_runs (
            execution_run_label, source_signal_run_label, source_policy_run_label,
            source_recommendation_run_label, source_governance_review_label,
            source_evaluation_label, source_guard_review_label, source_collection_label,
            source_registry_label, source_build_label, source_schedule_label,
            source_learning_run_label, source_multi_cycle_track_label, source_session_label,
            source_portfolio_label, paper_execution_count, recorded_execution_count,
            blocked_execution_count, paper_only_execution_count, no_live_signal_count,
            no_exchange_order_count, no_capital_deployment_count,
            no_model_training_count, zero_quantity_execution_count,
            zero_notional_execution_count, execution_check_count, pass_check_count,
            fail_check_count, safety_breach_count, leakage_breach_count,
            training_eligible_count, training_locked_count, baseline_accuracy_pct,
            average_label_confidence, average_net_paper_outcome_bps,
            engine_state, engine_decision, global_verdict, live_trading,
            live_order_sent, capital_deployment
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            label,
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
            paper_execution_count,
            recorded_execution_count,
            blocked_execution_count,
            paper_only_execution_count,
            no_live_signal_count,
            no_exchange_order_count,
            no_capital_count,
            no_model_training_count,
            zero_quantity_count,
            zero_notional_count,
            18,
            18 - fail_check_count,
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


def insert_execution_records(conn, label="execution-1", count=5):
    for index in range(1, count + 1):
        conn.execute(
            """
            INSERT INTO ai_paper_execution_records (
                paper_execution_id, execution_run_label, source_paper_signal_code,
                execution_rank, paper_execution_status, exchange_order_action,
                capital_action, live_signal_action, filled_quantity,
                paper_notional_value, live_trading, live_order_sent,
                capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{label}-paper-execution-{index}",
                label,
                f"PAPER_ONLY_RECOMMENDATION_{index}",
                index,
                "AI_PAPER_EXECUTION_RECORDED_PAPER_ONLY",
                "NO_EXCHANGE_ORDER",
                "NO_CAPITAL_DEPLOYMENT",
                "NO_LIVE_SIGNAL",
                "0.0",
                "0.0",
                "DISABLED",
                0,
                "BLOCKED",
            ),
        )


def insert_execution_checks(conn, label="execution-1", count=18):
    for index in range(1, count + 1):
        conn.execute(
            """
            INSERT INTO ai_paper_execution_agent_checks (
                check_id, execution_run_label, check_status,
                live_trading, live_order_sent, capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"{label}-check-{index}",
                label,
                "AI_PAPER_EXECUTION_AGENT_CHECK_PASS",
                "DISABLED",
                0,
                "BLOCKED",
            ),
        )


def seed_good(conn):
    create_input_tables(conn)
    insert_execution_run(conn)
    insert_execution_records(conn)
    insert_execution_checks(conn)


def test_parse_labels_deduplicates():
    assert parse_labels("execution-1,execution-2,execution-1") == ["execution-1", "execution-2"]


def test_feedback_loop_records_good_execution_run_and_persists(tmp_path):
    db_path = tmp_path / "mission83.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_self_learning_feedback_loop(
        db_path=db_path,
        feedback_run_label="feedback-1",
        report_label="report-1",
        execution_run_label="execution-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_READY
    assert result["global_verdict"] == VERDICT_READY
    assert result["feedback_item_count"] == 5
    assert result["recorded_feedback_count"] == 5
    assert result["blocked_feedback_count"] == 0
    assert result["feedback_only_count"] == 5
    assert result["no_model_training_count"] == 5
    assert result["no_strategy_reweighting_count"] == 5
    assert result["no_live_signal_count"] == 5
    assert result["no_exchange_order_count"] == 5
    assert result["no_capital_deployment_count"] == 5
    assert result["no_profitability_claim_count"] == 5
    assert result["feedback_check_count"] == 19
    assert result["pass_check_count"] == 19
    assert result["fail_check_count"] == 0
    assert result["next_mission"] == "Mission 84 Offline Model Training Harness"

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT feedback_run_label, engine_decision, global_verdict
            FROM ai_self_learning_feedback_runs
            WHERE feedback_run_label = ?
            """,
            ("feedback-1",),
        ).fetchone()

    assert row == ("feedback-1", ENGINE_DECISION_READY, VERDICT_READY)


def test_feedback_loop_rejects_missing_execution_run(tmp_path):
    result = run_self_learning_feedback_loop(
        db_path=tmp_path / "missing.db",
        feedback_run_label="missing-feedback",
        report_label="missing-report",
        execution_run_label="missing-execution",
    )

    assert result["engine_decision"] == ENGINE_DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["fail_check_count"] == 1


def test_feedback_loop_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "safety.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_execution_run(conn, safety_breach_count=1, live_trading="ENABLED")
        insert_execution_records(conn)
        insert_execution_checks(conn)
        conn.commit()

    result = run_self_learning_feedback_loop(
        db_path=db_path,
        feedback_run_label="safety-feedback",
        report_label="safety-report",
        execution_run_label="execution-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED


def test_feedback_loop_flags_unapproved_execution_agent(tmp_path):
    db_path = tmp_path / "unapproved.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_execution_run(
            conn,
            engine_state="AI_PAPER_EXECUTION_AGENT_UNSTABLE",
            engine_decision="AI_PAPER_EXECUTION_AGENT_REVIEW_REQUIRED",
            verdict="AI_PAPER_EXECUTION_AGENT_UNSTABLE_SHADOW_ONLY",
        )
        insert_execution_records(conn)
        insert_execution_checks(conn)
        conn.commit()

    result = run_self_learning_feedback_loop(
        db_path=db_path,
        feedback_run_label="unapproved-feedback",
        report_label="unapproved-report",
        execution_run_label="execution-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["feedback_item_count"] == 0


def test_feedback_loop_flags_source_failed_checks(tmp_path):
    db_path = tmp_path / "failed-checks.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_execution_run(conn, fail_check_count=1)
        insert_execution_records(conn)
        insert_execution_checks(conn)
        conn.commit()

    result = run_self_learning_feedback_loop(
        db_path=db_path,
        feedback_run_label="failed-checks-feedback",
        report_label="failed-checks-report",
        execution_run_label="execution-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["source_fail_check_count"] == 1


def test_feedback_loop_flags_leakage_breach(tmp_path):
    db_path = tmp_path / "leakage.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_execution_run(conn, leakage_breach_count=1)
        insert_execution_records(conn)
        insert_execution_checks(conn)
        conn.commit()

    result = run_self_learning_feedback_loop(
        db_path=db_path,
        feedback_run_label="leakage-feedback",
        report_label="leakage-report",
        execution_run_label="execution-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["leakage_breach_count"] == 1


def test_feedback_loop_flags_missing_execution_records(tmp_path):
    db_path = tmp_path / "missing-records.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_execution_run(conn)
        insert_execution_checks(conn)
        conn.commit()

    result = run_self_learning_feedback_loop(
        db_path=db_path,
        feedback_run_label="missing-records-feedback",
        report_label="missing-records-report",
        execution_run_label="execution-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["feedback_item_count"] == 0


def test_feedback_loop_flags_nonzero_source_execution(tmp_path):
    db_path = tmp_path / "nonzero.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_execution_run(conn)
        insert_execution_records(conn)
        conn.execute(
            """
            UPDATE ai_paper_execution_records
            SET filled_quantity = ?, paper_notional_value = ?
            WHERE paper_execution_id = ?
            """,
            ("1.0", "100.0", "execution-1-paper-execution-1"),
        )
        insert_execution_checks(conn)
        conn.commit()

    result = run_self_learning_feedback_loop(
        db_path=db_path,
        feedback_run_label="nonzero-feedback",
        report_label="nonzero-report",
        execution_run_label="execution-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["blocked_feedback_count"] == 1


def test_markdown_report_documents_feedback_only_no_training(tmp_path):
    db_path = tmp_path / "markdown.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_self_learning_feedback_loop(
        db_path=db_path,
        feedback_run_label="markdown-feedback",
        report_label="markdown-report",
        execution_run_label="execution-1",
    )

    assert "# DeltaGrid Mission 83" in result["markdown_report"]
    assert "feedback records only" in result["markdown_report"]
    assert "does not train a model" in result["markdown_report"]
    assert "does not reweight strategies" in result["markdown_report"]
    assert "does not create live trading signals" in result["markdown_report"]
    assert "Feedback records are not profitability evidence" in result["markdown_report"]

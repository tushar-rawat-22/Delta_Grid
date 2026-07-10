import sqlite3

from offchain.ai_dataset.paper_execution_agent import (
    ENGINE_DECISION_BLOCK_SAFETY,
    ENGINE_DECISION_READY,
    ENGINE_DECISION_REJECT_MISSING,
    ENGINE_DECISION_UNSTABLE,
    VERDICT_BLOCKED,
    VERDICT_MISSING,
    VERDICT_READY,
    VERDICT_UNSTABLE,
    parse_labels,
    run_paper_execution_agent,
)


def create_input_tables(conn):
    conn.execute(
        """
        CREATE TABLE ai_autonomous_paper_signal_runs (
            signal_run_label TEXT PRIMARY KEY,
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
            paper_signal_count INTEGER,
            ready_signal_count INTEGER,
            blocked_signal_count INTEGER,
            observe_only_signal_count INTEGER,
            no_live_signal_count INTEGER,
            no_execution_count INTEGER,
            no_capital_deployment_count INTEGER,
            training_disabled_count INTEGER,
            signal_check_count INTEGER,
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
        CREATE TABLE ai_autonomous_paper_signals (
            paper_signal_id TEXT PRIMARY KEY,
            signal_run_label TEXT,
            signal_rank INTEGER,
            paper_signal_code TEXT,
            paper_signal_title TEXT,
            paper_signal_status TEXT,
            paper_signal_action TEXT,
            paper_signal_side TEXT,
            model_training_action TEXT,
            live_signal_action TEXT,
            execution_action TEXT,
            capital_action TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_autonomous_paper_signal_checks (
            check_id TEXT PRIMARY KEY,
            signal_run_label TEXT,
            check_status TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )


def insert_signal_run(
    conn,
    label="signal-1",
    engine_state="AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_READY_PAPER_ONLY",
    engine_decision="AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_APPROVED_FOR_PAPER_EXECUTION_AGENT",
    verdict="AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_READY_SHADOW_ONLY",
    paper_signal_count=5,
    ready_signal_count=5,
    blocked_signal_count=0,
    observe_only_signal_count=5,
    no_live_signal_count=5,
    no_execution_count=5,
    no_capital_count=5,
    training_disabled_count=5,
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
        INSERT INTO ai_autonomous_paper_signal_runs (
            signal_run_label, source_policy_run_label, source_recommendation_run_label,
            source_governance_review_label, source_evaluation_label,
            source_guard_review_label, source_collection_label, source_registry_label,
            source_build_label, source_schedule_label, source_learning_run_label,
            source_multi_cycle_track_label, source_session_label, source_portfolio_label,
            paper_signal_count, ready_signal_count, blocked_signal_count,
            observe_only_signal_count, no_live_signal_count, no_execution_count,
            no_capital_deployment_count, training_disabled_count, signal_check_count,
            pass_check_count, fail_check_count, safety_breach_count, leakage_breach_count,
            training_eligible_count, training_locked_count, baseline_accuracy_pct,
            average_label_confidence, average_net_paper_outcome_bps, engine_state,
            engine_decision, global_verdict, live_trading, live_order_sent,
            capital_deployment
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            label,
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
            paper_signal_count,
            ready_signal_count,
            blocked_signal_count,
            observe_only_signal_count,
            no_live_signal_count,
            no_execution_count,
            no_capital_count,
            training_disabled_count,
            16,
            16 - fail_check_count,
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


def insert_paper_signals(conn, label="signal-1", count=5):
    for index in range(1, count + 1):
        conn.execute(
            """
            INSERT INTO ai_autonomous_paper_signals (
                paper_signal_id, signal_run_label, signal_rank, paper_signal_code,
                paper_signal_title, paper_signal_status, paper_signal_action,
                paper_signal_side, model_training_action, live_signal_action,
                execution_action, capital_action, live_trading, live_order_sent,
                capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{label}-paper-signal-{index}",
                label,
                index,
                f"PAPER_ONLY_RECOMMENDATION_{index}",
                f"Paper signal {index}",
                "AI_AUTONOMOUS_PAPER_SIGNAL_READY_PAPER_ONLY",
                "PAPER_OBSERVE_ONLY_NO_ORDER",
                "NO_TRADE",
                "KEEP_MODEL_TRAINING_DISABLED",
                "NO_LIVE_SIGNAL",
                "NO_EXECUTION",
                "NO_CAPITAL_DEPLOYMENT",
                "DISABLED",
                0,
                "BLOCKED",
            ),
        )


def insert_signal_checks(conn, label="signal-1", count=16):
    for index in range(1, count + 1):
        conn.execute(
            """
            INSERT INTO ai_autonomous_paper_signal_checks (
                check_id, signal_run_label, check_status,
                live_trading, live_order_sent, capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"{label}-check-{index}",
                label,
                "AI_AUTONOMOUS_PAPER_SIGNAL_CHECK_PASS",
                "DISABLED",
                0,
                "BLOCKED",
            ),
        )


def seed_good(conn):
    create_input_tables(conn)
    insert_signal_run(conn)
    insert_paper_signals(conn)
    insert_signal_checks(conn)


def test_parse_labels_deduplicates():
    assert parse_labels("signal-1,signal-2,signal-1") == ["signal-1", "signal-2"]


def test_paper_execution_agent_records_good_signal_run_and_persists(tmp_path):
    db_path = tmp_path / "mission82.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_paper_execution_agent(
        db_path=db_path,
        execution_run_label="execution-1",
        report_label="report-1",
        signal_run_label="signal-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_READY
    assert result["global_verdict"] == VERDICT_READY
    assert result["paper_execution_count"] == 5
    assert result["recorded_execution_count"] == 5
    assert result["blocked_execution_count"] == 0
    assert result["paper_only_execution_count"] == 5
    assert result["no_live_signal_count"] == 5
    assert result["no_exchange_order_count"] == 5
    assert result["no_capital_deployment_count"] == 5
    assert result["no_model_training_count"] == 5
    assert result["zero_quantity_execution_count"] == 5
    assert result["zero_notional_execution_count"] == 5
    assert result["execution_check_count"] == 18
    assert result["pass_check_count"] == 18
    assert result["fail_check_count"] == 0
    assert result["next_mission"] == "Mission 83 Self-Learning Feedback Loop"

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT execution_run_label, engine_decision, global_verdict
            FROM ai_paper_execution_agent_runs
            WHERE execution_run_label = ?
            """,
            ("execution-1",),
        ).fetchone()

    assert row == ("execution-1", ENGINE_DECISION_READY, VERDICT_READY)


def test_paper_execution_agent_rejects_missing_signal_run(tmp_path):
    result = run_paper_execution_agent(
        db_path=tmp_path / "missing.db",
        execution_run_label="missing-execution",
        report_label="missing-report",
        signal_run_label="missing-signal",
    )

    assert result["engine_decision"] == ENGINE_DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["fail_check_count"] == 1


def test_paper_execution_agent_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "safety.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_signal_run(conn, safety_breach_count=1, live_trading="ENABLED")
        insert_paper_signals(conn)
        insert_signal_checks(conn)
        conn.commit()

    result = run_paper_execution_agent(
        db_path=db_path,
        execution_run_label="safety-execution",
        report_label="safety-report",
        signal_run_label="signal-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED


def test_paper_execution_agent_flags_unapproved_signal_engine(tmp_path):
    db_path = tmp_path / "unapproved.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_signal_run(
            conn,
            engine_state="AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_UNSTABLE",
            engine_decision="AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_REVIEW_REQUIRED",
            verdict="AI_AUTONOMOUS_PAPER_SIGNAL_ENGINE_UNSTABLE_SHADOW_ONLY",
        )
        insert_paper_signals(conn)
        insert_signal_checks(conn)
        conn.commit()

    result = run_paper_execution_agent(
        db_path=db_path,
        execution_run_label="unapproved-execution",
        report_label="unapproved-report",
        signal_run_label="signal-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["paper_execution_count"] == 0


def test_paper_execution_agent_flags_source_failed_checks(tmp_path):
    db_path = tmp_path / "failed-checks.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_signal_run(conn, fail_check_count=1)
        insert_paper_signals(conn)
        insert_signal_checks(conn)
        conn.commit()

    result = run_paper_execution_agent(
        db_path=db_path,
        execution_run_label="failed-checks-execution",
        report_label="failed-checks-report",
        signal_run_label="signal-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["source_fail_check_count"] == 1


def test_paper_execution_agent_flags_leakage_breach(tmp_path):
    db_path = tmp_path / "leakage.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_signal_run(conn, leakage_breach_count=1)
        insert_paper_signals(conn)
        insert_signal_checks(conn)
        conn.commit()

    result = run_paper_execution_agent(
        db_path=db_path,
        execution_run_label="leakage-execution",
        report_label="leakage-report",
        signal_run_label="signal-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["leakage_breach_count"] == 1


def test_paper_execution_agent_flags_missing_paper_signals(tmp_path):
    db_path = tmp_path / "missing-signals.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_signal_run(conn)
        insert_signal_checks(conn)
        conn.commit()

    result = run_paper_execution_agent(
        db_path=db_path,
        execution_run_label="missing-signals-execution",
        report_label="missing-signals-report",
        signal_run_label="signal-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["paper_execution_count"] == 0


def test_paper_execution_agent_flags_blocked_source_signal(tmp_path):
    db_path = tmp_path / "blocked-signal.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_signal_run(conn)
        insert_paper_signals(conn)
        conn.execute(
            """
            UPDATE ai_autonomous_paper_signals
            SET paper_signal_status = ?
            WHERE paper_signal_id = ?
            """,
            ("AI_AUTONOMOUS_PAPER_SIGNAL_BLOCKED", "signal-1-paper-signal-1"),
        )
        insert_signal_checks(conn)
        conn.commit()

    result = run_paper_execution_agent(
        db_path=db_path,
        execution_run_label="blocked-signal-execution",
        report_label="blocked-signal-report",
        signal_run_label="signal-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["blocked_execution_count"] == 1


def test_markdown_report_documents_paper_only_no_order(tmp_path):
    db_path = tmp_path / "markdown.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_paper_execution_agent(
        db_path=db_path,
        execution_run_label="markdown-execution",
        report_label="markdown-report",
        signal_run_label="signal-1",
    )

    assert "# DeltaGrid Mission 82" in result["markdown_report"]
    assert "paper execution records only" in result["markdown_report"]
    assert "does not train a model" in result["markdown_report"]
    assert "does not create live trading signals" in result["markdown_report"]
    assert "does not perform exchange execution" in result["markdown_report"]
    assert "Paper execution records are not profitability evidence" in result["markdown_report"]

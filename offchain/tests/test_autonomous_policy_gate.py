import sqlite3

from offchain.ai_dataset.autonomous_policy_gate import (
    POLICY_DECISION_BLOCK_SAFETY,
    POLICY_DECISION_READY,
    POLICY_DECISION_REJECT_MISSING,
    POLICY_DECISION_UNSTABLE,
    VERDICT_BLOCKED,
    VERDICT_MISSING,
    VERDICT_READY,
    VERDICT_UNSTABLE,
    parse_labels,
    run_autonomous_policy_gate,
)


def create_input_tables(conn):
    conn.execute(
        """
        CREATE TABLE ai_research_recommendation_runs (
            recommendation_run_label TEXT PRIMARY KEY,
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
            recommendation_count INTEGER,
            ready_recommendation_count INTEGER,
            blocked_recommendation_count INTEGER,
            human_review_required_count INTEGER,
            no_live_signal_count INTEGER,
            no_execution_count INTEGER,
            no_capital_deployment_count INTEGER,
            training_disabled_count INTEGER,
            fail_check_count INTEGER,
            safety_breach_count INTEGER,
            leakage_breach_count INTEGER,
            training_eligible_count INTEGER,
            training_locked_count INTEGER,
            baseline_accuracy_pct TEXT,
            average_label_confidence TEXT,
            average_net_paper_outcome_bps TEXT,
            recommendation_mode TEXT,
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
        CREATE TABLE ai_research_recommendation_items (
            recommendation_id TEXT PRIMARY KEY,
            recommendation_run_label TEXT,
            live_signal_action TEXT,
            execution_action TEXT,
            capital_action TEXT,
            model_training_action TEXT,
            human_review_required INTEGER,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_research_recommendation_checks (
            check_id TEXT PRIMARY KEY,
            recommendation_run_label TEXT,
            check_status TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )


def insert_run(
    conn,
    label="rec-1",
    engine_state="AI_RESEARCH_RECOMMENDATION_ENGINE_READY_RESEARCH_ONLY",
    engine_decision="AI_RESEARCH_RECOMMENDATION_ENGINE_APPROVED_FOR_HUMAN_REVIEW_ONLY",
    verdict="AI_RESEARCH_RECOMMENDATION_READY_SHADOW_ONLY",
    recommendation_count=5,
    ready_count=5,
    blocked_count=0,
    human_review_count=5,
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
        INSERT INTO ai_research_recommendation_runs (
            recommendation_run_label, source_governance_review_label,
            source_evaluation_label, source_guard_review_label,
            source_collection_label, source_registry_label, source_build_label,
            source_schedule_label, source_learning_run_label,
            source_multi_cycle_track_label, source_session_label,
            source_portfolio_label, recommendation_count,
            ready_recommendation_count, blocked_recommendation_count,
            human_review_required_count, no_live_signal_count,
            no_execution_count, no_capital_deployment_count,
            training_disabled_count, fail_check_count, safety_breach_count,
            leakage_breach_count, training_eligible_count, training_locked_count,
            baseline_accuracy_pct, average_label_confidence,
            average_net_paper_outcome_bps, recommendation_mode, engine_state,
            engine_decision, global_verdict, live_trading, live_order_sent,
            capital_deployment
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            label,
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
            recommendation_count,
            ready_count,
            blocked_count,
            human_review_count,
            no_live_signal_count,
            no_execution_count,
            no_capital_count,
            training_disabled_count,
            fail_check_count,
            safety_breach_count,
            leakage_breach_count,
            training_eligible_count,
            training_locked_count,
            "100.0",
            "0.65",
            "-2.0",
            "RESEARCH_ONLY_RECOMMENDATION_NO_TRAINING_NO_SIGNAL",
            engine_state,
            engine_decision,
            verdict,
            live_trading,
            live_order_sent,
            capital_deployment,
        ),
    )


def insert_items(conn, label="rec-1", count=5):
    for index in range(1, count + 1):
        conn.execute(
            """
            INSERT INTO ai_research_recommendation_items (
                recommendation_id, recommendation_run_label, live_signal_action,
                execution_action, capital_action, model_training_action,
                human_review_required, live_trading, live_order_sent,
                capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{label}-item-{index}",
                label,
                "NO_LIVE_SIGNAL",
                "NO_EXECUTION",
                "NO_CAPITAL_DEPLOYMENT",
                "KEEP_MODEL_TRAINING_DISABLED",
                1,
                "DISABLED",
                0,
                "BLOCKED",
            ),
        )


def insert_checks(conn, label="rec-1", count=16):
    for index in range(1, count + 1):
        conn.execute(
            """
            INSERT INTO ai_research_recommendation_checks (
                check_id, recommendation_run_label, check_status,
                live_trading, live_order_sent, capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"{label}-check-{index}",
                label,
                "AI_RESEARCH_RECOMMENDATION_CHECK_PASS",
                "DISABLED",
                0,
                "BLOCKED",
            ),
        )


def seed_good(conn):
    create_input_tables(conn)
    insert_run(conn)
    insert_items(conn)
    insert_checks(conn)


def test_parse_labels_deduplicates():
    assert parse_labels("rec-1,rec-2,rec-1") == ["rec-1", "rec-2"]


def test_policy_gate_approves_good_recommendation_run_and_persists(tmp_path):
    db_path = tmp_path / "mission80.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_autonomous_policy_gate(
        db_path=db_path,
        policy_run_label="policy-1",
        report_label="report-1",
        recommendation_run_label="rec-1",
    )

    assert result["policy_decision"] == POLICY_DECISION_READY
    assert result["global_verdict"] == VERDICT_READY
    assert result["policy_rule_count"] == 12
    assert result["pass_rule_count"] == 12
    assert result["fail_rule_count"] == 0
    assert result["policy_decision_count"] == 5
    assert result["pass_decision_count"] == 5
    assert result["fail_decision_count"] == 0
    assert result["policy_check_count"] == 12
    assert result["pass_check_count"] == 12
    assert result["fail_check_count"] == 0
    assert result["next_mission"] == "Mission 81 Autonomous Paper Signal Engine"

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT policy_run_label, policy_decision, global_verdict
            FROM ai_autonomous_policy_gate_runs
            WHERE policy_run_label = ?
            """,
            ("policy-1",),
        ).fetchone()

    assert row == ("policy-1", POLICY_DECISION_READY, VERDICT_READY)


def test_policy_gate_rejects_missing_recommendation_run(tmp_path):
    result = run_autonomous_policy_gate(
        db_path=tmp_path / "missing.db",
        policy_run_label="missing-policy",
        report_label="missing-report",
        recommendation_run_label="missing-rec",
    )

    assert result["policy_decision"] == POLICY_DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["fail_check_count"] == 1


def test_policy_gate_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "safety.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_run(conn, safety_breach_count=1, live_trading="ENABLED")
        insert_items(conn)
        insert_checks(conn)
        conn.commit()

    result = run_autonomous_policy_gate(
        db_path=db_path,
        policy_run_label="safety-policy",
        report_label="safety-report",
        recommendation_run_label="rec-1",
    )

    assert result["policy_decision"] == POLICY_DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED


def test_policy_gate_flags_unapproved_recommendation_engine(tmp_path):
    db_path = tmp_path / "unapproved.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_run(
            conn,
            engine_state="AI_RESEARCH_RECOMMENDATION_ENGINE_UNSTABLE",
            engine_decision="AI_RESEARCH_RECOMMENDATION_ENGINE_REVIEW_REQUIRED",
            verdict="AI_RESEARCH_RECOMMENDATION_UNSTABLE_SHADOW_ONLY",
        )
        insert_items(conn)
        insert_checks(conn)
        conn.commit()

    result = run_autonomous_policy_gate(
        db_path=db_path,
        policy_run_label="unapproved-policy",
        report_label="unapproved-report",
        recommendation_run_label="rec-1",
    )

    assert result["policy_decision"] == POLICY_DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["fail_rule_count"] >= 1


def test_policy_gate_flags_source_failed_checks(tmp_path):
    db_path = tmp_path / "failed-source.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_run(conn, fail_check_count=1)
        insert_items(conn)
        insert_checks(conn)
        conn.commit()

    result = run_autonomous_policy_gate(
        db_path=db_path,
        policy_run_label="failed-source-policy",
        report_label="failed-source-report",
        recommendation_run_label="rec-1",
    )

    assert result["policy_decision"] == POLICY_DECISION_UNSTABLE
    assert result["fail_rule_count"] >= 1


def test_policy_gate_flags_leakage_breach(tmp_path):
    db_path = tmp_path / "leakage.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_run(conn, leakage_breach_count=1)
        insert_items(conn)
        insert_checks(conn)
        conn.commit()

    result = run_autonomous_policy_gate(
        db_path=db_path,
        policy_run_label="leakage-policy",
        report_label="leakage-report",
        recommendation_run_label="rec-1",
    )

    assert result["policy_decision"] == POLICY_DECISION_UNSTABLE
    assert result["leakage_breach_count"] == 1


def test_policy_gate_flags_training_unlocked(tmp_path):
    db_path = tmp_path / "training.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_run(conn, training_eligible_count=1, training_disabled_count=4)
        insert_items(conn)
        insert_checks(conn)
        conn.commit()

    result = run_autonomous_policy_gate(
        db_path=db_path,
        policy_run_label="training-policy",
        report_label="training-report",
        recommendation_run_label="rec-1",
    )

    assert result["policy_decision"] == POLICY_DECISION_UNSTABLE
    assert result["training_eligible_count"] == 1


def test_policy_gate_flags_live_signal_attempt(tmp_path):
    db_path = tmp_path / "signal.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_run(conn, no_live_signal_count=4)
        insert_items(conn)
        insert_checks(conn)
        conn.commit()

    result = run_autonomous_policy_gate(
        db_path=db_path,
        policy_run_label="signal-policy",
        report_label="signal-report",
        recommendation_run_label="rec-1",
    )

    assert result["policy_decision"] == POLICY_DECISION_UNSTABLE
    assert result["fail_rule_count"] >= 1


def test_markdown_report_documents_autonomous_policy_gate_not_human_gate(tmp_path):
    db_path = tmp_path / "markdown.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_autonomous_policy_gate(
        db_path=db_path,
        policy_run_label="markdown-policy",
        report_label="markdown-report",
        recommendation_run_label="rec-1",
    )

    assert "# DeltaGrid Mission 80" in result["markdown_report"]
    assert "replaces the earlier Human Approval Gate path" in result["markdown_report"]
    assert "autonomous paper-only signal generation" in result["markdown_report"]
    assert "does not train a model" in result["markdown_report"]
    assert "does not create live trading signals" in result["markdown_report"]
    assert "not profitability evidence" in result["markdown_report"]

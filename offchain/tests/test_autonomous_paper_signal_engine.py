import sqlite3

from offchain.ai_dataset.autonomous_paper_signal_engine import (
    ENGINE_DECISION_BLOCK_SAFETY,
    ENGINE_DECISION_READY,
    ENGINE_DECISION_REJECT_MISSING,
    ENGINE_DECISION_UNSTABLE,
    VERDICT_BLOCKED,
    VERDICT_MISSING,
    VERDICT_READY,
    VERDICT_UNSTABLE,
    parse_labels,
    run_autonomous_paper_signal_engine,
)


def create_input_tables(conn):
    conn.execute(
        """
        CREATE TABLE ai_autonomous_policy_gate_runs (
            policy_run_label TEXT PRIMARY KEY,
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
            policy_rule_count INTEGER,
            pass_rule_count INTEGER,
            fail_rule_count INTEGER,
            policy_decision_count INTEGER,
            pass_decision_count INTEGER,
            fail_decision_count INTEGER,
            policy_check_count INTEGER,
            pass_check_count INTEGER,
            fail_check_count INTEGER,
            safety_breach_count INTEGER,
            leakage_breach_count INTEGER,
            training_eligible_count INTEGER,
            training_locked_count INTEGER,
            baseline_accuracy_pct TEXT,
            average_label_confidence TEXT,
            average_net_paper_outcome_bps TEXT,
            policy_state TEXT,
            policy_decision TEXT,
            global_verdict TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_autonomous_policy_gate_rules (
            rule_id TEXT PRIMARY KEY,
            policy_run_label TEXT,
            rule_status TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_autonomous_policy_gate_decisions (
            decision_id TEXT PRIMARY KEY,
            policy_run_label TEXT,
            decision_status TEXT,
            decision_value TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_autonomous_policy_gate_checks (
            check_id TEXT PRIMARY KEY,
            policy_run_label TEXT,
            check_status TEXT,
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
            recommendation_rank INTEGER,
            recommendation_code TEXT,
            recommendation_title TEXT,
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


def insert_policy_run(
    conn,
    label="policy-1",
    recommendation_run_label="rec-1",
    policy_state="AI_AUTONOMOUS_POLICY_GATE_READY_PAPER_ONLY",
    policy_decision="AI_AUTONOMOUS_POLICY_GATE_APPROVED_FOR_AUTONOMOUS_PAPER_SIGNAL_ENGINE",
    verdict="AI_AUTONOMOUS_POLICY_GATE_READY_SHADOW_ONLY",
    fail_rule_count=0,
    fail_decision_count=0,
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
        INSERT INTO ai_autonomous_policy_gate_runs (
            policy_run_label, source_recommendation_run_label,
            source_governance_review_label, source_evaluation_label,
            source_guard_review_label, source_collection_label,
            source_registry_label, source_build_label, source_schedule_label,
            source_learning_run_label, source_multi_cycle_track_label,
            source_session_label, source_portfolio_label,
            policy_rule_count, pass_rule_count, fail_rule_count,
            policy_decision_count, pass_decision_count, fail_decision_count,
            policy_check_count, pass_check_count, fail_check_count,
            safety_breach_count, leakage_breach_count, training_eligible_count,
            training_locked_count, baseline_accuracy_pct, average_label_confidence,
            average_net_paper_outcome_bps, policy_state, policy_decision,
            global_verdict, live_trading, live_order_sent, capital_deployment
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            label,
            recommendation_run_label,
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
            12,
            12 - fail_rule_count,
            fail_rule_count,
            5,
            5 - fail_decision_count,
            fail_decision_count,
            12,
            12 - fail_check_count,
            fail_check_count,
            safety_breach_count,
            leakage_breach_count,
            training_eligible_count,
            training_locked_count,
            "100.0",
            "0.65",
            "-2.0",
            policy_state,
            policy_decision,
            verdict,
            live_trading,
            live_order_sent,
            capital_deployment,
        ),
    )


def insert_policy_rules(conn, label="policy-1", count=12):
    for index in range(1, count + 1):
        conn.execute(
            """
            INSERT INTO ai_autonomous_policy_gate_rules (
                rule_id, policy_run_label, rule_status,
                live_trading, live_order_sent, capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"{label}-rule-{index}",
                label,
                "AI_AUTONOMOUS_POLICY_RULE_PASS",
                "DISABLED",
                0,
                "BLOCKED",
            ),
        )


def insert_policy_decisions(conn, label="policy-1", count=5):
    for index in range(1, count + 1):
        conn.execute(
            """
            INSERT INTO ai_autonomous_policy_gate_decisions (
                decision_id, policy_run_label, decision_status, decision_value,
                live_trading, live_order_sent, capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{label}-decision-{index}",
                label,
                "AI_AUTONOMOUS_POLICY_DECISION_PASS",
                "ALLOW_PAPER_ONLY" if index == 1 else "KEEP_DISABLED",
                "DISABLED",
                0,
                "BLOCKED",
            ),
        )


def insert_policy_checks(conn, label="policy-1", count=12):
    for index in range(1, count + 1):
        conn.execute(
            """
            INSERT INTO ai_autonomous_policy_gate_checks (
                check_id, policy_run_label, check_status,
                live_trading, live_order_sent, capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"{label}-check-{index}",
                label,
                "AI_AUTONOMOUS_POLICY_GATE_CHECK_PASS",
                "DISABLED",
                0,
                "BLOCKED",
            ),
        )


def insert_recommendation_items(conn, label="rec-1", count=5):
    for index in range(1, count + 1):
        conn.execute(
            """
            INSERT INTO ai_research_recommendation_items (
                recommendation_id, recommendation_run_label, recommendation_rank,
                recommendation_code, recommendation_title, live_signal_action,
                execution_action, capital_action, model_training_action,
                human_review_required, live_trading, live_order_sent,
                capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{label}-item-{index}",
                label,
                index,
                f"RESEARCH_RECOMMENDATION_{index}",
                f"Research recommendation {index}",
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


def seed_good(conn):
    create_input_tables(conn)
    insert_policy_run(conn)
    insert_policy_rules(conn)
    insert_policy_decisions(conn)
    insert_policy_checks(conn)
    insert_recommendation_items(conn)


def test_parse_labels_deduplicates():
    assert parse_labels("policy-1,policy-2,policy-1") == ["policy-1", "policy-2"]


def test_paper_signal_engine_approves_good_policy_and_persists(tmp_path):
    db_path = tmp_path / "mission81.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_autonomous_paper_signal_engine(
        db_path=db_path,
        signal_run_label="signal-1",
        report_label="report-1",
        policy_run_label="policy-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_READY
    assert result["global_verdict"] == VERDICT_READY
    assert result["paper_signal_count"] == 5
    assert result["ready_signal_count"] == 5
    assert result["blocked_signal_count"] == 0
    assert result["observe_only_signal_count"] == 5
    assert result["no_live_signal_count"] == 5
    assert result["no_execution_count"] == 5
    assert result["no_capital_deployment_count"] == 5
    assert result["training_disabled_count"] == 5
    assert result["signal_check_count"] == 16
    assert result["pass_check_count"] == 16
    assert result["fail_check_count"] == 0
    assert result["next_mission"] == "Mission 82 Paper Execution Agent"

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT signal_run_label, engine_decision, global_verdict
            FROM ai_autonomous_paper_signal_runs
            WHERE signal_run_label = ?
            """,
            ("signal-1",),
        ).fetchone()

    assert row == ("signal-1", ENGINE_DECISION_READY, VERDICT_READY)


def test_paper_signal_engine_rejects_missing_policy_run(tmp_path):
    result = run_autonomous_paper_signal_engine(
        db_path=tmp_path / "missing.db",
        signal_run_label="missing-signal",
        report_label="missing-report",
        policy_run_label="missing-policy",
    )

    assert result["engine_decision"] == ENGINE_DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["fail_check_count"] == 1


def test_paper_signal_engine_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "safety.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_policy_run(conn, safety_breach_count=1, live_trading="ENABLED")
        insert_policy_rules(conn)
        insert_policy_decisions(conn)
        insert_policy_checks(conn)
        insert_recommendation_items(conn)
        conn.commit()

    result = run_autonomous_paper_signal_engine(
        db_path=db_path,
        signal_run_label="safety-signal",
        report_label="safety-report",
        policy_run_label="policy-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED


def test_paper_signal_engine_flags_unapproved_policy(tmp_path):
    db_path = tmp_path / "unapproved.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_policy_run(
            conn,
            policy_state="AI_AUTONOMOUS_POLICY_GATE_UNSTABLE",
            policy_decision="AI_AUTONOMOUS_POLICY_GATE_REVIEW_REQUIRED",
            verdict="AI_AUTONOMOUS_POLICY_GATE_UNSTABLE_SHADOW_ONLY",
        )
        insert_policy_rules(conn)
        insert_policy_decisions(conn)
        insert_policy_checks(conn)
        insert_recommendation_items(conn)
        conn.commit()

    result = run_autonomous_paper_signal_engine(
        db_path=db_path,
        signal_run_label="unapproved-signal",
        report_label="unapproved-report",
        policy_run_label="policy-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["paper_signal_count"] == 0


def test_paper_signal_engine_flags_source_failed_rules(tmp_path):
    db_path = tmp_path / "failed-rules.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_policy_run(conn, fail_rule_count=1)
        insert_policy_rules(conn)
        insert_policy_decisions(conn)
        insert_policy_checks(conn)
        insert_recommendation_items(conn)
        conn.commit()

    result = run_autonomous_paper_signal_engine(
        db_path=db_path,
        signal_run_label="failed-rules-signal",
        report_label="failed-rules-report",
        policy_run_label="policy-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["source_fail_rule_count"] == 1


def test_paper_signal_engine_flags_source_failed_decisions(tmp_path):
    db_path = tmp_path / "failed-decisions.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_policy_run(conn, fail_decision_count=1)
        insert_policy_rules(conn)
        insert_policy_decisions(conn)
        insert_policy_checks(conn)
        insert_recommendation_items(conn)
        conn.commit()

    result = run_autonomous_paper_signal_engine(
        db_path=db_path,
        signal_run_label="failed-decisions-signal",
        report_label="failed-decisions-report",
        policy_run_label="policy-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["source_fail_decision_count"] == 1


def test_paper_signal_engine_flags_leakage_breach(tmp_path):
    db_path = tmp_path / "leakage.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_policy_run(conn, leakage_breach_count=1)
        insert_policy_rules(conn)
        insert_policy_decisions(conn)
        insert_policy_checks(conn)
        insert_recommendation_items(conn)
        conn.commit()

    result = run_autonomous_paper_signal_engine(
        db_path=db_path,
        signal_run_label="leakage-signal",
        report_label="leakage-report",
        policy_run_label="policy-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["leakage_breach_count"] == 1


def test_paper_signal_engine_flags_missing_recommendation_items(tmp_path):
    db_path = tmp_path / "missing-items.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_policy_run(conn)
        insert_policy_rules(conn)
        insert_policy_decisions(conn)
        insert_policy_checks(conn)
        conn.commit()

    result = run_autonomous_paper_signal_engine(
        db_path=db_path,
        signal_run_label="missing-items-signal",
        report_label="missing-items-report",
        policy_run_label="policy-1",
    )

    assert result["engine_decision"] == ENGINE_DECISION_UNSTABLE
    assert result["paper_signal_count"] == 0


def test_markdown_report_documents_paper_only_no_execution(tmp_path):
    db_path = tmp_path / "markdown.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_autonomous_paper_signal_engine(
        db_path=db_path,
        signal_run_label="markdown-signal",
        report_label="markdown-report",
        policy_run_label="policy-1",
    )

    assert "# DeltaGrid Mission 81" in result["markdown_report"]
    assert "paper-only observe signals" in result["markdown_report"]
    assert "does not train a model" in result["markdown_report"]
    assert "does not create live trading signals" in result["markdown_report"]
    assert "does not perform execution" in result["markdown_report"]
    assert "Paper signals are not profitability evidence" in result["markdown_report"]

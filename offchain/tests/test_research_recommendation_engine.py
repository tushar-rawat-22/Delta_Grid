import sqlite3

from offchain.ai_dataset.research_recommendation_engine import (
    DECISION_BLOCK_SAFETY,
    DECISION_READY,
    DECISION_REJECT_MISSING,
    DECISION_UNSTABLE,
    VERDICT_BLOCKED,
    VERDICT_MISSING,
    VERDICT_READY,
    VERDICT_UNSTABLE,
    parse_labels,
    run_ai_research_recommendation_engine,
)


def create_input_tables(conn):
    conn.execute(
        """
        CREATE TABLE ai_offline_evaluation_governance_reviews (
            governance_review_label TEXT PRIMARY KEY,
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
            evidence_count INTEGER,
            pass_evidence_count INTEGER,
            fail_evidence_count INTEGER,
            approve_vote_count INTEGER,
            review_vote_count INTEGER,
            block_vote_count INTEGER,
            fail_check_count INTEGER,
            safety_breach_count INTEGER,
            leakage_breach_count INTEGER,
            training_eligible_count INTEGER,
            training_locked_count INTEGER,
            baseline_accuracy_pct TEXT,
            average_label_confidence TEXT,
            average_net_paper_outcome_bps TEXT,
            governance_state TEXT,
            governance_decision TEXT,
            global_verdict TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_offline_evaluation_governance_evidence (
            evidence_id TEXT PRIMARY KEY,
            governance_review_label TEXT,
            evidence_status TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_offline_evaluation_governance_votes (
            vote_id TEXT PRIMARY KEY,
            governance_review_label TEXT,
            vote_status TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_offline_evaluation_governance_checks (
            check_id TEXT PRIMARY KEY,
            governance_review_label TEXT,
            check_status TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )


def insert_governance(
    conn,
    label="gov-1",
    state="AI_OFFLINE_EVALUATION_GOVERNANCE_READY_RESEARCH_ONLY",
    decision="AI_OFFLINE_EVALUATION_GOVERNANCE_APPROVED_FOR_RESEARCH_RECOMMENDATION_ONLY",
    verdict="AI_OFFLINE_EVALUATION_GOVERNANCE_READY_SHADOW_ONLY",
    fail_evidence_count=0,
    approve_vote_count=5,
    review_vote_count=0,
    block_vote_count=0,
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
        INSERT INTO ai_offline_evaluation_governance_reviews (
            governance_review_label, source_evaluation_label,
            source_guard_review_label, source_collection_label,
            source_registry_label, source_build_label, source_schedule_label,
            source_learning_run_label, source_multi_cycle_track_label,
            source_session_label, source_portfolio_label, evidence_count,
            pass_evidence_count, fail_evidence_count, approve_vote_count,
            review_vote_count, block_vote_count, fail_check_count,
            safety_breach_count, leakage_breach_count, training_eligible_count,
            training_locked_count, baseline_accuracy_pct, average_label_confidence,
            average_net_paper_outcome_bps, governance_state, governance_decision,
            global_verdict, live_trading, live_order_sent, capital_deployment
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            label, "eval-1", "guard-1", "collection-1", "registry-1", "build-1",
            "schedule-1", "learning-1", "track-1", "session-1", "portfolio-1",
            14, 14 - fail_evidence_count, fail_evidence_count, approve_vote_count,
            review_vote_count, block_vote_count, fail_check_count, safety_breach_count,
            leakage_breach_count, training_eligible_count, training_locked_count,
            "100.0", "0.65", "-2.0", state, decision, verdict, live_trading,
            live_order_sent, capital_deployment,
        ),
    )


def insert_evidence(conn, label="gov-1", count=14):
    for index in range(1, count + 1):
        conn.execute(
            """
            INSERT INTO ai_offline_evaluation_governance_evidence (
                evidence_id, governance_review_label, evidence_status,
                live_trading, live_order_sent, capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"{label}-evidence-{index}", label,
                "AI_OFFLINE_EVALUATION_GOVERNANCE_EVIDENCE_PASS",
                "DISABLED", 0, "BLOCKED",
            ),
        )


def insert_votes(conn, label="gov-1", count=5):
    for index in range(1, count + 1):
        conn.execute(
            """
            INSERT INTO ai_offline_evaluation_governance_votes (
                vote_id, governance_review_label, vote_status,
                live_trading, live_order_sent, capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"{label}-vote-{index}", label,
                "AI_GOVERNANCE_BOARD_VOTE_APPROVE_RESEARCH_ONLY",
                "DISABLED", 0, "BLOCKED",
            ),
        )


def insert_checks(conn, label="gov-1", count=10):
    for index in range(1, count + 1):
        conn.execute(
            """
            INSERT INTO ai_offline_evaluation_governance_checks (
                check_id, governance_review_label, check_status,
                live_trading, live_order_sent, capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"{label}-check-{index}", label,
                "AI_OFFLINE_EVALUATION_GOVERNANCE_CHECK_PASS",
                "DISABLED", 0, "BLOCKED",
            ),
        )


def seed_good(conn):
    create_input_tables(conn)
    insert_governance(conn)
    insert_evidence(conn)
    insert_votes(conn)
    insert_checks(conn)


def test_parse_labels_deduplicates():
    assert parse_labels("gov-1,gov-2,gov-1") == ["gov-1", "gov-2"]


def test_recommendation_engine_approves_good_governance_and_persists(tmp_path):
    db_path = tmp_path / "mission79.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_research_recommendation_engine(
        db_path=db_path,
        recommendation_run_label="rec-1",
        report_label="report-1",
        governance_review_label="gov-1",
    )

    assert result["engine_decision"] == DECISION_READY
    assert result["global_verdict"] == VERDICT_READY
    assert result["recommendation_count"] == 5
    assert result["ready_recommendation_count"] == 5
    assert result["human_review_required_count"] == 5
    assert result["no_live_signal_count"] == 5
    assert result["no_execution_count"] == 5
    assert result["no_capital_deployment_count"] == 5
    assert result["training_disabled_count"] == 5
    assert result["recommendation_check_count"] == 16
    assert result["pass_check_count"] == 16
    assert result["fail_check_count"] == 0

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT recommendation_run_label, engine_decision, global_verdict
            FROM ai_research_recommendation_runs
            WHERE recommendation_run_label = ?
            """,
            ("rec-1",),
        ).fetchone()

    assert row == ("rec-1", DECISION_READY, VERDICT_READY)


def test_recommendation_engine_rejects_missing_governance(tmp_path):
    result = run_ai_research_recommendation_engine(
        db_path=tmp_path / "missing.db",
        recommendation_run_label="missing-rec",
        report_label="missing-report",
        governance_review_label="missing-gov",
    )

    assert result["engine_decision"] == DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["fail_check_count"] == 1


def test_recommendation_engine_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "safety.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_governance(conn, safety_breach_count=1, live_trading="ENABLED")
        insert_evidence(conn)
        insert_votes(conn)
        insert_checks(conn)
        conn.commit()

    result = run_ai_research_recommendation_engine(
        db_path=db_path,
        recommendation_run_label="safety-rec",
        report_label="safety-report",
        governance_review_label="gov-1",
    )

    assert result["engine_decision"] == DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED


def test_recommendation_engine_flags_unapproved_governance(tmp_path):
    db_path = tmp_path / "unapproved.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_governance(
            conn,
            state="AI_OFFLINE_EVALUATION_GOVERNANCE_UNSTABLE",
            decision="AI_OFFLINE_EVALUATION_GOVERNANCE_REVIEW_REQUIRED",
            verdict="AI_OFFLINE_EVALUATION_GOVERNANCE_UNSTABLE_SHADOW_ONLY",
        )
        insert_evidence(conn)
        insert_votes(conn)
        insert_checks(conn)
        conn.commit()

    result = run_ai_research_recommendation_engine(
        db_path=db_path,
        recommendation_run_label="unapproved-rec",
        report_label="unapproved-report",
        governance_review_label="gov-1",
    )

    assert result["engine_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["recommendation_count"] == 0


def test_recommendation_engine_flags_failed_evidence(tmp_path):
    db_path = tmp_path / "failed-evidence.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_governance(conn, fail_evidence_count=1)
        insert_evidence(conn)
        insert_votes(conn)
        insert_checks(conn)
        conn.commit()

    result = run_ai_research_recommendation_engine(
        db_path=db_path,
        recommendation_run_label="failed-evidence-rec",
        report_label="failed-evidence-report",
        governance_review_label="gov-1",
    )

    assert result["engine_decision"] == DECISION_UNSTABLE
    assert result["source_fail_evidence_count"] == 1


def test_recommendation_engine_flags_vote_review_required(tmp_path):
    db_path = tmp_path / "votes.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_governance(conn, approve_vote_count=4, review_vote_count=1)
        insert_evidence(conn)
        insert_votes(conn)
        insert_checks(conn)
        conn.commit()

    result = run_ai_research_recommendation_engine(
        db_path=db_path,
        recommendation_run_label="votes-rec",
        report_label="votes-report",
        governance_review_label="gov-1",
    )

    assert result["engine_decision"] == DECISION_UNSTABLE
    assert result["source_approve_vote_count"] == 4


def test_recommendation_engine_flags_leakage_breach(tmp_path):
    db_path = tmp_path / "leakage.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_governance(conn, leakage_breach_count=1)
        insert_evidence(conn)
        insert_votes(conn)
        insert_checks(conn)
        conn.commit()

    result = run_ai_research_recommendation_engine(
        db_path=db_path,
        recommendation_run_label="leakage-rec",
        report_label="leakage-report",
        governance_review_label="gov-1",
    )

    assert result["engine_decision"] == DECISION_UNSTABLE
    assert result["leakage_breach_count"] == 1


def test_recommendation_engine_flags_training_unlocked(tmp_path):
    db_path = tmp_path / "training.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_governance(conn, training_eligible_count=1, training_locked_count=3)
        insert_evidence(conn)
        insert_votes(conn)
        insert_checks(conn)
        conn.commit()

    result = run_ai_research_recommendation_engine(
        db_path=db_path,
        recommendation_run_label="training-rec",
        report_label="training-report",
        governance_review_label="gov-1",
    )

    assert result["engine_decision"] == DECISION_UNSTABLE
    assert result["training_eligible_count"] == 1


def test_markdown_report_contains_no_training_signal_or_profit_claim(tmp_path):
    db_path = tmp_path / "markdown.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_research_recommendation_engine(
        db_path=db_path,
        recommendation_run_label="markdown-rec",
        report_label="markdown-report",
        governance_review_label="gov-1",
    )

    assert "# DeltaGrid Mission 79" in result["markdown_report"]
    assert "does not train a model" in result["markdown_report"]
    assert "does not create live trading signals" in result["markdown_report"]
    assert "Every recommendation requires human review" in result["markdown_report"]
    assert "not profitability evidence" in result["markdown_report"]

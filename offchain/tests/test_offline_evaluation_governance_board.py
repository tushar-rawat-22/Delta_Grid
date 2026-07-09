import sqlite3

from offchain.ai_dataset.offline_evaluation_governance_board import (
    DECISION_BLOCK_SAFETY,
    DECISION_READY,
    DECISION_REJECT_MISSING,
    DECISION_UNSTABLE,
    VERDICT_BLOCKED,
    VERDICT_MISSING,
    VERDICT_READY,
    VERDICT_UNSTABLE,
    parse_labels,
    run_ai_offline_evaluation_governance_board,
)


def create_input_tables(conn):
    conn.execute(
        """
        CREATE TABLE ai_offline_evaluation_runs (
            evaluation_label TEXT PRIMARY KEY,
            source_guard_review_label TEXT,
            source_collection_label TEXT,
            source_registry_label TEXT,
            source_build_label TEXT,
            source_schedule_label TEXT,
            source_learning_run_label TEXT,
            source_multi_cycle_track_label TEXT,
            source_session_label TEXT,
            source_portfolio_label TEXT,
            final_label_count INTEGER,
            evaluation_case_count INTEGER,
            metric_count INTEGER,
            fail_check_count INTEGER,
            safety_breach_count INTEGER,
            leakage_breach_count INTEGER,
            training_eligible_count INTEGER,
            training_locked_count INTEGER,
            baseline_accuracy_pct TEXT,
            average_label_confidence TEXT,
            average_net_paper_outcome_bps TEXT,
            evaluation_mode TEXT,
            evaluation_state TEXT,
            evaluation_decision TEXT,
            global_verdict TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_offline_evaluation_cases (
            evaluation_case_id TEXT PRIMARY KEY,
            evaluation_label TEXT,
            training_eligible INTEGER,
            offline_evaluation_candidate INTEGER,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_offline_evaluation_metrics (
            metric_id TEXT PRIMARY KEY,
            evaluation_label TEXT,
            metric_name TEXT,
            metric_value TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_offline_evaluation_checks (
            check_id TEXT PRIMARY KEY,
            evaluation_label TEXT,
            check_status TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )


def insert_run(
    conn,
    evaluation_label="eval-1",
    state="AI_OFFLINE_EVALUATION_HARNESS_READY",
    decision="AI_OFFLINE_EVALUATION_APPROVED_FOR_GOVERNANCE_REVIEW",
    verdict="AI_OFFLINE_EVALUATION_READY_SHADOW_ONLY",
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
        INSERT INTO ai_offline_evaluation_runs (
            evaluation_label, source_guard_review_label, source_collection_label,
            source_registry_label, source_build_label, source_schedule_label,
            source_learning_run_label, source_multi_cycle_track_label,
            source_session_label, source_portfolio_label, final_label_count,
            evaluation_case_count, metric_count, fail_check_count,
            safety_breach_count, leakage_breach_count, training_eligible_count,
            training_locked_count, baseline_accuracy_pct, average_label_confidence,
            average_net_paper_outcome_bps, evaluation_mode, evaluation_state,
            evaluation_decision, global_verdict, live_trading, live_order_sent,
            capital_deployment
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            evaluation_label, "guard-1", "collection-1", "registry-1", "build-1",
            "schedule-1", "learning-1", "track-1", "session-1", "portfolio-1",
            4, 4, 10, fail_check_count, safety_breach_count, leakage_breach_count,
            training_eligible_count, training_locked_count, "100.0", "0.65", "-2.0",
            "DETERMINISTIC_BASELINE_OFFLINE_EVALUATION_NO_MODEL_TRAINING",
            state, decision, verdict, live_trading, live_order_sent, capital_deployment,
        ),
    )


def insert_cases(conn, evaluation_label="eval-1", count=4, training_eligible=0):
    for index in range(1, count + 1):
        conn.execute(
            """
            INSERT INTO ai_offline_evaluation_cases (
                evaluation_case_id, evaluation_label, training_eligible,
                offline_evaluation_candidate, live_trading, live_order_sent,
                capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{evaluation_label}-case-{index}", evaluation_label,
                training_eligible, 1, "DISABLED", 0, "BLOCKED",
            ),
        )


def insert_metrics(conn, evaluation_label="eval-1", count=10):
    for index in range(1, count + 1):
        conn.execute(
            """
            INSERT INTO ai_offline_evaluation_metrics (
                metric_id, evaluation_label, metric_name, metric_value,
                live_trading, live_order_sent, capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{evaluation_label}-metric-{index}", evaluation_label,
                f"metric_{index}", str(index), "DISABLED", 0, "BLOCKED",
            ),
        )


def insert_checks(conn, evaluation_label="eval-1", count=16):
    for index in range(1, count + 1):
        conn.execute(
            """
            INSERT INTO ai_offline_evaluation_checks (
                check_id, evaluation_label, check_status, live_trading,
                live_order_sent, capital_deployment
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"{evaluation_label}-check-{index}", evaluation_label,
                "AI_OFFLINE_EVALUATION_CHECK_PASS", "DISABLED", 0, "BLOCKED",
            ),
        )


def seed_good(conn):
    create_input_tables(conn)
    insert_run(conn)
    insert_cases(conn)
    insert_metrics(conn)
    insert_checks(conn)


def test_parse_labels_deduplicates():
    assert parse_labels("eval-1,eval-2,eval-1") == ["eval-1", "eval-2"]


def test_governance_approves_good_evaluation_and_persists(tmp_path):
    db_path = tmp_path / "mission78.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_offline_evaluation_governance_board(
        db_path=db_path,
        governance_review_label="gov-1",
        report_label="report-1",
        evaluation_label="eval-1",
    )

    assert result["governance_decision"] == DECISION_READY
    assert result["global_verdict"] == VERDICT_READY
    assert result["evidence_count"] == 14
    assert result["pass_evidence_count"] == 14
    assert result["fail_evidence_count"] == 0
    assert result["board_vote_count"] == 5
    assert result["approve_vote_count"] == 5
    assert result["governance_check_count"] == 10
    assert result["pass_check_count"] == 10
    assert result["fail_check_count"] == 0

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT governance_review_label, governance_decision, global_verdict
            FROM ai_offline_evaluation_governance_reviews
            WHERE governance_review_label = ?
            """,
            ("gov-1",),
        ).fetchone()

    assert row == ("gov-1", DECISION_READY, VERDICT_READY)


def test_governance_rejects_missing_evaluation(tmp_path):
    result = run_ai_offline_evaluation_governance_board(
        db_path=tmp_path / "missing.db",
        governance_review_label="missing-gov",
        report_label="missing-report",
        evaluation_label="missing-eval",
    )

    assert result["governance_decision"] == DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["fail_check_count"] == 1


def test_governance_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "safety.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_run(conn, safety_breach_count=1, live_trading="ENABLED")
        insert_cases(conn)
        insert_metrics(conn)
        insert_checks(conn)
        conn.commit()

    result = run_ai_offline_evaluation_governance_board(
        db_path=db_path,
        governance_review_label="safety-gov",
        report_label="safety-report",
        evaluation_label="eval-1",
    )

    assert result["governance_decision"] == DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED
    assert result["block_vote_count"] == 5


def test_governance_flags_unapproved_evaluation(tmp_path):
    db_path = tmp_path / "unapproved.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_run(
            conn,
            state="AI_OFFLINE_EVALUATION_HARNESS_UNSTABLE",
            decision="AI_OFFLINE_EVALUATION_UNSTABLE_REVIEW_REQUIRED",
            verdict="AI_OFFLINE_EVALUATION_UNSTABLE_SHADOW_ONLY",
        )
        insert_cases(conn)
        insert_metrics(conn)
        insert_checks(conn)
        conn.commit()

    result = run_ai_offline_evaluation_governance_board(
        db_path=db_path,
        governance_review_label="unapproved-gov",
        report_label="unapproved-report",
        evaluation_label="eval-1",
    )

    assert result["governance_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["review_vote_count"] == 5


def test_governance_flags_source_failed_checks(tmp_path):
    db_path = tmp_path / "failed-source.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_run(conn, fail_check_count=1)
        insert_cases(conn)
        insert_metrics(conn)
        insert_checks(conn)
        conn.commit()

    result = run_ai_offline_evaluation_governance_board(
        db_path=db_path,
        governance_review_label="failed-source-gov",
        report_label="failed-source-report",
        evaluation_label="eval-1",
    )

    assert result["governance_decision"] == DECISION_UNSTABLE
    assert result["fail_evidence_count"] >= 1


def test_governance_flags_leakage_breach(tmp_path):
    db_path = tmp_path / "leakage.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_run(conn, leakage_breach_count=1)
        insert_cases(conn)
        insert_metrics(conn)
        insert_checks(conn)
        conn.commit()

    result = run_ai_offline_evaluation_governance_board(
        db_path=db_path,
        governance_review_label="leakage-gov",
        report_label="leakage-report",
        evaluation_label="eval-1",
    )

    assert result["governance_decision"] == DECISION_UNSTABLE
    assert result["leakage_breach_count"] == 1


def test_governance_flags_missing_cases(tmp_path):
    db_path = tmp_path / "missing-cases.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_run(conn)
        insert_metrics(conn)
        insert_checks(conn)
        conn.commit()

    result = run_ai_offline_evaluation_governance_board(
        db_path=db_path,
        governance_review_label="missing-cases-gov",
        report_label="missing-cases-report",
        evaluation_label="eval-1",
    )

    assert result["governance_decision"] == DECISION_UNSTABLE
    assert result["evaluation_case_count"] == 0


def test_governance_flags_training_unlocked(tmp_path):
    db_path = tmp_path / "training.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_run(conn, training_eligible_count=1, training_locked_count=3)
        insert_cases(conn, training_eligible=1)
        insert_metrics(conn)
        insert_checks(conn)
        conn.commit()

    result = run_ai_offline_evaluation_governance_board(
        db_path=db_path,
        governance_review_label="training-gov",
        report_label="training-report",
        evaluation_label="eval-1",
    )

    assert result["governance_decision"] == DECISION_UNSTABLE
    assert result["training_eligible_count"] == 1


def test_markdown_report_contains_no_training_and_no_profit_claim(tmp_path):
    db_path = tmp_path / "markdown.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_offline_evaluation_governance_board(
        db_path=db_path,
        governance_review_label="markdown-gov",
        report_label="markdown-report",
        evaluation_label="eval-1",
    )

    assert "# DeltaGrid Mission 78" in result["markdown_report"]
    assert "does not train a model" in result["markdown_report"]
    assert "not profitability evidence" in result["markdown_report"]
    assert "No exchange orders were sent." in result["markdown_report"]

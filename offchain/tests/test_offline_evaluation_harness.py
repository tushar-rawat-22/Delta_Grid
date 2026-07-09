import json
import sqlite3

from offchain.ai_dataset.offline_evaluation_harness import (
    DECISION_BLOCK_SAFETY,
    DECISION_READY,
    DECISION_REJECT_MISSING,
    DECISION_UNSTABLE,
    TARGET_NEGATIVE,
    TARGET_NEUTRAL,
    TARGET_POSITIVE,
    VERDICT_BLOCKED,
    VERDICT_MISSING,
    VERDICT_READY,
    VERDICT_UNSTABLE,
    parse_labels,
    run_ai_offline_evaluation_harness,
)


def create_input_tables(conn):
    conn.execute(
        """
        CREATE TABLE ai_label_quality_leakage_guard_reviews (
            review_label TEXT PRIMARY KEY,
            source_collection_label TEXT,
            source_registry_label TEXT,
            source_build_label TEXT,
            source_schedule_label TEXT,
            source_guard_review_label TEXT,
            source_learning_run_label TEXT,
            source_multi_cycle_track_label TEXT,
            source_session_label TEXT,
            source_portfolio_label TEXT,
            guard_state TEXT,
            guard_decision TEXT,
            global_verdict TEXT,
            fail_check_count INTEGER,
            safety_breach_count INTEGER,
            leakage_breach_count INTEGER,
            average_label_confidence TEXT,
            average_net_paper_outcome_bps TEXT,
            worst_net_paper_outcome_bps TEXT,
            best_net_paper_outcome_bps TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_label_quality_leakage_guard_checks (
            check_id TEXT PRIMARY KEY,
            review_label TEXT,
            check_category TEXT,
            check_name TEXT,
            check_status TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_label_quality_leakage_guard_findings (
            finding_id TEXT PRIMARY KEY,
            review_label TEXT,
            finding_status TEXT,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_paper_outcome_final_labels (
            final_label_id TEXT PRIMARY KEY,
            collection_label TEXT,
            source_collection_record_id TEXT,
            source_feature_record_id TEXT,
            source_training_entry_id TEXT,
            outcome_label TEXT,
            target_label TEXT,
            net_paper_outcome_bps TEXT,
            label_confidence TEXT,
            training_eligible INTEGER,
            offline_evaluation_candidate INTEGER,
            live_trading TEXT,
            live_order_sent INTEGER,
            capital_deployment TEXT,
            metadata_json TEXT
        )
        """
    )


def insert_guard(
    conn,
    review_label="review-1",
    state="AI_LABEL_QUALITY_LEAKAGE_GUARD_READY",
    decision="AI_LABEL_QUALITY_LEAKAGE_GUARD_APPROVED_FOR_OFFLINE_EVALUATION",
    verdict="AI_LABEL_QUALITY_LEAKAGE_GUARD_READY_SHADOW_ONLY",
    fail_check_count=0,
    safety_breach_count=0,
    leakage_breach_count=0,
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO ai_label_quality_leakage_guard_reviews (
            review_label, source_collection_label, source_registry_label,
            source_build_label, source_schedule_label, source_guard_review_label,
            source_learning_run_label, source_multi_cycle_track_label,
            source_session_label, source_portfolio_label, guard_state,
            guard_decision, global_verdict, fail_check_count, safety_breach_count,
            leakage_breach_count, average_label_confidence,
            average_net_paper_outcome_bps, worst_net_paper_outcome_bps,
            best_net_paper_outcome_bps, live_trading, live_order_sent,
            capital_deployment
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review_label, "collection-1", "registry-1", "build-1", "schedule-1",
            "guard-upstream-1", "learning-1", "track-1", "session-1",
            "portfolio-1", state, decision, verdict, fail_check_count,
            safety_breach_count, leakage_breach_count, "0.65", "-2", "-2", "-2",
            live_trading, live_order_sent, capital_deployment,
        ),
    )


def insert_label(
    conn,
    collection_label="collection-1",
    index=1,
    target=TARGET_NEUTRAL,
    confidence="0.65",
    training_eligible=0,
    offline_candidate=1,
):
    outcome = {
        TARGET_POSITIVE: "AI_PAPER_OUTCOME_LABEL_POSITIVE_AFTER_COST",
        TARGET_NEUTRAL: "AI_PAPER_OUTCOME_LABEL_COST_DRAG_NEUTRAL",
        TARGET_NEGATIVE: "AI_PAPER_OUTCOME_LABEL_NEGATIVE_AFTER_COST",
    }.get(target, "AI_PAPER_OUTCOME_LABEL_COST_DRAG_NEUTRAL")

    conn.execute(
        """
        INSERT INTO ai_paper_outcome_final_labels (
            final_label_id, collection_label, source_collection_record_id,
            source_feature_record_id, source_training_entry_id, outcome_label,
            target_label, net_paper_outcome_bps, label_confidence,
            training_eligible, offline_evaluation_candidate, live_trading,
            live_order_sent, capital_deployment, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{collection_label}-label-{index}", collection_label,
            f"{collection_label}-record-{index}", f"feature-{index}",
            f"training-{index}", outcome, target, "-2", confidence,
            training_eligible, offline_candidate, "DISABLED", 0, "BLOCKED",
            json.dumps({}),
        ),
    )


def insert_check(conn, review_label="review-1"):
    conn.execute(
        """
        INSERT INTO ai_label_quality_leakage_guard_checks (
            check_id, review_label, check_category, check_name, check_status,
            live_trading, live_order_sent, capital_deployment
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{review_label}-safety", review_label, "safety",
            "safety breach count", "AI_LABEL_QUALITY_LEAKAGE_CHECK_PASS",
            "DISABLED", 0, "BLOCKED",
        ),
    )


def insert_clear_finding(conn, review_label="review-1"):
    conn.execute(
        """
        INSERT INTO ai_label_quality_leakage_guard_findings (
            finding_id, review_label, finding_status, live_trading,
            live_order_sent, capital_deployment
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            f"{review_label}-clear", review_label,
            "AI_LABEL_LEAKAGE_FINDING_CLEAR", "DISABLED", 0, "BLOCKED",
        ),
    )


def seed_good(conn):
    create_input_tables(conn)
    insert_guard(conn)
    for index in range(1, 5):
        insert_label(conn, index=index)
    insert_check(conn)
    insert_clear_finding(conn)


def test_parse_labels_deduplicates():
    assert parse_labels("review-1,review-2,review-1") == ["review-1", "review-2"]


def test_offline_evaluation_approves_good_guard_and_persists(tmp_path):
    db_path = tmp_path / "mission77.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_offline_evaluation_harness(
        db_path=db_path,
        evaluation_label="eval-1",
        report_label="report-1",
        guard_review_label="review-1",
    )

    assert result["evaluation_decision"] == DECISION_READY
    assert result["global_verdict"] == VERDICT_READY
    assert result["final_label_count"] == 4
    assert result["evaluation_case_count"] == 4
    assert result["metric_count"] == 10
    assert result["correct_prediction_count"] == 4
    assert result["baseline_accuracy_pct"] == 100.0
    assert result["pass_check_count"] == 16
    assert result["fail_check_count"] == 0

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT evaluation_label, evaluation_decision, global_verdict FROM ai_offline_evaluation_runs WHERE evaluation_label = ?",
            ("eval-1",),
        ).fetchone()

    assert row == ("eval-1", DECISION_READY, VERDICT_READY)


def test_offline_evaluation_rejects_missing_guard(tmp_path):
    result = run_ai_offline_evaluation_harness(
        db_path=tmp_path / "missing.db",
        evaluation_label="missing-eval",
        report_label="missing-report",
        guard_review_label="missing-review",
    )

    assert result["evaluation_decision"] == DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["fail_check_count"] == 1


def test_offline_evaluation_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "safety.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_guard(conn, safety_breach_count=1, live_trading="ENABLED")
        conn.commit()

    result = run_ai_offline_evaluation_harness(
        db_path=db_path,
        evaluation_label="safety-eval",
        report_label="safety-report",
        guard_review_label="review-1",
    )

    assert result["evaluation_decision"] == DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED


def test_offline_evaluation_flags_unapproved_guard(tmp_path):
    db_path = tmp_path / "unapproved.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_guard(
            conn,
            state="AI_LABEL_QUALITY_LEAKAGE_GUARD_UNSTABLE",
            decision="AI_LABEL_QUALITY_LEAKAGE_GUARD_UNSTABLE_REVIEW_REQUIRED",
            verdict="AI_LABEL_QUALITY_LEAKAGE_GUARD_UNSTABLE_SHADOW_ONLY",
        )
        conn.commit()

    result = run_ai_offline_evaluation_harness(
        db_path=db_path,
        evaluation_label="unapproved-eval",
        report_label="unapproved-report",
        guard_review_label="review-1",
    )

    assert result["evaluation_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE


def test_offline_evaluation_flags_leakage_breach(tmp_path):
    db_path = tmp_path / "leakage.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_guard(conn, leakage_breach_count=1)
        insert_clear_finding(conn)
        conn.commit()

    result = run_ai_offline_evaluation_harness(
        db_path=db_path,
        evaluation_label="leakage-eval",
        report_label="leakage-report",
        guard_review_label="review-1",
    )

    assert result["evaluation_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["leakage_breach_count"] == 1


def test_offline_evaluation_flags_missing_labels(tmp_path):
    db_path = tmp_path / "missing-labels.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_guard(conn)
        conn.commit()

    result = run_ai_offline_evaluation_harness(
        db_path=db_path,
        evaluation_label="missing-labels-eval",
        report_label="missing-labels-report",
        guard_review_label="review-1",
    )

    assert result["evaluation_decision"] == DECISION_UNSTABLE
    assert result["final_label_count"] == 0


def test_offline_evaluation_flags_low_confidence(tmp_path):
    db_path = tmp_path / "confidence.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.execute(
            "UPDATE ai_paper_outcome_final_labels SET label_confidence = ? WHERE final_label_id = ?",
            ("0.40", "collection-1-label-1"),
        )
        conn.commit()

    result = run_ai_offline_evaluation_harness(
        db_path=db_path,
        evaluation_label="confidence-eval",
        report_label="confidence-report",
        guard_review_label="review-1",
    )

    assert result["evaluation_decision"] == DECISION_UNSTABLE


def test_offline_evaluation_flags_training_unlocked(tmp_path):
    db_path = tmp_path / "training.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.execute(
            "UPDATE ai_paper_outcome_final_labels SET training_eligible = ? WHERE final_label_id = ?",
            (1, "collection-1-label-1"),
        )
        conn.commit()

    result = run_ai_offline_evaluation_harness(
        db_path=db_path,
        evaluation_label="training-eval",
        report_label="training-report",
        guard_review_label="review-1",
    )

    assert result["evaluation_decision"] == DECISION_UNSTABLE
    assert result["training_eligible_count"] == 1


def test_offline_evaluation_non_neutral_actuals_reduce_baseline_accuracy(tmp_path):
    db_path = tmp_path / "non-neutral.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_guard(conn)
        insert_label(conn, index=1, target=TARGET_POSITIVE)
        insert_label(conn, index=2, target=TARGET_NEGATIVE)
        insert_label(conn, index=3, target=TARGET_NEUTRAL)
        insert_label(conn, index=4, target=TARGET_NEUTRAL)
        insert_check(conn)
        insert_clear_finding(conn)
        conn.commit()

    result = run_ai_offline_evaluation_harness(
        db_path=db_path,
        evaluation_label="non-neutral-eval",
        report_label="non-neutral-report",
        guard_review_label="review-1",
    )

    assert result["evaluation_decision"] == DECISION_READY
    assert result["correct_prediction_count"] == 2
    assert result["incorrect_prediction_count"] == 2
    assert result["baseline_accuracy_pct"] == 50.0


def test_markdown_report_contains_no_training_scope(tmp_path):
    db_path = tmp_path / "markdown.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_offline_evaluation_harness(
        db_path=db_path,
        evaluation_label="markdown-eval",
        report_label="markdown-report",
        guard_review_label="review-1",
    )

    assert "# DeltaGrid Mission 77" in result["markdown_report"]
    assert "does not train a model" in result["markdown_report"]
    assert "not profitability evidence" in result["markdown_report"]
    assert "No exchange orders were sent." in result["markdown_report"]

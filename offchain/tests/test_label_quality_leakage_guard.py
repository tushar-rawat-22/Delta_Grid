import json
import sqlite3

from offchain.ai_dataset.label_quality_leakage_guard import (
    DECISION_BLOCK_SAFETY,
    DECISION_READY,
    DECISION_REJECT_MISSING,
    DECISION_UNSTABLE,
    FINDING_STATUS_BREACH,
    VERDICT_BLOCKED,
    VERDICT_MISSING,
    VERDICT_READY,
    VERDICT_UNSTABLE,
    parse_labels,
    run_ai_label_quality_leakage_guard,
)


def create_input_tables(conn):
    conn.execute(
        """
        CREATE TABLE ai_paper_outcome_collection_runs (
            collection_label TEXT PRIMARY KEY,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_registry_label TEXT,
            source_build_label TEXT,
            source_schedule_label TEXT,
            source_guard_review_label TEXT,
            source_learning_run_label TEXT,
            source_multi_cycle_track_label TEXT,
            source_session_label TEXT,
            source_portfolio_label TEXT,
            feature_record_count INTEGER NOT NULL,
            training_registry_entry_count INTEGER NOT NULL,
            collection_record_count INTEGER NOT NULL,
            final_label_count INTEGER NOT NULL,
            pending_before_count INTEGER NOT NULL,
            finalized_label_count INTEGER NOT NULL,
            training_eligible_count INTEGER NOT NULL,
            training_locked_count INTEGER NOT NULL,
            offline_evaluation_candidate_count INTEGER NOT NULL,
            lineage_complete_count INTEGER NOT NULL,
            collection_check_count INTEGER NOT NULL,
            pass_check_count INTEGER NOT NULL,
            fail_check_count INTEGER NOT NULL,
            safety_breach_count INTEGER NOT NULL,
            average_net_paper_outcome_bps TEXT NOT NULL,
            worst_net_paper_outcome_bps TEXT NOT NULL,
            best_net_paper_outcome_bps TEXT NOT NULL,
            average_fee_drag_bps TEXT NOT NULL,
            collection_mode TEXT NOT NULL,
            collection_state TEXT NOT NULL,
            collection_decision TEXT NOT NULL,
            global_verdict TEXT NOT NULL,
            recommended_action TEXT NOT NULL,
            next_mission TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            markdown_report TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_paper_outcome_collection_records (
            collection_record_id TEXT PRIMARY KEY,
            collection_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_registry_label TEXT NOT NULL,
            source_feature_record_id TEXT NOT NULL,
            source_training_entry_id TEXT,
            source_dataset_row_id TEXT,
            planned_symbol TEXT NOT NULL,
            planned_cycle_index INTEGER NOT NULL,
            gross_paper_outcome_bps TEXT NOT NULL,
            fee_drag_bps TEXT NOT NULL,
            net_paper_outcome_bps TEXT NOT NULL,
            outcome_label TEXT NOT NULL,
            target_label TEXT NOT NULL,
            label_confidence TEXT NOT NULL,
            training_eligible INTEGER NOT NULL,
            offline_evaluation_candidate INTEGER NOT NULL,
            collection_mode TEXT NOT NULL,
            collection_record_status TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_paper_outcome_final_labels (
            final_label_id TEXT PRIMARY KEY,
            collection_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_collection_record_id TEXT NOT NULL,
            source_feature_record_id TEXT NOT NULL,
            source_training_entry_id TEXT,
            outcome_label TEXT NOT NULL,
            target_label TEXT NOT NULL,
            net_paper_outcome_bps TEXT NOT NULL,
            label_confidence TEXT NOT NULL,
            final_label_status TEXT NOT NULL,
            training_eligible INTEGER NOT NULL,
            offline_evaluation_candidate INTEGER NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_paper_outcome_collection_checks (
            check_id TEXT PRIMARY KEY,
            collection_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_registry_label TEXT NOT NULL,
            check_category TEXT NOT NULL,
            check_name TEXT NOT NULL,
            check_status TEXT NOT NULL,
            observed_value TEXT NOT NULL,
            threshold_value TEXT NOT NULL,
            check_reason TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_run(
    conn,
    collection_label="collection-1",
    safety_breach_count=0,
    fail_check_count=0,
    state="AI_PAPER_OUTCOME_COLLECTION_LABELS_FINALIZED_TRAINING_LOCKED",
    decision="AI_PAPER_OUTCOME_COLLECTION_APPROVED_FOR_LABEL_QUALITY_REVIEW",
    verdict="AI_PAPER_OUTCOME_COLLECTION_READY_SHADOW_ONLY",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO ai_paper_outcome_collection_runs (
            collection_label, report_label, created_at, source_registry_label,
            source_build_label, source_schedule_label, source_guard_review_label,
            source_learning_run_label, source_multi_cycle_track_label,
            source_session_label, source_portfolio_label, feature_record_count,
            training_registry_entry_count, collection_record_count, final_label_count,
            pending_before_count, finalized_label_count, training_eligible_count,
            training_locked_count, offline_evaluation_candidate_count, lineage_complete_count,
            collection_check_count, pass_check_count, fail_check_count, safety_breach_count,
            average_net_paper_outcome_bps, worst_net_paper_outcome_bps,
            best_net_paper_outcome_bps, average_fee_drag_bps, collection_mode,
            collection_state, collection_decision, global_verdict, recommended_action,
            next_mission, live_trading, live_order_sent, capital_deployment,
            summary_json, markdown_report
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            collection_label, f"{collection_label}-report", "2026-01-01T00:00:00+00:00",
            "registry-1", "build-1", "schedule-1", "guard-1", "learning-1",
            "track-1", "session-1", "portfolio-1", 4, 4, 4, 4, 4, 4, 0, 4, 4, 4,
            16, 16, fail_check_count, safety_breach_count, "-2", "-2", "-2", "2",
            "LOCAL_DETERMINISTIC_PAPER_OUTCOME_LABEL_FINALIZATION", state, decision,
            verdict, "HAND_OFF_FINALIZED_LABELS_TO_LABEL_QUALITY_GUARD",
            "Mission 76 AI Label Quality and Leakage Guard", live_trading,
            live_order_sent, capital_deployment, "{}", "# report",
        ),
    )


def insert_record(conn, collection_label="collection-1", index=1, symbol="BTCUSDT", metadata=None):
    if metadata is None:
        metadata = {}

    conn.execute(
        """
        INSERT INTO ai_paper_outcome_collection_records (
            collection_record_id, collection_label, created_at, source_registry_label,
            source_feature_record_id, source_training_entry_id, source_dataset_row_id,
            planned_symbol, planned_cycle_index, gross_paper_outcome_bps, fee_drag_bps,
            net_paper_outcome_bps, outcome_label, target_label, label_confidence,
            training_eligible, offline_evaluation_candidate, collection_mode,
            collection_record_status, live_trading, live_order_sent, capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{collection_label}-record-{index}", collection_label,
            "2026-01-01T00:00:00+00:00", "registry-1", f"feature-{index}",
            f"training-{index}", f"dataset-{index}", symbol, index, "0", "2", "-2",
            "AI_PAPER_OUTCOME_LABEL_COST_DRAG_NEUTRAL",
            "AI_TARGET_LABEL_COST_DRAG_NEUTRAL_EARLY", "0.65", 0, 1,
            "LOCAL_DETERMINISTIC_PAPER_OUTCOME_LABEL_FINALIZATION",
            "AI_PAPER_OUTCOME_COLLECTION_RECORD_FINALIZED", "DISABLED", 0,
            "BLOCKED", json.dumps(metadata),
        ),
    )


def insert_label(
    conn,
    collection_label="collection-1",
    index=1,
    outcome="AI_PAPER_OUTCOME_LABEL_COST_DRAG_NEUTRAL",
    target="AI_TARGET_LABEL_COST_DRAG_NEUTRAL_EARLY",
    confidence="0.65",
    training_eligible=0,
    offline_candidate=1,
    metadata=None,
):
    if metadata is None:
        metadata = {}

    conn.execute(
        """
        INSERT INTO ai_paper_outcome_final_labels (
            final_label_id, collection_label, created_at, source_collection_record_id,
            source_feature_record_id, source_training_entry_id, outcome_label,
            target_label, net_paper_outcome_bps, label_confidence, final_label_status,
            training_eligible, offline_evaluation_candidate, live_trading, live_order_sent,
            capital_deployment, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{collection_label}-label-{index}", collection_label,
            "2026-01-01T00:00:00+00:00", f"{collection_label}-record-{index}",
            f"feature-{index}", f"training-{index}", outcome, target, "-2",
            confidence, "AI_PAPER_OUTCOME_FINAL_LABEL_READY_TRAINING_LOCKED",
            training_eligible, offline_candidate, "DISABLED", 0, "BLOCKED",
            json.dumps(metadata),
        ),
    )


def insert_check(conn, collection_label="collection-1"):
    conn.execute(
        """
        INSERT INTO ai_paper_outcome_collection_checks (
            check_id, collection_label, created_at, source_registry_label,
            check_category, check_name, check_status, observed_value, threshold_value,
            check_reason, live_trading, live_order_sent, capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{collection_label}-safety", collection_label,
            "2026-01-01T00:00:00+00:00", "registry-1", "safety",
            "safety breach count", "AI_PAPER_OUTCOME_COLLECTION_CHECK_PASS",
            "0", "0", "test", "DISABLED", 0, "BLOCKED", "{}",
        ),
    )


def seed_good(conn):
    create_input_tables(conn)
    insert_run(conn)
    for index, symbol in enumerate(["BTCUSDT", "ETHUSDT", "BTCUSDT", "ETHUSDT"], start=1):
        insert_record(conn, index=index, symbol=symbol)
        insert_label(conn, index=index)
    insert_check(conn)


def test_parse_labels_deduplicates():
    assert parse_labels("collection-1,collection-2,collection-1") == ["collection-1", "collection-2"]


def test_guard_approves_good_labels_and_persists(tmp_path):
    db_path = tmp_path / "mission76.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_label_quality_leakage_guard(
        db_path=db_path,
        review_label="review-1",
        report_label="report-1",
        collection_label="collection-1",
    )

    assert result["guard_decision"] == DECISION_READY
    assert result["global_verdict"] == VERDICT_READY
    assert result["final_label_count"] == 4
    assert result["allowed_label_count"] == 4
    assert result["leakage_breach_count"] == 0
    assert result["quality_check_count"] == 16
    assert result["pass_check_count"] == 16
    assert result["fail_check_count"] == 0

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT review_label, guard_decision, global_verdict FROM ai_label_quality_leakage_guard_reviews WHERE review_label = ?",
            ("review-1",),
        ).fetchone()

    assert row == ("review-1", DECISION_READY, VERDICT_READY)


def test_guard_rejects_missing_collection(tmp_path):
    result = run_ai_label_quality_leakage_guard(
        db_path=tmp_path / "missing.db",
        review_label="missing-review",
        report_label="missing-report",
        collection_label="missing-collection",
    )

    assert result["guard_decision"] == DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["fail_check_count"] == 1


def test_guard_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "safety.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_run(conn, safety_breach_count=1, live_trading="ENABLED")
        conn.commit()

    result = run_ai_label_quality_leakage_guard(
        db_path=db_path,
        review_label="safety-review",
        report_label="safety-report",
        collection_label="collection-1",
    )

    assert result["guard_decision"] == DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED


def test_guard_flags_unapproved_collection(tmp_path):
    db_path = tmp_path / "unapproved.db"
    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_run(
            conn,
            state="AI_PAPER_OUTCOME_COLLECTION_UNSTABLE",
            decision="AI_PAPER_OUTCOME_COLLECTION_UNSTABLE_REVIEW_REQUIRED",
            verdict="AI_PAPER_OUTCOME_COLLECTION_UNSTABLE_SHADOW_ONLY",
        )
        conn.commit()

    result = run_ai_label_quality_leakage_guard(
        db_path=db_path,
        review_label="unapproved-review",
        report_label="unapproved-report",
        collection_label="collection-1",
    )

    assert result["guard_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE


def test_guard_flags_pending_label(tmp_path):
    db_path = tmp_path / "pending.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.execute(
            "UPDATE ai_paper_outcome_final_labels SET outcome_label = ? WHERE final_label_id = ?",
            ("AI_OUTCOME_DATASET_LABEL_PENDING_PAPER_OBSERVATION", "collection-1-label-1"),
        )
        conn.commit()

    result = run_ai_label_quality_leakage_guard(
        db_path=db_path,
        review_label="pending-review",
        report_label="pending-report",
        collection_label="collection-1",
    )

    assert result["guard_decision"] == DECISION_UNSTABLE
    assert result["pending_label_count"] == 1


def test_guard_flags_low_confidence(tmp_path):
    db_path = tmp_path / "confidence.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.execute(
            "UPDATE ai_paper_outcome_final_labels SET label_confidence = ? WHERE final_label_id = ?",
            ("0.40", "collection-1-label-1"),
        )
        conn.commit()

    result = run_ai_label_quality_leakage_guard(
        db_path=db_path,
        review_label="confidence-review",
        report_label="confidence-report",
        collection_label="collection-1",
        min_label_confidence=0.60,
    )

    assert result["guard_decision"] == DECISION_UNSTABLE
    assert result["low_confidence_label_count"] == 1


def test_guard_flags_training_unlocked(tmp_path):
    db_path = tmp_path / "training.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.execute(
            "UPDATE ai_paper_outcome_final_labels SET training_eligible = ? WHERE final_label_id = ?",
            (1, "collection-1-label-1"),
        )
        conn.commit()

    result = run_ai_label_quality_leakage_guard(
        db_path=db_path,
        review_label="training-review",
        report_label="training-report",
        collection_label="collection-1",
    )

    assert result["guard_decision"] == DECISION_UNSTABLE
    assert result["training_eligible_count"] == 1


def test_guard_detects_leakage_in_metadata(tmp_path):
    db_path = tmp_path / "leakage.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.execute(
            "UPDATE ai_paper_outcome_final_labels SET metadata_json = ? WHERE final_label_id = ?",
            (json.dumps({"future_price": 12345}), "collection-1-label-1"),
        )
        conn.commit()

    result = run_ai_label_quality_leakage_guard(
        db_path=db_path,
        review_label="leakage-review",
        report_label="leakage-report",
        collection_label="collection-1",
    )

    assert result["guard_decision"] == DECISION_UNSTABLE
    assert result["leakage_breach_count"] >= 1
    assert any(f["finding_status"] == FINDING_STATUS_BREACH for f in result["leakage_findings"])


def test_guard_flags_missing_lineage(tmp_path):
    db_path = tmp_path / "lineage.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.execute(
            "UPDATE ai_paper_outcome_final_labels SET source_training_entry_id = ? WHERE final_label_id = ?",
            ("", "collection-1-label-1"),
        )
        conn.commit()

    result = run_ai_label_quality_leakage_guard(
        db_path=db_path,
        review_label="lineage-review",
        report_label="lineage-report",
        collection_label="collection-1",
    )

    assert result["guard_decision"] == DECISION_UNSTABLE
    assert result["lineage_complete_count"] == 3


def test_markdown_report_contains_training_locked_scope(tmp_path):
    db_path = tmp_path / "markdown.db"
    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_label_quality_leakage_guard(
        db_path=db_path,
        review_label="markdown-review",
        report_label="markdown-report",
        collection_label="collection-1",
    )

    assert "# DeltaGrid Mission 76" in result["markdown_report"]
    assert "does not train a model" in result["markdown_report"]
    assert "Training remains locked" in result["markdown_report"]
    assert "No exchange orders were sent." in result["markdown_report"]

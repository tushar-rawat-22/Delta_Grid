import json
import sqlite3

from offchain.ai_dataset.paper_outcome_label_finalizer import (
    COLLECTION_STATE_READY_LOCKED,
    DECISION_BLOCK_SAFETY,
    DECISION_READY_LOCKED,
    DECISION_REJECT_MISSING,
    DECISION_UNSTABLE,
    OUTCOME_NEGATIVE,
    OUTCOME_NEUTRAL,
    OUTCOME_POSITIVE,
    VERDICT_BLOCKED,
    VERDICT_MISSING,
    VERDICT_READY,
    VERDICT_UNSTABLE,
    parse_labels,
    run_ai_paper_outcome_label_finalizer,
)


def create_input_tables(conn):
    conn.execute(
        """
        CREATE TABLE ai_feature_store_training_registries (
            registry_label TEXT PRIMARY KEY,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_build_label TEXT,
            source_schedule_label TEXT,
            source_guard_review_label TEXT,
            source_learning_run_label TEXT,
            source_multi_cycle_track_label TEXT,
            source_session_label TEXT,
            source_portfolio_label TEXT,
            dataset_row_count INTEGER NOT NULL,
            feature_record_count INTEGER NOT NULL,
            training_registry_entry_count INTEGER NOT NULL,
            pending_outcome_count INTEGER NOT NULL,
            training_eligible_count INTEGER NOT NULL,
            training_locked_count INTEGER NOT NULL,
            lineage_complete_count INTEGER NOT NULL,
            feature_snapshot_complete_count INTEGER NOT NULL,
            registry_check_count INTEGER NOT NULL,
            pass_check_count INTEGER NOT NULL,
            fail_check_count INTEGER NOT NULL,
            safety_breach_count INTEGER NOT NULL,
            learning_score TEXT NOT NULL,
            max_feature_drift TEXT NOT NULL,
            feature_namespace TEXT NOT NULL,
            feature_version TEXT NOT NULL,
            registry_state TEXT NOT NULL,
            registry_decision TEXT NOT NULL,
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
        CREATE TABLE ai_feature_store_feature_records (
            feature_record_id TEXT PRIMARY KEY,
            registry_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_build_label TEXT,
            source_dataset_row_id TEXT,
            source_schedule_label TEXT,
            source_guard_review_label TEXT,
            source_learning_run_label TEXT,
            source_multi_cycle_track_label TEXT,
            source_session_label TEXT,
            source_portfolio_label TEXT,
            feature_namespace TEXT NOT NULL,
            feature_version TEXT NOT NULL,
            planned_symbol TEXT NOT NULL,
            planned_cycle_index INTEGER NOT NULL,
            feature_snapshot_json TEXT NOT NULL,
            outcome_label TEXT NOT NULL,
            target_label TEXT NOT NULL,
            training_eligible INTEGER NOT NULL,
            feature_record_status TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_training_dataset_registry_entries (
            training_entry_id TEXT PRIMARY KEY,
            registry_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_feature_record_id TEXT NOT NULL,
            source_dataset_row_id TEXT,
            source_build_label TEXT,
            training_entry_status TEXT NOT NULL,
            training_eligible INTEGER NOT NULL,
            outcome_label TEXT NOT NULL,
            target_label TEXT NOT NULL,
            exclusion_reason TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_feature_store_training_registry_checks (
            check_id TEXT PRIMARY KEY,
            registry_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_build_label TEXT NOT NULL,
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


def insert_registry(
    conn,
    registry_label="registry-1",
    safety_breach_count=0,
    fail_check_count=0,
    state="AI_FEATURE_STORE_REGISTRY_READY_TRAINING_LOCKED",
    decision="AI_FEATURE_STORE_REGISTRY_APPROVED_TRAINING_LOCKED",
    verdict="AI_FEATURE_STORE_TRAINING_REGISTRY_READY_SHADOW_ONLY",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO ai_feature_store_training_registries (
            registry_label,
            report_label,
            created_at,
            source_build_label,
            source_schedule_label,
            source_guard_review_label,
            source_learning_run_label,
            source_multi_cycle_track_label,
            source_session_label,
            source_portfolio_label,
            dataset_row_count,
            feature_record_count,
            training_registry_entry_count,
            pending_outcome_count,
            training_eligible_count,
            training_locked_count,
            lineage_complete_count,
            feature_snapshot_complete_count,
            registry_check_count,
            pass_check_count,
            fail_check_count,
            safety_breach_count,
            learning_score,
            max_feature_drift,
            feature_namespace,
            feature_version,
            registry_state,
            registry_decision,
            global_verdict,
            recommended_action,
            next_mission,
            live_trading,
            live_order_sent,
            capital_deployment,
            summary_json,
            markdown_report
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            registry_label,
            f"{registry_label}-report",
            "2026-01-01T00:00:00+00:00",
            "build-1",
            "schedule-1",
            "guard-1",
            "learning-1",
            "track-1",
            "session-1",
            "portfolio-1",
            4,
            4,
            4,
            4,
            0,
            4,
            4,
            4,
            15,
            15,
            fail_check_count,
            safety_breach_count,
            "84.8641975",
            "0",
            "paper_outcome_feature_store",
            "v1",
            state,
            decision,
            verdict,
            "CONTINUE_PAPER_OUTCOME_COLLECTION_BEFORE_TRAINING_DATASET_ACTIVATION",
            "Mission 75 AI Paper Outcome Collection and Label Finalizer",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
            "# report",
        ),
    )


def insert_feature_record(conn, registry_label="registry-1", index=1, symbol="BTCUSDT", cycle=1, source_learning="learning-1"):
    feature_id = f"{registry_label}-feature-{index}"
    snapshot = {
        "learning_score": 84.8641975,
        "max_feature_drift": 0.0,
        "planned_cycle_count": 2,
        "planned_symbol_count": 2,
    }

    conn.execute(
        """
        INSERT INTO ai_feature_store_feature_records (
            feature_record_id,
            registry_label,
            created_at,
            source_build_label,
            source_dataset_row_id,
            source_schedule_label,
            source_guard_review_label,
            source_learning_run_label,
            source_multi_cycle_track_label,
            source_session_label,
            source_portfolio_label,
            feature_namespace,
            feature_version,
            planned_symbol,
            planned_cycle_index,
            feature_snapshot_json,
            outcome_label,
            target_label,
            training_eligible,
            feature_record_status,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            feature_id,
            registry_label,
            "2026-01-01T00:00:00+00:00",
            "build-1",
            f"dataset-row-{index}",
            "schedule-1",
            "guard-1",
            source_learning,
            "track-1",
            "session-1",
            "portfolio-1",
            "paper_outcome_feature_store",
            "v1",
            symbol,
            cycle,
            json.dumps(snapshot),
            "AI_OUTCOME_DATASET_LABEL_PENDING_PAPER_OBSERVATION",
            "AI_OUTCOME_TARGET_PENDING_COLLECTION",
            0,
            "AI_FEATURE_STORE_RECORD_REGISTERED_PENDING_OUTCOME",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
        ),
    )

    return feature_id


def insert_training_entry(conn, registry_label="registry-1", feature_id="registry-1-feature-1", index=1):
    conn.execute(
        """
        INSERT INTO ai_training_dataset_registry_entries (
            training_entry_id,
            registry_label,
            created_at,
            source_feature_record_id,
            source_dataset_row_id,
            source_build_label,
            training_entry_status,
            training_eligible,
            outcome_label,
            target_label,
            exclusion_reason,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{feature_id}-training-entry",
            registry_label,
            "2026-01-01T00:00:00+00:00",
            feature_id,
            f"dataset-row-{index}",
            "build-1",
            "AI_TRAINING_DATASET_ENTRY_LOCKED_PENDING_OUTCOME",
            0,
            "AI_OUTCOME_DATASET_LABEL_PENDING_PAPER_OBSERVATION",
            "AI_OUTCOME_TARGET_PENDING_COLLECTION",
            "pending",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
        ),
    )


def insert_registry_check(conn, registry_label="registry-1"):
    conn.execute(
        """
        INSERT INTO ai_feature_store_training_registry_checks (
            check_id,
            registry_label,
            created_at,
            source_build_label,
            check_category,
            check_name,
            check_status,
            observed_value,
            threshold_value,
            check_reason,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{registry_label}-safety",
            registry_label,
            "2026-01-01T00:00:00+00:00",
            "build-1",
            "safety",
            "safety breach count",
            "AI_FEATURE_STORE_REGISTRY_CHECK_PASS",
            "0",
            "0",
            "test",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
        ),
    )


def seed_good(conn):
    create_input_tables(conn)
    insert_registry(conn)

    features = [
        insert_feature_record(conn, index=1, symbol="BTCUSDT", cycle=1),
        insert_feature_record(conn, index=2, symbol="ETHUSDT", cycle=1),
        insert_feature_record(conn, index=3, symbol="BTCUSDT", cycle=2),
        insert_feature_record(conn, index=4, symbol="ETHUSDT", cycle=2),
    ]

    for index, feature_id in enumerate(features, start=1):
        insert_training_entry(conn, feature_id=feature_id, index=index)

    insert_registry_check(conn)


def test_parse_labels_deduplicates():
    assert parse_labels("registry-1,registry-2,registry-1") == ["registry-1", "registry-2"]


def test_finalizer_collects_and_finalizes_labels(tmp_path):
    db_path = tmp_path / "mission75.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_paper_outcome_label_finalizer(
        db_path=db_path,
        collection_label="collection-1",
        report_label="report-1",
        registry_label="registry-1",
    )

    assert result["collection_decision"] == DECISION_READY_LOCKED
    assert result["global_verdict"] == VERDICT_READY
    assert result["collection_state"] == COLLECTION_STATE_READY_LOCKED
    assert result["feature_record_count"] == 4
    assert result["collection_record_count"] == 4
    assert result["final_label_count"] == 4
    assert result["pending_before_count"] == 4
    assert result["finalized_label_count"] == 4
    assert result["training_eligible_count"] == 0
    assert result["training_locked_count"] == 4
    assert result["offline_evaluation_candidate_count"] == 4
    assert result["collection_check_count"] == 16
    assert result["pass_check_count"] == 16
    assert result["fail_check_count"] == 0
    assert result["average_net_paper_outcome_bps"] == -2.0

    with sqlite3.connect(db_path) as conn:
        run = conn.execute(
            """
            SELECT collection_label, collection_decision, global_verdict
            FROM ai_paper_outcome_collection_runs
            WHERE collection_label = ?
            """,
            ("collection-1",),
        ).fetchone()

        label_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM ai_paper_outcome_final_labels
            WHERE collection_label = ?
            """,
            ("collection-1",),
        ).fetchone()[0]

    assert run == ("collection-1", DECISION_READY_LOCKED, VERDICT_READY)
    assert label_count == 4


def test_finalizer_rejects_missing_registry(tmp_path):
    db_path = tmp_path / "mission75-missing.db"

    result = run_ai_paper_outcome_label_finalizer(
        db_path=db_path,
        collection_label="missing-collection",
        report_label="missing-report",
        registry_label="missing-registry",
    )

    assert result["collection_decision"] == DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["fail_check_count"] == 1


def test_finalizer_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission75-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_registry(conn, safety_breach_count=1, live_trading="ENABLED")
        conn.commit()

    result = run_ai_paper_outcome_label_finalizer(
        db_path=db_path,
        collection_label="safety-collection",
        report_label="safety-report",
        registry_label="registry-1",
    )

    assert result["collection_decision"] == DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED
    assert result["safety_breach_count"] >= 1


def test_finalizer_flags_unapproved_registry(tmp_path):
    db_path = tmp_path / "mission75-unapproved.db"

    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_registry(
            conn,
            state="AI_FEATURE_STORE_REGISTRY_UNSTABLE",
            decision="AI_FEATURE_STORE_REGISTRY_UNSTABLE_REVIEW_REQUIRED",
            verdict="AI_FEATURE_STORE_TRAINING_REGISTRY_UNSTABLE_SHADOW_ONLY",
        )
        conn.commit()

    result = run_ai_paper_outcome_label_finalizer(
        db_path=db_path,
        collection_label="unapproved-collection",
        report_label="unapproved-report",
        registry_label="registry-1",
    )

    assert result["collection_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE


def test_finalizer_flags_missing_feature_records(tmp_path):
    db_path = tmp_path / "mission75-missing-records.db"

    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_registry(conn)
        conn.commit()

    result = run_ai_paper_outcome_label_finalizer(
        db_path=db_path,
        collection_label="missing-records-collection",
        report_label="missing-records-report",
        registry_label="registry-1",
    )

    assert result["collection_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["feature_record_count"] == 0


def test_finalizer_flags_missing_training_entries(tmp_path):
    db_path = tmp_path / "mission75-training.db"

    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_registry(conn)
        insert_feature_record(conn, index=1, symbol="BTCUSDT", cycle=1)
        insert_feature_record(conn, index=2, symbol="ETHUSDT", cycle=1)
        insert_feature_record(conn, index=3, symbol="BTCUSDT", cycle=2)
        insert_feature_record(conn, index=4, symbol="ETHUSDT", cycle=2)
        conn.commit()

    result = run_ai_paper_outcome_label_finalizer(
        db_path=db_path,
        collection_label="training-collection",
        report_label="training-report",
        registry_label="registry-1",
    )

    assert result["collection_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["training_registry_entry_count"] == 0


def test_finalizer_preserves_training_lock(tmp_path):
    db_path = tmp_path / "mission75-lock.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_paper_outcome_label_finalizer(
        db_path=db_path,
        collection_label="lock-collection",
        report_label="lock-report",
        registry_label="registry-1",
    )

    assert all(label["training_eligible"] == 0 for label in result["final_labels"])
    assert all(record["training_eligible"] == 0 for record in result["collection_records"])
    assert result["offline_evaluation_candidate_count"] == 4


def test_finalizer_positive_label_path(tmp_path):
    db_path = tmp_path / "mission75-positive.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_paper_outcome_label_finalizer(
        db_path=db_path,
        collection_label="positive-collection",
        report_label="positive-report",
        registry_label="registry-1",
        gross_outcome_bps=12,
        fee_drag_bps=2,
    )

    assert result["average_net_paper_outcome_bps"] == 10.0
    assert all(label["outcome_label"] == OUTCOME_POSITIVE for label in result["final_labels"])


def test_finalizer_negative_label_path(tmp_path):
    db_path = tmp_path / "mission75-negative.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_paper_outcome_label_finalizer(
        db_path=db_path,
        collection_label="negative-collection",
        report_label="negative-report",
        registry_label="registry-1",
        gross_outcome_bps=-10,
        fee_drag_bps=2,
    )

    assert result["average_net_paper_outcome_bps"] == -12.0
    assert all(label["outcome_label"] == OUTCOME_NEGATIVE for label in result["final_labels"])


def test_finalizer_neutral_default_label_path(tmp_path):
    db_path = tmp_path / "mission75-neutral.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_paper_outcome_label_finalizer(
        db_path=db_path,
        collection_label="neutral-collection",
        report_label="neutral-report",
        registry_label="registry-1",
    )

    assert all(label["outcome_label"] == OUTCOME_NEUTRAL for label in result["final_labels"])


def test_markdown_report_contains_training_locked_scope(tmp_path):
    db_path = tmp_path / "mission75-markdown.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_paper_outcome_label_finalizer(
        db_path=db_path,
        collection_label="markdown-collection",
        report_label="markdown-report",
        registry_label="registry-1",
    )

    assert "# DeltaGrid Mission 75" in result["markdown_report"]
    assert "does not train a model" in result["markdown_report"]
    assert "Training remains locked" in result["markdown_report"]
    assert "No exchange orders were sent." in result["markdown_report"]

import json
import sqlite3

from offchain.ai_dataset.feature_store_training_registry import (
    DECISION_BLOCK_SAFETY,
    DECISION_READY_LOCKED,
    DECISION_REJECT_MISSING,
    DECISION_UNSTABLE,
    FEATURE_RECORD_STATUS,
    HANDOFF_STATUS_READY,
    TRAINING_ENTRY_STATUS_LOCKED,
    VERDICT_BLOCKED,
    VERDICT_MISSING,
    VERDICT_READY,
    VERDICT_UNSTABLE,
    parse_labels,
    run_ai_feature_store_training_registry,
)


def create_input_tables(conn):
    conn.execute(
        """
        CREATE TABLE ai_outcome_dataset_builds (
            build_label TEXT PRIMARY KEY,
            report_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_schedule_label TEXT,
            source_guard_review_label TEXT,
            source_learning_run_label TEXT,
            source_multi_cycle_track_label TEXT,
            source_session_label TEXT,
            source_portfolio_label TEXT,
            planned_cycle_count INTEGER NOT NULL,
            planned_symbol_count INTEGER NOT NULL,
            planned_item_count INTEGER NOT NULL,
            dataset_row_count INTEGER NOT NULL,
            pending_outcome_count INTEGER NOT NULL,
            training_eligible_count INTEGER NOT NULL,
            lineage_complete_count INTEGER NOT NULL,
            quality_check_count INTEGER NOT NULL,
            pass_check_count INTEGER NOT NULL,
            fail_check_count INTEGER NOT NULL,
            safety_breach_count INTEGER NOT NULL,
            learning_score TEXT NOT NULL,
            max_feature_drift TEXT NOT NULL,
            build_state TEXT NOT NULL,
            build_decision TEXT NOT NULL,
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
        CREATE TABLE ai_outcome_dataset_rows (
            dataset_row_id TEXT PRIMARY KEY,
            build_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_schedule_label TEXT,
            source_schedule_item_id TEXT NOT NULL,
            source_guard_review_label TEXT,
            source_learning_run_label TEXT,
            source_multi_cycle_track_label TEXT,
            source_session_label TEXT,
            source_portfolio_label TEXT,
            row_index INTEGER NOT NULL,
            planned_cycle_index INTEGER NOT NULL,
            planned_symbol TEXT NOT NULL,
            planned_start_at TEXT NOT NULL,
            planned_end_at TEXT NOT NULL,
            outcome_label TEXT NOT NULL,
            target_label TEXT NOT NULL,
            training_eligible INTEGER NOT NULL,
            row_status TEXT NOT NULL,
            feature_snapshot_json TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE ai_outcome_dataset_quality_checks (
            check_id TEXT PRIMARY KEY,
            build_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_schedule_label TEXT NOT NULL,
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

    conn.execute(
        """
        CREATE TABLE ai_outcome_dataset_handoffs (
            handoff_id TEXT PRIMARY KEY,
            build_label TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_schedule_label TEXT NOT NULL,
            target_mission TEXT NOT NULL,
            handoff_status TEXT NOT NULL,
            dataset_row_count INTEGER NOT NULL,
            training_eligible_count INTEGER NOT NULL,
            handoff_reason TEXT NOT NULL,
            live_trading TEXT NOT NULL,
            live_order_sent INTEGER NOT NULL,
            capital_deployment TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """
    )


def insert_build(
    conn,
    build_label="build-1",
    safety_breach_count=0,
    fail_check_count=0,
    build_state="AI_OUTCOME_DATASET_BUILD_READY",
    build_decision="AI_OUTCOME_DATASET_BUILD_APPROVED_FOR_FEATURE_STORE_HANDOFF",
    verdict="AI_OUTCOME_DATASET_BUILD_READY_SHADOW_ONLY",
    live_trading="DISABLED",
    live_order_sent=0,
    capital_deployment="BLOCKED",
):
    conn.execute(
        """
        INSERT INTO ai_outcome_dataset_builds (
            build_label,
            report_label,
            created_at,
            source_schedule_label,
            source_guard_review_label,
            source_learning_run_label,
            source_multi_cycle_track_label,
            source_session_label,
            source_portfolio_label,
            planned_cycle_count,
            planned_symbol_count,
            planned_item_count,
            dataset_row_count,
            pending_outcome_count,
            training_eligible_count,
            lineage_complete_count,
            quality_check_count,
            pass_check_count,
            fail_check_count,
            safety_breach_count,
            learning_score,
            max_feature_drift,
            build_state,
            build_decision,
            global_verdict,
            recommended_action,
            next_mission,
            live_trading,
            live_order_sent,
            capital_deployment,
            summary_json,
            markdown_report
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            build_label,
            f"{build_label}-report",
            "2026-01-01T00:00:00+00:00",
            "schedule-1",
            "guard-1",
            "learning-1",
            "track-1",
            "session-1",
            "portfolio-1",
            2,
            2,
            4,
            4,
            4,
            0,
            4,
            14,
            14,
            fail_check_count,
            safety_breach_count,
            "84.8641975",
            "0",
            build_state,
            build_decision,
            verdict,
            "HAND_OFF_AI_OUTCOME_DATASET_TO_FEATURE_STORE",
            "Mission 74 AI Feature Store and Training Dataset Registry",
            live_trading,
            live_order_sent,
            capital_deployment,
            "{}",
            "# report",
        ),
    )


def insert_row(
    conn,
    build_label="build-1",
    row_index=1,
    symbol="BTCUSDT",
    cycle=1,
    feature_snapshot=None,
    source_learning="learning-1",
):
    if feature_snapshot is None:
        feature_snapshot = {
            "learning_score": 84.8641975,
            "max_feature_drift": 0.0,
            "planned_cycle_count": 2,
            "planned_symbol_count": 2,
        }

    conn.execute(
        """
        INSERT INTO ai_outcome_dataset_rows (
            dataset_row_id,
            build_label,
            created_at,
            source_schedule_label,
            source_schedule_item_id,
            source_guard_review_label,
            source_learning_run_label,
            source_multi_cycle_track_label,
            source_session_label,
            source_portfolio_label,
            row_index,
            planned_cycle_index,
            planned_symbol,
            planned_start_at,
            planned_end_at,
            outcome_label,
            target_label,
            training_eligible,
            row_status,
            feature_snapshot_json,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{build_label}-row-{row_index}",
            build_label,
            "2026-01-01T00:00:00+00:00",
            "schedule-1",
            f"schedule-1-cycle-{cycle}-{symbol}",
            "guard-1",
            source_learning,
            "track-1",
            "session-1",
            "portfolio-1",
            row_index,
            cycle,
            symbol,
            "2026-01-01T00:00:00+00:00",
            "2026-01-02T00:00:00+00:00",
            "AI_OUTCOME_DATASET_LABEL_PENDING_PAPER_OBSERVATION",
            "AI_OUTCOME_TARGET_PENDING_COLLECTION",
            0,
            "AI_OUTCOME_DATASET_ROW_READY_FOR_PAPER_COLLECTION",
            json.dumps(feature_snapshot),
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
        ),
    )


def insert_quality_check(conn, build_label="build-1"):
    conn.execute(
        """
        INSERT INTO ai_outcome_dataset_quality_checks (
            check_id,
            build_label,
            created_at,
            source_schedule_label,
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
            f"{build_label}-safety",
            build_label,
            "2026-01-01T00:00:00+00:00",
            "schedule-1",
            "safety",
            "safety breach count",
            "AI_OUTCOME_DATASET_CHECK_PASS",
            "0",
            "0",
            "test",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
        ),
    )


def insert_handoff(conn, build_label="build-1", status=HANDOFF_STATUS_READY):
    conn.execute(
        """
        INSERT INTO ai_outcome_dataset_handoffs (
            handoff_id,
            build_label,
            created_at,
            source_schedule_label,
            target_mission,
            handoff_status,
            dataset_row_count,
            training_eligible_count,
            handoff_reason,
            live_trading,
            live_order_sent,
            capital_deployment,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{build_label}-handoff",
            build_label,
            "2026-01-01T00:00:00+00:00",
            "schedule-1",
            "Mission 74 AI Feature Store and Training Dataset Registry",
            status,
            4,
            0,
            "test",
            "DISABLED",
            0,
            "BLOCKED",
            "{}",
        ),
    )


def seed_good(conn):
    create_input_tables(conn)
    insert_build(conn)
    insert_row(conn, row_index=1, symbol="BTCUSDT", cycle=1)
    insert_row(conn, row_index=2, symbol="ETHUSDT", cycle=1)
    insert_row(conn, row_index=3, symbol="BTCUSDT", cycle=2)
    insert_row(conn, row_index=4, symbol="ETHUSDT", cycle=2)
    insert_quality_check(conn)
    insert_handoff(conn)


def test_parse_labels_deduplicates():
    assert parse_labels("build-1,build-2,build-1") == ["build-1", "build-2"]


def test_registry_registers_good_build_and_persists(tmp_path):
    db_path = tmp_path / "mission74.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_feature_store_training_registry(
        db_path=db_path,
        registry_label="registry-1",
        report_label="report-1",
        build_label="build-1",
    )

    assert result["registry_decision"] == DECISION_READY_LOCKED
    assert result["global_verdict"] == VERDICT_READY
    assert result["feature_record_count"] == 4
    assert result["training_registry_entry_count"] == 4
    assert result["training_eligible_count"] == 0
    assert result["training_locked_count"] == 4
    assert result["pending_outcome_count"] == 4
    assert result["registry_check_count"] == 15
    assert result["pass_check_count"] == 15
    assert result["fail_check_count"] == 0

    with sqlite3.connect(db_path) as conn:
        registry = conn.execute(
            """
            SELECT registry_label, registry_decision, global_verdict
            FROM ai_feature_store_training_registries
            WHERE registry_label = ?
            """,
            ("registry-1",),
        ).fetchone()

        feature_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM ai_feature_store_feature_records
            WHERE registry_label = ?
            """,
            ("registry-1",),
        ).fetchone()[0]

    assert registry == ("registry-1", DECISION_READY_LOCKED, VERDICT_READY)
    assert feature_count == 4


def test_registry_rejects_missing_build(tmp_path):
    db_path = tmp_path / "mission74-missing.db"

    result = run_ai_feature_store_training_registry(
        db_path=db_path,
        registry_label="missing-registry",
        report_label="missing-report",
        build_label="missing-build",
    )

    assert result["registry_decision"] == DECISION_REJECT_MISSING
    assert result["global_verdict"] == VERDICT_MISSING
    assert result["fail_check_count"] == 1


def test_registry_blocks_safety_breach(tmp_path):
    db_path = tmp_path / "mission74-safety.db"

    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_build(conn, safety_breach_count=1, live_trading="ENABLED")
        insert_handoff(conn)
        conn.commit()

    result = run_ai_feature_store_training_registry(
        db_path=db_path,
        registry_label="safety-registry",
        report_label="safety-report",
        build_label="build-1",
    )

    assert result["registry_decision"] == DECISION_BLOCK_SAFETY
    assert result["global_verdict"] == VERDICT_BLOCKED
    assert result["safety_breach_count"] >= 1


def test_registry_flags_unapproved_build(tmp_path):
    db_path = tmp_path / "mission74-unapproved.db"

    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_build(
            conn,
            build_state="AI_OUTCOME_DATASET_BUILD_UNSTABLE",
            build_decision="AI_OUTCOME_DATASET_BUILD_UNSTABLE_REVIEW_REQUIRED",
            verdict="AI_OUTCOME_DATASET_BUILD_UNSTABLE_SHADOW_ONLY",
        )
        insert_handoff(conn)
        conn.commit()

    result = run_ai_feature_store_training_registry(
        db_path=db_path,
        registry_label="unapproved-registry",
        report_label="unapproved-report",
        build_label="build-1",
    )

    assert result["registry_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["fail_check_count"] >= 1


def test_registry_flags_missing_rows(tmp_path):
    db_path = tmp_path / "mission74-missing-rows.db"

    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_build(conn)
        insert_handoff(conn)
        conn.commit()

    result = run_ai_feature_store_training_registry(
        db_path=db_path,
        registry_label="missing-rows-registry",
        report_label="missing-rows-report",
        build_label="build-1",
    )

    assert result["registry_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["feature_record_count"] == 0


def test_registry_flags_handoff_not_ready(tmp_path):
    db_path = tmp_path / "mission74-handoff.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.execute(
            """
            UPDATE ai_outcome_dataset_handoffs
            SET handoff_status = ?
            WHERE build_label = ?
            """,
            ("AI_OUTCOME_DATASET_HANDOFF_NOT_READY", "build-1"),
        )
        conn.commit()

    result = run_ai_feature_store_training_registry(
        db_path=db_path,
        registry_label="handoff-registry",
        report_label="handoff-report",
        build_label="build-1",
    )

    assert result["registry_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE


def test_registry_keeps_training_locked(tmp_path):
    db_path = tmp_path / "mission74-training-lock.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_feature_store_training_registry(
        db_path=db_path,
        registry_label="lock-registry",
        report_label="lock-report",
        build_label="build-1",
    )

    assert all(entry["training_entry_status"] == TRAINING_ENTRY_STATUS_LOCKED for entry in result["training_registry_entries"])
    assert all(entry["training_eligible"] == 0 for entry in result["training_registry_entries"])
    assert all(record["feature_record_status"] == FEATURE_RECORD_STATUS for record in result["feature_records"])


def test_registry_flags_missing_feature_snapshot(tmp_path):
    db_path = tmp_path / "mission74-snapshot.db"

    with sqlite3.connect(db_path) as conn:
        create_input_tables(conn)
        insert_build(conn)
        insert_row(conn, row_index=1, symbol="BTCUSDT", cycle=1, feature_snapshot={})
        insert_row(conn, row_index=2, symbol="ETHUSDT", cycle=1)
        insert_row(conn, row_index=3, symbol="BTCUSDT", cycle=2)
        insert_row(conn, row_index=4, symbol="ETHUSDT", cycle=2)
        insert_handoff(conn)
        conn.commit()

    result = run_ai_feature_store_training_registry(
        db_path=db_path,
        registry_label="snapshot-registry",
        report_label="snapshot-report",
        build_label="build-1",
    )

    assert result["registry_decision"] == DECISION_UNSTABLE
    assert result["global_verdict"] == VERDICT_UNSTABLE
    assert result["feature_snapshot_complete_count"] == 3


def test_markdown_report_contains_training_locked_scope(tmp_path):
    db_path = tmp_path / "mission74-markdown.db"

    with sqlite3.connect(db_path) as conn:
        seed_good(conn)
        conn.commit()

    result = run_ai_feature_store_training_registry(
        db_path=db_path,
        registry_label="markdown-registry",
        report_label="markdown-report",
        build_label="build-1",
    )

    assert "# DeltaGrid Mission 74" in result["markdown_report"]
    assert "does not train a model" in result["markdown_report"]
    assert "Training remains locked" in result["markdown_report"]
    assert "No exchange orders were sent." in result["markdown_report"]

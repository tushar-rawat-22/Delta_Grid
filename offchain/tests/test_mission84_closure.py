from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from offchain.ai_dataset.mission84_closure import (
    EFFECTIVE_STATUS,
    MISSION84_OUTCOME,
    MISSION84_STATUS_CLOSED,
    MISSION84_STATUS_BLOCKED,
    NEXT_WORKSTREAM,
    build_supersession,
    ensure_schema,
    limitation_codes,
    load_real_data_eligible_candidates,
    run_mission84_closure,
)
from offchain.ai_dataset.multi_strategy_backtest_pack import (
    CAPITAL_DEPLOYMENT_STATUS,
    LIVE_ORDER_SENT_VALUE,
    LIVE_TRADING_STATUS,
    MISSION85_STATUS,
)


SOURCE_RUN_LABEL = "mission84-8-final-check"
CLOSURE_RUN_LABEL = "mission84-closure-test"
REPORT_LABEL = "mission84-closure-test-report"
CREATED_AT = "2026-07-12T00:00:00+00:00"


def _insert_mapping(
    conn: sqlite3.Connection,
    table: str,
    row: dict[str, object],
) -> None:
    columns = tuple(row)
    placeholders = ",".join("?" for _ in columns)

    conn.execute(
        f"INSERT INTO {table} ({','.join(columns)}) "
        f"VALUES ({placeholders})",
        tuple(row[column] for column in columns),
    )


def _create_source_db(
    db_path: Path,
    *,
    declared_count: int = 4,
    source_safety_breach: int = 0,
    unsafe_registry: bool = False,
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE ai_alpha_candidate_promotion_runs (
                promotion_run_label TEXT PRIMARY KEY,
                mission85_status TEXT NOT NULL,
                provisional_candidate_count INTEGER NOT NULL,
                model_training_count INTEGER NOT NULL,
                model_artifact_count INTEGER NOT NULL,
                model_promotion_count INTEGER NOT NULL,
                strategy_reweighting_count INTEGER NOT NULL,
                live_signal_count INTEGER NOT NULL,
                exchange_order_count INTEGER NOT NULL,
                capital_deployment_count INTEGER NOT NULL,
                paid_api_count INTEGER NOT NULL,
                private_key_use_count INTEGER NOT NULL,
                profitability_claim_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL
            );

            CREATE TABLE ai_alpha_candidate_registry (
                registry_entry_id TEXT PRIMARY KEY,
                promotion_run_label TEXT NOT NULL,
                review_id TEXT NOT NULL,
                source_robustness_result_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                strategy_family_code TEXT NOT NULL,
                asset_group TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                cost_model_code TEXT NOT NULL,
                registry_status TEXT NOT NULL,
                evidence_scope TEXT NOT NULL,
                next_validation_stage TEXT NOT NULL,
                model_training_action TEXT NOT NULL,
                model_artifact_action TEXT NOT NULL,
                model_promotion_action TEXT NOT NULL,
                strategy_reweighting_action TEXT NOT NULL,
                live_signal_action TEXT NOT NULL,
                exchange_order_action TEXT NOT NULL,
                capital_action TEXT NOT NULL,
                paid_api_action TEXT NOT NULL,
                profitability_claim_action TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );

            CREATE TABLE ai_walk_forward_robustness_results (
                robustness_result_id TEXT PRIMARY KEY,
                source_result_id TEXT NOT NULL
            );

            CREATE TABLE ai_multi_strategy_backtest_results (
                result_id TEXT PRIMARY KEY,
                asset_group TEXT NOT NULL,
                symbol TEXT NOT NULL,
                companion_symbol TEXT NOT NULL
            );
            """
        )

        source_run = {
            "promotion_run_label": SOURCE_RUN_LABEL,
            "mission85_status": MISSION85_STATUS,
            "provisional_candidate_count": declared_count,
            "model_training_count": 0,
            "model_artifact_count": 0,
            "model_promotion_count": 0,
            "strategy_reweighting_count": 0,
            "live_signal_count": 0,
            "exchange_order_count": 0,
            "capital_deployment_count": 0,
            "paid_api_count": 0,
            "private_key_use_count": 0,
            "profitability_claim_count": 0,
            "fail_check_count": 0,
            "safety_breach_count": source_safety_breach,
        }
        _insert_mapping(
            conn,
            "ai_alpha_candidate_promotion_runs",
            source_run,
        )

        candidates = [
            (
                "TIME_SERIES_MOMENTUM",
                "CRYPTO",
                "1D",
                "CRYPTO_PAPER_CONSERVATIVE",
                "ADA",
                "BNB",
            ),
            (
                "VOLATILITY_REGIME_FILTER",
                "CRYPTO",
                "1D",
                "CRYPTO_PAPER_CONSERVATIVE",
                "ADA",
                "BNB",
            ),
            (
                "FUNDING_BASIS_CARRY",
                "FX",
                "1H",
                "FX_PAPER_CONSERVATIVE",
                "AUDUSD",
                "EURUSD",
            ),
            (
                "HYBRID_ENSEMBLE",
                "ETF_MACRO",
                "4H",
                "ETF_PAPER_CONSERVATIVE",
                "EEM",
                "GLD",
            ),
        ]

        for index, (
            strategy,
            asset_group,
            timeframe,
            cost_model,
            symbol,
            companion,
        ) in enumerate(candidates):
            registry_row = {
                "registry_entry_id": f"registry-{index}",
                "promotion_run_label": SOURCE_RUN_LABEL,
                "review_id": f"review-{index}",
                "source_robustness_result_id": (
                    f"robustness-{index}"
                ),
                "created_at": CREATED_AT,
                "strategy_family_code": strategy,
                "asset_group": asset_group,
                "timeframe": timeframe,
                "cost_model_code": cost_model,
                "registry_status": (
                    "PROVISIONAL_ALPHA_RESEARCH_CANDIDATE_"
                    "FIXTURE_ONLY_UNVALIDATED"
                ),
                "evidence_scope": (
                    "SYNTHETIC_FIXTURE_WALK_FORWARD_"
                    "ONLY_UNVALIDATED"
                ),
                "next_validation_stage": (
                    "Mission 84.9 Real-Data Alpha "
                    "Replication Pack"
                ),
                "model_training_action": (
                    "INVALID"
                    if unsafe_registry and index == 0
                    else "NO_MODEL_TRAINING"
                ),
                "model_artifact_action": "NO_MODEL_ARTIFACT",
                "model_promotion_action": "NO_MODEL_PROMOTION",
                "strategy_reweighting_action": (
                    "NO_STRATEGY_REWEIGHTING"
                ),
                "live_signal_action": "NO_LIVE_SIGNAL",
                "exchange_order_action": "NO_EXCHANGE_ORDER",
                "capital_action": "NO_CAPITAL_DEPLOYMENT",
                "paid_api_action": "NO_PAID_API",
                "profitability_claim_action": (
                    "NO_PROFITABILITY_CLAIM"
                ),
                "live_trading": LIVE_TRADING_STATUS,
                "live_order_sent": LIVE_ORDER_SENT_VALUE,
                "capital_deployment": (
                    CAPITAL_DEPLOYMENT_STATUS
                ),
                "metadata_json": "{}",
            }
            _insert_mapping(
                conn,
                "ai_alpha_candidate_registry",
                registry_row,
            )

            _insert_mapping(
                conn,
                "ai_walk_forward_robustness_results",
                {
                    "robustness_result_id": (
                        f"robustness-{index}"
                    ),
                    "source_result_id": f"result-{index}",
                },
            )

            _insert_mapping(
                conn,
                "ai_multi_strategy_backtest_results",
                {
                    "result_id": f"result-{index}",
                    "asset_group": asset_group,
                    "symbol": symbol,
                    "companion_symbol": companion,
                },
            )

        conn.commit()


def _run(db_path: Path) -> dict[str, object]:
    return run_mission84_closure(
        db_path=db_path,
        closure_run_label=CLOSURE_RUN_LABEL,
        report_label=REPORT_LABEL,
        source_promotion_run_label=SOURCE_RUN_LABEL,
        expected_fixture_candidates=4,
        created_at=CREATED_AT,
    )


def test_ensure_schema_creates_closure_tables(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "closure.db"
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }

    assert "ai_mission84_closure_runs" in tables
    assert "ai_mission84_candidate_supersessions" in tables
    assert "ai_mission84_closure_checks" in tables
    assert "ai_mission84_closure_reports" in tables


def test_build_supersession_is_fail_closed() -> None:
    row = {
        "registry_entry_id": "registry-1",
        "strategy_family_code": "TIME_SERIES_MOMENTUM",
        "asset_group": "CRYPTO",
        "timeframe": "1D",
        "cost_model_code": "CRYPTO_PAPER_CONSERVATIVE",
        "registry_status": (
            "PROVISIONAL_ALPHA_RESEARCH_CANDIDATE_"
            "FIXTURE_ONLY_UNVALIDATED"
        ),
        "evidence_scope": (
            "SYNTHETIC_FIXTURE_WALK_FORWARD_ONLY_UNVALIDATED"
        ),
        "next_validation_stage": (
            "Mission 84.9 Real-Data Alpha Replication Pack"
        ),
    }

    result = build_supersession(
        row,
        CLOSURE_RUN_LABEL,
        SOURCE_RUN_LABEL,
        CREATED_AT,
    )

    assert result["effective_status"] == EFFECTIVE_STATUS
    assert result["real_data_eligible"] == 0
    assert result["model_training_eligible"] == 0
    assert result["model_promotion_eligible"] == 0
    assert result["live_signal_eligible"] == 0
    assert result["capital_deployment_eligible"] == 0


def test_noncrypto_funding_limitation_is_recorded() -> None:
    codes = limitation_codes(
        {
            "strategy_family_code": "FUNDING_BASIS_CARRY",
            "asset_group": "FX",
        }
    )

    assert (
        "FUNDING_BASIS_INVALID_FOR_NONCRYPTO_ASSET_GROUP"
        in codes
    )


def test_successful_closure_records_authoritative_counts(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "closure.db"
    _create_source_db(db_path)

    summary = _run(db_path)

    assert summary["mission84_status"] == MISSION84_STATUS_CLOSED
    assert summary["mission84_outcome"] == MISSION84_OUTCOME
    assert summary["fixture_screening_candidate_count"] == 4
    assert summary["superseded_candidate_count"] == 4
    assert summary["source_pair_count"] == 3
    assert summary["source_pair_reuse_count"] == 1
    assert (
        summary["invalid_noncrypto_funding_candidate_count"]
        == 1
    )
    assert summary["real_data_validated_candidate_count"] == 0
    assert summary["model_training_eligible_count"] == 0
    assert summary["fail_check_count"] == 0
    assert summary["safety_breach_count"] == 0
    assert summary["next_workstream"] == NEXT_WORKSTREAM
    assert "not real-market alpha evidence" in (
        summary["markdown_report"]
    )


def test_original_registry_rows_are_not_mutated(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "closure.db"
    _create_source_db(db_path)

    with sqlite3.connect(db_path) as conn:
        before = conn.execute(
            """
            SELECT registry_entry_id, registry_status,
                   next_validation_stage
            FROM ai_alpha_candidate_registry
            ORDER BY registry_entry_id
            """
        ).fetchall()

    _run(db_path)

    with sqlite3.connect(db_path) as conn:
        after = conn.execute(
            """
            SELECT registry_entry_id, registry_status,
                   next_validation_stage
            FROM ai_alpha_candidate_registry
            ORDER BY registry_entry_id
            """
        ).fetchall()

    assert after == before


def test_effective_registry_view_applies_supersession(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "closure.db"
    _create_source_db(db_path)
    _run(db_path)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                effective_registry_status,
                real_data_eligible,
                model_training_eligible,
                model_promotion_eligible
            FROM ai_alpha_candidate_registry_effective
            ORDER BY registry_entry_id
            """
        ).fetchall()

    assert len(rows) == 4
    assert all(row[0] == EFFECTIVE_STATUS for row in rows)
    assert all(row[1:] == (0, 0, 0) for row in rows)


def test_real_data_candidate_loader_returns_empty(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "closure.db"
    _create_source_db(db_path)
    _run(db_path)

    assert load_real_data_eligible_candidates(db_path) == []


def test_closure_is_idempotent_for_same_run_label(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "closure.db"
    _create_source_db(db_path)

    first = _run(db_path)
    second = _run(db_path)

    with sqlite3.connect(db_path) as conn:
        run_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM ai_mission84_closure_runs
            WHERE closure_run_label = ?
            """,
            (CLOSURE_RUN_LABEL,),
        ).fetchone()[0]

        supersession_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM ai_mission84_candidate_supersessions
            WHERE closure_run_label = ?
            """,
            (CLOSURE_RUN_LABEL,),
        ).fetchone()[0]

        check_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM ai_mission84_closure_checks
            WHERE closure_run_label = ?
            """,
            (CLOSURE_RUN_LABEL,),
        ).fetchone()[0]

    assert first["pass_check_count"] == second["pass_check_count"]
    assert run_count == 1
    assert supersession_count == 4
    assert check_count == second["closure_check_count"]


def test_source_safety_breach_blocks_closure(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "closure.db"
    _create_source_db(
        db_path,
        source_safety_breach=1,
    )

    summary = _run(db_path)

    assert summary["mission84_status"] == MISSION84_STATUS_BLOCKED
    assert summary["fail_check_count"] > 0
    assert summary["safety_breach_count"] > 0


def test_declared_candidate_count_mismatch_blocks_closure(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "closure.db"
    _create_source_db(
        db_path,
        declared_count=5,
    )

    summary = _run(db_path)

    assert summary["mission84_status"] == MISSION84_STATUS_BLOCKED
    assert summary["fail_check_count"] > 0


def test_unsafe_registry_action_blocks_closure(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "closure.db"
    _create_source_db(
        db_path,
        unsafe_registry=True,
    )

    summary = _run(db_path)

    assert summary["mission84_status"] == MISSION84_STATUS_BLOCKED
    assert summary["fail_check_count"] > 0
    assert summary["safety_breach_count"] > 0


def test_missing_source_tables_raise(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "closure.db"

    with pytest.raises(
        RuntimeError,
        match="missing Mission 84 source tables",
    ):
        run_mission84_closure(
            db_path=db_path,
            closure_run_label=CLOSURE_RUN_LABEL,
            report_label=REPORT_LABEL,
            source_promotion_run_label=SOURCE_RUN_LABEL,
            expected_fixture_candidates=4,
            created_at=CREATED_AT,
        )


def test_closure_documentation_is_authoritative() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    required_docs = (
        "README.md",
        "docs/PROJECT_SOURCE_OF_TRUTH.md",
        "docs/ROADMAP.md",
        "docs/MISSION_INDEX.md",
        "docs/ARCHITECTURE_STATE.md",
        "docs/INSTITUTIONAL_ALPHA_RESEARCH_PLAN.md",
        "docs/DECISION_LOG.md",
        "docs/CHANGELOG.md",
        "docs/DELTA_AUTONOMOUS_BOT_ROADMAP.md",
    )

    for relative_path in required_docs:
        text = (repo_root / relative_path).read_text(
            encoding="utf-8"
        )
        assert "<!-- MISSION-84-CLOSURE:START -->" in text
        assert "<!-- MISSION-84-CLOSURE:END -->" in text

    roadmap = (
        repo_root / "docs/ROADMAP.md"
    ).read_text(encoding="utf-8")
    source_of_truth = (
        repo_root / "docs/PROJECT_SOURCE_OF_TRUTH.md"
    ).read_text(encoding="utf-8")
    research_plan = (
        repo_root / "docs/INSTITUTIONAL_ALPHA_RESEARCH_PLAN.md"
    ).read_text(encoding="utf-8")

    assert (
        "Next: Mission 84.9 Real-Data Alpha Replication Pack."
        not in roadmap
    )
    assert (
        "- Next mission: Mission 84.9 Real-Data Alpha "
        "Replication Pack."
        not in source_of_truth
    )
    assert (
        "The next required stage is Mission 84.9 "
        "Real-Data Alpha Replication Pack"
        not in research_plan
    )

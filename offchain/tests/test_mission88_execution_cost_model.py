from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from offchain.backtest.mission86_real_market_data_foundation import (
    canonical_json,
)
from offchain.backtest.mission88_execution_cost_model import (
    EXPECTED_SOURCE_CERTIFICATE_HASH,
    MISSION88_STATUS,
    MISSION89_AUTHORIZED_SCOPE,
    MISSION89_STATUS,
    MODEL_STATUS,
    NOTIONAL_BANDS,
    SCENARIOS,
    build_cost_profiles,
    build_model_core,
    decimal_value,
    ensure_schema,
    run_cost_model,
    validate_profiles,
    validate_source_certification,
    write_artifact,
)
from offchain.research.funding_carry_research_contract import (
    CONTRACT_STATUS,
    MISSION85_CONTRACT,
    contract_hash,
)


CREATED_AT = "2026-07-12T00:00:00+00:00"


def write_contract(path: Path) -> None:
    envelope = {
        "contract": MISSION85_CONTRACT,
        "contract_hash_sha256": (
            contract_hash(MISSION85_CONTRACT)
        ),
        "contract_status": CONTRACT_STATUS,
        "locked_at": CREATED_AT,
    }

    path.write_text(
        json.dumps(
            envelope,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def create_source_db(
    db_path: Path,
    *,
    invalid: bool = False,
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE mission87_certification_runs (
                certification_run_label TEXT PRIMARY KEY,
                contract_hash TEXT NOT NULL,
                certificate_hash TEXT NOT NULL,
                certification_status TEXT NOT NULL,
                mission87_status TEXT NOT NULL,
                certified_series_count INTEGER NOT NULL,
                rejected_series_count INTEGER NOT NULL,
                quality_check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                holdout_performance_evaluated INTEGER NOT NULL,
                backtesting_performed INTEGER NOT NULL,
                profitability_analyzed INTEGER NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL
            );

            CREATE TABLE mission87_series_certifications (
                certification_run_label TEXT NOT NULL,
                stream TEXT NOT NULL,
                symbol TEXT NOT NULL,
                certification_status TEXT NOT NULL
            );
            """
        )

        conn.execute(
            """
            INSERT INTO mission87_certification_runs (
                certification_run_label,
                contract_hash,
                certificate_hash,
                certification_status,
                mission87_status,
                certified_series_count,
                rejected_series_count,
                quality_check_count,
                pass_check_count,
                fail_check_count,
                safety_breach_count,
                holdout_performance_evaluated,
                backtesting_performed,
                profitability_analyzed,
                live_trading,
                live_order_sent,
                capital_deployment
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                "mission87-final-check",
                contract_hash(MISSION85_CONTRACT),
                EXPECTED_SOURCE_CERTIFICATE_HASH,
                (
                    "CERTIFIED_FOR_RESEARCH_"
                    "PENDING_EXECUTION_COST_MODEL"
                ),
                (
                    "COMPLETE_REAL_MARKET_"
                    "DATASET_CERTIFICATION"
                ),
                15,
                0,
                23,
                22 if invalid else 23,
                1 if invalid else 0,
                0,
                0,
                0,
                0,
                "DISABLED",
                0,
                "BLOCKED",
            ),
        )

        streams = (
            "spot_ohlcv",
            "perpetual_ohlcv",
            "mark_price_ohlcv",
            "index_price_ohlcv",
            "funding_rates",
        )
        symbols = (
            "BTCUSDT",
            "ETHUSDT",
            "SOLUSDT",
        )

        for stream in streams:
            for symbol in symbols:
                conn.execute(
                    """
                    INSERT INTO
                        mission87_series_certifications (
                            certification_run_label,
                            stream,
                            symbol,
                            certification_status
                        ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        "mission87-final-check",
                        stream,
                        symbol,
                        (
                            "CERTIFIED_FOR_RESEARCH_"
                            "PENDING_EXECUTION_COST_MODEL"
                        ),
                    ),
                )

        conn.commit()


def profiles():
    return build_cost_profiles(
        MISSION85_CONTRACT
    )


def test_default_matrix_has_twenty_seven_profiles() -> None:
    result = profiles()

    assert len(result) == 27
    assert len(SCENARIOS) == 3
    assert len(NOTIONAL_BANDS) == 3


def test_scenario_costs_are_monotonic() -> None:
    result = validate_profiles(
        profiles(),
        MISSION85_CONTRACT,
    )

    assert result["scenario_monotonic"] is True


def test_notional_costs_are_monotonic() -> None:
    result = validate_profiles(
        profiles(),
        MISSION85_CONTRACT,
    )

    assert result["notional_monotonic"] is True


def test_severe_cost_is_at_least_double_normal() -> None:
    result = validate_profiles(
        profiles(),
        MISSION85_CONTRACT,
    )

    assert result["severe_double_normal"] is True


def test_fees_never_undercut_charter() -> None:
    result = validate_profiles(
        profiles(),
        MISSION85_CONTRACT,
    )

    assert result["fees_not_below_charter"] is True


def test_profile_formula_is_consistent() -> None:
    result = validate_profiles(
        profiles(),
        MISSION85_CONTRACT,
    )

    assert result["formula_consistent"] is True


def test_no_negative_cost_components() -> None:
    result = validate_profiles(
        profiles(),
        MISSION85_CONTRACT,
    )

    assert result["components_nonnegative"] is True


def test_model_hash_is_deterministic() -> None:
    first = build_model_core(
        MISSION85_CONTRACT,
        profiles(),
    )
    second = build_model_core(
        MISSION85_CONTRACT,
        profiles(),
    )

    first_hash = hashlib.sha256(
        canonical_json(first).encode("utf-8")
    ).hexdigest()
    second_hash = hashlib.sha256(
        canonical_json(second).encode("utf-8")
    ).hexdigest()

    assert first_hash == second_hash


def test_artifact_hash_is_deterministic(
    tmp_path: Path,
) -> None:
    core = build_model_core(
        MISSION85_CONTRACT,
        profiles(),
    )

    first_hash, _ = write_artifact(
        tmp_path / "first.json",
        core,
        CREATED_AT,
    )
    second_hash, _ = write_artifact(
        tmp_path / "second.json",
        core,
        "2026-07-12T01:00:00+00:00",
    )

    assert first_hash == second_hash


def test_schema_is_created(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mission88.db"
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

    assert "mission88_cost_model_runs" in tables
    assert "mission88_cost_scenarios" in tables
    assert "mission88_cost_profiles" in tables
    assert "mission88_model_checks" in tables
    assert "mission88_cost_model_artifacts" in tables


def test_valid_source_certification_has_no_errors() -> None:
    source = {
        "contract_hash": (
            contract_hash(MISSION85_CONTRACT)
        ),
        "certificate_hash": (
            EXPECTED_SOURCE_CERTIFICATE_HASH
        ),
        "certification_status": (
            "CERTIFIED_FOR_RESEARCH_"
            "PENDING_EXECUTION_COST_MODEL"
        ),
        "mission87_status": (
            "COMPLETE_REAL_MARKET_"
            "DATASET_CERTIFICATION"
        ),
        "certified_series_count": 15,
        "rejected_series_count": 0,
        "quality_check_count": 23,
        "pass_check_count": 23,
        "fail_check_count": 0,
        "safety_breach_count": 0,
        "holdout_performance_evaluated": 0,
        "backtesting_performed": 0,
        "profitability_analyzed": 0,
        "live_trading": "DISABLED",
        "live_order_sent": 0,
        "capital_deployment": "BLOCKED",
        "persisted_series_count": 15,
        "persisted_rejected_count": 0,
    }

    assert validate_source_certification(source) == []


def test_invalid_source_certification_is_rejected() -> None:
    source = {
        "contract_hash": "wrong",
        "persisted_series_count": 14,
        "persisted_rejected_count": 1,
    }

    assert validate_source_certification(source)


def test_run_persists_complete_model(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mission88.db"
    contract_path = tmp_path / "contract.json"
    artifact_path = tmp_path / "cost_model.json"

    write_contract(contract_path)
    create_source_db(db_path)

    summary = run_cost_model(
        db_path=db_path,
        contract_path=contract_path,
        artifact_path=artifact_path,
        run_label="mission88-test",
        created_at=CREATED_AT,
    )

    assert summary["mission88_status"] == (
        MISSION88_STATUS
    )
    assert summary["model_status"] == MODEL_STATUS
    assert summary["profile_count"] == 27
    assert summary["check_count"] == 24
    assert summary["pass_check_count"] == 24
    assert summary["fail_check_count"] == 0
    assert summary["safety_breach_count"] == 0
    assert summary["mission89_status"] == (
        MISSION89_STATUS
    )
    assert summary[
        "mission89_authorized_scope"
    ] == MISSION89_AUTHORIZED_SCOPE

    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM mission88_cost_profiles
            """
        ).fetchone()[0] == 27

        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM mission88_cost_scenarios
            """
        ).fetchone()[0] == 3


def test_run_is_idempotent(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mission88.db"
    contract_path = tmp_path / "contract.json"
    artifact_path = tmp_path / "cost_model.json"

    write_contract(contract_path)
    create_source_db(db_path)

    first = run_cost_model(
        db_path=db_path,
        contract_path=contract_path,
        artifact_path=artifact_path,
        run_label="mission88-test",
        created_at=CREATED_AT,
    )
    second = run_cost_model(
        db_path=db_path,
        contract_path=contract_path,
        artifact_path=artifact_path,
        run_label="mission88-test",
        created_at=CREATED_AT,
    )

    assert first["model_hash"] == second["model_hash"]

    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM mission88_cost_model_runs
            """
        ).fetchone()[0] == 1

        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM mission88_cost_profiles
            """
        ).fetchone()[0] == 27


def test_invalid_source_blocks_model(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mission88.db"
    contract_path = tmp_path / "contract.json"

    write_contract(contract_path)
    create_source_db(
        db_path,
        invalid=True,
    )

    with pytest.raises(
        RuntimeError,
        match="source certification invalid",
    ):
        run_cost_model(
            db_path=db_path,
            contract_path=contract_path,
            artifact_path=(
                tmp_path / "cost_model.json"
            ),
            run_label="mission88-test",
            created_at=CREATED_AT,
        )


def test_run_reads_no_market_data_rows(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mission88.db"
    contract_path = tmp_path / "contract.json"

    write_contract(contract_path)
    create_source_db(db_path)

    summary = run_cost_model(
        db_path=db_path,
        contract_path=contract_path,
        artifact_path=(
            tmp_path / "cost_model.json"
        ),
        run_label="mission88-test",
        created_at=CREATED_AT,
    )

    assert summary["market_data_rows_read"] == 0
    assert (
        summary[
            "holdout_performance_evaluated"
        ]
        == 0
    )
    assert summary["backtesting_performed"] == 0
    assert summary["profitability_analyzed"] == 0


def test_module_contains_no_market_table_queries() -> None:
    source_path = Path(__file__).resolve().parents[1] / (
        "backtest/mission88_execution_cost_model.py"
    )
    text = source_path.read_text(
        encoding="utf-8"
    )

    forbidden = (
        "mission86_market_bars",
        "mission86_funding_rates",
        "SELECT close_price",
        "SELECT funding_rate",
    )

    assert all(
        item not in text
        for item in forbidden
    )


def test_mission88_documentation_is_authoritative() -> None:
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
        text = (
            repo_root / relative_path
        ).read_text(encoding="utf-8")

        assert (
            "<!-- MISSION-88-COST-MODEL:START -->"
            in text
        )
        assert (
            "<!-- MISSION-88-COST-MODEL:END -->"
            in text
        )
        assert (
            "Mission 88 Execution and Cost Reality Model"
            in text
        )
        assert (
            "Mission 89 Baseline Strategy Falsification"
            in text
        )
        assert "assumption-bounded" in text.lower()
        assert "no strategy backtest" in text.lower()
        assert "no order-book precision claim" in text.lower()

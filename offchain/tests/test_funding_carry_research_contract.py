from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest

from offchain.research.funding_carry_research_contract import (
    CONTRACT_ID,
    GLOBAL_VERDICT,
    LEGACY_MODEL_PROMOTION_STATUS,
    MISSION85_CONTRACT,
    MISSION85_STATUS,
    MISSION86_STATUS,
    contract_hash,
    load_locked_contract,
    lock_contract,
    parameter_variants,
    validate_contract,
)


CREATED_AT = "2026-07-12T00:00:00+00:00"


def test_default_contract_is_valid() -> None:
    result = validate_contract(MISSION85_CONTRACT)

    assert result["valid"] is True
    assert result["fail_check_count"] == 0
    assert result["safety_breach_count"] == 0
    assert result["pass_check_count"] == result["check_count"]


def test_parameter_budget_is_exactly_twelve() -> None:
    variants = parameter_variants(MISSION85_CONTRACT)

    assert len(variants) == 12
    assert len(
        {
            (
                row["minimum_trailing_funding_rate_bps"],
                row["maximum_absolute_entry_basis_bps"],
                row["maximum_holding_days"],
            )
            for row in variants
        }
    ) == 12


def test_universe_change_fails_validation() -> None:
    contract = deepcopy(MISSION85_CONTRACT)
    contract["universe"]["symbols"].append("XRPUSDT")

    result = validate_contract(contract)

    assert result["valid"] is False
    assert result["fail_check_count"] > 0


def test_sample_fallback_fails_validation() -> None:
    contract = deepcopy(MISSION85_CONTRACT)
    contract["data_contract"]["allow_sample_fallback"] = True

    result = validate_contract(contract)

    assert result["valid"] is False
    assert result["fail_check_count"] > 0


def test_holdout_tuning_fails_validation() -> None:
    contract = deepcopy(MISSION85_CONTRACT)
    contract["research_splits"][-1][
        "parameter_tuning_allowed"
    ] = True

    result = validate_contract(contract)

    assert result["valid"] is False
    assert result["fail_check_count"] > 0


def test_lookahead_signal_fails_validation() -> None:
    contract = deepcopy(MISSION85_CONTRACT)
    contract["observable_signal_contract"][
        "future_funding_rate_use_allowed"
    ] = True

    result = validate_contract(contract)

    assert result["valid"] is False
    assert result["fail_check_count"] > 0


def test_machine_learning_fails_validation() -> None:
    contract = deepcopy(MISSION85_CONTRACT)
    contract["strategy_rules"][
        "machine_learning_allowed"
    ] = True

    result = validate_contract(contract)

    assert result["valid"] is False
    assert result["fail_check_count"] > 0


def test_unsafe_contract_fails_validation() -> None:
    contract = deepcopy(MISSION85_CONTRACT)
    contract["safety"]["real_orders_allowed"] = True

    result = validate_contract(contract)

    assert result["valid"] is False
    assert result["safety_breach_count"] == 1


def test_lock_contract_persists_file_and_database(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mission85.db"
    contract_path = tmp_path / "contract.json"

    summary = lock_contract(
        db_path=db_path,
        contract_path=contract_path,
        lock_run_label="mission85-test",
        report_label="mission85-test-report",
        created_at=CREATED_AT,
    )

    assert summary["mission85_status"] == MISSION85_STATUS
    assert summary["mission86_status"] == MISSION86_STATUS
    assert summary["global_verdict"] == GLOBAL_VERDICT
    assert summary["parameter_variant_count"] == 12
    assert summary["fail_check_count"] == 0
    assert summary["safety_breach_count"] == 0

    envelope = load_locked_contract(contract_path)

    assert envelope["contract"]["contract_id"] == CONTRACT_ID
    assert (
        envelope["contract_hash_sha256"]
        == contract_hash(envelope["contract"])
    )

    with sqlite3.connect(db_path) as conn:
        contract_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM mission85_research_contracts
            """
        ).fetchone()[0]

        run_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM mission85_research_contract_runs
            """
        ).fetchone()[0]

        check_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM mission85_research_contract_checks
            """
        ).fetchone()[0]

    assert contract_count == 1
    assert run_count == 1
    assert check_count == summary["check_count"]


def test_same_contract_is_idempotent(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mission85.db"
    contract_path = tmp_path / "contract.json"

    first = lock_contract(
        db_path=db_path,
        contract_path=contract_path,
        lock_run_label="mission85-test",
        report_label="mission85-test-report",
        created_at=CREATED_AT,
    )
    second = lock_contract(
        db_path=db_path,
        contract_path=contract_path,
        lock_run_label="mission85-test",
        report_label="mission85-test-report",
        created_at=CREATED_AT,
    )

    assert first["contract_hash"] == second["contract_hash"]

    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM mission85_research_contracts
            """
        ).fetchone()[0] == 1

        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM mission85_research_contract_runs
            """
        ).fetchone()[0] == 1


def test_different_contract_cannot_overwrite_locked_file(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mission85.db"
    contract_path = tmp_path / "contract.json"

    lock_contract(
        db_path=db_path,
        contract_path=contract_path,
        lock_run_label="mission85-test",
        report_label="mission85-test-report",
        created_at=CREATED_AT,
    )

    changed = deepcopy(MISSION85_CONTRACT)
    changed["research_objective"]["alternative_hypothesis"] = (
        "Changed after lock"
    )

    with pytest.raises(
        RuntimeError,
        match="different hash",
    ):
        lock_contract(
            db_path=db_path,
            contract_path=contract_path,
            lock_run_label="mission85-conflict",
            report_label="mission85-conflict-report",
            contract=changed,
            created_at=CREATED_AT,
        )


def test_contract_file_contains_no_dynamic_hash_mismatch(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mission85.db"
    contract_path = tmp_path / "contract.json"

    lock_contract(
        db_path=db_path,
        contract_path=contract_path,
        created_at=CREATED_AT,
    )

    envelope = json.loads(
        contract_path.read_text(encoding="utf-8")
    )

    assert (
        envelope["contract_hash_sha256"]
        == contract_hash(envelope["contract"])
    )


def test_legacy_model_promotion_plan_is_retired() -> None:
    assert (
        MISSION85_CONTRACT["legacy_plan_resolution"][
            "legacy_plan_status"
        ]
        == LEGACY_MODEL_PROMOTION_STATUS
    )


def test_mission85_documentation_is_authoritative() -> None:
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

        assert "<!-- MISSION-85-CHARTER:START -->" in text
        assert "<!-- MISSION-85-CHARTER:END -->" in text
        assert "Mission 85 Crypto Funding-Carry Research Charter" in text
        assert "Mission 86 Real-Market Data Foundation" in text

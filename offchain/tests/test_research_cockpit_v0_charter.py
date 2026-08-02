from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess


ROOT = Path(__file__).resolve().parents[2]
BASE_COMMIT = "9605c4b294d15f4e1ec4929c9706f1ff9f938072"
CONTRACT_PATH = (
    ROOT / "contracts" / "DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER_V1.json"
)
CHARTER_PATH = ROOT / "docs" / "DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER.md"
REGISTRY_PATH = ROOT / "docs" / "documentation-status.json"
DOCS_HOME = ROOT / "docs" / "README.md"
FINAL_FREEZE_PATH = ROOT / "contracts" / "DELTAGRID_FINAL_FREEZE_V1.json"
EXPECTED_CONTRACT_HASH = (
    "b4064f4651730618bf6497e631e913ebde7d6c9db926943d46aa11b3bc223bc1"
)
EXPECTED_AUDIT_MANIFEST_HASH = (
    "e165ad38328399c5e39e4a656779a64697ba060049968ea69a249ce5ae0a398e"
)

LOCKED_CHANGED_PATHS = {
    "contracts/DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER_V1.json",
    "docs/DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER.md",
    "docs/README.md",
    "docs/documentation-status.json",
    "offchain/tests/test_current_policy_docs.py",
    "offchain/tests/test_document_status_banners.py",
    "offchain/tests/test_documentation_status.py",
    "offchain/tests/test_human_cli_report_language.py",
    "offchain/tests/test_public_docstrings_operator_guidance.py",
    "offchain/tests/test_research_cockpit_v0_charter.py",
    "offchain/tests/test_research_evidence_summaries.py",
}

FALSE_AUTHORIZATIONS = {
    "cockpit_implementation_authorized",
    "cockpit_research_authorized",
    "real_market_backtest_authorized",
    "validation_access_authorized",
    "holdout_access_authorized",
    "paper_trading_authorized",
    "live_trading_authorized",
    "capital_deployment_authorized",
    "model_training_authorized",
    "autonomous_research_authorized",
    "autonomous_promotion_authorized",
    "exchange_access_authorized",
}

CONTROL_IDENTIFIERS = [
    "NO_TRADE_CONTROL",
    "BUY_AND_HOLD_CONTROL",
    "SEEDED_RANDOM_CONTROL",
    "SIMULATOR_STATE_MACHINE_CONTROL",
]

MANIFEST_FIELDS = {
    "schema_version",
    "experiment_id",
    "experiment_type",
    "controlling_contract_id",
    "controlling_contract_hash_sha256",
    "repository_commit",
    "repository_clean",
    "dataset_ids",
    "dataset_hashes",
    "split_identity",
    "protected_data_permissions",
    "control_identifier",
    "allowed_parameters",
    "deterministic_seed",
    "cost_model_identity",
    "execution_model_identity",
    "risk_model_identity",
    "declared_trial_number",
    "total_trial_budget",
    "output_directory",
    "requested_artifacts",
    "authorization_stage",
    "operator",
    "creation_timestamp",
    "canonical_hash_sha256",
}

RESULT_FIELDS = {
    "schema_version",
    "result_bundle_id",
    "manifest_id",
    "manifest_hash_sha256",
    "code_identity",
    "repository_commit",
    "dataset_ids",
    "dataset_hashes",
    "simulator_identity",
    "cost_model_identity",
    "execution_model_identity",
    "risk_model_identity",
    "start_timestamp",
    "end_timestamp",
    "status_token",
    "reason_token",
    "failure_stop_or_rejection_reason",
    "human_explanation",
    "gross_result",
    "net_result",
    "benchmark",
    "costs_by_component",
    "maximum_drawdown",
    "exposure",
    "turnover",
    "trade_count",
    "concentration",
    "timing_diagnostics",
    "protected_access_counts",
    "artifact_paths",
    "warnings",
    "verification_results",
    "canonical_result_hash_sha256",
}

AUDITED_INTERFACE_PATHS = [
    "contracts/DELTAGRID_FINAL_FREEZE_V1.json",
    "docs/documentation-status.json",
    "offchain/backtest/mission86_real_market_data_foundation.py",
    "offchain/backtest/mission87_dataset_certification.py",
    "offchain/backtest/mission88_execution_cost_model.py",
    "offchain/backtest/mission89_baseline_strategy_falsification.py",
    "offchain/backtest/mission90_directional_strategy_tournament.py",
    "offchain/research/alpha_search_b/engine.py",
    "offchain/research/alpha_search_b/pipeline.py",
    "scripts/mission_control.py",
    "scripts/mission_pack_runner.py",
]

COMPATIBILITY_TEST_COUNTS = {
    "offchain/tests/test_documentation_status.py": 29,
    "offchain/tests/test_current_policy_docs.py": 13,
    "offchain/tests/test_document_status_banners.py": 14,
    "offchain/tests/test_research_evidence_summaries.py": 28,
    "offchain/tests/test_human_cli_report_language.py": 14,
    "offchain/tests/test_public_docstrings_operator_guidance.py": 26,
}


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def base_bytes(path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{BASE_COMMIT}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def canonical_hash(value: dict) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def changed_paths() -> set[str]:
    lines = git("status", "--porcelain", "--untracked-files=all").stdout.splitlines()
    return {line[3:] for line in lines if line}


def test_exact_locked_changed_path_manifest_and_git_scope() -> None:
    contract = load(CONTRACT_PATH)
    recorded = contract["implementation_path_budget"]
    assert set(recorded["mission93_locked_changed_paths"]) == LOCKED_CHANGED_PATHS
    assert recorded["mission93_locked_changed_path_count"] == 11
    assert recorded["mission93_maximum_changed_paths"] == 13
    assert changed_paths() == LOCKED_CHANGED_PATHS
    assert git("diff", "--cached", "--name-only").stdout == ""
    assert all(PurePosixPath(path).as_posix() == path for path in LOCKED_CHANGED_PATHS)


def test_contract_identity_base_and_canonical_hash() -> None:
    contract = load(CONTRACT_PATH)
    assert contract["contract_id"] == "deltagrid-research-cockpit-v0-charter-v1"
    assert contract["contract_version"] == 1
    assert contract["base_commit"] == BASE_COMMIT
    core = dict(contract)
    assert core.pop("contract_hash_sha256") == EXPECTED_CONTRACT_HASH
    assert canonical_hash(core) == EXPECTED_CONTRACT_HASH
    assert contract["interface_audit"]["audit_manifest_sha256"] == (
        EXPECTED_AUDIT_MANIFEST_HASH
    )


def test_final_freeze_remains_controlling_and_byte_identical() -> None:
    contract = load(CONTRACT_PATH)
    freeze = contract["final_freeze_contract"]
    assert freeze["path"] == "contracts/DELTAGRID_FINAL_FREEZE_V1.json"
    assert freeze["contract_id"] == "deltagrid-final-freeze-v1"
    assert freeze["remains_authoritative"] is True
    assert "remains authoritative" in freeze["authority_statement"]
    assert FINAL_FREEZE_PATH.read_bytes() == base_bytes(
        "contracts/DELTAGRID_FINAL_FREEZE_V1.json"
    )


def test_every_research_trading_and_implementation_authorization_is_false() -> None:
    contract = load(CONTRACT_PATH)
    assert FALSE_AUTHORIZATIONS <= set(contract)
    assert all(contract[field] is False for field in FALSE_AUTHORIZATIONS)
    current = contract["current_authority"]
    assert current["validated_profitable_strategy_exists"] is False
    assert current["selected_candidate"] is None
    assert current["research_status"] == "FROZEN"
    assert current["future_capability_work_requires_explicit_versioned_contract"]


def test_exact_four_non_alpha_controls_and_no_execution_authority() -> None:
    contract = load(CONTRACT_PATH)
    controls = contract["non_alpha_controls"]
    assert [item["control_identifier"] for item in controls] == CONTROL_IDENTIFIERS
    assert all(item["non_alpha"] is True for item in controls)
    assert all(item["execution_authorized"] is False for item in controls)
    assert contract["control_execution_authorized"] is False
    seeded = next(
        item for item in controls
        if item["control_identifier"] == "SEEDED_RANDOM_CONTROL"
    )
    assert seeded["explicit_seed_required"] is True


def test_cockpit_boundary_is_local_read_only_and_non_authoritative() -> None:
    boundary = load(CONTRACT_PATH)["cockpit_v0_boundary"]
    for field in (
        "local",
        "single_user",
        "offline_by_default",
        "read_only_by_default",
        "development_and_verification_tooling",
        "evidence_controlled",
        "reconstructable_from_persisted_artifacts",
    ):
        assert boundary[field] is True
    for field in (
        "backtesting_engine",
        "strategy_optimizer",
        "autonomous_agent",
        "model_trainer",
        "trading_interface",
        "ui_session_state_is_research_authority",
    ):
        assert boundary[field] is False
    assert boundary["default_result_order"] == (
        "CHRONOLOGICAL_NOT_PERFORMANCE_RANKED"
    )


def test_future_manifest_contract_is_complete_and_fail_closed() -> None:
    manifest = load(CONTRACT_PATH)["future_experiment_manifest_contract"]
    assert set(manifest["required_fields"]) == MANIFEST_FIELDS
    required_failures = {
        "DIRTY_REPOSITORY",
        "CONTRACT_HASH_MISMATCH",
        "UNKNOWN_DATASET",
        "DATASET_HASH_MISMATCH",
        "UNKNOWN_CONTROL",
        "UNKNOWN_PARAMETER",
        "MISSING_REQUIRED_SEED",
        "TRIAL_BUDGET_EXHAUSTED",
        "UNAUTHORIZED_SPLIT",
        "VALIDATION_REQUEST_FORBIDDEN",
        "HOLDOUT_REQUEST_FORBIDDEN",
        "CONTRACT_IMPLEMENTATION_MISMATCH",
    }
    assert required_failures <= set(manifest["fail_closed_conditions"])
    assert manifest["exact_allowed_parameter_policy"] == (
        "UNKNOWN_PARAMETERS_REJECTED"
    )
    assert "EXPLICIT_SEED" in manifest["seed_policy"]


def test_future_result_bundle_contract_is_complete() -> None:
    result = load(CONTRACT_PATH)["future_result_bundle_contract"]
    assert set(result["required_fields"]) == RESULT_FIELDS
    assert result["machine_tokens_separate_from_human_explanations"] is True
    assert result["software_pass_implies_profitable_strategy"] is False
    assert result["default_display_order"] == "CHRONOLOGICAL"


def test_trial_ledger_counts_every_outcome_and_prevents_resets() -> None:
    ledger = load(CONTRACT_PATH)["trial_ledger"]
    assert ledger["schema_status"] == "REQUIRED_INTERFACE_MISSING"
    assert ledger["persistent"] is True
    assert ledger["append_only_logical_history"] is True
    assert ledger["atomic_trial_budget_reservation_required"] is True
    assert set(ledger["counted_outcomes"]) == {
        "COMPLETED",
        "FAILED",
        "STOPPED",
        "REJECTED",
        "MANUALLY_INITIATED",
        "LATER_SUPERSEDED",
    }
    assert {
        "HIDDEN_FAILED_TRIALS",
        "TRIAL_COUNT_RESETS",
        "PROVIDER_CHANGES_AFTER_FAILURE",
        "SPLIT_CHANGES_AFTER_FAILURE",
        "FAMILY_RELABELLING",
        "UNLIMITED_FEATURE_OR_PARAMETER_SEARCH",
        "SELECTION_FROM_VISIBLE_WINNERS_ONLY",
    } == set(ledger["prohibitions"])
    assert ledger["ui_session_state_may_be_ledger_authority"] is False


def test_anti_overfitting_support_and_gaps_are_explicit() -> None:
    support = load(CONTRACT_PATH)["anti_overfitting_support"]
    assert support["raw_sharpe"].startswith("PRESENT_HISTORICAL")
    assert support["probabilistic_sharpe_ratio"] == "NOT_IDENTIFIED_INTERFACE_GAP"
    assert support["deflated_sharpe_ratio_or_probability"].startswith(
        "PRESENT_HISTORICAL"
    )
    assert support["probability_of_backtest_overfitting"].startswith(
        "PRESENT_HISTORICAL"
    )
    assert "HOLM" in support["multiple_testing_correction"]
    assert "SEEDED" in support["seeded_null_controls"]
    assert support["new_statistical_calculation_implemented_by_this_mission"] is False


def test_duplicate_pnl_cost_risk_and_decision_logic_is_prohibited() -> None:
    prohibited = set(load(CONTRACT_PATH)["duplicate_logic_prohibitions"])
    assert {
        "SIGNALS",
        "FILLS",
        "POSITION_STATE",
        "PNL",
        "FEES",
        "SPREAD",
        "SLIPPAGE",
        "LATENCY",
        "FUNDING",
        "MARKET_IMPACT",
        "DRAWDOWN",
        "EXPOSURE",
        "STATISTICAL_DECISIONS",
        "PROMOTION_DECISIONS",
    } <= prohibited


def test_exact_audited_paths_counts_and_interface_gaps() -> None:
    audit = load(CONTRACT_PATH)["interface_audit"]
    assert audit["audited_interface_paths"] == AUDITED_INTERFACE_PATHS
    assert audit["audited_interface_count"] == 27
    assert audit["current_reusable_interface_count"] == 3
    assert audit["historical_only_interface_count"] == 20
    assert audit["machine_only_interface_count"] == 4
    assert audit["historical_or_machine_only_interface_count"] == 24
    assert audit["interface_gap_count"] == 5
    assert [gap["gap_id"] for gap in audit["exact_interface_gaps"]] == [
        "GAP-01",
        "GAP-02",
        "GAP-03",
        "GAP-04",
        "GAP-05",
    ]
    assert all(gap["minimal_missing_interface"] for gap in audit["exact_interface_gaps"])


def test_architecture_is_thin_and_blocked_until_gaps_close() -> None:
    architecture = load(CONTRACT_PATH)["adapter_architecture"]
    assert architecture["sequence"] == [
        "LOCAL_COCKPIT_UI",
        "DETERMINISTIC_EXPERIMENT_MANIFEST",
        "THIN_COCKPIT_APPLICATION_SERVICE",
        "EXISTING_AUTHORITATIVE_DELTAGRID_ENGINE",
        "EXISTING_SIMULATOR_COSTS_RISK_AND_EVALUATION",
        "DETERMINISTIC_RESULT_BUNDLE",
        "READ_ONLY_COCKPIT_VIEWS",
    ]
    assert architecture["status"] == "PROPOSED_BUT_BLOCKED_BY_FIVE_INTERFACE_GAPS"
    assert architecture["ui_may_persist_authority"] is False
    assert architecture["ui_may_recalculate_domain_results"] is False


def test_dependency_cap_and_prohibited_architecture() -> None:
    decision = load(CONTRACT_PATH)["dependency_decision"]
    assert decision["later_authorized_new_runtime_dependencies"] == ["streamlit"]
    assert decision["later_authorized_new_runtime_dependency_count"] == 1
    assert decision["maximum_new_runtime_dependencies"] == 3
    assert decision["optional_not_authorized_by_default"] == ["plotly"]
    assert decision["not_required"] == ["duckdb"]
    assert set(decision["prohibited"]) == {
        "external database servers",
        "React",
        "Node.js",
        "Kubernetes",
        "Redis",
        "Celery",
        "microservices",
    }
    assert "NO INSTALLATION AUTHORIZED_NOW" in decision["status"]


def test_docs_navigation_and_final_stop_decision() -> None:
    docs_home = DOCS_HOME.read_text(encoding="utf-8")
    charter = CHARTER_PATH.read_text(encoding="utf-8")
    assert (
        "[Research Cockpit v0 charter]"
        "(DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER.md)"
    ) in docs_home
    assert "STOP_REPOSITORY_INTERFACE_GAPS_FOUND" in docs_home
    assert "does not authorize a" in docs_home
    assert "Final decision: `STOP_REPOSITORY_INTERFACE_GAPS_FOUND`." in charter
    assert "No dashboard, strategy, market" in charter
    contract = load(CONTRACT_PATH)
    assert contract["final_decision"] == "STOP_REPOSITORY_INTERFACE_GAPS_FOUND"
    assert contract["next_authorized_action"] == (
        "STOP_REPOSITORY_INTERFACE_GAPS_FOUND"
    )


def test_registry_has_exact_two_additions_and_required_totals() -> None:
    registry = load(REGISTRY_PATH)
    by_path = {item["path"]: item for item in registry["documents"]}
    counts = Counter(item["classification"] for item in registry["documents"])
    assert len(by_path) == 168
    assert counts == {
        "CURRENT_PUBLIC": 10,
        "CURRENT_INTERNAL": 6,
        "HISTORICAL": 97,
        "SUPERSEDED": 8,
        "DESIGN_ONLY": 2,
        "EVIDENCE_IMMUTABLE": 10,
        "MACHINE_REFERENCE": 35,
    }
    machine = by_path[
        "contracts/DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER_V1.json"
    ]
    human = by_path["docs/DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER.md"]
    assert machine["classification"] == "MACHINE_REFERENCE"
    assert machine["authority_level"] == "CURRENT_CONTROLLING_STAGE_CONTRACT"
    assert human["classification"] == "CURRENT_INTERNAL"
    assert human["authority_level"] == "CURRENT_CONTROLLING_STAGE_EXPLANATION"
    for item in (machine, human):
        assert item["test_dependent"] is True
        assert item["conflicts_with_current_state"] is False
        assert item["recommended_treatment"] == "LEAVE_UNCHANGED"
        assert "final freeze continues to control" in item["notes"].casefold()


def test_all_166_base_registry_entries_are_parsed_value_identical() -> None:
    base = json.loads(base_bytes("docs/documentation-status.json"))
    current = load(REGISTRY_PATH)
    base_by_path = {item["path"]: item for item in base["documents"]}
    current_by_path = {item["path"]: item for item in current["documents"]}
    assert len(base_by_path) == 166
    assert len(current_by_path) == 168
    assert set(current_by_path) - set(base_by_path) == {
        "contracts/DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER_V1.json",
        "docs/DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER.md",
    }
    assert all(current_by_path[path] == item for path, item in base_by_path.items())
    assert {key: value for key, value in current.items() if key != "documents"} == {
        key: value for key, value in base.items() if key != "documents"
    }


def test_exactly_one_contract_added_and_all_base_contracts_are_identical() -> None:
    base_contracts = {
        path
        for path in git(
            "ls-tree", "-r", "--name-only", BASE_COMMIT, "--", "contracts"
        ).stdout.splitlines()
        if path.endswith(".json") and PurePosixPath(path).parent.as_posix() == "contracts"
    }
    current_contracts = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "contracts").glob("*.json")
    }
    new_contract = "contracts/DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER_V1.json"
    assert current_contracts == base_contracts | {new_contract}
    assert current_contracts - base_contracts == {new_contract}
    for path in base_contracts:
        assert (ROOT / path).read_bytes() == base_bytes(path)
    contract = load(CONTRACT_PATH)
    assert all(contract[field] is False for field in FALSE_AUTHORIZATIONS)
    assert contract["final_freeze_contract"]["remains_authoritative"] is True


def test_protected_implementation_dependency_evidence_and_history_are_unchanged() -> None:
    changed = changed_paths()
    assert not any(
        path.startswith(
            (
                "offchain/backtest/",
                "offchain/research/",
                "offchain/risk/",
                "offchain/simulator/",
                "offchain/portfolio/",
                "offchain/governance/",
                "scripts/",
                "docs/evidence/",
                "docs/research-summaries/",
                "docs/ADR/",
            )
        )
        for path in changed
    )
    assert "offchain/requirements.txt" not in changed
    assert "README.md" not in changed
    assert not any("SHA256SUMS" in path for path in changed)
    assert not any(path.endswith((".html", ".css", ".js", ".ts", ".tsx")) for path in changed)
    assert not any(
        path.endswith(".py") and not path.startswith("offchain/tests/")
        for path in changed
    )


def test_compatibility_test_function_counts_and_names_are_preserved() -> None:
    for path, expected_count in COMPATIBILITY_TEST_COUNTS.items():
        old_tree = ast.parse(base_bytes(path).decode("utf-8"))
        new_tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        old_names = [
            node.name
            for node in ast.walk(old_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ]
        new_names = [
            node.name
            for node in ast.walk(new_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ]
        assert len(old_names) == expected_count
        assert new_names == old_names


def test_valid_decision_token_and_no_positive_authority_language() -> None:
    contract = load(CONTRACT_PATH)
    assert contract["final_decision"] in {
        "AUTHORIZE_COCKPIT_IMPLEMENTATION_ONLY",
        "STOP_REPOSITORY_INTERFACE_GAPS_FOUND",
    }
    assert contract["final_decision"] == "STOP_REPOSITORY_INTERFACE_GAPS_FOUND"
    combined = " ".join(
        (
            CONTRACT_PATH.read_text(encoding="utf-8"),
            CHARTER_PATH.read_text(encoding="utf-8"),
        )
    ).casefold()
    forbidden = {
        "paper trading is authorized",
        "live trading is authorized",
        "capital deployment is authorized",
        "model training is authorized",
        "validated profitable strategy exists\": true",
        "control_execution_authorized\": true",
    }
    assert not any(phrase in combined for phrase in forbidden)

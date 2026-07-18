from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts" / "DELTAGRID_FINAL_FREEZE_V1.json"
RESET = ROOT / "contracts" / "DELTAGRID_PRODUCT_RESET_V1.json"
ALPHA_A = ROOT / "contracts" / "ALPHA_SEARCH_A_REJECTION_V1.json"
ALPHA_B_PROTOCOL = ROOT / "contracts" / "ALPHA_SEARCH_B_PROTOCOL_V1.json"
ALPHA_B_COST = ROOT / "contracts" / "ALPHA_SEARCH_B_COST_ATTRIBUTION_V1.json"
ALPHA_B_DECISION = (
    ROOT / "docs/evidence/alpha_search_b_development/DEVELOPMENT_DECISION.json"
)
ALPHA_B_ACCESS = (
    ROOT / "docs/evidence/alpha_search_b_development/PROHIBITED_ACCESS_AUDIT.json"
)
README = ROOT / "README.md"
REPORT = ROOT / "docs/DELTAGRID_FINAL_PROJECT_REPORT.md"
FREEZE = ROOT / "docs/DELTAGRID_FINAL_FREEZE.md"
INTAKE = ROOT / "docs/FUTURE_STRATEGY_INTAKE_POLICY.md"
ML_POLICY = ROOT / "docs/DELTAGRID_ML_RESEARCH_ADAPTER.md"
VERIFICATION = (
    ROOT
    / "docs/evidence/deltagrid_final_freeze/FINAL_FREEZE_VERIFICATION.json"
)
MANIFEST = ROOT / "docs/evidence/deltagrid_final_freeze/SHA256SUMS.txt"

BASE_COMMIT = "a31f4da4fc8b52ca2fa6aaad697350d6e9180736"
PROTOCOL_HASH = "ee82fdb3758028cfa6455ffa610cbff46855890ded65cc2175801897fe509469"
COST_HASH = "e102f6aa21f83dfdc05090411c790f1d2ed2803d02f310fb3289e67c2790165c"
DECISION_HASH = "3aa332f04287e55d8ceefeb7d19b2265363f70a703bda2cc98efab85f1f2984a"
ACCESS_HASH = "9d25db64ce691d1d04903849237331a938ecbfdf31877a00a1c3f43155e21ed1"
LEGITIMATE_HISTORICAL_COMMIT_KEYS = {
    "research_closure_base_commit",
    "alpha_search_b_publication_commit",
}
FORBIDDEN_TRANSIENT_CONTRACT_KEYS = {
    "final_freeze_publication_commit",
    "publication_commit",
    "current_git_head",
    "git_head",
    "current_branch",
    "branch_name",
    "worktree_path",
    "absolute_repository_path",
    "repository_path",
    "generated_timestamp",
    "generated_at",
    "creation_timestamp",
    "created_at",
    "verification_timestamp",
    "verified_at",
    "hostname",
    "username",
    "command_duration",
    "command_duration_seconds",
    "random_run_identifier",
    "random_run_id",
    "run_id",
}
TRANSIENT_CONTRACT_KEY_MARKERS = (
    "publication_commit",
    "current_git_head",
    "current_head",
    "git_head",
    "current_branch",
    "branch_name",
    "worktree_path",
    "repository_path",
    "generated_timestamp",
    "generated_at",
    "creation_timestamp",
    "created_at",
    "verification_timestamp",
    "verified_at",
    "hostname",
    "username",
    "command_duration",
    "random_run_identifier",
    "random_run_id",
    "run_id",
)
PRIVATE_KEY_HEADER_PATTERN = re.compile(
    r"-----BEGIN(?: [A-Z][A-Z0-9-]*)* PRIVATE KEY-----",
    re.IGNORECASE,
)
EXPECTED_MANIFEST_PATHS = [
    "README.md",
    "contracts/DELTAGRID_FINAL_FREEZE_V1.json",
    "docs/DELTAGRID_FINAL_FREEZE.md",
    "docs/DELTAGRID_FINAL_PROJECT_REPORT.md",
    "docs/DELTAGRID_ML_RESEARCH_ADAPTER.md",
    "docs/FUTURE_STRATEGY_INTAKE_POLICY.md",
    "docs/evidence/deltagrid_final_freeze/FINAL_FREEZE_VERIFICATION.json",
    "offchain/tests/test_deltagrid_final_freeze.py",
]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_hash(value: dict) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_contract_key(key: str) -> str:
    snake_case = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key)
    return re.sub(r"[^a-z0-9]+", "_", snake_case.lower()).strip("_")


def is_credential_like_high_entropy(value: str) -> bool:
    if re.fullmatch(r"[0-9a-fA-F]{64}", value):
        return False
    return bool(
        re.search(r"[a-z]", value)
        and re.search(r"[A-Z]", value)
        and re.search(r"\d", value)
    )


def test_final_freeze_contract_identity_and_canonical_hash() -> None:
    assert CONTRACT.is_file()
    contract = load(CONTRACT)
    assert contract["contract_id"] == "deltagrid-final-freeze-v1"
    assert contract["contract_version"] == 1
    core = dict(contract)
    claimed = core.pop("contract_hash_sha256")
    assert canonical_hash(core) == claimed
    assert "contract_hash_sha256" not in core
    assert contract["research_closure_base_commit"] == BASE_COMMIT
    assert contract["alpha_search_b_publication_commit"] == BASE_COMMIT
    normalized_keys = {normalize_contract_key(key) for key in contract}
    assert FORBIDDEN_TRANSIENT_CONTRACT_KEYS.isdisjoint(normalized_keys)
    for key in normalized_keys - LEGITIMATE_HISTORICAL_COMMIT_KEYS:
        assert not any(marker in key for marker in TRANSIENT_CONTRACT_KEY_MARKERS)


def test_final_research_outcomes_and_no_selected_candidate() -> None:
    contract = load(CONTRACT)
    assert contract["final_project_status"] == (
        "COMPLETED_RESEARCH_PLATFORM_NO_VALIDATED_ALPHA"
    )
    assert contract["alpha_search_a_outcome"] == "REJECTED_BEFORE_STRATEGY_BUILD"
    assert contract["alpha_search_b_outcome"] == (
        "ALPHA_SEARCH_B_REJECTED_DEVELOPMENT"
    )
    assert contract["selected_candidate"] is None
    assert contract["remaining_authorized_alpha_family_count"] == 0
    assert contract["alpha_discovery_status"] == (
        "STOPPED_ALL_AUTHORIZED_FAMILIES_REJECTED"
    )
    assert contract["validated_profitable_strategy"] is False
    assert contract["no_profitability_claim"] is True


def test_access_trading_rescue_and_capital_remain_closed() -> None:
    contract = load(CONTRACT)
    assert contract["scoped_alpha_search_b_validation_access_count"] == 0
    assert contract["scoped_alpha_search_b_holdout_access_count"] == 0
    for key in (
        "freqtrade_translation_authorized",
        "dry_run_authorized",
        "live_trading_authorized",
        "capital_deployment_authorized",
        "replacement_or_rescue_family_authorized",
        "ml_self_promotion_authorized",
        "automatic_capital_authorization",
    ):
        assert contract[key] is False


def test_freeze_reopening_and_ml_status_are_fail_closed() -> None:
    contract = load(CONTRACT)
    assert contract["infrastructure_freeze_status"] == "ACTIVE"
    assert contract["mission_numbering_retired"] is True
    assert contract["historical_records_immutable"] is True
    assert contract["future_strategy_reopening_requirement"] == (
        "NEW_VERSIONED_REOPENING_CONTRACT_REQUIRED"
    )
    assert contract["future_ml_status"] == "DOCUMENTED_NOT_AUTHORIZED"
    assert "NEW_VERSIONED_REOPENING_CONTRACT" in contract["supersession_policy"]
    assert "OUTSIDE_GIT" in contract["raw_market_data_tracking_policy"]


def test_committed_historical_contracts_still_control_outcomes() -> None:
    alpha_a = load(ALPHA_A)
    reset = load(RESET)
    decision = load(ALPHA_B_DECISION)
    assert alpha_a["status"] == "REJECTED_BEFORE_STRATEGY_BUILD"
    assert alpha_a["strategy_signals_evaluated"] == 0
    assert alpha_a["pnl_metrics_evaluated"] == 0
    assert decision["decision"] == "ALPHA_SEARCH_B_REJECTED_DEVELOPMENT"
    assert decision["selected_candidate"] is None
    assert decision["validation_performance_accessed"] is False
    assert decision["holdout_performance_accessed"] is False
    assert reset["final_research_budget"]["remaining_new_economic_families"] == 0
    assert reset["mission_numbering"] == "RETIRED"


def test_controlling_historical_identities_match_repository_bytes() -> None:
    contract = load(CONTRACT)
    protocol = load(ALPHA_B_PROTOCOL)
    protocol_core = dict(protocol)
    assert protocol_core.pop("contract_hash_sha256") == PROTOCOL_HASH
    assert canonical_hash(protocol_core) == PROTOCOL_HASH
    assert contract["alpha_search_b_protocol_identity"] == PROTOCOL_HASH
    assert contract["alpha_search_b_cost_identity_type"] == "FILE_SHA256"
    assert contract["alpha_search_b_cost_attribution_identity"] == COST_HASH
    assert file_hash(ALPHA_B_COST) == COST_HASH
    assert contract["alpha_search_b_decision_identity_type"] == "FILE_SHA256"
    assert contract["alpha_search_b_development_decision_identity"] == DECISION_HASH
    assert file_hash(ALPHA_B_DECISION) == DECISION_HASH
    assert contract["alpha_search_b_prohibited_access_audit_file_sha256"] == (
        ACCESS_HASH
    )
    assert file_hash(ALPHA_B_ACCESS) == ACCESS_HASH
    assert "preserved_ignored_artifact_tree_sha256" not in contract
    assert "ignored_artifact_count" not in contract


def test_committed_pre_freeze_baselines_are_labelled_historically() -> None:
    contract = load(CONTRACT)
    assert contract["pre_freeze_alpha_search_b_reset_focused_pass_count"] == 37
    assert contract["pre_freeze_complete_suite_pass_count"] == 715
    assert contract["pre_freeze_warning_count"] == 1
    readme = README.read_text(encoding="utf-8")
    report = REPORT.read_text(encoding="utf-8")
    assert "Committed pre-freeze evidence records 37" in readme
    assert "715 passing complete off-chain tests" in readme
    assert "committed pre-freeze Alpha Search B/reset focused baseline is 37" in report
    assert "committed complete off-chain baseline is 715" in report
    assert "not represented as current post-change totals" in report


def test_readme_prominently_states_the_public_closure() -> None:
    readme = README.read_text(encoding="utf-8")
    opening = readme[:900]
    assert "no validated profitable strategy" in opening
    assert "does not authorize live trading or capital deployment" in opening
    assert "Infrastructure maturity does not establish alpha" in opening
    assert "Test success verifies those properties only; it does not establish alpha" in readme
    assert "No Alpha Search B candidate was authorized for Freqtrade translation" in readme
    assert "not a permanent assertion about every future repository HEAD" in readme


def test_final_report_contains_every_required_historical_phase() -> None:
    report = REPORT.read_text(encoding="utf-8")
    required = (
        "Mission 84 synthetic research closure",
        "Mission 85 research-charter lock",
        "Mission 86 real-market data foundation",
        "Mission 87 dataset certification",
        "Mission 88 execution-cost model",
        "Mission 89 funding/basis-carry rejection",
        "Mission 90 directional-tournament rejection",
        "Historical Freqtrade hybrid and parity boundary",
        "Product reset",
        "Alpha Search A hypothesis and rejection",
        "Alpha Search B protocol",
        "Alpha Search B data acquisition and certification",
        "Alpha Search B feature engine",
        "Alpha Search B simulator",
        "Alpha Search B candidate-level results",
        "Null controls",
        "Holm multiple-testing adjustment",
        "Replication analysis",
        "P&L attribution",
        "Cost attribution",
        "Final Alpha Search B development decision",
        "Controlling-hash appendix",
    )
    for heading in required:
        assert heading in report
    assert "Alpha Search B acquisition and development publication recorded zero" in report
    assert "A future final-freeze publication commit does not yet exist" in report
    assert "Current Freqtrade dry-run, live trading, and capital deployment remain unauthorized" in report


def test_report_candidate_table_uses_recorded_development_values() -> None:
    report = REPORT.read_text(encoding="utf-8")
    expected_rows = (
        "| `BTC_SELF_FLOW_PERSISTENCE_60M` | 227 trades | -20.7017875081200",
        "| `BTC_SELF_FLOW_PERSISTENCE_120M` | 218 trades | -21.2115871703000",
        "| `BTC_FLOW_LEADS_ETH_60M` | 14 trades | -0.9213430000",
        "| `BTC_FLOW_LEADS_SOL_60M` | 15 trades | -0.0853141960",
    )
    for row in expected_rows:
        assert row in report
    assert "All four failed required gates; `selected_candidate` is `null`" in report


def test_evidence_classes_and_deterministic_verification_scope_are_explicit() -> None:
    report = REPORT.read_text(encoding="utf-8")
    assert "A. Committed controlling evidence" in report
    assert "B. Current final-freeze verification" in report
    assert "C. Operator-reported publication metadata" in report
    evidence = load(VERIFICATION)
    assert evidence["verification_scope"] == (
        "PRE_PUBLICATION_FINAL_FREEZE_CANDIDATE"
    )
    assert evidence["evidence_class"] == "CURRENT_FINAL_FREEZE_VERIFICATION"
    assert evidence["research_closure_base_commit"] == BASE_COMMIT
    actions = evidence["publication_actions_during_verification"]
    assert actions == {
        "commit_performed": False,
        "push_performed": False,
        "pull_request_created": False,
        "merge_performed": False,
    }


def test_future_strategy_policy_requires_full_reopening_governance() -> None:
    policy = INTAKE.read_text(encoding="utf-8")
    assert "requires a new versioned reopening contract" in policy
    for required in (
        "overlap audit",
        "causally available at the decision timestamp",
        "total experiment budget",
        "one fixed validation stage and one sealed holdout",
        "market-impact",
        "multiple-testing control",
        "independent-engine ledger parity",
        "separate proof-capital authorization",
        "separate live-trading authorization",
        "Relabelling a rejected family",
        "Automatic strategy, dry-run, model, or capital promotion",
    ):
        assert required in policy


def test_ml_policy_prohibits_leakage_random_splits_and_self_promotion() -> None:
    policy = ML_POLICY.read_text(encoding="utf-8")
    assert "design policy only" in policy
    assert "No implementation, model training, evaluation" in policy
    assert "Authoritative random train/test splitting is prohibited" in policy
    assert "Rolling or expanding chronological evaluation is required" in policy
    assert "purging and an appropriate gap or embargo" in policy
    assert "may not promote itself, authorize trading, or authorize capital" in policy
    assert "Alpha Search A outcomes cannot be used as a search oracle" in policy
    assert "Alpha Search B outcomes cannot be used as a search oracle" in policy
    assert "FreqAI may be considered only as an isolated future implementation" in policy


def test_checksum_manifest_has_exact_paths_and_verifies() -> None:
    lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    parsed: list[tuple[str, str]] = []
    for line in lines:
        digest, path = line.split("  ", 1)
        assert re.fullmatch(r"[0-9a-f]{64}", digest)
        parsed.append((digest, path))
    assert [path for _, path in parsed] == EXPECTED_MANIFEST_PATHS
    assert str(MANIFEST.relative_to(ROOT)) not in EXPECTED_MANIFEST_PATHS
    for digest, relative in parsed:
        assert file_hash(ROOT / relative) == digest


def test_no_raw_alpha_search_b_data_is_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files", "offchain/data/alpha_search_b"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == ""


def test_closure_files_contain_no_obvious_credential_material() -> None:
    paths = [
        ROOT / relative
        for relative in EXPECTED_MANIFEST_PATHS
        if (ROOT / relative).exists()
    ] + [MANIFEST]
    assignment = re.compile(
        r"(?i)\b(?:api[_-]?key|secret|access[_-]?token)\s*[:=]\s*[\"']?"
        r"[A-Za-z0-9_./+=-]{12,}"
    )
    high_entropy = re.compile(r"[A-Za-z0-9+/=_-]{48,}")
    private_key_prefix = "-----BEGIN "
    required_private_key_types = ("", "RSA", "EC", "DSA", "OPENSSH", "ENCRYPTED")
    for key_type in required_private_key_types:
        type_prefix = f"{key_type} " if key_type else ""
        header = private_key_prefix + type_prefix + "PRIVATE KEY-----"
        assert PRIVATE_KEY_HEADER_PATTERN.fullmatch(header)
    for header in (
        private_key_prefix + "PUBLIC KEY-----",
        private_key_prefix + "RSA PUBLIC KEY-----",
    ):
        assert PRIVATE_KEY_HEADER_PATTERN.search(header) is None
    approved_sha256_identities = {
        PROTOCOL_HASH,
        COST_HASH,
        DECISION_HASH,
        ACCESS_HASH,
        load(CONTRACT)["contract_hash_sha256"],
    }
    for identity in approved_sha256_identities:
        assert re.fullmatch(r"[0-9a-f]{64}", identity)
        assert PRIVATE_KEY_HEADER_PATTERN.search(identity) is None
        assert is_credential_like_high_entropy(identity) is False

    findings: list[tuple[str, str]] = []
    bearer_marker = "BEARER" + " "
    for path in paths:
        text = path.read_text(encoding="utf-8")
        upper = text.upper()
        if PRIVATE_KEY_HEADER_PATTERN.search(text):
            findings.append((str(path.relative_to(ROOT)), "private-key-header"))
        if bearer_marker in upper:
            findings.append((str(path.relative_to(ROOT)), "bearer-literal"))
        if assignment.search(text):
            findings.append((str(path.relative_to(ROOT)), "credential-assignment"))
        for value in high_entropy.findall(text):
            if not is_credential_like_high_entropy(value):
                continue
            findings.append((str(path.relative_to(ROOT)), "high-entropy-value"))
    assert findings == []

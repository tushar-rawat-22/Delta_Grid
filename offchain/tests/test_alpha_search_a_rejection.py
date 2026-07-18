from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REJECTION_CONTRACT = ROOT / "contracts" / "ALPHA_SEARCH_A_REJECTION_V1.json"
REJECTION_EVIDENCE = (
    ROOT
    / "docs"
    / "evidence"
    / "alpha_search_a_feasibility"
    / "FEASIBILITY_REJECTION.json"
)
RESET_CONTRACT = ROOT / "contracts" / "DELTAGRID_PRODUCT_RESET_V1.json"
EXPECTED_REJECTION_HASH = (
    "4114319b1ea9313da0815386219b991183d3f7cbb3016a4895a768f44c4af1df"
)
EXPECTED_EVIDENCE_HASH = (
    "3be6f6f57f010e43a70c8db5e7fe3fb2e07bb44916fe270567c2447523f612ba"
)


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


def programs() -> list[dict]:
    return load(RESET_CONTRACT)["final_research_budget"]["programs"]


def test_alpha_search_a_is_rejected_before_strategy_construction() -> None:
    rejection = load(REJECTION_CONTRACT)
    assert rejection["program_id"] == "ALPHA_SEARCH_A_MACRO_RISK_REGIME"
    assert rejection["status"] == "REJECTED_BEFORE_STRATEGY_BUILD"
    assert rejection["decision"] == "STOP_NO_PROTOCOL_RESCUE"
    assert rejection["failure_code"] == (
        "REQUIRED_FIRST_AVAILABILITY_EVIDENCE_UNAVAILABLE"
    )
    assert rejection["failed_required_series"] == "SP500"
    assert rejection["focused_test_count_before_provider_stop"] == 35
    assert rejection["focused_tests_passed"] is True


def test_no_rescue_or_substitution_is_authorized() -> None:
    rejection = load(REJECTION_CONTRACT)
    for field in (
        "parameter_rescue_authorized",
        "provider_substitution_authorized",
        "series_substitution_authorized",
        "sample_threshold_reduction_authorized",
        "decision_timestamp_change_authorized",
    ):
        assert rejection[field] is False


def test_all_prohibited_access_counters_remain_zero() -> None:
    rejection = load(REJECTION_CONTRACT)
    for field in (
        "btc_price_fields_accessed",
        "btc_return_fields_accessed",
        "strategy_signals_evaluated",
        "pnl_metrics_evaluated",
        "secret_disclosure_count",
    ):
        assert rejection[field] == 0
    for field in (
        "btc_archives_accessed",
        "validation_performance_accessed",
        "holdout_performance_accessed",
        "freqtrade_strategy_created",
        "backtest_run",
        "dry_run",
        "live_trading",
        "capital_deployment",
    ):
        assert rejection[field] is False


def test_no_profitability_conclusion_is_claimed() -> None:
    claim = load(REJECTION_CONTRACT)["economic_claim"]
    assert claim == (
        "No conclusion is made about whether macro regimes can predict BTC. "
        "The frozen data-feasibility protocol was rejected."
    )


def test_alpha_search_b_is_only_authorized_remaining_family() -> None:
    remaining = [
        item
        for item in programs()
        if item["program_id"] != "ALPHA_SEARCH_A_MACRO_RISK_REGIME"
    ]
    assert [item["program_id"] for item in remaining] == [
        "ALPHA_SEARCH_B_MICROSTRUCTURE_LIQUIDITY_STATE"
    ]
    assert load(REJECTION_CONTRACT)["next_program"] == remaining[0]["program_id"]


def test_remaining_family_count_is_zero_after_alpha_search_b_rejection() -> None:
    reset = load(RESET_CONTRACT)
    assert reset["final_research_budget"]["remaining_new_economic_families"] == 0


def test_reset_invariants_remain_active() -> None:
    reset = load(RESET_CONTRACT)
    assert reset["mission_numbering"] == "RETIRED"
    freeze = reset["infrastructure_freeze"]
    assert all(
        freeze[field] is False
        for field in (
            "new_dashboards",
            "new_agent_frameworks",
            "new_execution_engines",
            "new_evidence_subsystems",
            "new_ui_work",
            "new_live_trading_features",
        )
    )
    assert reset["current_state"]["validated_profitable_strategy"] is False


def test_capital_and_trading_authority_remain_blocked() -> None:
    reset = load(RESET_CONTRACT)
    assert reset["capital_policy"]["leverage"] == 1
    assert reset["capital_policy"]["maximum_open_positions"] == 1
    assert reset["current_state"]["live_trading_authorized"] is False
    assert reset["current_state"]["capital_deployment_authorized"] is False


def test_pyarrow_is_exactly_pinned() -> None:
    lines = (ROOT / "offchain" / "requirements.txt").read_text().splitlines()
    assert [line for line in lines if line.lower().startswith("pyarrow")] == [
        "pyarrow==25.0.0"
    ]


def test_rejection_contract_and_evidence_hashes_are_deterministic() -> None:
    contract = load(REJECTION_CONTRACT)
    contract_core = dict(contract)
    assert contract_core.pop("contract_hash_sha256") == EXPECTED_REJECTION_HASH
    assert canonical_hash(contract_core) == EXPECTED_REJECTION_HASH

    evidence = load(REJECTION_EVIDENCE)
    evidence_core = dict(evidence)
    assert evidence_core.pop("evidence_hash_sha256") == EXPECTED_EVIDENCE_HASH
    assert evidence_core["rejection_contract_hash_sha256"] == EXPECTED_REJECTION_HASH
    assert canonical_hash(evidence_core) == EXPECTED_EVIDENCE_HASH

    for key, value in contract_core.items():
        assert evidence[key] == value


def test_removed_feasibility_implementation_files_do_not_exist() -> None:
    for relative in (
        "contracts/ALPHA_SEARCH_A_FEASIBILITY_V1.json",
        "offchain/research/alpha_search_a_feasibility.py",
        "offchain/tests/test_alpha_search_a_feasibility.py",
        "docs/ALPHA_SEARCH_A_FEASIBILITY.md",
    ):
        assert not (ROOT / relative).exists()


def test_no_tracked_raw_provider_file_exists() -> None:
    result = subprocess.run(
        ["git", "ls-files", "offchain/data/alpha_search_a_feasibility"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == ""
    assert not (ROOT / "offchain/data/alpha_search_a_feasibility").exists()


def test_no_fred_key_or_secret_shaped_value_exists_in_diff() -> None:
    diff = subprocess.run(
        ["git", "diff", "--no-ext-diff"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    new_files = (
        REJECTION_CONTRACT,
        REJECTION_EVIDENCE,
        ROOT / "docs/ALPHA_SEARCH_A_REJECTION.md",
        ROOT / "offchain/tests/test_alpha_search_a_rejection.py",
    )
    data = diff + b"\n".join(path.read_bytes() for path in new_files)
    key = os.environ.get("FRED_API_KEY", "").encode()
    assert not key or key not in data
    secret_query_token = b"api_" + b"key="
    assert secret_query_token not in data.lower()
    secret_shaped = re.findall(
        rb"(?<![a-z0-9])[a-z0-9]{32}(?![a-z0-9])",
        data.lower(),
    )
    assert secret_shaped == []

from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from offchain.research.development_runtime.artifacts import verify_development_result as real_m102_verifier
from offchain.research.development_runtime.kernel import TargetExposureIntent
from offchain.research.development_runtime.loader import MarketEvent
from offchain.research.development_runtime.registry import ExperimentRegistry, FamilyDefinition, VariantDefinition
from offchain.research.statistical_governance import (
    ACK_ACTIVATE_PROGRAM, ACK_ADMIT_CAMPAIGN, ACK_AUTHORIZE_STAGE, ACK_INITIALIZE, GovernanceError,
    M102ResultSource, PRNG_ID, ProtectedCustodySource, ProtectedEvaluator,
    StatisticalAdapter, activate_program, admit_campaign, authorize_stage, commit_campaign_proposal,
    create_program, derive_null_seed, empirical_p_value, holm_step_down,
    initialize_governance, load_contracts, minimum_repetitions, open_protected_stage,
    production_protected_evaluator_registry, production_statistical_adapter_registry,
    qualify_development, record_development_result, recover_protected_stage,
    register_materialization, validate_campaign_proposal, validate_partition_spec,
    verify_development_binding,
)
from offchain.research.statistical_governance import integrations, store
from offchain.research.statistical_governance import protected
from offchain.research.statistical_governance.core import (
    AUTONOMY_V5_HASH, AUTONOMY_V5_ID, MISSION100_HASH, MISSION100_ID,
    MISSION101_HASH, MISSION101_ID, MISSION102_HASH, MISSION102_ID,
    MISSION103_HASH, MISSION103_ID, MISSION94_HASH, MISSION94_ID,
    MISSION99_HASH, MISSION99_ID, M102_COST_EXECUTION_ID, M102_RISK_ID,
    canonical_bytes, canonical_hash, contract_hash,
)
from offchain.research.statistical_governance.statistics import NULL_SEED_DOMAIN
from offchain.research.statistical_governance.statistics import build_randomization_plan


H = lambda value: canonical_hash({"value": value})
COMMIT = "a" * 40
COST_EXECUTION_HASH = H("exact-cost-execution")
NOW = "2026-08-10T00:00:00.000000Z"


ADAPTER_DEFINITION = {"version": "v1", "input_schema": "m103-stat-input-v1",
    "output_schema": "m103-null-evidence-v1", "measurement_algorithm": "test-measurements-v1",
    "deterministic": True, "null_algorithm": {"kind": "M103_SHA256_COUNTER_ORDINAL_PLAN_V1",
        "algorithm_id": "FREQUENCY_MATCHED", "plan_definition": "ORDINAL_AND_U256_DRAW_V1"}}
EVALUATOR_DEFINITION = {"version": "v1", "input_schema": "m103-protected-input-v1",
    "output_schema": "m103-measurements-v1", "measurement_algorithm": "m102-metrics-projection-v1",
    "deterministic": True}


def adapter_function(value: dict) -> dict:
    score = value["verified_result"]["metrics"]["score"]
    plan = value["randomization_plan"]
    results = [{**entry, "statistic": "1" if score == "good" or entry["ordinal"] % 2 else "3"}
        for entry in plan["entries"]]
    null_core = {"kind": "EMPIRICAL_PLAN_RESULTS_V1", "plan_commitment": plan["plan_commitment"],
        "observed_statistic": "2", "results": results}
    measurements = {"sample_count": "20", "drawdown": "0.05", "rank_score": "2" if score == "good" else "10", "score_stat": "2"}
    return {
        "null_evidence": {**null_core, "evidence_commitment": canonical_hash(null_core)},
        "measurements": measurements, "measurement_evidence_hash": canonical_hash(measurements),
    }


TEST_ADAPTER = StatisticalAdapter("test-adapter", ADAPTER_DEFINITION, adapter_function)
def evaluator_function(value: dict) -> dict:
    measurements = {key: value["authoritative_metrics"][key] for key in ("net_pnl", "max_drawdown")}
    return {"measurements": measurements, "measurement_evidence_hash": canonical_hash(measurements)}


TEST_EVALUATOR = ProtectedEvaluator("test-evaluator", EVALUATOR_DEFINITION, evaluator_function)


def _contracts() -> dict:
    return {AUTONOMY_V5_ID: AUTONOMY_V5_HASH, MISSION103_ID: MISSION103_HASH,
        MISSION102_ID: MISSION102_HASH, MISSION101_ID: MISSION101_HASH,
        MISSION100_ID: MISSION100_HASH, MISSION99_ID: MISSION99_HASH,
        MISSION94_ID: MISSION94_HASH}


def _hypothesis(number: int) -> dict:
    m94 = {"trial_id": f"trial-{number}", "request_hash": H(f"request-{number}"),
        "budget_id": "budget-a", "budget_hash": H("budget"), "declared_trial_number": number,
        "fixed_trial_budget": 10}
    m101 = {"permit_id": "permit-a", "permit_hash": H("permit"),
        "dataset_id": "dataset-a", "descriptor_hash": H("descriptor"), "release_id": "release-development",
        "release_core_hash": H("release-core"), "release_certificate_hash": H("release-certificate")}
    m102 = {"registry_snapshot_hash": H("m102-registry"), "repository_commit": COMMIT}
    core = {"family_hash": H("family-a"), "variant_hash": H(f"variant-{number}"),
        "parameters": {"window": str(number)}, "execution_id": M102_COST_EXECUTION_ID,
        "execution_hash": COST_EXECUTION_HASH, "risk_id": M102_RISK_ID, "risk_hash": H("risk"),
        "m94": m94, "m101": m101, "m102": m102,
        "statistical_adapter_hash": TEST_ADAPTER.adapter_hash}
    return {"hypothesis_id": f"hypothesis-{number}", "hypothesis_hash": canonical_hash(core),
        "economic_family_id": "family-a", "family_hash": core["family_hash"],
        "variant_id": f"variant-{number}", "variant_hash": core["variant_hash"],
        "parameters": core["parameters"], "execution_id": M102_COST_EXECUTION_ID,
        "execution_hash": COST_EXECUTION_HASH, "risk_id": M102_RISK_ID,
        "risk_hash": H("risk"), "m94": m94, "m101": m101, "m102": m102,
        "statistical_adapter_id": TEST_ADAPTER.adapter_id,
        "statistical_adapter_hash": TEST_ADAPTER.adapter_hash}


def proposal(m: int = 2) -> dict:
    return {"schema_version": "1.0", "proposal_id": "proposal-a", "repository_commit": COMMIT,
        "economic_lineage_id": "lineage-a", "parent_campaign_hash": None,
        "evidence_epoch": "epoch-a", "evidence_cutoff_policy": {"kind": "FIXED", "cutoff": NOW},
        "family_universe": [{"family_id": "family-a", "family_hash": H("family-a")}],
        "hypothesis_universe": [_hypothesis(i) for i in range(1, m + 1)],
        "total_result_guided_capacity": m, "maximum_program_count": 1,
        "valid_until": "2099-01-01T00:00:00Z", "controlling_contracts": _contracts()}


def _spec(stage: str, index: int) -> dict:
    base = 1_893_456_000_000 + index * 100_000_000
    cutoff = datetime.fromtimestamp((base + 80_000_000) / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return {"schema_version": "1.0", "stage": stage, "stream_symbols": ["spot_ohlcv:BTCUSDT"],
        "stream_intervals": {"spot_ohlcv": "1h"}, "context_start": base, "scoring_start": base + 10_000_000,
        "scoring_end": base + 50_000_000, "availability_cutoff": cutoff,
        "time_unit": "MILLISECONDS", "minimum_samples": 2, "maximum_samples": 1000,
        "purge_ms": 1000, "gap_ms": 1000, "embargo_ms": 1000, "forward_horizon_ms": 1000,
        "data_certification_policy": "M99_M100_M101_VERIFIED",
        "availability_policy": "AVAILABLE_AT_OR_BEFORE_FROZEN_CUTOFF",
        "disjoint_from": list(("REPLICATION", "VALIDATION", "HOLDOUT")[:index]),
        "protected_start_state": "FLAT_CASH"}


def protocol(source: dict | None = None, *, exact: bool = False) -> dict:
    source = source or proposal()
    rules = {stage: {"statistic": "net_pnl", "direction": "GREATER", "threshold": "0",
        "measurement_gates": [{"measurement_id": "max_drawdown", "operator": "LE", "threshold": "100"}],
        "decision_rule": "M103_EXACT_ALL_GATES_AND_STATISTIC_V1",
        "minimum_scored_samples": 2} for stage in ("REPLICATION", "VALIDATION", "HOLDOUT")}
    return {"schema_version": "1.0", "program_id": "program-a", "repository_commit": COMMIT,
        "hypotheses": source["hypothesis_universe"], "primary_statistic": "score_stat",
        "direction": "GREATER", "null_policy": {"kind": "EXACT_ENUMERATION" if exact else "EMPIRICAL_MONTE_CARLO",
            "algorithm": "COMPLETE_SIGN_FLIP" if exact else "FREQUENCY_MATCHED"},
        "alpha": "0.05", "null_repetitions": 0 if exact else 5000,
        "hard_gates": [{"measurement_id": "sample_count", "operator": "GE", "threshold": "10"},
            {"measurement_id": "drawdown", "operator": "LE", "threshold": "0.1"}],
        "ranking_rule": "NUMERIC_VECTOR_ASCENDING_V1",
        "ranking_measurements": ["rank_score"],
        "tie_break_rule": "SEMANTIC_HYPOTHESIS_HASH_ASCENDING_V1",
        "maximum_selected_candidates": 1,
        "protected_partition_specs": [_spec(stage, index) for index, stage in enumerate(("REPLICATION", "VALIDATION", "HOLDOUT"))],
        "protected_acceptance_rules": rules,
        "protected_engines": {stage: {"executor_id": "DELTAGRID_M103_M102_EXACT_CANDIDATE_EXECUTOR_V1",
            "evaluator_id": TEST_EVALUATOR.evaluator_id, "evaluator_hash": TEST_EVALUATOR.evaluator_hash}
            for stage in ("REPLICATION", "VALIDATION", "HOLDOUT")},
        "protected_custody_policy": {"custody_runtime_root_hash": H("custody-root"),
            "source_policy_id": "M100_APPEND_ONLY_SINGLE_ROOT_V1",
            "completeness_policy_id": "M100_CHECKPOINT_THROUGH_FROZEN_CUTOFF_V1"},
        "prng_algorithm_version": PRNG_ID,
        "no_success_rescue": True, "expected_campaign_proposal_hash": canonical_hash(source)}


def verified(hypothesis: dict, score: str = "good") -> dict:
    return {"terminal_status": "SUCCESS", "verdict": "VERIFIED", "verification_mode": "FULL_REPLAY_FINALIZED",
        "verifier": "DELTAGRID_M102_INDEPENDENT_RESULT_VERIFIER_V1",
        "trial_id": hypothesis["m94"]["trial_id"], "request_hash": hypothesis["m94"]["request_hash"],
        "budget_id": hypothesis["m94"]["budget_id"], "budget_hash": hypothesis["m94"]["budget_hash"],
        "declared_trial_number": hypothesis["m94"]["declared_trial_number"], "fixed_trial_budget": hypothesis["m94"]["fixed_trial_budget"],
        "result_link_hash": H(f"link-{hypothesis['hypothesis_id']}"),
        "completion_event_timestamp": NOW, "result_linked_at": NOW,
        "permit_id": hypothesis["m101"]["permit_id"], "permit_hash": hypothesis["m101"]["permit_hash"],
        "dataset_id": hypothesis["m101"]["dataset_id"], "descriptor_hash": hypothesis["m101"]["descriptor_hash"],
        "release_id": hypothesis["m101"]["release_id"], "release_core_hash": hypothesis["m101"]["release_core_hash"],
        "release_certificate_hash": hypothesis["m101"]["release_certificate_hash"],
        "execution_spec_id": f"m102-spec-{hypothesis['hypothesis_id']}",
        "execution_spec_hash": H(f"spec-{hypothesis['hypothesis_id']}"),
        "authority_decision_time": NOW,
        "registry_snapshot_hash": hypothesis["m102"]["registry_snapshot_hash"],
        "result_bundle_id": f"bundle-{hypothesis['hypothesis_id']}", "result_hash": H(f"result-{hypothesis['hypothesis_id']}"),
        "repository_commit": COMMIT, "family_id": hypothesis["economic_family_id"], "family_hash": hypothesis["family_hash"],
        "variant_id": hypothesis["variant_id"], "variant_hash": hypothesis["variant_hash"],
        "parameters": hypothesis["parameters"], "cost_execution_id": M102_COST_EXECUTION_ID,
        "cost_execution_hash": hypothesis["execution_hash"], "risk_id": M102_RISK_ID,
        "risk_hash": hypothesis["risk_hash"],
        "metrics": {"score": score}}


def failed_verified(hypothesis: dict) -> dict:
    value = verified(hypothesis)
    keep = {"trial_id", "request_hash", "budget_id", "budget_hash", "declared_trial_number",
        "fixed_trial_budget", "permit_id", "permit_hash", "dataset_id", "descriptor_hash",
        "release_id", "release_core_hash", "release_certificate_hash", "execution_spec_id",
        "execution_spec_hash", "authority_decision_time", "registry_snapshot_hash", "repository_commit",
        "family_id", "family_hash", "variant_id", "variant_hash", "parameters", "cost_execution_id",
        "cost_execution_hash", "risk_id", "risk_hash"}
    return {"terminal_status": "FAILED", **{key: value[key] for key in keep},
        "failure_timestamp": NOW, "result_link_absent": True}


def source(number: int = 1) -> M102ResultSource:
    return M102ResultSource("/result", f"trial-{number}", "/ledger", "/authority", {}, "/release", "/custody")


def frozen_program(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, item: dict | None = None) -> tuple[Path, dict, dict]:
    monkeypatch.setattr(store, "trusted_utc_now", lambda: NOW)
    root = tmp_path / "m103-frozen"
    initialize_governance(root, acknowledgement=ACK_INITIALIZE)
    proposal_value = item or proposal()
    committed = commit_campaign_proposal(root, proposal_value)
    campaign = admit_campaign(root, proposal_hash=committed["proposal_hash"], acknowledgement=ACK_ADMIT_CAMPAIGN,
        validity_seconds=31_536_000)
    create_program(root, campaign_id=campaign["campaign_id"], protocol=protocol(proposal_value))
    return root, proposal_value, campaign


def admitted_program(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, source_proposal: dict | None = None) -> tuple[Path, dict]:
    root, item, campaign = frozen_program(tmp_path, monkeypatch, item=source_proposal)
    activate_program(root, campaign_id=campaign["campaign_id"], program_id="program-a",
        acknowledgement=ACK_ACTIVATE_PROGRAM)
    return root, item


def qualify(root: Path, item: dict, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setattr(store, "_resolve_statistical_adapter", lambda identifier, digest: TEST_ADAPTER)
    monkeypatch.setattr(store, "validate_candidate_observable_scope", lambda candidate, materialization: None)
    monkeypatch.setattr(store, "_verify_terminal_m102_source", lambda value: (
        verified(item["hypothesis_universe"][0]) if value.trial_id == "trial-1"
        else failed_verified(item["hypothesis_universe"][1])))
    record_development_result(root, program_id="program-a", hypothesis_id="hypothesis-1", result_source=source())
    record_development_result(root, program_id="program-a", hypothesis_id="hypothesis-2", result_source=source(2))
    return qualify_development(root, program_id="program-a")


def test_contract_lineage_includes_m99_and_m100() -> None:
    autonomy, mission = load_contracts()
    assert contract_hash(autonomy) == AUTONOMY_V5_HASH
    assert contract_hash(mission) == MISSION103_HASH
    assert mission["mission99_contract_hash_sha256"] == MISSION99_HASH
    assert mission["mission100_contract_hash_sha256"] == MISSION100_HASH
    assert mission["protected_partitions"]["present_observable_inputs_inside_materialization_hash"] is True
    assert mission["protected_opening"]["candidate_observable_scored_event_count_source"] == "AUTHORITATIVE_M102_LEDGER_EVENT_ROWS_LENGTH"
    assert mission["protected_opening"]["minimum_scored_samples_execution_coverage_resource_gate"] is True
    assert mission["protected_opening"]["unfilled_intent_count_supported_by_m103_v1_acceptance_language"] is False
    assert "unfilled_intent_count" not in mission["protected_opening"]["supported_protected_decimal_text_measurements"]


def test_production_registries_are_empty_and_semantic_hashes_are_derived() -> None:
    assert production_statistical_adapter_registry().entry_count == 0
    assert production_protected_evaluator_registry().entry_count == 0
    assert TEST_ADAPTER.adapter_hash == canonical_hash({"adapter_id": "test-adapter", "definition": ADAPTER_DEFINITION})
    with pytest.raises(TypeError):
        type(production_statistical_adapter_registry())([TEST_ADAPTER])


def test_proposal_needs_no_future_result_hash_and_rejects_one() -> None:
    item = proposal()
    assert validate_campaign_proposal(item)
    assert "result_hash" not in item["hypothesis_universe"][0]["m102"]
    assert "execution_spec_id" not in item["hypothesis_universe"][0]["m102"]
    assert "execution_spec_hash" not in item["hypothesis_universe"][0]["m102"]
    assert "result_link_hash" not in item["hypothesis_universe"][0]["m94"]
    malicious = deepcopy(item); malicious["hypothesis_universe"][0]["m102"]["result_hash"] = H("future")
    with pytest.raises(GovernanceError, match="GOVERNED_IDENTITY_BINDING_INVALID"):
        validate_campaign_proposal(malicious)


def test_family_id_hash_cross_swap_is_rejected() -> None:
    item = proposal(); item["family_universe"].append({"family_id": "family-b", "family_hash": H("family-b")})
    target = item["hypothesis_universe"][0]; target["family_hash"] = H("family-b")
    with pytest.raises(GovernanceError, match="HYPOTHESIS_FAMILY_BINDING_MISMATCH"):
        validate_campaign_proposal(item)


def test_seed_direct_canonical_json_known_vector() -> None:
    kwargs = {"founder_nonce_hex": "00" * 32, "proposal_hash": "11" * 32, "program_hash": "22" * 32,
        "hypothesis_hash": "33" * 32, "family_hash": "44" * 32, "variant_hash": "55" * 32,
        "adapter_hash": "66" * 32, "prng_algorithm_version": PRNG_ID}
    core = {key: value for key, value in kwargs.items() if key != "founder_nonce_hex"}
    expected = int.from_bytes(hashlib.sha256(NULL_SEED_DOMAIN + bytes(32) + canonical_bytes(core)).digest(), "big")
    assert derive_null_seed(**kwargs) == expected
    assert expected == 11827571926302566770158800989975386176841345131445988425050655460461951578007


def test_statistics_boundaries() -> None:
    assert minimum_repetitions(251, "0.05") == 5019
    assert empirical_p_value(favorable_count=0, repetitions=5000) == Fraction(1, 5001)
    result = holm_step_down({"a": "1/100", "b": "1/50", "c": "1/2"}, alpha="0.05")
    assert [row["rejected"] for row in result["ordered_evidence"]] == [True, True, False]


def test_real_m102_interface_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    assert set(inspect.signature(real_m102_verifier).parameters) == {"result_runtime", "trial_id", "ledger_path",
        "authority_root", "descriptor", "release_directory", "custody_runtime_root", "registry",
        "require_finalized", "repository_observer"}
    captured = {}
    compact = {"trial_id": "trial-1", "result_bundle_id": "bundle-1", "canonical_result_hash": H("result"),
        "verdict": "VERIFIED", "verifier": "DELTAGRID_M102_INDEPENDENT_RESULT_VERIFIER_V1",
        "metrics": {"score": "good"}, "verification_mode": "FULL_REPLAY_FINALIZED"}
    def fake_verify(**kwargs): captured.update(kwargs); return compact
    spec = {"authority_binding": {"request_hash": H("request"), "budget_id": "budget-a", "declared_trial_number": 1,
        "fixed_trial_budget": 2, "permit_id": "permit-a",
        "permit_hash": H("permit"), "dataset_id": "dataset-a", "dataset_descriptor_hash": H("descriptor"),
        "release_id": "release-a", "release_core_hash": H("release-core"), "release_certificate_hash": H("release-cert"),
        "repository_commit": COMMIT, "authority_decision_time": NOW}, "variant_definition": {"fee_model": {"bps": "1"}, "slippage_model": {"bps": "2"},
            "strategy_parameters": {"window": "1"}, "initial_research_nav": "1000", "max_gross_research_exposure": "1000",
            "max_net_research_exposure": "1000", "per_instrument_bounds": {"spot_ohlcv:BTCUSDT": "1000"}},
        "fill_model": "fill-v1", "target_exposure_model": "target-v1", "position_effective_time_model": "position-v1",
        "variant_definition_hash": H("variant"), "family_definition_hash": H("family"), "family_id": "family-a",
        "variant_id": "variant-1", "registry_snapshot_hash": H("registry"), "execution_spec_id": "spec-1",
        "canonical_execution_spec_hash": H("spec")}
    result = {"canonical_result_hash": H("result"), "result_bundle_id": "bundle-1"}
    monkeypatch.setattr(integrations, "verify_development_result", fake_verify)
    monkeypatch.setattr(integrations, "validate_result_runtime", lambda value: Path("/runtime"))
    monkeypatch.setattr(integrations, "trial_directory", lambda *args, **kwargs: Path("/runtime/trial-1"))
    monkeypatch.setattr(integrations, "read_canonical", lambda path, **kwargs: (spec if path.name == "execution-spec.json" else result, b""))
    monkeypatch.setattr(integrations, "read_trial_binding", lambda *args, **kwargs: {"result_link": {
        "result_bundle_hash": H("result"), "canonical_result_link_hash": H("link"), "linked_at": NOW},
        "completion_event": {"event_timestamp": NOW},
        "budget": {"canonical_budget_hash": H("budget")}})
    evidence = integrations._verify_finalized_m102_source(source())
    assert captured["require_finalized"] is True
    assert type(captured["registry"]).__name__ == "ExperimentRegistry"
    assert evidence["result_hash"] == H("result") and evidence["result_link_hash"] == H("link")


def test_caller_cannot_submit_verified_mapping() -> None:
    assert "verified_result" not in inspect.signature(record_development_result).parameters
    assert "statistical_registry" not in inspect.signature(record_development_result).parameters


def test_m103_computes_empirical_p_and_candidate_binds_final_hashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, item = admitted_program(tmp_path, monkeypatch)
    result = qualify(root, item, monkeypatch)
    assert result["status"] == "REPLICATION_ELIGIBLE"
    with store.connection(root, readonly=True) as conn:
        evidence = json.loads(conn.execute("SELECT evidence_json FROM development_results WHERE hypothesis_id='hypothesis-1'").fetchone()[0])
        candidate = json.loads(conn.execute("SELECT candidate_json FROM candidates").fetchone()[0])
    assert evidence["raw_p_value"] == "1/5001"
    assert candidate["m102"]["result_hash"] == H("result-hypothesis-1")
    assert candidate["m94"]["result_link_hash"] == H("link-hypothesis-1")


def test_adapter_fake_p_value_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, item = admitted_program(tmp_path, monkeypatch)
    malicious = StatisticalAdapter("test-adapter", ADAPTER_DEFINITION,
        lambda value: {**adapter_function(value), "raw_p_value": "0"})
    monkeypatch.setattr(store, "_resolve_statistical_adapter", lambda *args: malicious)
    monkeypatch.setattr(store, "_verify_terminal_m102_source", lambda value: verified(item["hypothesis_universe"][0]))
    with pytest.raises(GovernanceError, match="STATISTICAL_ADAPTER_OUTPUT_INVALID"):
        record_development_result(root, program_id="program-a", hypothesis_id="hypothesis-1", result_source=source())


def test_adapter_cannot_change_seed_or_repetition_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, item = admitted_program(tmp_path, monkeypatch)
    def bad(value):
        output = adapter_function(value); output["null_evidence"]["results"][0]["draw_u256_hex"] = "f" * 64; return output
    monkeypatch.setattr(store, "_resolve_statistical_adapter", lambda *args: StatisticalAdapter("test-adapter", ADAPTER_DEFINITION, bad))
    monkeypatch.setattr(store, "_verify_terminal_m102_source", lambda value: verified(item["hypothesis_universe"][0]))
    with pytest.raises(GovernanceError, match="RANDOMIZATION_PLAN_TRANSCRIPT_MISMATCH"):
        record_development_result(root, program_id="program-a", hypothesis_id="hypothesis-1", result_source=source())


def test_exact_enumeration_authoritative_reference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    item = proposal(1); monkeypatch.setattr(store, "trusted_utc_now", lambda: NOW)
    root = tmp_path / "exact"; initialize_governance(root, acknowledgement=ACK_INITIALIZE)
    commitment = commit_campaign_proposal(root, item); campaign = admit_campaign(root, proposal_hash=commitment["proposal_hash"], acknowledgement=ACK_ADMIT_CAMPAIGN)
    create_program(root, campaign_id=campaign["campaign_id"], protocol=protocol(item, exact=True))
    activate_program(root, campaign_id=campaign["campaign_id"], program_id="program-a", acknowledgement=ACK_ACTIVATE_PROGRAM)
    configurations = [{"configuration_id": f"config-{index}", "signs": [index % 2]} for index in range(16)]
    exact_definition = {"version": "v1", "input_schema": "m103-stat-input-v1", "output_schema": "m103-null-evidence-v1",
        "measurement_algorithm": "test-measurements-v1", "deterministic": True,
        "null_algorithm": {"kind": "PREREGISTERED_EXACT_ENUMERATION_V1", "algorithm_id": "COMPLETE_SIGN_FLIP",
            "configurations": configurations, "observed_configuration_id": "config-0"}}
    def exact_adapter(value):
        results = [{"configuration_id": item["configuration_id"], "statistic": "2" if index < 3 else "1"}
            for index, item in enumerate(value["enumeration_space"]["configurations"])]
        null = {"kind": "EXACT_ENUMERATION_RESULTS_V1",
            "enumeration_commitment": value["enumeration_space"]["enumeration_commitment"],
            "observed_statistic": "2", "results": results}
        measurements = {"score_stat": "2", "sample_count": "20", "drawdown": "0.05", "rank_score": "2"}
        return {"null_evidence": {**null, "evidence_commitment": canonical_hash(null)},
            "measurements": measurements, "measurement_evidence_hash": canonical_hash(measurements)}
    monkeypatch.setattr(store, "_resolve_statistical_adapter", lambda *args: StatisticalAdapter("test-adapter", exact_definition, exact_adapter))
    monkeypatch.setattr(store, "_verify_terminal_m102_source", lambda value: verified(item["hypothesis_universe"][0]))
    record_development_result(root, program_id="program-a", hypothesis_id="hypothesis-1", result_source=source())
    with store.connection(root, readonly=True) as conn:
        evidence = json.loads(conn.execute("SELECT evidence_json FROM development_results").fetchone()[0])
    assert evidence["raw_p_value"] == "3/16"


def test_numeric_ranking_uses_two_before_ten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, item = admitted_program(tmp_path, monkeypatch)
    monkeypatch.setattr(store, "_resolve_statistical_adapter", lambda *args: TEST_ADAPTER)
    for index, score in ((0, "good"), (1, "ordinary")):
        monkeypatch.setattr(store, "_verify_terminal_m102_source", lambda value, i=index, s=score: verified(item["hypothesis_universe"][i], s))
        record_development_result(root, program_id="program-a", hypothesis_id=f"hypothesis-{index+1}", result_source=source(index + 1))
    result = qualify_development(root, program_id="program-a")
    with store.connection(root, readonly=True) as conn: candidate = json.loads(conn.execute("SELECT candidate_json FROM candidates").fetchone()[0])
    assert result["status"] == "REPLICATION_ELIGIBLE" and candidate["hypothesis_id"] == "hypothesis-1"


def test_partition_boundaries_are_exact_future_utc_and_ordered() -> None:
    assert validate_partition_spec(_spec("REPLICATION", 0))["time_unit"] == "MILLISECONDS"
    item = _spec("REPLICATION", 0); item["scoring_start"] = item["context_start"]
    with pytest.raises(GovernanceError, match="PARTITION_BOUND_INVALID"): validate_partition_spec(item)


@pytest.mark.parametrize("usage", ["statistic", "gate"])
def test_unfilled_intent_count_is_rejected_when_program_is_frozen(
    usage: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(store, "trusted_utc_now", lambda: NOW)
    root = tmp_path / f"unsupported-{usage}"; initialize_governance(root, acknowledgement=ACK_INITIALIZE)
    item = proposal(); commitment = commit_campaign_proposal(root, item)
    campaign = admit_campaign(root, proposal_hash=commitment["proposal_hash"], acknowledgement=ACK_ADMIT_CAMPAIGN)
    invalid = protocol(item)
    if usage == "statistic":
        invalid["protected_acceptance_rules"]["REPLICATION"]["statistic"] = "unfilled_intent_count"
    else:
        invalid["protected_acceptance_rules"]["REPLICATION"]["measurement_gates"] = [
            {"measurement_id": "unfilled_intent_count", "operator": "EQ", "threshold": "0"},
        ]
    with pytest.raises(GovernanceError, match="PROTECTED_MEASUREMENT_UNSUPPORTED"):
        create_program(root, campaign_id=campaign["campaign_id"], protocol=invalid)


def test_supported_decimal_text_protected_metrics_still_freeze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _item, _campaign = frozen_program(tmp_path, monkeypatch)
    with store.connection(root, readonly=True) as conn:
        saved = json.loads(conn.execute("SELECT protocol_json FROM programs").fetchone()[0])
    assert saved["protected_acceptance_rules"]["REPLICATION"]["statistic"] == "net_pnl"
    assert saved["protected_acceptance_rules"]["REPLICATION"]["measurement_gates"][0]["measurement_id"] == "max_drawdown"


def _fake_materialization(stage: str, spec: dict, *, duplicate: str | None = None) -> dict:
    context = [H(f"context-{stage}")]; scored = [duplicate or H(f"scored-{stage}-1"), H(f"scored-{stage}-2")]
    core = {"stage": stage, "specification_hash": spec["specification_hash"], "release_id": f"release-{stage.lower()}",
        "release_core_hash": H(f"release-{stage}"), "certificate_hash": H(f"certificate-{stage}"), "descriptor": {},
        "exact_observable_inputs": sorted(spec["stream_symbols"]),
        "present_observable_inputs": sorted(spec["stream_symbols"]),
        "completeness_proof_hash": H(f"complete-{stage}"),
        "context_record_hashes": context, "context_record_set_hash": canonical_hash(context),
        "scored_record_hashes": scored, "scored_record_set_hash": canonical_hash(scored),
        "ordered_context_record_hashes": context, "ordered_context_hash": canonical_hash(context),
        "ordered_scored_record_hashes": scored, "ordered_scored_hash": canonical_hash(scored),
        "context_count": len(context), "scored_count": len(scored), "release_directory": "/release", "custody_runtime_root": "/custody"}
    return {**core, "materialization_hash": canonical_hash(core)}


def test_materialization_has_no_caller_metadata_and_enforces_exact_sets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert "metadata" not in inspect.signature(register_materialization).parameters
    root, item = admitted_program(tmp_path, monkeypatch); qualify(root, item, monkeypatch)
    monkeypatch.setattr(store, "trusted_utc_now", lambda: "2040-01-01T00:00:00.000000Z")
    captured = {}
    def fake(source_value, spec, policy): captured.update(spec); return _fake_materialization(spec["stage"], spec)
    monkeypatch.setattr(store, "_materialize_verified_custody", fake)
    result = register_materialization(root, program_id="program-a", stage="REPLICATION", source=ProtectedCustodySource("/release", "/custody"))
    assert captured["data_certification_policy"] == "M99_M100_M101_VERIFIED"
    assert result["context_record_set_hash"] != result["scored_record_set_hash"]


def test_pairwise_duplicate_scored_hash_rejected_even_with_different_times(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, item = admitted_program(tmp_path, monkeypatch); qualify(root, item, monkeypatch)
    monkeypatch.setattr(store, "trusted_utc_now", lambda: "2040-01-01T00:00:00.000000Z")
    shared = H("shared-scored")
    monkeypatch.setattr(store, "_materialize_verified_custody", lambda source, spec, policy: _fake_materialization(spec["stage"], spec, duplicate=shared))
    register_materialization(root, program_id="program-a", stage="REPLICATION", source=ProtectedCustodySource("/r", "/c"))
    with pytest.raises(GovernanceError, match="PROTECTED_PARTITIONS_NOT_DISJOINT"):
        register_materialization(root, program_id="program-a", stage="VALIDATION", source=ProtectedCustodySource("/r", "/c"))


def test_open_has_no_payload_loader_and_m103_decides_evaluator_measurements(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert "payload_loader" not in inspect.signature(open_protected_stage).parameters
    assert "evaluator_registry" not in inspect.signature(open_protected_stage).parameters
    root, item = admitted_program(tmp_path, monkeypatch); qualify(root, item, monkeypatch)
    monkeypatch.setattr(store, "trusted_utc_now", lambda: "2040-01-01T00:00:00.000000Z")
    monkeypatch.setattr(store, "_materialize_verified_custody", lambda source, spec, policy: _fake_materialization(spec["stage"], spec))
    register_materialization(root, program_id="program-a", stage="REPLICATION", source=ProtectedCustodySource("/r", "/c"))
    monkeypatch.setattr(store, "_resolve_protected_evaluator", lambda *args: TEST_EVALUATOR)
    monkeypatch.setattr(store, "_verify_repository_context", lambda expected: None)
    authorization = authorize_stage(root, program_id="program-a", stage="REPLICATION", acknowledgement=ACK_AUTHORIZE_STAGE)
    monkeypatch.setattr(store, "_load_protected_input", lambda materialization, execution: {"exact": True})
    monkeypatch.setattr(store, "execute_protected_candidate", lambda candidate, protected_input: {
        "ledger": {"canonical_event_ledger_hash": H("ledger"), "event_rows": [{}, {}]},
        "metrics": {"net_pnl": "1", "max_drawdown": "0.05"},
        "execution_evidence": {"candidate_observable_scored_event_count": 2},
        "execution_evidence_hash": H("protected-execution")})
    result = open_protected_stage(root, authorization_id=authorization["authorization_id"])
    assert result["status"] == "VALIDATION_ELIGIBLE"


def test_crash_recovery_uses_same_internal_input_and_exact_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, item = admitted_program(tmp_path, monkeypatch); qualify(root, item, monkeypatch)
    monkeypatch.setattr(store, "trusted_utc_now", lambda: "2040-01-01T00:00:00.000000Z")
    monkeypatch.setattr(store, "_materialize_verified_custody", lambda source, spec, policy: _fake_materialization(spec["stage"], spec))
    register_materialization(root, program_id="program-a", stage="REPLICATION", source=ProtectedCustodySource("/r", "/c"))
    monkeypatch.setattr(store, "_resolve_protected_evaluator", lambda *args: TEST_EVALUATOR)
    monkeypatch.setattr(store, "_verify_repository_context", lambda expected: None)
    auth = authorize_stage(root, program_id="program-a", stage="REPLICATION", acknowledgement=ACK_AUTHORIZE_STAGE)
    with pytest.raises(GovernanceError, match="INJECTED_CRASH_AFTER_OPENED_COMMIT"):
        open_protected_stage(root, authorization_id=auth["authorization_id"], crash_point="AFTER_OPENED_COMMIT")
    with store.connection(root, readonly=True) as conn:
        execution = json.loads(conn.execute("SELECT execution_json FROM stage_executions").fetchone()[0])
    with pytest.raises(GovernanceError, match="EXACT_STAGE_RECOVERY_IDENTITY_REQUIRED"):
        recover_protected_stage(root, stage_execution_id=execution["stage_execution_id"], expected_execution_hash=H("changed"))
    monkeypatch.setattr(store, "_load_protected_input", lambda materialization, exact: {"same": True})
    monkeypatch.setattr(store, "execute_protected_candidate", lambda candidate, protected_input: {
        "ledger": {"canonical_event_ledger_hash": H("ledger"), "event_rows": [{}, {}]},
        "metrics": {"net_pnl": "1", "max_drawdown": "0.05"},
        "execution_evidence": {"candidate_observable_scored_event_count": 2},
        "execution_evidence_hash": H("protected-execution")})
    result = recover_protected_stage(root, stage_execution_id=execution["stage_execution_id"], expected_execution_hash=execution["execution_hash"])
    assert result["recovered"] is True and result["status"] == "VALIDATION_ELIGIBLE"


def test_candidate_presence_is_checked_at_authorization_and_before_open_consumption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, item = admitted_program(tmp_path, monkeypatch); qualify(root, item, monkeypatch)
    monkeypatch.setattr(store, "trusted_utc_now", lambda: "2040-01-01T00:00:00.000000Z")
    monkeypatch.setattr(store, "_materialize_verified_custody", lambda source, spec, policy: _fake_materialization(spec["stage"], spec))
    register_materialization(root, program_id="program-a", stage="REPLICATION", source=ProtectedCustodySource("/r", "/c"))
    monkeypatch.setattr(store, "_resolve_protected_evaluator", lambda *args: TEST_EVALUATOR)
    monkeypatch.setattr(store, "_verify_repository_context", lambda expected: None)
    checks = []
    monkeypatch.setattr(store, "validate_candidate_observable_scope", lambda candidate, materialization: checks.append(
        tuple(materialization["present_observable_inputs"])))
    authorization = authorize_stage(root, program_id="program-a", stage="REPLICATION", acknowledgement=ACK_AUTHORIZE_STAGE)
    assert checks == [("spot_ohlcv:BTCUSDT",)]
    payload_calls = []
    def reject_open(candidate, materialization):
        checks.append(tuple(materialization["present_observable_inputs"]))
        raise GovernanceError("PROTECTED_CANDIDATE_OBSERVABLE_SCOPE_INCOMPLETE")
    monkeypatch.setattr(store, "validate_candidate_observable_scope", reject_open)
    monkeypatch.setattr(store, "_load_protected_input", lambda *args: payload_calls.append(True))
    with pytest.raises(GovernanceError, match="PROTECTED_CANDIDATE_OBSERVABLE_SCOPE_INCOMPLETE"):
        open_protected_stage(root, authorization_id=authorization["authorization_id"])
    assert checks == [("spot_ohlcv:BTCUSDT",), ("spot_ohlcv:BTCUSDT",)] and payload_calls == []
    with store.connection(root, readonly=True) as conn:
        assert conn.execute("SELECT COUNT(*) FROM authorization_consumptions").fetchone()[0] == 0


def test_authoritative_candidate_event_rows_control_protected_sample_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(store, "trusted_utc_now", lambda: NOW)
    root = tmp_path / "sample-gate"; initialize_governance(root, acknowledgement=ACK_INITIALIZE)
    item = proposal(); commitment = commit_campaign_proposal(root, item)
    campaign = admit_campaign(root, proposal_hash=commitment["proposal_hash"], acknowledgement=ACK_ADMIT_CAMPAIGN)
    program_value = protocol(item)
    program_value["protected_acceptance_rules"]["REPLICATION"]["minimum_scored_samples"] = 50
    create_program(root, campaign_id=campaign["campaign_id"], protocol=program_value)
    activate_program(root, campaign_id=campaign["campaign_id"], program_id="program-a", acknowledgement=ACK_ACTIVATE_PROGRAM)
    qualify(root, item, monkeypatch)
    monkeypatch.setattr(store, "trusted_utc_now", lambda: "2040-01-01T00:00:00.000000Z")
    def sixty_record_materialization(source, spec, policy):
        value = _fake_materialization(spec["stage"], spec)
        core = dict(value); core.pop("materialization_hash")
        scored = [H(f"candidate-superset-{index}") for index in range(60)]
        core.update({"scored_record_hashes": scored, "scored_record_set_hash": canonical_hash(scored),
            "ordered_scored_record_hashes": scored, "ordered_scored_hash": canonical_hash(scored),
            "scored_count": len(scored)})
        return {**core, "materialization_hash": canonical_hash(core)}
    monkeypatch.setattr(store, "_materialize_verified_custody", sixty_record_materialization)
    register_materialization(root, program_id="program-a", stage="REPLICATION", source=ProtectedCustodySource("/r", "/c"))
    monkeypatch.setattr(store, "_resolve_protected_evaluator", lambda *args: TEST_EVALUATOR)
    monkeypatch.setattr(store, "_verify_repository_context", lambda expected: None)
    authorization = authorize_stage(root, program_id="program-a", stage="REPLICATION", acknowledgement=ACK_AUTHORIZE_STAGE)
    monkeypatch.setattr(store, "_load_protected_input", lambda *args: {"exact": True})
    event_rows = [{"event": index} for index in range(20)]
    monkeypatch.setattr(store, "execute_protected_candidate", lambda *args: {
        "ledger": {"canonical_event_ledger_hash": H("candidate-20-ledger"), "event_rows": event_rows},
        "metrics": {"net_pnl": "1", "max_drawdown": "0.05"},
        "execution_evidence": {"candidate_observable_context_event_count": 3,
            "candidate_observable_scored_event_count": len(event_rows)},
        "execution_evidence_hash": H("candidate-20-execution"),
    })
    result = open_protected_stage(root, authorization_id=authorization["authorization_id"])
    assert result["status"] == "PROGRAM_REJECTED"
    with store.connection(root, readonly=True) as conn:
        decision = json.loads(conn.execute("SELECT decision_json FROM stage_decisions").fetchone()[0])
    assert decision["candidate_observable_scored_event_count"] == 20
    assert decision["sample_passed"] is False
    assert "scored_sample_count" not in decision


def test_sufficient_authoritative_candidate_event_rows_pass_sample_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, item = admitted_program(tmp_path, monkeypatch); qualify(root, item, monkeypatch)
    monkeypatch.setattr(store, "trusted_utc_now", lambda: "2040-01-01T00:00:00.000000Z")
    monkeypatch.setattr(store, "_materialize_verified_custody", lambda source, spec, policy: _fake_materialization(spec["stage"], spec))
    register_materialization(root, program_id="program-a", stage="REPLICATION", source=ProtectedCustodySource("/r", "/c"))
    monkeypatch.setattr(store, "_resolve_protected_evaluator", lambda *args: TEST_EVALUATOR)
    monkeypatch.setattr(store, "_verify_repository_context", lambda expected: None)
    authorization = authorize_stage(root, program_id="program-a", stage="REPLICATION", acknowledgement=ACK_AUTHORIZE_STAGE)
    monkeypatch.setattr(store, "_load_protected_input", lambda *args: {"exact": True})
    event_rows = [{"event": 1}, {"event": 2}]
    monkeypatch.setattr(store, "execute_protected_candidate", lambda *args: {
        "ledger": {"canonical_event_ledger_hash": H("candidate-2-ledger"), "event_rows": event_rows},
        "metrics": {"net_pnl": "1", "max_drawdown": "0.05"},
        "execution_evidence": {"candidate_observable_context_event_count": 1,
            "candidate_observable_scored_event_count": len(event_rows)},
        "execution_evidence_hash": H("candidate-2-execution"),
    })
    result = open_protected_stage(root, authorization_id=authorization["authorization_id"])
    assert result["status"] == "VALIDATION_ELIGIBLE"
    with store.connection(root, readonly=True) as conn:
        decision = json.loads(conn.execute("SELECT decision_json FROM stage_decisions").fetchone()[0])
    assert decision["candidate_observable_scored_event_count"] == len(event_rows)
    assert decision["sample_passed"] is True


def test_trusted_commit_time_is_not_public() -> None:
    assert "committed_at" not in inspect.signature(commit_campaign_proposal).parameters


def test_v1_rejects_multiple_program_capacity_and_second_program(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    invalid = proposal(); invalid["maximum_program_count"] = 2
    with pytest.raises(GovernanceError, match="PROGRAM_COUNT_INVALID"):
        validate_campaign_proposal(invalid)
    root, item = admitted_program(tmp_path, monkeypatch)
    second = protocol(item); second["program_id"] = "program-b"
    with store.connection(root, readonly=True) as conn:
        campaign_id = conn.execute("SELECT campaign_id FROM campaigns").fetchone()[0]
    with pytest.raises(GovernanceError, match="CAMPAIGN_PROGRAM_ALREADY_FROZEN"):
        create_program(root, campaign_id=campaign_id, protocol=second)


def test_no_second_program_after_partial_result_or_new_seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, item = admitted_program(tmp_path, monkeypatch)
    original_seed = store.derive_program_null_seed(root, program_id="program-a", hypothesis_id="hypothesis-1")
    monkeypatch.setattr(store, "_verify_terminal_m102_source", lambda value: failed_verified(item["hypothesis_universe"][0]))
    record_development_result(root, program_id="program-a", hypothesis_id="hypothesis-1", result_source=source())
    with store.connection(root, readonly=True) as conn:
        campaign_id = conn.execute("SELECT campaign_id FROM campaigns").fetchone()[0]
    second = protocol(item); second["program_id"] = "program-b"
    with pytest.raises(GovernanceError, match="CAMPAIGN_PROGRAM_ALREADY_FROZEN"):
        create_program(root, campaign_id=campaign_id, protocol=second)
    assert store.derive_program_null_seed(root, program_id="program-a", hypothesis_id="hypothesis-1") == original_seed


def test_primary_statistic_must_equal_null_observed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, item = admitted_program(tmp_path, monkeypatch)
    def malicious(value):
        output = adapter_function(value); output["null_evidence"]["observed_statistic"] = "999"
        core = dict(output["null_evidence"]); core.pop("evidence_commitment")
        output["null_evidence"]["evidence_commitment"] = canonical_hash(core); return output
    monkeypatch.setattr(store, "_resolve_statistical_adapter", lambda *args: StatisticalAdapter("test-adapter", ADAPTER_DEFINITION, malicious))
    monkeypatch.setattr(store, "_verify_terminal_m102_source", lambda value: verified(item["hypothesis_universe"][0]))
    with pytest.raises(GovernanceError, match="PRIMARY_STATISTIC_BINDING_MISMATCH"):
        record_development_result(root, program_id="program-a", hypothesis_id="hypothesis-1", result_source=source())


def test_null_algorithm_label_must_match_adapter_semantics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, item = admitted_program(tmp_path, monkeypatch)
    definition = deepcopy(ADAPTER_DEFINITION); definition["null_algorithm"]["algorithm_id"] = "DIFFERENT_ALGORITHM"
    monkeypatch.setattr(store, "_resolve_statistical_adapter", lambda *args: StatisticalAdapter("test-adapter", definition, adapter_function))
    monkeypatch.setattr(store, "_verify_terminal_m102_source", lambda value: verified(item["hypothesis_universe"][0]))
    with pytest.raises(GovernanceError, match="NULL_ALGORITHM_BINDING_MISMATCH"):
        record_development_result(root, program_id="program-a", hypothesis_id="hypothesis-1", result_source=source())


def test_m103_randomization_plan_is_stable_and_ordinally_bound() -> None:
    first = build_randomization_plan(123, 5000); second = build_randomization_plan(123, 5000)
    assert first == second
    assert first["entries"][0]["ordinal"] == 0 and first["entries"][-1]["ordinal"] == 4999
    assert first["plan_commitment"] == canonical_hash({"definition": first["definition"], "entries": first["entries"]})


def test_candidate_binds_complete_compact_development_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, item = admitted_program(tmp_path, monkeypatch); qualify(root, item, monkeypatch)
    with store.connection(root, readonly=True) as conn:
        candidate = json.loads(conn.execute("SELECT candidate_json FROM candidates").fetchone()[0])
        row = conn.execute("SELECT evidence_hash,evidence_json FROM development_results WHERE hypothesis_id='hypothesis-1'").fetchone()
    evidence = json.loads(row["evidence_json"])
    assert candidate["development_result_evidence_hash"] == row["evidence_hash"]
    assert candidate["verified_result_hash"] == evidence["verified_result_hash"]
    assert candidate["measurement_evidence_hash"] == evidence["measurement_evidence_hash"]
    assert candidate["null_evidence_commitment"] == evidence["null_evidence_commitment"]
    assert candidate["randomization_plan_commitment"] == evidence["randomization_plan_commitment"]
    assert "null_evidence" not in candidate


def _market_event(name: str, custody_hash: str, time_ms: int, price: str) -> MarketEvent:
    payload = {"close": price, "close_time_ms": time_ms}
    return MarketEvent(f"event-{name}", custody_hash, H(f"source-{name}"), "spot_ohlcv", "BTCUSDT", "1h",
        time_ms, datetime.fromtimestamp(time_ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        1, canonical_hash(payload), payload)


class _VariantStrategy:
    def __init__(self, parameters): self.side = parameters["side"]
    def on_event(self, event, state):
        if self.side == "long" and state["positions"]["spot_ohlcv:BTCUSDT"] == "0" and not state["pending_instruments"]:
            return [TargetExposureIntent("BTCUSDT", "spot_ohlcv", "100")]
        return []


def _variant(identifier: str, side: str) -> VariantDefinition:
    return VariantDefinition(identifier, ("spot_ohlcv",), ("BTCUSDT",), ("spot_ohlcv:BTCUSDT",),
        ("spot_ohlcv:BTCUSDT",), (), "1000", "1000", "1000", {"spot_ohlcv:BTCUSDT": "1000"},
        "0", "0", False, {"side": side})


def _protected_candidate(registry: ExperimentRegistry, family: FamilyDefinition, variant: VariantDefinition, trial_number: int) -> dict:
    execution = {"fee_bps": variant.fee_bps, "slippage_bps": variant.slippage_bps,
        "fill_model": "NEXT_ELIGIBLE_BAR_CLOSE_V1", "target_exposure_model": "TARGET_NOTIONAL_AT_BENCHMARK_CLOSE_V1",
        "position_effective_time_model": "MAX_BENCHMARK_CLOSE_AND_FILL_EVIDENCE_AVAILABLE_V1",
        "variant_definition_hash": variant.definition_hash}
    return {"candidate_hash": H(f"candidate-{variant.variant_id}"), "family_id": family.family_id,
        "family_hash": family.definition_hash, "variant_id": variant.variant_id, "variant_hash": variant.definition_hash,
        "parameters": variant.core()["strategy_parameters"], "execution_hash": canonical_hash(execution),
        "repository_commit": COMMIT, "m94": {"declared_trial_number": trial_number, "fixed_trial_budget": 2},
        "risk_identity": canonical_hash({"initial_research_nav": variant.initial_research_nav,
            "max_gross_research_exposure": variant.max_gross_research_exposure,
            "max_net_research_exposure": variant.max_net_research_exposure,
            "per_instrument_bounds": dict(sorted(variant.per_instrument_bounds.items()))}),
        "m102": {"registry_snapshot_hash": registry.snapshot_hash}}


def test_protected_executor_runs_exact_variant_flat_and_context_not_scored(monkeypatch: pytest.MonkeyPatch) -> None:
    variant_a, variant_b = _variant("variant-a", "long"), _variant("variant-b", "flat")
    family = FamilyDefinition("family-a", (variant_a, variant_b), lambda parameters: _VariantStrategy(parameters))
    registry = ExperimentRegistry((family,)); monkeypatch.setattr(protected, "production_registry", lambda: registry)
    candidate_a = _protected_candidate(registry, family, variant_a, 1)
    candidate_b = _protected_candidate(registry, family, variant_b, 2)
    protected_input = {"context_events": (_market_event("context", "f" * 64, 1000, "100"),),
        "scored_events": (_market_event("s1", "e" * 64, 2000, "10"), _market_event("s2", "d" * 64, 3000, "20"),
            _market_event("s3", "c" * 64, 4000, "30"))}
    result_a = protected.execute_protected_candidate(candidate_a, protected_input)
    result_b = protected.execute_protected_candidate(candidate_b, protected_input)
    assert result_a["metrics"]["net_pnl"] != result_b["metrics"]["net_pnl"]
    assert result_a["metrics"]["initial_research_nav"] == "1000"
    assert all(row["fill_event_id"] != "event-context" for row in result_a["ledger"]["fill_rows"])
    substituted = {**candidate_a, "variant_id": variant_b.variant_id, "variant_hash": variant_b.definition_hash}
    with pytest.raises(GovernanceError, match="PROTECTED_CANDIDATE_RECONSTRUCTION_MISMATCH"):
        protected.execute_protected_candidate(substituted, protected_input)


def test_protected_loader_preserves_m102_causal_order_not_hash_order(monkeypatch: pytest.MonkeyPatch) -> None:
    early = _market_event("early", "f" * 64, 1000, "10"); late = _market_event("late", "0" * 64, 2000, "20")
    monkeypatch.setattr(integrations, "load_causal_events_by_custody_hashes", lambda *args, **kwargs: (early, late))
    core = {"descriptor": {}, "release_directory": "/r",
        "custody_runtime_root": "/c", "exact_observable_inputs": ["spot_ohlcv:BTCUSDT"],
        "present_observable_inputs": ["spot_ohlcv:BTCUSDT"],
        "release_id": "release", "release_core_hash": H("release"), "certificate_hash": H("certificate"),
        "ordered_context_record_hashes": [early.custody_record_hash], "ordered_scored_record_hashes": [late.custody_record_hash]}
    materialization = {**core, "materialization_hash": canonical_hash(core)}
    execution = {"materialization_hash": materialization["materialization_hash"], "stage": "REPLICATION", "candidate_hash": H("candidate"),
        "repository_commit": COMMIT, "program_hash": H("program"), "candidate_execution_hash": COST_EXECUTION_HASH,
        "deterministic_randomness": "NONE_UNLESS_PROTOCOL_BOUND"}
    loaded = integrations._load_protected_input(materialization, execution)
    assert [event.event_id for event in loaded["context_events"] + loaded["scored_events"]] == ["event-early", "event-late"]


def test_protected_engine_is_prefrozen_and_authorization_cannot_substitute() -> None:
    assert "evaluator_id" not in inspect.signature(authorize_stage).parameters
    assert "evaluator_hash" not in inspect.signature(authorize_stage).parameters


def test_protected_acceptance_gate_ids_unique() -> None:
    source_value = proposal(); value = protocol(source_value)
    duplicate = value["protected_acceptance_rules"]["REPLICATION"]["measurement_gates"][0]
    value["protected_acceptance_rules"]["REPLICATION"]["measurement_gates"].append(deepcopy(duplicate))
    from offchain.research.statistical_governance.protocol import _validate_program_protocol_at
    with pytest.raises(GovernanceError, match="MEASUREMENT_GATE_SET_MISMATCH"):
        _validate_program_protocol_at(value, proposal=source_value, decision_time=NOW)


def test_exact_enumeration_space_substitution_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    item = proposal(1); monkeypatch.setattr(store, "trusted_utc_now", lambda: NOW)
    root = tmp_path / "exact-substitution"; initialize_governance(root, acknowledgement=ACK_INITIALIZE)
    commitment = commit_campaign_proposal(root, item)
    campaign = admit_campaign(root, proposal_hash=commitment["proposal_hash"], acknowledgement=ACK_ADMIT_CAMPAIGN)
    create_program(root, campaign_id=campaign["campaign_id"], protocol=protocol(item, exact=True))
    activate_program(root, campaign_id=campaign["campaign_id"], program_id="program-a", acknowledgement=ACK_ACTIVATE_PROGRAM)
    configurations = [{"configuration_id": "observed"}, {"configuration_id": "other"}]
    definition = {"version": "v1", "input_schema": "m103-stat-input-v1", "output_schema": "m103-null-evidence-v1",
        "measurement_algorithm": "test-measurements-v1", "deterministic": True,
        "null_algorithm": {"kind": "PREREGISTERED_EXACT_ENUMERATION_V1", "algorithm_id": "COMPLETE_SIGN_FLIP",
            "configurations": configurations, "observed_configuration_id": "observed"}}
    def substitute(value):
        null = {"kind": "EXACT_ENUMERATION_RESULTS_V1", "enumeration_commitment": value["enumeration_space"]["enumeration_commitment"],
            "observed_statistic": "2", "results": [{"configuration_id": "other", "statistic": "1"},
                {"configuration_id": "observed", "statistic": "2"}]}
        measurements = {"score_stat": "2", "sample_count": "20", "drawdown": "0.05", "rank_score": "2"}
        return {"null_evidence": {**null, "evidence_commitment": canonical_hash(null)}, "measurements": measurements,
            "measurement_evidence_hash": canonical_hash(measurements)}
    monkeypatch.setattr(store, "_resolve_statistical_adapter", lambda *args: StatisticalAdapter("test-adapter", definition, substitute))
    monkeypatch.setattr(store, "_verify_terminal_m102_source", lambda value: verified(item["hypothesis_universe"][0]))
    with pytest.raises(GovernanceError, match="EXACT_ENUMERATION_SPACE_SUBSTITUTION"):
        record_development_result(root, program_id="program-a", hypothesis_id="hypothesis-1", result_source=source())


def test_exact_pair_scope_purge_gap_horizon_and_snapshot_determinism(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custody = tmp_path / "custody"; custody.mkdir(); release_a = tmp_path / "release-a"; release_a.mkdir(); release_b = tmp_path / "release-b"; release_b.mkdir()
    spec = validate_partition_spec({**_spec("REPLICATION", 0),
        "stream_symbols": ["spot_ohlcv:BTCUSDT", "perpetual_ohlcv:ETHUSDT"],
        "stream_intervals": {"spot_ohlcv": "1h", "perpetual_ohlcv": "1h"}})
    base = spec["context_start"]
    definitions = [
        ("spot_ohlcv", "BTCUSDT", base + 1_000_000),
        ("perpetual_ohlcv", "ETHUSDT", base + 2_000_000),
        ("spot_ohlcv", "ETHUSDT", base + 3_000_000),
        ("perpetual_ohlcv", "BTCUSDT", base + 4_000_000),
        ("spot_ohlcv", "BTCUSDT", spec["scoring_start"] - 500),
        ("spot_ohlcv", "BTCUSDT", spec["scoring_start"] + 1_000_000),
        ("perpetual_ohlcv", "ETHUSDT", spec["scoring_end"] - 500),
        ("perpetual_ohlcv", "ETHUSDT", spec["scoring_end"] - 2_000),
    ]
    rows = []
    for index, (stream, symbol, event_time) in enumerate(definitions):
        rows.append({"custody_record_hash": H(f"record-{index}"), "stream": stream, "symbol": symbol,
            "event_time_ms": event_time, "available_at": "2029-01-01T00:00:00.000000Z"})
    envelope = {"release_id": "release", "release_core_hash": H("release"), "certificate_hash": H("cert"),
        "release_core": {"custody_records": rows}}
    descriptor = {"selected_custody_record_hashes": [row["custody_record_hash"] for row in rows]}
    monkeypatch.setattr(integrations, "verify_release_envelope_without_values", lambda *args, **kwargs: envelope)
    monkeypatch.setattr(integrations, "build_development_dataset_descriptor", lambda *args, **kwargs: descriptor)
    monkeypatch.setattr(integrations, "_verify_cutoff_completeness", lambda *args, **kwargs: H("complete"))
    policy = {"custody_runtime_root_hash": canonical_hash(str(custody.resolve()))}
    first = integrations._materialize_verified_custody(ProtectedCustodySource(release_a, custody), spec, policy)
    second = integrations._materialize_verified_custody(ProtectedCustodySource(release_b, custody), spec, policy)
    selected_hashes = set(first["context_record_hashes"]) | set(first["scored_record_hashes"])
    selected_pairs = {f"{row['stream']}:{row['symbol']}" for row in rows if row["custody_record_hash"] in selected_hashes}
    assert selected_pairs == {"spot_ohlcv:BTCUSDT", "perpetual_ohlcv:ETHUSDT"}
    assert H("record-4") not in selected_hashes  # context-to-score gap/purge exclusion
    assert H("record-6") not in selected_hashes  # forward horizon excludes stage tail
    assert first["context_record_hashes"] == second["context_record_hashes"]
    assert first["scored_record_hashes"] == second["scored_record_hashes"]


def test_alternate_custody_root_is_rejected_before_release_selection(tmp_path: Path) -> None:
    authorized = tmp_path / "authorized"; alternate = tmp_path / "alternate"; release = tmp_path / "release"
    authorized.mkdir(); alternate.mkdir(); release.mkdir()
    policy = {"custody_runtime_root_hash": canonical_hash(str(authorized.resolve()))}
    with pytest.raises(GovernanceError, match="PROTECTED_CUSTODY_ROOT_UNAUTHORIZED"):
        integrations._materialize_verified_custody(ProtectedCustodySource(release, alternate), validate_partition_spec(_spec("REPLICATION", 0)), policy)


def test_interstage_embargo_and_gap_are_executable_protocol_boundaries() -> None:
    source_value = proposal(); value = protocol(source_value)
    value["protected_partition_specs"][1]["context_start"] = value["protected_partition_specs"][0]["scoring_end"]
    from offchain.research.statistical_governance.protocol import _validate_program_protocol_at
    with pytest.raises(GovernanceError, match="PROTECTED_PARTITIONS_NOT_DISJOINT"):
        _validate_program_protocol_at(value, proposal=source_value, decision_time=NOW)


def test_nondeterministic_or_fake_protected_measurements_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, item = admitted_program(tmp_path, monkeypatch); qualify(root, item, monkeypatch)
    monkeypatch.setattr(store, "trusted_utc_now", lambda: "2040-01-01T00:00:00.000000Z")
    monkeypatch.setattr(store, "_materialize_verified_custody", lambda source, spec, policy: _fake_materialization(spec["stage"], spec))
    register_materialization(root, program_id="program-a", stage="REPLICATION", source=ProtectedCustodySource("/r", "/c"))
    fake = ProtectedEvaluator("test-evaluator", EVALUATOR_DEFINITION, lambda value: {
        "measurements": {"net_pnl": "999", "max_drawdown": "0"},
        "measurement_evidence_hash": canonical_hash({"net_pnl": "999", "max_drawdown": "0"})})
    monkeypatch.setattr(store, "_resolve_protected_evaluator", lambda *args: fake)
    monkeypatch.setattr(store, "_verify_repository_context", lambda expected: None)
    authorization = authorize_stage(root, program_id="program-a", stage="REPLICATION", acknowledgement=ACK_AUTHORIZE_STAGE)
    monkeypatch.setattr(store, "_load_protected_input", lambda materialization, execution: {"exact": True})
    monkeypatch.setattr(store, "execute_protected_candidate", lambda candidate, protected_input: {
        "ledger": {"canonical_event_ledger_hash": H("ledger-negative"), "event_rows": [{}, {}]},
        "metrics": {"net_pnl": "-1", "max_drawdown": "1"},
        "execution_evidence": {"candidate_observable_scored_event_count": 2},
        "execution_evidence_hash": H("protected-execution-negative")})
    with pytest.raises(GovernanceError, match="PROTECTED_MEASUREMENT_NOT_AUTHORITATIVE"):
        open_protected_stage(root, authorization_id=authorization["authorization_id"])


def test_stale_and_incomplete_cutoff_snapshots_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    release = tmp_path / "release"; release.mkdir(); (release / "source-backup.zip").touch()
    spec = validate_partition_spec(_spec("REPLICATION", 0)); pairs = {"spot_ohlcv:BTCUSDT"}
    @contextmanager
    def stale(_path):
        yield tmp_path, {"created_at": "2029-01-01T00:00:00.000000Z"}, H("manifest")
    monkeypatch.setattr(integrations, "_verified_materialization", stale)
    with pytest.raises(GovernanceError, match="PROTECTED_CUSTODY_SNAPSHOT_STALE"):
        integrations._verify_cutoff_completeness(release, pairs, spec)
    @contextmanager
    def recent(_path):
        yield tmp_path, {"created_at": "2040-01-01T00:00:00.000000Z"}, H("manifest")
    class _Rows:
        def execute(self, _sql): return []
    @contextmanager
    def journal_open(*args, **kwargs): yield SimpleNamespace(conn=_Rows())
    monkeypatch.setattr(integrations, "_verified_materialization", recent)
    monkeypatch.setattr(integrations.Journal, "open", journal_open)
    with pytest.raises(GovernanceError, match="PROTECTED_CUSTODY_SNAPSHOT_INCOMPLETE"):
        integrations._verify_cutoff_completeness(release, pairs, spec)


def test_expiration_boundaries_are_exclusive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "trusted_utc_now", lambda: NOW)
    root = tmp_path / "expiry"; initialize_governance(root, acknowledgement=ACK_INITIALIZE)
    item = proposal(); item["valid_until"] = NOW
    committed = commit_campaign_proposal(root, item)
    with pytest.raises(GovernanceError, match="CAMPAIGN_PROPOSAL_EXPIRED"):
        admit_campaign(root, proposal_hash=committed["proposal_hash"], acknowledgement=ACK_ADMIT_CAMPAIGN)


def test_nondeterministic_protected_measurement_engine_is_ineligible() -> None:
    calls = iter(("1", "2"))
    evaluator = ProtectedEvaluator("nondeterministic-evaluator", EVALUATOR_DEFINITION, lambda value: {
        "measurements": {"net_pnl": next(calls)}, "measurement_evidence_hash": H("changing")})
    with pytest.raises(GovernanceError, match="NONDETERMINISTIC_PROTECTED_MEASUREMENT"):
        store._measure_deterministically(evaluator, {"authoritative_metrics": {"net_pnl": "1"}})


def test_program_hash_precedes_nonce_and_activation_is_one_use(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, item, campaign = frozen_program(tmp_path, monkeypatch)
    with store.connection(root, readonly=True) as conn:
        admission = json.loads(conn.execute("SELECT admission_json FROM campaigns").fetchone()[0])
        program_hash = conn.execute("SELECT program_hash FROM programs").fetchone()[0]
        assert conn.execute("SELECT COUNT(*) FROM program_activations").fetchone()[0] == 0
    assert "founder_nonce_hex" not in admission
    assert len(program_hash) == 64
    with pytest.raises(GovernanceError, match="PROGRAM_ACTIVATION_REQUIRED"):
        store.derive_program_null_seed(root, program_id="program-a", hypothesis_id="hypothesis-1")
    calls = []
    monkeypatch.setattr(store, "_verify_terminal_m102_source", lambda value: calls.append(value))
    with pytest.raises(GovernanceError, match="PROGRAM_ACTIVATION_REQUIRED"):
        record_development_result(root, program_id="program-a", hypothesis_id="hypothesis-1", result_source=source())
    assert calls == []
    entropy_calls = []
    monkeypatch.setattr(store, "secure_nonce", lambda: entropy_calls.append(True) or bytes.fromhex("ab" * 32))
    activation = activate_program(root, campaign_id=campaign["campaign_id"], program_id="program-a",
        acknowledgement=ACK_ACTIVATE_PROGRAM)
    assert entropy_calls == [True] and activation["activated_at"] == NOW
    assert "nonce" not in activation
    first_seed = store.derive_program_null_seed(root, program_id="program-a", hypothesis_id="hypothesis-1")
    assert first_seed == store.derive_program_null_seed(root, program_id="program-a", hypothesis_id="hypothesis-1")
    with pytest.raises(GovernanceError, match="PROGRAM_ACTIVATION_STATE_INVALID"):
        activate_program(root, campaign_id=campaign["campaign_id"], program_id="program-a",
            acknowledgement=ACK_ACTIVATE_PROGRAM)
    replacement = protocol(item); replacement["program_id"] = "program-b"
    with pytest.raises(GovernanceError, match="CAMPAIGN_PROGRAM_ALREADY_FROZEN"):
        create_program(root, campaign_id=campaign["campaign_id"], protocol=replacement)
    inspected = store.inspect_governance(root)
    assert "nonce" not in json.dumps(inspected).lower()


def test_result_chronology_rejects_pre_activation_and_bad_link_times(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, item = admitted_program(tmp_path, monkeypatch)
    monkeypatch.setattr(store, "_resolve_statistical_adapter", lambda *args: TEST_ADAPTER)
    pre_activation = verified(item["hypothesis_universe"][0])
    pre_activation["authority_decision_time"] = "2026-08-09T23:59:59.999999Z"
    monkeypatch.setattr(store, "_verify_terminal_m102_source", lambda value: pre_activation)
    with pytest.raises(GovernanceError, match="DEVELOPMENT_CHRONOLOGY_INVALID"):
        record_development_result(root, program_id="program-a", hypothesis_id="hypothesis-1", result_source=source())

    completion_before_authority = verified(item["hypothesis_universe"][0])
    completion_before_authority["authority_decision_time"] = "2026-08-10T00:00:00.000001Z"
    monkeypatch.setattr(store, "_verify_terminal_m102_source", lambda value: completion_before_authority)
    with pytest.raises(GovernanceError, match="DEVELOPMENT_CHRONOLOGY_INVALID"):
        record_development_result(root, program_id="program-a", hypothesis_id="hypothesis-1", result_source=source())

    mismatched_link = verified(item["hypothesis_universe"][0])
    mismatched_link["result_linked_at"] = "2026-08-10T00:00:00.000001Z"
    monkeypatch.setattr(store, "_verify_terminal_m102_source", lambda value: mismatched_link)
    with pytest.raises(GovernanceError, match="DEVELOPMENT_CHRONOLOGY_INVALID"):
        record_development_result(root, program_id="program-a", hypothesis_id="hypothesis-1", result_source=source())


def test_terminal_status_is_derived_and_unresolved_attempt_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert "terminal_status" not in inspect.signature(record_development_result).parameters
    root, item = admitted_program(tmp_path, monkeypatch)
    with pytest.raises(TypeError):
        record_development_result(root, program_id="program-a", hypothesis_id="hypothesis-1",
            result_source=source(), terminal_status="MISSING")
    monkeypatch.setattr(store, "_verify_terminal_m102_source", lambda value: (_ for _ in ()).throw(GovernanceError("M102_ATTEMPT_NONTERMINAL")))
    with pytest.raises(GovernanceError, match="M102_ATTEMPT_NONTERMINAL"):
        record_development_result(root, program_id="program-a", hypothesis_id="hypothesis-1", result_source=source())
    with pytest.raises(GovernanceError, match="ALL_HYPOTHESES_NOT_TERMINAL"):
        qualify_development(root, program_id="program-a")
    monkeypatch.setattr(store, "_verify_terminal_m102_source", lambda value: failed_verified(item["hypothesis_universe"][0]))
    recorded = record_development_result(root, program_id="program-a", hypothesis_id="hypothesis-1", result_source=source())
    assert recorded["terminal_status"] == "FAILED"
    with store.connection(root, readonly=True) as conn:
        evidence = json.loads(conn.execute("SELECT evidence_json FROM development_results").fetchone()[0])
    assert evidence["raw_p_value"] == "1" and evidence["claimed_execution_spec_hash"]


def test_delayed_context_is_excluded_at_exact_scoring_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custody = tmp_path / "custody-delay"; custody.mkdir()
    release = tmp_path / "release-delay"; release.mkdir()
    spec = validate_partition_spec(_spec("REPLICATION", 0))
    before = datetime.fromtimestamp((spec["scoring_start"] - 1) / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    boundary = datetime.fromtimestamp(spec["scoring_start"] / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    rows = [
        {"custody_record_hash": H("context-on-time"), "stream": "spot_ohlcv", "symbol": "BTCUSDT",
            "event_time_ms": spec["context_start"] + 1000, "available_at": before},
        {"custody_record_hash": H("context-late-boundary"), "stream": "spot_ohlcv", "symbol": "BTCUSDT",
            "event_time_ms": spec["context_start"] + 2000, "available_at": boundary},
        {"custody_record_hash": H("scored"), "stream": "spot_ohlcv", "symbol": "BTCUSDT",
            "event_time_ms": spec["scoring_start"] + 1000, "available_at": boundary},
    ]
    envelope = {"release_id": "release", "release_core_hash": H("release"), "certificate_hash": H("certificate"),
        "release_core": {"custody_records": rows}}
    monkeypatch.setattr(integrations, "verify_release_envelope_without_values", lambda *args, **kwargs: envelope)
    monkeypatch.setattr(integrations, "build_development_dataset_descriptor", lambda *args, **kwargs: {
        "selected_custody_record_hashes": [row["custody_record_hash"] for row in rows]})
    monkeypatch.setattr(integrations, "_verify_cutoff_completeness", lambda *args, **kwargs: H("complete"))
    value = integrations._materialize_verified_custody(
        ProtectedCustodySource(release, custody), spec,
        {"custody_runtime_root_hash": canonical_hash(str(custody.resolve()))},
    )
    assert value["context_record_hashes"] == [H("context-on-time")]
    assert H("context-late-boundary") not in value["context_record_hashes"]


def test_materialization_derives_actual_present_inputs_and_hash_binds_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    custody = tmp_path / "custody-present"; custody.mkdir()
    release = tmp_path / "release-present"; release.mkdir()
    raw_spec = _spec("REPLICATION", 0)
    raw_spec["stream_symbols"] = [
        "spot_ohlcv:BTCUSDT", "funding_rates:BTCUSDT", "mark_price_ohlcv:BTCUSDT",
    ]
    raw_spec["stream_intervals"] = {
        "spot_ohlcv": "1h", "funding_rates": None, "mark_price_ohlcv": "1h",
    }
    spec = validate_partition_spec(raw_spec)
    before = datetime.fromtimestamp((spec["scoring_start"] - 1) / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    rows = [
        {"custody_record_hash": H("present-context-spot"), "stream": "spot_ohlcv", "symbol": "BTCUSDT",
            "event_time_ms": spec["context_start"] + 1000, "available_at": before},
        {"custody_record_hash": H("present-scored-funding"), "stream": "funding_rates", "symbol": "BTCUSDT",
            "event_time_ms": spec["scoring_start"] + 1000, "available_at": before},
    ]
    envelope = {"release_id": "release", "release_core_hash": H("release"), "certificate_hash": H("certificate"),
        "release_core": {"custody_records": rows}}
    monkeypatch.setattr(integrations, "verify_release_envelope_without_values", lambda *args, **kwargs: envelope)
    monkeypatch.setattr(integrations, "build_development_dataset_descriptor", lambda *args, **kwargs: {
        "selected_custody_record_hashes": [row["custody_record_hash"] for row in rows]})
    monkeypatch.setattr(integrations, "_verify_cutoff_completeness", lambda *args, **kwargs: H("complete"))
    materialization = integrations._materialize_verified_custody(
        ProtectedCustodySource(release, custody), spec,
        {"custody_runtime_root_hash": canonical_hash(str(custody.resolve()))},
    )
    assert materialization["present_observable_inputs"] == [
        "funding_rates:BTCUSDT", "spot_ohlcv:BTCUSDT",
    ]
    assert "mark_price_ohlcv:BTCUSDT" in materialization["exact_observable_inputs"]
    integrations.verify_materialization_integrity(materialization)
    substituted = {**materialization, "present_observable_inputs": ["spot_ohlcv:BTCUSDT"]}
    with pytest.raises(GovernanceError, match="PROTECTED_MATERIALIZATION_INTEGRITY_INVALID"):
        integrations.verify_materialization_integrity(substituted)


def test_exact_hash_loader_receives_only_materialized_union(monkeypatch: pytest.MonkeyPatch) -> None:
    context = _market_event("context-exact", "1" * 64, 1000, "10")
    scored = _market_event("scored-exact", "2" * 64, 2000, "20")
    captured = {}
    def exact_loader(**kwargs):
        captured.update(kwargs)
        assert "sentinel-excluded" not in kwargs["custody_record_hashes"]
        return (context, scored)
    monkeypatch.setattr(integrations, "load_causal_events_by_custody_hashes", exact_loader)
    core = {"release_directory": "/release",
        "custody_runtime_root": "/custody", "exact_observable_inputs": ["spot_ohlcv:BTCUSDT"],
        "present_observable_inputs": ["spot_ohlcv:BTCUSDT"],
        "release_id": "release", "release_core_hash": H("release"), "certificate_hash": H("certificate"),
        "descriptor": {"selected_custody_record_hashes": [context.custody_record_hash, scored.custody_record_hash, "sentinel-excluded"]},
        "ordered_context_record_hashes": [context.custody_record_hash],
        "ordered_scored_record_hashes": [scored.custody_record_hash]}
    materialization = {**core, "materialization_hash": canonical_hash(core)}
    execution = {"materialization_hash": materialization["materialization_hash"], "stage": "REPLICATION",
        "candidate_hash": H("candidate"), "repository_commit": COMMIT, "program_hash": H("program"),
        "candidate_execution_hash": COST_EXECUTION_HASH, "deterministic_randomness": "NONE_UNLESS_PROTOCOL_BOUND"}
    loaded = integrations._load_protected_input(materialization, execution)
    assert captured["custody_record_hashes"] == (context.custody_record_hash, scored.custody_record_hash)
    assert loaded["context_events"] == (context,) and loaded["scored_events"] == (scored,)


def test_candidate_observable_scope_and_context_reveal_count(monkeypatch: pytest.MonkeyPatch) -> None:
    variant = _variant("variant-observable", "flat")
    family = FamilyDefinition("family-observable", (variant,), lambda parameters: _VariantStrategy(parameters))
    registry = ExperimentRegistry((family,)); monkeypatch.setattr(protected, "production_registry", lambda: registry)
    candidate = _protected_candidate(registry, family, variant, 1)
    with pytest.raises(GovernanceError, match="PROTECTED_CANDIDATE_OBSERVABLE_SCOPE_INCOMPLETE"):
        protected.validate_candidate_observable_scope(candidate, {"present_observable_inputs": ["funding_rates:BTCUSDT"]})
    protected.validate_candidate_observable_scope(candidate, {"present_observable_inputs": [
        "spot_ohlcv:BTCUSDT", "funding_rates:BTCUSDT"]})

    counts = []
    class RevealSensitive:
        def on_event(self, event, state):
            counts.append(state["revealed_event_count"]); return []
    protected._warm_context(RevealSensitive(), variant, (
        _market_event("reveal-1", "3" * 64, 1000, "10"),
        _market_event("reveal-2", "4" * 64, 2000, "20"),
        _market_event("reveal-3", "5" * 64, 3000, "30"),
    ))
    assert counts == [0, 1, 2]


def test_candidate_scope_uses_actual_presence_but_allows_unused_program_superset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variant = VariantDefinition(
        "variant-two-inputs", ("spot_ohlcv", "funding_rates"), ("BTCUSDT",),
        ("spot_ohlcv:BTCUSDT", "funding_rates:BTCUSDT"), ("spot_ohlcv:BTCUSDT",),
        ("funding_rates",), "1000", "1000", "1000", {"spot_ohlcv:BTCUSDT": "1000"},
        "0", "0", False, {"side": "flat"},
    )
    family = FamilyDefinition("family-two-inputs", (variant,), lambda parameters: _VariantStrategy(parameters))
    registry = ExperimentRegistry((family,)); monkeypatch.setattr(protected, "production_registry", lambda: registry)
    candidate = _protected_candidate(registry, family, variant, 1)
    declared_superset = [
        "funding_rates:BTCUSDT", "mark_price_ohlcv:BTCUSDT", "spot_ohlcv:BTCUSDT",
    ]
    with pytest.raises(GovernanceError, match="PROTECTED_CANDIDATE_OBSERVABLE_SCOPE_INCOMPLETE"):
        protected.validate_candidate_observable_scope(candidate, {
            "exact_observable_inputs": declared_superset,
            "present_observable_inputs": ["spot_ohlcv:BTCUSDT"],
        })
    protected.validate_candidate_observable_scope(candidate, {
        "exact_observable_inputs": declared_superset,
        "present_observable_inputs": ["funding_rates:BTCUSDT", "spot_ohlcv:BTCUSDT"],
    })


def test_context_reveal_count_continues_into_fresh_flat_scored_kernel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instances = []
    class RevealAndFinancialProbe:
        def __init__(self, _parameters):
            self.calls = []; instances.append(self)
        def on_event(self, event, state):
            self.calls.append({"event_id": event.event_id, "revealed": state["revealed_event_count"],
                "cash": state["cash"], "equity": state["equity"], "positions": dict(state["positions"]),
                "gross": state["gross_exposure"], "net": state["net_exposure"],
                "pending": tuple(state["pending_instruments"])})
            if state["revealed_event_count"] in {0, 2}:
                return [TargetExposureIntent("BTCUSDT", "spot_ohlcv", "100")]
            return []
    variant = _variant("variant-reveal-continuity", "flat")
    family = FamilyDefinition("family-reveal-continuity", (variant,), RevealAndFinancialProbe)
    registry = ExperimentRegistry((family,)); monkeypatch.setattr(protected, "production_registry", lambda: registry)
    candidate = _protected_candidate(registry, family, variant, 1)
    protected_input = {
        "context_events": (_market_event("context-1", "1" * 64, 1000, "10"),
            _market_event("context-2", "2" * 64, 2000, "20")),
        "scored_events": (_market_event("scored-1", "3" * 64, 3000, "30"),
            _market_event("scored-2", "4" * 64, 4000, "40")),
    }
    result = protected.execute_protected_candidate(candidate, protected_input)
    assert len(instances) == 2
    assert [call["revealed"] for call in instances[0].calls] == [0, 1, 2, 3]
    first_scored = instances[0].calls[2]
    assert first_scored["cash"] == first_scored["equity"] == "1000"
    assert set(first_scored["positions"].values()) == {"0"}
    assert first_scored["gross"] == first_scored["net"] == "0" and first_scored["pending"] == ()
    assert all(row["decision_event_id"] != "event-context-1" for row in result["ledger"]["intent_rows"])
    assert result["execution_evidence"]["context_intents_fills_pnl_counted"] is False
    assert result["execution_evidence"]["candidate_observable_context_event_count"] == 2
    assert result["execution_evidence"]["candidate_observable_scored_event_count"] == 2
    assert result["execution_evidence"]["candidate_observable_scored_event_count"] == len(result["ledger"]["event_rows"])


def test_variant_specific_execution_hashes_coexist_and_selected_hash_controls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    item = proposal()
    second = item["hypothesis_universe"][1]
    second["execution_hash"] = H("second-execution")
    semantic = {"family_hash": second["family_hash"], "variant_hash": second["variant_hash"],
        "parameters": second["parameters"], "execution_id": second["execution_id"],
        "execution_hash": second["execution_hash"], "risk_id": second["risk_id"],
        "risk_hash": second["risk_hash"], "m94": second["m94"], "m101": second["m101"],
        "m102": second["m102"], "statistical_adapter_hash": second["statistical_adapter_hash"]}
    second["hypothesis_hash"] = canonical_hash(semantic)
    root, item = admitted_program(tmp_path, monkeypatch, source_proposal=item)
    monkeypatch.setattr(store, "_resolve_statistical_adapter", lambda *args: TEST_ADAPTER)
    monkeypatch.setattr(store, "_verify_terminal_m102_source", lambda value: verified(
        item["hypothesis_universe"][int(value.trial_id.rsplit("-", 1)[1]) - 1]))
    record_development_result(root, program_id="program-a", hypothesis_id="hypothesis-1", result_source=source(1))
    record_development_result(root, program_id="program-a", hypothesis_id="hypothesis-2", result_source=source(2))
    qualify_development(root, program_id="program-a")
    with store.connection(root, readonly=True) as conn:
        candidate = json.loads(conn.execute("SELECT candidate_json FROM candidates").fetchone()[0])
        program_value = json.loads(conn.execute("SELECT protocol_json FROM programs").fetchone()[0])
    declared_hashes = {hypothesis["execution_hash"] for hypothesis in item["hypothesis_universe"]}
    assert declared_hashes == {COST_EXECUTION_HASH, H("second-execution")}
    assert candidate["execution_hash"] in declared_hashes
    assert all("cost_execution_hash" not in spec for spec in program_value["protected_partition_specs"])
    assert all("cost_execution_hash" not in rule for rule in program_value["protected_acceptance_rules"].values())


@pytest.mark.parametrize("field,value", [
    ("repository_commit", "b" * 40),
    ("family_id", "wrong-family"),
    ("variant_id", "wrong-variant"),
    ("registry_snapshot_hash", H("wrong-registry")),
    ("permit_id", "wrong-permit"),
    ("dataset_id", "wrong-dataset"),
])
def test_post_result_execution_spec_stable_identity_mismatch_rejected(field: str, value: str) -> None:
    hypothesis = proposal(1)["hypothesis_universe"][0]
    evidence = verified(hypothesis)
    evidence[field] = value
    with pytest.raises(GovernanceError, match="DEVELOPMENT_RESULT_BINDING_MISMATCH"):
        verify_development_binding(hypothesis, evidence)


def test_post_result_execution_spec_identity_is_captured_not_preregistered() -> None:
    hypothesis = proposal(1)["hypothesis_universe"][0]
    assert set(hypothesis["m102"]) == {"registry_snapshot_hash", "repository_commit"}
    evidence = verified(hypothesis)
    bound = verify_development_binding(hypothesis, evidence)
    assert bound["execution_spec_id"] == evidence["execution_spec_id"]
    assert bound["execution_spec_hash"] == evidence["execution_spec_hash"]

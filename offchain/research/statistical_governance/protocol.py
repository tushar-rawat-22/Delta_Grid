"""Immutable campaign/program schemas and exact decision rules."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from .core import (
    AUTONOMY_V5_HASH, AUTONOMY_V5_ID, MISSION100_HASH, MISSION100_ID,
    MISSION101_HASH, MISSION101_ID, MISSION102_HASH, MISSION102_ID,
    MISSION103_HASH, MISSION103_ID, MISSION94_HASH, MISSION94_ID,
    MISSION99_HASH, MISSION99_ID, M102_COST_EXECUTION_ID, M102_RISK_ID,
    STAGES, GovernanceError, canonical_hash,
    freeze_json, parse_utc, require_commit, require_decimal_text, require_hash,
    require_identifier, trusted_utc_now,
)
from .statistics import PRNG_ID, as_fraction, validate_monte_carlo_resolution


PROPOSAL_FIELDS = {"schema_version", "proposal_id", "repository_commit", "economic_lineage_id",
    "parent_campaign_hash", "evidence_epoch", "evidence_cutoff_policy", "family_universe",
    "hypothesis_universe", "total_result_guided_capacity", "maximum_program_count", "valid_until",
    "controlling_contracts"}
HYPOTHESIS_FIELDS = {"hypothesis_id", "hypothesis_hash", "economic_family_id", "family_hash",
    "variant_id", "variant_hash", "parameters", "execution_id", "execution_hash", "risk_id", "risk_hash", "m94", "m101",
    "m102", "statistical_adapter_id", "statistical_adapter_hash"}
PARTITION_FIELDS = {"schema_version", "stage", "stream_symbols", "stream_intervals", "context_start",
    "scoring_start", "scoring_end", "availability_cutoff", "time_unit", "minimum_samples",
    "maximum_samples", "purge_ms", "gap_ms", "embargo_ms", "forward_horizon_ms",
    "data_certification_policy", "availability_policy", "disjoint_from", "protected_start_state"}
GATE_FIELDS = {"measurement_id", "operator", "threshold"}
RULE_FIELDS = {"statistic", "direction", "threshold", "measurement_gates",
    "decision_rule", "minimum_scored_samples"}
M102_NUMERIC_METRICS = {"initial_research_nav", "final_equity", "gross_pnl", "fees",
    "slippage_costs", "funding_cash_flow", "net_pnl", "turnover", "gross_exposure",
    "net_exposure", "peak_equity", "max_drawdown"}


def _exact_mapping(value: Any, fields: set[str], reason: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise GovernanceError(reason)
    return freeze_json(dict(value))


def validate_controlling_contracts(value: Any) -> dict[str, str]:
    expected = {AUTONOMY_V5_ID: AUTONOMY_V5_HASH, MISSION103_ID: MISSION103_HASH,
        MISSION102_ID: MISSION102_HASH, MISSION101_ID: MISSION101_HASH,
        MISSION100_ID: MISSION100_HASH, MISSION99_ID: MISSION99_HASH, MISSION94_ID: MISSION94_HASH}
    if not isinstance(value, Mapping) or dict(value) != expected:
        raise GovernanceError("CONTROLLING_CONTRACTS_MISMATCH")
    return dict(value)


def _validate_gate(value: Any) -> dict[str, Any]:
    gate = _exact_mapping(value, GATE_FIELDS, "MEASUREMENT_GATE_SCHEMA_INVALID")
    require_identifier(gate["measurement_id"], "measurement_id")
    if gate["operator"] not in {"GT", "GE", "LT", "LE", "EQ"}:
        raise GovernanceError("MEASUREMENT_GATE_OPERATOR_INVALID")
    require_decimal_text(gate["threshold"], "threshold")
    return gate


def apply_measurement_gates(measurements: Any, gates: Any) -> dict[str, bool]:
    if not isinstance(measurements, Mapping) or not isinstance(gates, list):
        raise GovernanceError("MEASUREMENT_EVIDENCE_INVALID")
    parsed: dict[str, Decimal] = {}
    for key, value in measurements.items():
        require_identifier(key, "measurement_id")
        parsed[key] = require_decimal_text(value, key)
    outcomes: dict[str, bool] = {}
    operations = {"GT": Decimal.__gt__, "GE": Decimal.__ge__, "LT": Decimal.__lt__,
                  "LE": Decimal.__le__, "EQ": Decimal.__eq__}
    for gate_value in gates:
        gate = _validate_gate(gate_value)
        identifier = gate["measurement_id"]
        if identifier not in parsed or identifier in outcomes:
            raise GovernanceError("MEASUREMENT_GATE_SET_MISMATCH")
        outcomes[identifier] = bool(operations[gate["operator"]](parsed[identifier], Decimal(gate["threshold"])))
    if set(parsed) != set(outcomes):
        raise GovernanceError("MEASUREMENT_GATE_SET_MISMATCH")
    return outcomes


def validate_campaign_proposal(value: Mapping[str, Any]) -> dict[str, Any]:
    proposal = _exact_mapping(value, PROPOSAL_FIELDS, "CAMPAIGN_PROPOSAL_SCHEMA_INVALID")
    if proposal["schema_version"] != "1.0":
        raise GovernanceError("CAMPAIGN_PROPOSAL_SCHEMA_INVALID")
    require_identifier(proposal["proposal_id"], "proposal_id")
    require_identifier(proposal["economic_lineage_id"], "economic_lineage_id")
    require_commit(proposal["repository_commit"])
    if proposal["parent_campaign_hash"] is not None:
        require_hash(proposal["parent_campaign_hash"], "parent_campaign_hash")
    if not isinstance(proposal["evidence_epoch"], str) or not proposal["evidence_epoch"]:
        raise GovernanceError("EVIDENCE_EPOCH_INVALID")
    if not isinstance(proposal["evidence_cutoff_policy"], dict) or not proposal["evidence_cutoff_policy"]:
        raise GovernanceError("EVIDENCE_POLICY_INVALID")
    families = proposal["family_universe"]
    if not isinstance(families, list) or not families or len(families) > 1000:
        raise GovernanceError("FAMILY_UNIVERSE_INVALID")
    pairs: set[tuple[str, str]] = set()
    for item in families:
        family = _exact_mapping(item, {"family_id", "family_hash"}, "FAMILY_UNIVERSE_INVALID")
        pair = (require_identifier(family["family_id"], "family_id"), require_hash(family["family_hash"], "family_hash"))
        if pair in pairs or any(existing[0] == pair[0] or existing[1] == pair[1] for existing in pairs):
            raise GovernanceError("FAMILY_UNIVERSE_INVALID")
        pairs.add(pair)
    hypotheses = proposal["hypothesis_universe"]
    if not isinstance(hypotheses, list) or not hypotheses or len(hypotheses) > 1_000:
        raise GovernanceError("HYPOTHESIS_UNIVERSE_INVALID")
    hypothesis_ids: set[str] = set(); hypothesis_hashes: set[str] = set()
    for raw in hypotheses:
        item = _exact_mapping(raw, HYPOTHESIS_FIELDS, "HYPOTHESIS_SCHEMA_INVALID")
        hypothesis_ids.add(require_identifier(item["hypothesis_id"], "hypothesis_id"))
        supplied_hash = require_hash(item["hypothesis_hash"], "hypothesis_hash")
        hypothesis_hashes.add(supplied_hash)
        require_identifier(item["execution_id"], "execution_id")
        if (item["economic_family_id"], item["family_hash"]) not in pairs:
            raise GovernanceError("HYPOTHESIS_FAMILY_BINDING_MISMATCH")
        require_identifier(item["variant_id"], "variant_id"); require_hash(item["variant_hash"], "variant_hash")
        if item["execution_id"] != M102_COST_EXECUTION_ID or item["risk_id"] != M102_RISK_ID:
            raise GovernanceError("GOVERNED_IDENTITY_BINDING_INVALID")
        require_hash(item["execution_hash"], "execution_hash"); require_hash(item["risk_hash"], "risk_hash")
        require_identifier(item["statistical_adapter_id"], "statistical_adapter_id")
        require_hash(item["statistical_adapter_hash"], "statistical_adapter_hash")
        schemas = {
            "m94": {"trial_id", "request_hash", "budget_id", "budget_hash", "declared_trial_number", "fixed_trial_budget"},
            "m101": {"permit_id", "permit_hash", "dataset_id", "descriptor_hash", "release_id", "release_core_hash", "release_certificate_hash"},
            "m102": {"registry_snapshot_hash", "repository_commit"},
        }
        for layer, fields in schemas.items():
            binding = _exact_mapping(item[layer], fields, "GOVERNED_IDENTITY_BINDING_INVALID")
            for key, nested in binding.items():
                if key in {"declared_trial_number", "fixed_trial_budget"}:
                    if type(nested) is not int or nested < 1: raise GovernanceError("GOVERNED_IDENTITY_BINDING_INVALID")
                elif key == "repository_commit": require_commit(nested)
                elif key.endswith("hash"): require_hash(nested, key)
                else: require_identifier(nested, key)
        if item["m102"]["repository_commit"] != proposal["repository_commit"]:
            raise GovernanceError("HISTORICAL_CODE_MISMATCH")
        semantic_core = {"family_hash": item["family_hash"], "variant_hash": item["variant_hash"],
            "parameters": item["parameters"], "execution_id": item["execution_id"],
            "execution_hash": item["execution_hash"], "risk_id": item["risk_id"],
            "risk_hash": item["risk_hash"], "m94": item["m94"],
            "m101": item["m101"], "m102": item["m102"], "statistical_adapter_hash": item["statistical_adapter_hash"]}
        if canonical_hash(semantic_core) != supplied_hash:
            raise GovernanceError("HYPOTHESIS_SEMANTIC_HASH_MISMATCH")
    if len(hypothesis_ids) != len(hypotheses) or len(hypothesis_hashes) != len(hypotheses):
        raise GovernanceError("HYPOTHESIS_UNIVERSE_INVALID")
    if type(proposal["total_result_guided_capacity"]) is not int or proposal["total_result_guided_capacity"] != len(hypotheses):
        raise GovernanceError("RESULT_GUIDED_CAPACITY_MISMATCH")
    if proposal["maximum_program_count"] != 1:
        raise GovernanceError("PROGRAM_COUNT_INVALID")
    parse_utc(proposal["valid_until"], "valid_until")
    validate_controlling_contracts(proposal["controlling_contracts"])
    return proposal


def proposal_commitment(value: Mapping[str, Any]) -> dict[str, Any]:
    proposal = validate_campaign_proposal(value); digest = canonical_hash(proposal)
    anti_reset = canonical_hash({"economic_lineage_id": proposal["economic_lineage_id"],
        "evidence_epoch": proposal["evidence_epoch"], "evidence_cutoff_policy": proposal["evidence_cutoff_policy"]})
    return {"proposal": proposal, "proposal_hash": digest, "anti_reset_key": anti_reset,
            "proposal_commitment_id": f"m103-proposal-{digest}"}


def validate_partition_spec(value: Mapping[str, Any]) -> dict[str, Any]:
    spec = _exact_mapping(value, PARTITION_FIELDS, "PARTITION_SPEC_SCHEMA_INVALID")
    if spec["schema_version"] != "1.0" or spec["stage"] not in STAGES or spec["time_unit"] != "MILLISECONDS":
        raise GovernanceError("PARTITION_SPEC_SCHEMA_INVALID")
    if not isinstance(spec["stream_symbols"], list) or not spec["stream_symbols"] or len(set(spec["stream_symbols"])) != len(spec["stream_symbols"]):
        raise GovernanceError("PARTITION_UNIVERSE_INVALID")
    for value in spec["stream_symbols"]:
        if type(value) is not str or value.count(":") != 1: raise GovernanceError("PARTITION_UNIVERSE_INVALID")
        stream, symbol = value.split(":", 1); require_identifier(stream, "stream"); require_identifier(symbol, "symbol")
    if not isinstance(spec["stream_intervals"], dict): raise GovernanceError("PARTITION_FREQUENCY_INVALID")
    exact_streams = {item.split(":", 1)[0] for item in spec["stream_symbols"]}
    if set(spec["stream_intervals"]) != exact_streams:
        raise GovernanceError("PARTITION_FREQUENCY_INVALID")
    for stream, interval in spec["stream_intervals"].items():
        require_identifier(stream, "stream")
        if interval is not None: require_identifier(interval, "interval")
    for key in ("context_start", "scoring_start", "scoring_end"):
        if type(spec[key]) is not int or spec[key] < 0: raise GovernanceError("PARTITION_BOUND_INVALID", key)
    if not spec["context_start"] < spec["scoring_start"] < spec["scoring_end"]:
        raise GovernanceError("PARTITION_BOUND_INVALID")
    cutoff = parse_utc(spec["availability_cutoff"], "availability_cutoff")
    if int(cutoff.timestamp() * 1000) < spec["scoring_end"]:
        raise GovernanceError("PARTITION_AVAILABILITY_INVALID")
    for key in ("minimum_samples", "maximum_samples", "purge_ms", "gap_ms", "embargo_ms", "forward_horizon_ms"):
        if type(spec[key]) is not int or spec[key] < 0: raise GovernanceError("PARTITION_BOUND_INVALID", key)
    if spec["minimum_samples"] < 1 or spec["maximum_samples"] < spec["minimum_samples"]:
        raise GovernanceError("PARTITION_BOUND_INVALID")
    if spec["scoring_start"] - spec["context_start"] <= spec["purge_ms"] + spec["gap_ms"] + spec["forward_horizon_ms"]:
        raise GovernanceError("PURGE_GAP_CONTEXT_INSUFFICIENT")
    if spec["scoring_end"] - spec["scoring_start"] <= spec["forward_horizon_ms"]:
        raise GovernanceError("FORWARD_HORIZON_INSUFFICIENT")
    if spec["data_certification_policy"] != "M99_M100_M101_VERIFIED" or spec["availability_policy"] != "AVAILABLE_AT_OR_BEFORE_FROZEN_CUTOFF":
        raise GovernanceError("PARTITION_CUSTODY_POLICY_INVALID")
    if spec["disjoint_from"] != list(STAGES[:STAGES.index(spec["stage"])]):
        raise GovernanceError("PARTITION_DISJOINTNESS_INVALID")
    if spec["protected_start_state"] != "FLAT_CASH": raise GovernanceError("PROTECTED_STAGE_NON_FLAT_START")
    digest = canonical_hash(spec)
    return {**spec, "specification_id": f"m103-partition-spec-{digest}", "specification_hash": digest}


PROGRAM_FIELDS = {"schema_version", "program_id", "repository_commit", "hypotheses",
    "primary_statistic", "direction", "null_policy", "alpha", "null_repetitions", "hard_gates",
    "ranking_rule", "ranking_measurements", "tie_break_rule", "maximum_selected_candidates",
    "protected_partition_specs", "protected_acceptance_rules", "protected_engines", "protected_custody_policy",
    "prng_algorithm_version", "no_success_rescue", "expected_campaign_proposal_hash"}


def _validate_program_protocol_at(
    value: Mapping[str, Any], *, proposal: Mapping[str, Any], decision_time: str,
) -> dict[str, Any]:
    program = _exact_mapping(value, PROGRAM_FIELDS, "PROGRAM_PROTOCOL_SCHEMA_INVALID")
    if program["schema_version"] != "1.0": raise GovernanceError("PROGRAM_PROTOCOL_SCHEMA_INVALID")
    require_identifier(program["program_id"], "program_id"); require_commit(program["repository_commit"])
    if program["repository_commit"] != proposal["repository_commit"]: raise GovernanceError("HISTORICAL_CODE_MISMATCH")
    if program["expected_campaign_proposal_hash"] != canonical_hash(proposal): raise GovernanceError("CAMPAIGN_PROPOSAL_BINDING_MISMATCH")
    if program["hypotheses"] != proposal["hypothesis_universe"]: raise GovernanceError("HYPOTHESIS_UNIVERSE_MISMATCH")
    if program["maximum_selected_candidates"] != 1 or program["no_success_rescue"] is not True: raise GovernanceError("NO_RESCUE_RULE_INVALID")
    if program["direction"] not in {"GREATER", "LESS"}: raise GovernanceError("STATISTIC_DIRECTION_INVALID")
    policy = program["null_policy"]
    if not isinstance(policy, dict) or set(policy) != {"kind", "algorithm"} or policy["kind"] not in {"EMPIRICAL_MONTE_CARLO", "EXACT_ENUMERATION"}:
        raise GovernanceError("NULL_POLICY_INVALID")
    as_fraction(program["alpha"], "alpha")
    if policy["kind"] == "EMPIRICAL_MONTE_CARLO":
        validate_monte_carlo_resolution(len(program["hypotheses"]), program["alpha"], program["null_repetitions"])
        if program["null_repetitions"] > 10_000: raise GovernanceError("NULL_REPETITIONS_RUNTIME_LIMIT")
    elif program["null_repetitions"] != 0: raise GovernanceError("EXACT_ENUMERATION_REPETITIONS_INVALID")
    require_identifier(program["primary_statistic"], "primary_statistic")
    if program["ranking_rule"] != "NUMERIC_VECTOR_ASCENDING_V1" or program["tie_break_rule"] != "SEMANTIC_HYPOTHESIS_HASH_ASCENDING_V1":
        raise GovernanceError("RANKING_RULE_INVALID")
    if (
        not isinstance(program["ranking_measurements"], list)
        or not program["ranking_measurements"]
        or len(set(program["ranking_measurements"])) != len(program["ranking_measurements"])
    ):
        raise GovernanceError("RANKING_RULE_INVALID")
    for identifier in program["ranking_measurements"]:
        require_identifier(identifier, "ranking_measurement")
    if program["prng_algorithm_version"] != PRNG_ID: raise GovernanceError("PRNG_ALGORITHM_INVALID")
    if not isinstance(program["hard_gates"], list) or not program["hard_gates"]:
        raise GovernanceError("MEASUREMENT_GATE_SCHEMA_INVALID")
    gates = [_validate_gate(gate) for gate in program["hard_gates"]]
    if len({gate["measurement_id"] for gate in gates}) != len(gates): raise GovernanceError("MEASUREMENT_GATE_SET_MISMATCH")
    custody = _exact_mapping(program["protected_custody_policy"], {"custody_runtime_root_hash", "source_policy_id", "completeness_policy_id"}, "PROTECTED_CUSTODY_POLICY_INVALID")
    require_hash(custody["custody_runtime_root_hash"], "custody_runtime_root_hash")
    if custody["source_policy_id"] != "M100_APPEND_ONLY_SINGLE_ROOT_V1" or custody["completeness_policy_id"] != "M100_CHECKPOINT_THROUGH_FROZEN_CUTOFF_V1":
        raise GovernanceError("PROTECTED_CUSTODY_POLICY_INVALID")
    specs = [validate_partition_spec(item) for item in program["protected_partition_specs"]] if isinstance(program["protected_partition_specs"], list) else []
    if len(specs) != 3 or [item["stage"] for item in specs] != list(STAGES): raise GovernanceError("PARTITION_SPEC_SET_INVALID")
    now = parse_utc(decision_time, "decision_time"); now_ms = int(now.timestamp() * 1000)
    previous_spec = None
    for spec in specs:
        if spec["scoring_start"] <= now_ms: raise GovernanceError("PROTECTED_BOUNDARY_NOT_PROSPECTIVE")
        if previous_spec is not None:
            minimum = previous_spec["scoring_end"] + previous_spec["forward_horizon_ms"] + previous_spec["embargo_ms"] + spec["gap_ms"]
            if spec["context_start"] < minimum: raise GovernanceError("PROTECTED_PARTITIONS_NOT_DISJOINT")
        previous_spec = spec
    engines = program["protected_engines"]
    if not isinstance(engines, dict) or set(engines) != set(STAGES): raise GovernanceError("PROTECTED_ENGINE_SET_INVALID")
    for stage in STAGES:
        engine = _exact_mapping(engines[stage], {"executor_id", "evaluator_id", "evaluator_hash"}, "PROTECTED_ENGINE_SET_INVALID")
        if engine["executor_id"] != "DELTAGRID_M103_M102_EXACT_CANDIDATE_EXECUTOR_V1": raise GovernanceError("PROTECTED_ENGINE_SET_INVALID")
        require_identifier(engine["evaluator_id"], "evaluator_id"); require_hash(engine["evaluator_hash"], "evaluator_hash")
    rules = program["protected_acceptance_rules"]
    if not isinstance(rules, dict) or set(rules) != set(STAGES): raise GovernanceError("PROTECTED_ACCEPTANCE_RULES_INVALID")
    for stage, rule_value in rules.items():
        rule = _exact_mapping(rule_value, RULE_FIELDS, "PROTECTED_ACCEPTANCE_RULES_INVALID")
        require_identifier(rule["statistic"], "statistic")
        if rule["statistic"] not in M102_NUMERIC_METRICS: raise GovernanceError("PROTECTED_MEASUREMENT_UNSUPPORTED")
        if rule["direction"] not in {"GREATER", "LESS"}: raise GovernanceError("PROTECTED_ACCEPTANCE_RULES_INVALID")
        require_decimal_text(rule["threshold"], "threshold")
        if rule["decision_rule"] != "M103_EXACT_ALL_GATES_AND_STATISTIC_V1" or type(rule["minimum_scored_samples"]) is not int or rule["minimum_scored_samples"] < 1:
            raise GovernanceError("PROTECTED_ACCEPTANCE_RULES_INVALID")
        if not isinstance(rule["measurement_gates"], list): raise GovernanceError("PROTECTED_ACCEPTANCE_RULES_INVALID")
        protected_gates = [_validate_gate(gate) for gate in rule["measurement_gates"]]
        if len({gate["measurement_id"] for gate in protected_gates}) != len(protected_gates): raise GovernanceError("MEASUREMENT_GATE_SET_MISMATCH")
        if any(gate["measurement_id"] not in M102_NUMERIC_METRICS for gate in protected_gates): raise GovernanceError("PROTECTED_MEASUREMENT_UNSUPPORTED")
        if rule["minimum_scored_samples"] > specs[STAGES.index(stage)]["maximum_samples"]: raise GovernanceError("PROTECTED_SAMPLE_GATE_UNEXECUTABLE")
    return program


def validate_program_protocol(value: Mapping[str, Any], *, proposal: Mapping[str, Any]) -> dict[str, Any]:
    """Validate against a trusted current time; callers cannot select the clock."""

    return _validate_program_protocol_at(value, proposal=proposal, decision_time=trusted_utc_now())


def verify_development_binding(declared: Mapping[str, Any], verified: Mapping[str, Any]) -> dict[str, Any]:
    success_required = {"terminal_status", "verdict", "verification_mode", "verifier", "trial_id", "request_hash", "budget_id", "budget_hash",
        "declared_trial_number", "fixed_trial_budget", "result_link_hash", "completion_event_timestamp",
        "result_linked_at", "permit_id", "permit_hash", "dataset_id", "descriptor_hash", "execution_spec_id",
        "release_id", "release_core_hash", "release_certificate_hash", "execution_spec_hash",
        "authority_decision_time", "registry_snapshot_hash", "result_bundle_id", "result_hash", "repository_commit",
        "family_id", "family_hash", "variant_id", "variant_hash", "parameters", "cost_execution_id",
        "cost_execution_hash", "risk_id", "risk_hash", "metrics"}
    failure_required = {"terminal_status", "trial_id", "request_hash", "budget_id", "budget_hash",
        "declared_trial_number", "fixed_trial_budget", "permit_id", "permit_hash", "dataset_id",
        "descriptor_hash", "release_id", "release_core_hash", "release_certificate_hash",
        "execution_spec_id", "execution_spec_hash", "authority_decision_time", "failure_timestamp",
        "registry_snapshot_hash", "repository_commit", "family_id", "family_hash", "variant_id",
        "variant_hash", "parameters", "cost_execution_id", "cost_execution_hash", "risk_id",
        "risk_hash", "result_link_absent"}
    if not isinstance(verified, Mapping) or verified.get("terminal_status") not in {"SUCCESS", "FAILED"}:
        raise GovernanceError("M102_TERMINAL_EVIDENCE_REQUIRED")
    required = success_required if verified["terminal_status"] == "SUCCESS" else failure_required
    if set(verified) != required:
        raise GovernanceError("M102_TERMINAL_EVIDENCE_REQUIRED")
    if verified["terminal_status"] == "SUCCESS" and (
        verified["verdict"] != "VERIFIED"
        or verified["verification_mode"] != "FULL_REPLAY_FINALIZED"
        or verified["verifier"] != "DELTAGRID_M102_INDEPENDENT_RESULT_VERIFIER_V1"
    ):
        raise GovernanceError("FINALIZED_M102_RESULT_REQUIRED")
    if verified["terminal_status"] == "FAILED" and verified["result_link_absent"] is not True:
        raise GovernanceError("M102_FAILED_TERMINAL_EVIDENCE_INVALID")
    checks = {"trial_id": declared["m94"]["trial_id"], "request_hash": declared["m94"]["request_hash"],
        "budget_id": declared["m94"]["budget_id"], "budget_hash": declared["m94"]["budget_hash"],
        "declared_trial_number": declared["m94"]["declared_trial_number"], "fixed_trial_budget": declared["m94"]["fixed_trial_budget"],
        "permit_id": declared["m101"]["permit_id"], "permit_hash": declared["m101"]["permit_hash"],
        "dataset_id": declared["m101"]["dataset_id"], "descriptor_hash": declared["m101"]["descriptor_hash"],
        "release_id": declared["m101"]["release_id"], "release_core_hash": declared["m101"]["release_core_hash"],
        "release_certificate_hash": declared["m101"]["release_certificate_hash"],
        "registry_snapshot_hash": declared["m102"]["registry_snapshot_hash"], "repository_commit": declared["m102"]["repository_commit"],
        "family_id": declared["economic_family_id"], "family_hash": declared["family_hash"], "variant_id": declared["variant_id"],
        "variant_hash": declared["variant_hash"], "parameters": declared["parameters"],
        "cost_execution_id": declared["execution_id"], "cost_execution_hash": declared["execution_hash"],
        "risk_id": declared["risk_id"], "risk_hash": declared["risk_hash"]}
    if any(verified.get(key) != expected for key, expected in checks.items()): raise GovernanceError("DEVELOPMENT_RESULT_BINDING_MISMATCH")
    for key in required:
        if key.endswith("hash"): require_hash(verified[key], key)
    require_identifier(verified["execution_spec_id"], "execution_spec_id")
    parse_utc(verified["authority_decision_time"], "authority_decision_time")
    parse_utc(verified["completion_event_timestamp"] if verified["terminal_status"] == "SUCCESS" else verified["failure_timestamp"], "terminal_timestamp")
    if verified["terminal_status"] == "SUCCESS":
        parse_utc(verified["result_linked_at"], "result_linked_at")
    return freeze_json(dict(verified))


__all__ = ["validate_campaign_proposal", "proposal_commitment", "validate_partition_spec",
    "validate_program_protocol", "verify_development_binding", "validate_controlling_contracts",
    "apply_measurement_gates"]

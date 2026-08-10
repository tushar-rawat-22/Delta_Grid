"""Mission 102 execution-specification, artifact, and replay verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from offchain.research.reopening.dataset import verify_development_dataset_descriptor

from .authority import capture_authority_snapshot, read_trial_binding
from .core import (
    ACCOUNTING_KERNEL_ID,
    AUTONOMY_V4_HASH,
    AUTONOMY_V4_ID,
    EVENT_LEDGER_ID,
    EVENT_ORDERING_ID,
    EXECUTION_RUNTIME_ID,
    EXECUTION_SPEC_ID,
    DECIMAL_CONTEXT_ID,
    FILL_MODEL_ID,
    INSTRUMENT_IDENTITY_ID,
    POSITION_EFFECTIVE_TIME_ID,
    TARGET_EXPOSURE_MODEL_ID,
    MISSION101_HASH,
    MISSION101_ID,
    MISSION102_HASH,
    MISSION102_ID,
    MISSION94_HASH,
    MISSION94_ID,
    RESULT_BUNDLE_ID,
    VERIFIER_ID,
    DevelopmentRuntimeError,
    canonical_hash,
    get_repository_observation,
    read_canonical,
)
from .kernel import AccountingKernel
from .loader import load_causal_events
from .registry import ExperimentRegistry, FamilyDefinition, VariantDefinition
from .runtime import trial_directory, validate_result_runtime


def build_execution_specification(
    snapshot: Mapping[str, Any], descriptor: Mapping[str, Any], registry: ExperimentRegistry,
    family: FamilyDefinition, variant: VariantDefinition,
) -> dict[str, Any]:
    authority_binding = dict(snapshot)
    snapshot_core = dict(authority_binding)
    supplied_snapshot_hash = snapshot_core.pop("authority_snapshot_hash", None)
    if canonical_hash(snapshot_core) != supplied_snapshot_hash:
        raise DevelopmentRuntimeError("AUTHORITY_SNAPSHOT_HASH_MISMATCH")
    registry_core = registry.snapshot_core()
    if canonical_hash(registry_core) != registry.snapshot_hash:
        raise DevelopmentRuntimeError("REGISTRY_SNAPSHOT_HASH_MISMATCH")
    core = {
        "schema_version": "1.0",
        "execution_spec_schema": EXECUTION_SPEC_ID,
        "execution_runtime": EXECUTION_RUNTIME_ID,
        "mission102_contract": {"contract_id": MISSION102_ID, "contract_hash_sha256": MISSION102_HASH},
        "autonomy_contract": {"contract_id": AUTONOMY_V4_ID, "contract_hash_sha256": AUTONOMY_V4_HASH},
        "mission101_contract": {"contract_id": MISSION101_ID, "contract_hash_sha256": MISSION101_HASH},
        "mission94_contract": {"contract_id": MISSION94_ID, "contract_hash_sha256": MISSION94_HASH},
        "authority_binding": authority_binding,
        "descriptor_record_set_hash": descriptor["selected_record_set_hash"],
        "selected_record_count": descriptor["selected_record_count"],
        "registry_snapshot_core": registry_core,
        "registry_snapshot_hash": registry.snapshot_hash,
        "family_id": family.family_id,
        "family_definition_hash": family.definition_hash,
        "variant_id": variant.variant_id,
        "variant_definition_hash": variant.definition_hash,
        "variant_definition": variant.core(),
        "instrument_identity": INSTRUMENT_IDENTITY_ID,
        "event_ordering": EVENT_ORDERING_ID,
        "fill_model": FILL_MODEL_ID,
        "target_exposure_model": TARGET_EXPOSURE_MODEL_ID,
        "position_effective_time_model": POSITION_EFFECTIVE_TIME_ID,
        "decimal_context": DECIMAL_CONTEXT_ID,
        "accounting_kernel": ACCOUNTING_KERNEL_ID,
        "data_class": "REAL_MARKET_DEVELOPMENT",
    }
    digest = canonical_hash(core)
    return {**core, "execution_spec_id": f"m102-execution-spec-{digest}", "canonical_execution_spec_hash": digest}


def build_result_artifacts(specification: Mapping[str, Any], ledger: Mapping[str, Any], metrics: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    ledger_core = dict(ledger)
    ledger_hash = ledger_core.pop("canonical_event_ledger_hash")
    if canonical_hash(ledger_core) != ledger_hash:
        raise DevelopmentRuntimeError("EVENT_LEDGER_HASH_MISMATCH")
    bound_ledger_core = {
        **ledger_core,
        "execution_spec_id": specification["execution_spec_id"],
        "execution_spec_hash": specification["canonical_execution_spec_hash"],
    }
    bound_ledger = {**bound_ledger_core, "canonical_event_ledger_hash": canonical_hash(bound_ledger_core)}
    result_core = {
        "schema_version": "1.0",
        "result_type": RESULT_BUNDLE_ID,
        "verifier": VERIFIER_ID,
        "trial_id": specification["authority_binding"]["trial_id"],
        "execution_spec_id": specification["execution_spec_id"],
        "execution_spec_hash": specification["canonical_execution_spec_hash"],
        "event_ledger_hash": bound_ledger["canonical_event_ledger_hash"],
        "family_id": specification["family_id"],
        "family_definition_hash": specification["family_definition_hash"],
        "variant_id": specification["variant_id"],
        "variant_definition_hash": specification["variant_definition_hash"],
        "registry_snapshot_hash": specification["registry_snapshot_hash"],
        "repository_commit": specification["authority_binding"]["repository_commit"],
        "authority_snapshot_hash": specification["authority_binding"]["authority_snapshot_hash"],
        "fill_model": FILL_MODEL_ID,
        "target_exposure_model": TARGET_EXPOSURE_MODEL_ID,
        "position_effective_time_model": POSITION_EFFECTIVE_TIME_ID,
        "decimal_context": DECIMAL_CONTEXT_ID,
        "accounting_kernel": ACCOUNTING_KERNEL_ID,
        "metrics": dict(metrics),
        "authority_boundary": {
            "development_result_execution": True, "validation": False, "holdout": False,
            "model_or_ml": False, "candidate_promotion": False, "paper": False,
            "live": False, "exchange_credentials_orders_or_capital": False,
            "profitability_claim": False,
        },
    }
    result_hash = canonical_hash(result_core)
    result = {
        **result_core,
        "result_bundle_id": f"result-bundle-{result_hash[:32]}",
        "canonical_result_hash": result_hash,
    }
    return bound_ledger, result


def verify_development_result(
    *, result_runtime: str | Path, trial_id: str, ledger_path: str | Path,
    authority_root: str | Path, descriptor: Mapping[str, Any] | str | Path,
    release_directory: str | Path, custody_runtime_root: str | Path,
    registry: ExperimentRegistry,
    require_finalized: bool = True,
    repository_observer: Callable[[], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fully replay exact-commit bytes and prove the requested M94 state."""

    runtime = validate_result_runtime(result_runtime)
    directory = trial_directory(runtime, trial_id, create=False)
    spec, _spec_raw = read_canonical(directory / "execution-spec.json", maximum_bytes=8 * 1024 * 1024)
    stored_ledger, _ledger_raw = read_canonical(directory / "event-ledger.json")
    stored_result, _result_raw = read_canonical(directory / "result.json")
    spec_core = dict(spec)
    supplied_spec_id = spec_core.pop("execution_spec_id", None)
    supplied_spec_hash = spec_core.pop("canonical_execution_spec_hash", None)
    if canonical_hash(spec_core) != supplied_spec_hash or supplied_spec_id != f"m102-execution-spec-{supplied_spec_hash}":
        raise DevelopmentRuntimeError("EXECUTION_SPEC_HASH_MISMATCH")
    binding = spec["authority_binding"]
    if binding["trial_id"] != trial_id:
        raise DevelopmentRuntimeError("RESULT_TRIAL_MISMATCH")
    snapshot_core = dict(binding)
    snapshot_hash = snapshot_core.pop("authority_snapshot_hash", None)
    if canonical_hash(snapshot_core) != snapshot_hash:
        raise DevelopmentRuntimeError("AUTHORITY_SNAPSHOT_HASH_MISMATCH")
    observation = get_repository_observation(repository_observer)
    if not observation["clean"]:
        raise DevelopmentRuntimeError("DIRTY_REPOSITORY")
    if observation["head"] != binding["repository_commit"]:
        raise DevelopmentRuntimeError("HISTORICAL_EXECUTION_CODE_CONTEXT_REQUIRED")
    persisted_registry_core = spec.get("registry_snapshot_core")
    if (
        not isinstance(persisted_registry_core, dict)
        or canonical_hash(persisted_registry_core) != spec.get("registry_snapshot_hash")
        or persisted_registry_core != registry.snapshot_core()
        or spec.get("registry_snapshot_hash") != registry.snapshot_hash
    ):
        raise DevelopmentRuntimeError("REGISTRY_SNAPSHOT_RECONSTRUCTION_MISMATCH")
    verified_descriptor = verify_development_dataset_descriptor(
        descriptor, release_directory=release_directory, runtime_root=custody_runtime_root
    )
    m94 = read_trial_binding(ledger_path, trial_id, allow_completed=require_finalized)
    if require_finalized:
        if m94["lifecycle_state"] != "COMPLETED":
            raise DevelopmentRuntimeError("FINALIZED_RESULT_REQUIRED")
    elif m94["lifecycle_state"] != "ADMITTED" or m94["result_link"] is not None:
        raise DevelopmentRuntimeError("PREFINALIZATION_STATE_INVALID")
    snapshot = capture_authority_snapshot(
        trial_id=trial_id, ledger_path=ledger_path, authority_root=authority_root,
        descriptor=verified_descriptor,
        authority_decision_time=binding["authority_decision_time"],
        repository_observer=repository_observer, require_current=False,
        preliminary_trial=m94,
    )
    family, variant = registry.resolve(binding["experiment_family"], binding["declared_trial_number"], binding["fixed_trial_budget"])
    variant.validate_dataset_scope(verified_descriptor)
    expected_spec = build_execution_specification(snapshot, verified_descriptor, registry, family, variant)
    if expected_spec != spec:
        raise DevelopmentRuntimeError("EXECUTION_SPEC_RECONSTRUCTION_MISMATCH")
    events = load_causal_events(
        verified_descriptor, release_directory=release_directory,
        custody_runtime_root=custody_runtime_root,
        observable_inputs=variant.observable_inputs,
    )
    adapter = family.adapter_factory(variant.strategy_parameters)
    ledger, metrics = AccountingKernel(variant, adapter).run(events)
    expected_ledger, expected_result = build_result_artifacts(spec, ledger, metrics)
    if expected_ledger != stored_ledger:
        raise DevelopmentRuntimeError("EVENT_LEDGER_REPLAY_MISMATCH")
    if expected_result != stored_result:
        raise DevelopmentRuntimeError("RESULT_REPLAY_MISMATCH")
    if require_finalized:
        link = m94["result_link"]
        completion = m94["completion_event"]
        if link is None or completion is None:
            raise DevelopmentRuntimeError("FINALIZED_RESULT_LINK_MISMATCH")
        expected_link_core = {
            "trial_id": trial_id,
            "result_bundle_id": expected_result["result_bundle_id"],
            "result_bundle_hash": expected_result["canonical_result_hash"],
            "result_bundle_path": f"{trial_id}/result.json",
            "linked_at": completion["event_timestamp"],
        }
        if (
            completion["status_token"] != "COMPLETED"
            or completion["reason_token"] != "M102_DEVELOPMENT_RESULT_VERIFIED"
            or {key: link[key] for key in expected_link_core} != expected_link_core
            or link["canonical_result_link_hash"] != canonical_hash(expected_link_core)
        ):
            raise DevelopmentRuntimeError("FINALIZED_RESULT_LINK_MISMATCH")
    return {
        "trial_id": trial_id, "result_bundle_id": stored_result["result_bundle_id"],
        "canonical_result_hash": stored_result["canonical_result_hash"],
        "verdict": "VERIFIED", "verifier": VERIFIER_ID,
        "metrics": stored_result["metrics"],
        "verification_mode": "FULL_REPLAY_FINALIZED" if require_finalized else "FULL_REPLAY_PREFINALIZATION",
    }

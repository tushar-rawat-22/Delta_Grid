"""One-shot Mission 102 orchestration with recovery and independent replay."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from offchain.research.reopening.dataset import verify_development_dataset_descriptor

from .artifacts import build_execution_specification, build_result_artifacts, verify_development_result
from .authority import capture_authority_snapshot, read_trial_binding
from .core import ACK_EXECUTE, DevelopmentRuntimeError, load_contracts, trusted_utc_now
from .finalizer import finalize_verified_result, terminalize_failed_claim
from .kernel import AccountingKernel
from .loader import load_causal_events, verify_release_envelope_without_values
from .registry import ExperimentRegistry, production_registry
from .runtime import claim_execution_spec, publish_artifact, trial_directory, trial_lock, validate_result_runtime


def plan_development_execution(
    *, trial_id: str, ledger_path: str | Path, authority_root: str | Path,
    descriptor: Mapping[str, Any] | str | Path, release_directory: str | Path,
    custody_runtime_root: str | Path, registry: ExperimentRegistry | None = None,
    time_provider: Callable[[], str] | None = None,
    repository_observer: Callable[[], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    load_contracts()
    selected = verify_development_dataset_descriptor(descriptor)
    envelope = verify_release_envelope_without_values(
        release_directory, custody_runtime_root=custody_runtime_root
    )
    if (
        selected["source_forward_custody_release_id"] != envelope["release_id"]
        or selected["release_core_hash"] != envelope["release_core_hash"]
        or selected["release_certificate_hash"] != envelope["certificate_hash"]
        or not set(selected["selected_custody_record_hashes"]) <= envelope["custody_record_hashes"]
    ):
        raise DevelopmentRuntimeError("DATASET_RELEASE_BINDING_MISMATCH")
    snapshot = capture_authority_snapshot(
        trial_id=trial_id, ledger_path=ledger_path, authority_root=authority_root,
        descriptor=selected, time_provider=time_provider,
        repository_observer=repository_observer,
    )
    selected_registry = registry or production_registry()
    family, variant = selected_registry.resolve(
        snapshot["experiment_family"], snapshot["declared_trial_number"], snapshot["fixed_trial_budget"]
    )
    variant.validate_dataset_scope(selected)
    specification = build_execution_specification(snapshot, selected, selected_registry, family, variant)
    return {"trial_id": trial_id, "execution_specification": specification, "market_values_opened": False, "writes_performed": False}


def execute_development_trial(
    *, trial_id: str, ledger_path: str | Path, authority_root: str | Path,
    descriptor: Mapping[str, Any] | str | Path, release_directory: str | Path,
    custody_runtime_root: str | Path, result_runtime: str | Path,
    acknowledgement: str, registry: ExperimentRegistry | None = None,
    time_provider: Callable[[], str] | None = None,
    audit_time_provider: Callable[[], str] | None = None,
    repository_observer: Callable[[], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if acknowledgement != ACK_EXECUTE:
        raise DevelopmentRuntimeError("EXECUTION_ACKNOWLEDGEMENT_REQUIRED")
    load_contracts()
    selected_registry = registry or production_registry()
    preliminary = read_trial_binding(ledger_path, trial_id, allow_completed=True)
    if preliminary["lifecycle_state"] == "COMPLETED":
        return verify_development_result(
            result_runtime=result_runtime, trial_id=trial_id, ledger_path=ledger_path,
            authority_root=authority_root, descriptor=descriptor,
            release_directory=release_directory, custody_runtime_root=custody_runtime_root,
            registry=selected_registry, require_finalized=True,
            repository_observer=repository_observer,
        )
    with trial_lock(result_runtime, trial_id, ledger_path=ledger_path) as runtime:
        locked_trial = read_trial_binding(ledger_path, trial_id)
        selected = verify_development_dataset_descriptor(descriptor)
        envelope = verify_release_envelope_without_values(
            release_directory, custody_runtime_root=custody_runtime_root
        )
        if (
            selected["source_forward_custody_release_id"] != envelope["release_id"]
            or selected["release_core_hash"] != envelope["release_core_hash"]
            or selected["release_certificate_hash"] != envelope["certificate_hash"]
            or not set(selected["selected_custody_record_hashes"]) <= envelope["custody_record_hashes"]
        ):
            raise DevelopmentRuntimeError("DATASET_RELEASE_BINDING_MISMATCH")
        snapshot = capture_authority_snapshot(
            trial_id=trial_id, ledger_path=ledger_path, authority_root=authority_root,
            descriptor=selected, time_provider=time_provider,
            repository_observer=repository_observer,
            preliminary_trial=locked_trial,
        )
        family, variant = selected_registry.resolve(
            snapshot["experiment_family"], snapshot["declared_trial_number"], snapshot["fixed_trial_budget"]
        )
        variant.validate_dataset_scope(selected)
        specification = build_execution_specification(snapshot, selected, selected_registry, family, variant)
        directory = trial_directory(runtime, trial_id, create=True)
        _claimed, _recovery = claim_execution_spec(directory, specification)
        try:
            events = load_causal_events(
                selected, release_directory=release_directory, custody_runtime_root=custody_runtime_root,
                observable_inputs=variant.observable_inputs,
            )
            adapter = family.adapter_factory(variant.strategy_parameters)
            ledger, metrics = AccountingKernel(variant, adapter).run(events)
            event_ledger, result = build_result_artifacts(specification, ledger, metrics)
            publish_artifact(directory, "event-ledger.json", event_ledger)
            publish_artifact(directory, "result.json", result)
            verified = verify_development_result(
                result_runtime=runtime, trial_id=trial_id, ledger_path=ledger_path,
                authority_root=authority_root, descriptor=selected,
                release_directory=release_directory, custody_runtime_root=custody_runtime_root,
                registry=selected_registry, require_finalized=False,
                repository_observer=repository_observer,
            )
            finalized = finalize_verified_result(
                ledger_path, verified=verified, result_relative_path=f"{trial_id}/result.json",
                linked_at=(audit_time_provider or trusted_utc_now)(),
            )
            finalized_verified = verify_development_result(
                result_runtime=runtime, trial_id=trial_id, ledger_path=ledger_path,
                authority_root=authority_root, descriptor=selected,
                release_directory=release_directory, custody_runtime_root=custody_runtime_root,
                registry=selected_registry, require_finalized=True,
                repository_observer=repository_observer,
            )
            return {**finalized_verified, "finalization": finalized}
        except Exception as error:
            try:
                terminalize_failed_claim(
                    ledger_path, trial_id=trial_id,
                    reason=getattr(error, "reason", "INTERNAL_INTEGRITY_FAILURE"),
                    event_at=(audit_time_provider or trusted_utc_now)(),
                )
            except DevelopmentRuntimeError:
                pass
            raise


def inspect_development_results(result_runtime: str | Path) -> dict[str, Any]:
    root = validate_result_runtime(result_runtime)
    trials = []
    for item in sorted(root.iterdir(), key=lambda path: path.name):
        if item.name == ".locks":
            continue
        directory = trial_directory(root, item.name, create=False)
        artifacts = []
        for child in directory.iterdir():
            if child.name not in {"execution-spec.json", "event-ledger.json", "result.json"} or child.is_symlink() or not child.is_file() or child.stat().st_mode & 0o777 != 0o600:
                raise DevelopmentRuntimeError("RESULT_RUNTIME_LAYOUT_INVALID")
            artifacts.append(child.name)
        trials.append({"trial_id": item.name, "artifacts": sorted(artifacts)})
        if len(trials) > 10_000:
            raise DevelopmentRuntimeError("RESULT_COUNT_LIMIT")
    return {"runtime_root": str(root), "trial_count": len(trials), "trials": trials, "writes_performed": False}

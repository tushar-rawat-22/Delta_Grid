"""Internal M94-M102 and M99-M101 verification bridges for Mission 103."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Mapping
from urllib.parse import quote

from offchain.research.admission.models import canonical_hash as m94_hash
from offchain.research.development_runtime.artifacts import verify_development_result
from offchain.research.development_runtime.authority import ADMISSION_REASON, read_trial_binding
from offchain.research.development_runtime.core import get_repository_observation, read_canonical
from offchain.research.development_runtime.loader import (
    load_causal_events_by_custody_hashes, verify_release_envelope_without_values,
)
from offchain.research.development_runtime.registry import production_registry
from offchain.research.development_runtime.runtime import trial_directory, validate_result_runtime
from offchain.research.reopening.admission import _trial_ledger_path, _verify_trial_ledger_file
from offchain.research.reopening.dataset import STREAM_INTERVALS, build_development_dataset_descriptor
from offchain.research.reopening.bridge import _verified_materialization
from offchain.market_data_acquisition.journal import Journal

from .core import (
    M102_COST_EXECUTION_ID, M102_RISK_ID, GovernanceError, canonical_hash,
    freeze_json, parse_utc,
)


M102_FAILURE_REASON = "M102_EXECUTION_OR_INTEGRITY_FAILURE"


@dataclass(frozen=True)
class M102ResultSource:
    result_runtime: str | Path
    trial_id: str
    ledger_path: str | Path
    authority_root: str | Path
    descriptor: Mapping[str, Any] | str | Path
    release_directory: str | Path
    custody_runtime_root: str | Path


@dataclass(frozen=True)
class ProtectedCustodySource:
    release_directory: str | Path
    custody_runtime_root: str | Path


def _verify_repository_context(expected_commit: str) -> None:
    try:
        observation = get_repository_observation()
    except Exception as error:
        raise GovernanceError("PROTECTED_REPOSITORY_CONTEXT_INVALID") from error
    if not observation.get("clean") or observation.get("head") != expected_commit:
        raise GovernanceError("PROTECTED_REPOSITORY_CONTEXT_INVALID")


def _verify_finalized_m102_source(source: M102ResultSource) -> dict[str, Any]:
    """Run M102's real replay verifier, then bind its canonical stored artifacts."""

    if type(source) is not M102ResultSource:
        raise GovernanceError("M102_RESULT_SOURCE_INVALID")
    try:
        compact = verify_development_result(
            result_runtime=source.result_runtime, trial_id=source.trial_id,
            ledger_path=source.ledger_path, authority_root=source.authority_root,
            descriptor=source.descriptor, release_directory=source.release_directory,
            custody_runtime_root=source.custody_runtime_root, registry=production_registry(),
            require_finalized=True,
        )
        runtime = validate_result_runtime(source.result_runtime)
        directory = trial_directory(runtime, source.trial_id, create=False)
        spec, _ = read_canonical(directory / "execution-spec.json", maximum_bytes=8 * 1024 * 1024)
        result, _ = read_canonical(directory / "result.json", maximum_bytes=8 * 1024 * 1024)
        binding = read_trial_binding(source.ledger_path, source.trial_id, allow_completed=True)
    except Exception as error:
        raise GovernanceError("FINALIZED_M102_RESULT_REQUIRED") from error
    link = binding.get("result_link")
    completion = binding.get("completion_event")
    budget = binding.get("budget")
    authority = spec.get("authority_binding") if isinstance(spec, dict) else None
    variant = spec.get("variant_definition") if isinstance(spec, dict) else None
    if (
        compact.get("verdict") != "VERIFIED"
        or compact.get("verification_mode") != "FULL_REPLAY_FINALIZED"
        or not isinstance(link, dict) or not isinstance(completion, dict) or not isinstance(budget, dict)
        or not isinstance(authority, dict) or not isinstance(variant, dict)
        or result.get("canonical_result_hash") != compact.get("canonical_result_hash")
        or result.get("result_bundle_id") != compact.get("result_bundle_id")
        or link.get("result_bundle_hash") != result.get("canonical_result_hash")
    ):
        raise GovernanceError("FINALIZED_M102_RESULT_REQUIRED")
    cost_execution = {
        "fee_bps": variant.get("fee_model", {}).get("bps") if isinstance(variant.get("fee_model"), dict) else None,
        "slippage_bps": variant.get("slippage_model", {}).get("bps") if isinstance(variant.get("slippage_model"), dict) else None,
        "fill_model": spec.get("fill_model"), "target_exposure_model": spec.get("target_exposure_model"),
        "position_effective_time_model": spec.get("position_effective_time_model"),
        "variant_definition_hash": spec.get("variant_definition_hash"),
    }
    risk = {"initial_research_nav": variant.get("initial_research_nav"),
        "max_gross_research_exposure": variant.get("max_gross_research_exposure"),
        "max_net_research_exposure": variant.get("max_net_research_exposure"),
        "per_instrument_bounds": variant.get("per_instrument_bounds")}
    evidence = {
        **compact,
        "request_hash": authority.get("request_hash"), "budget_id": authority.get("budget_id"),
        "budget_hash": budget["canonical_budget_hash"],
        "declared_trial_number": authority.get("declared_trial_number"),
        "fixed_trial_budget": authority.get("fixed_trial_budget"),
        "result_link_hash": link.get("canonical_result_link_hash"),
        "completion_event_timestamp": completion.get("event_timestamp"),
        "result_linked_at": link.get("linked_at"),
        "permit_id": authority.get("permit_id"), "permit_hash": authority.get("permit_hash"),
        "dataset_id": authority.get("dataset_id"), "descriptor_hash": authority.get("dataset_descriptor_hash"),
        "release_id": authority.get("release_id"), "release_core_hash": authority.get("release_core_hash"),
        "release_certificate_hash": authority.get("release_certificate_hash"),
        "execution_spec_id": spec.get("execution_spec_id"),
        "execution_spec_hash": spec.get("canonical_execution_spec_hash"),
        "authority_decision_time": authority.get("authority_decision_time"),
        "registry_snapshot_hash": spec.get("registry_snapshot_hash"),
        "result_hash": result.get("canonical_result_hash"),
        "repository_commit": authority.get("repository_commit"), "family_id": spec.get("family_id"),
        "family_hash": spec.get("family_definition_hash"), "variant_id": spec.get("variant_id"),
        "variant_hash": spec.get("variant_definition_hash"), "parameters": variant.get("strategy_parameters"),
        "cost_execution_id": M102_COST_EXECUTION_ID,
        "cost_execution_hash": canonical_hash(cost_execution),
        "risk_id": M102_RISK_ID, "risk_hash": canonical_hash(risk),
        "terminal_status": "SUCCESS",
    }
    evidence.pop("canonical_result_hash", None)
    return freeze_json(evidence)


def _terminal_trial_state(source: M102ResultSource) -> str:
    """Read only the hardened M94 event status to select the verifier path."""

    try:
        path = _trial_ledger_path(source.ledger_path, must_exist=True)
        _verify_trial_ledger_file(path)
        conn = sqlite3.connect(
            "file:" + quote(str(path), safe="/") + "?mode=ro", uri=True,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            rows = conn.execute(
                "SELECT * FROM trial_events WHERE trial_id=? ORDER BY sequence_number",
                (source.trial_id,),
            ).fetchall()
            if len(rows) != 3:
                raise GovernanceError("M102_ATTEMPT_NONTERMINAL")
            previous = None
            for index, row in enumerate(rows, 1):
                core = {key: row[key] for key in (
                    "trial_id", "sequence_number", "status_token", "reason_token", "event_timestamp",
                )}
                timestamp = parse_utc(row["event_timestamp"], "m94_event_timestamp")
                if (
                    row["sequence_number"] != index
                    or row["canonical_event_hash"] != m94_hash(core)
                    or row["event_id"] != f"event-{row['canonical_event_hash'][:32]}"
                    or (previous is not None and timestamp < previous)
                ):
                    raise GovernanceError("M94_TERMINAL_EVIDENCE_INVALID")
                previous = timestamp
            statuses = [row["status_token"] for row in rows]
            if statuses[:2] != ["RESERVED", "ADMITTED"] or rows[0]["reason_token"] != "TRIAL_RESERVED" or rows[1]["reason_token"] != ADMISSION_REASON:
                raise GovernanceError("M94_TERMINAL_EVIDENCE_INVALID")
            if statuses[2] not in {"COMPLETED", "FAILED"}:
                raise GovernanceError("M102_ATTEMPT_NONTERMINAL")
            return str(statuses[2])
        finally:
            conn.close()
    except GovernanceError:
        raise
    except Exception as error:
        raise GovernanceError("M94_TERMINAL_EVIDENCE_INVALID") from error


def _verify_claimed_execution_spec(source: M102ResultSource) -> dict[str, Any]:
    try:
        runtime = validate_result_runtime(source.result_runtime)
        directory = trial_directory(runtime, source.trial_id, create=False)
        spec, _ = read_canonical(directory / "execution-spec.json", maximum_bytes=8 * 1024 * 1024)
    except Exception as error:
        raise GovernanceError("M102_FAILED_EXECUTION_SPEC_REQUIRED") from error
    spec_core = dict(spec)
    spec_id = spec_core.pop("execution_spec_id", None)
    spec_hash = spec_core.pop("canonical_execution_spec_hash", None)
    authority = spec.get("authority_binding") if isinstance(spec, dict) else None
    variant = spec.get("variant_definition") if isinstance(spec, dict) else None
    registry_core = spec.get("registry_snapshot_core") if isinstance(spec, dict) else None
    if (
        canonical_hash(spec_core) != spec_hash
        or spec_id != f"m102-execution-spec-{spec_hash}"
        or not isinstance(authority, dict)
        or not isinstance(variant, dict)
        or not isinstance(registry_core, dict)
        or canonical_hash(registry_core) != spec.get("registry_snapshot_hash")
        or canonical_hash(variant) != spec.get("variant_definition_hash")
    ):
        raise GovernanceError("M102_FAILED_EXECUTION_SPEC_INVALID")
    registry = production_registry()
    if registry.snapshot_core() != registry_core or registry.snapshot_hash != spec.get("registry_snapshot_hash"):
        raise GovernanceError("M102_FAILED_EXECUTION_SPEC_INVALID")
    try:
        family, registered_variant = registry.resolve(
            authority.get("experiment_family"), authority.get("declared_trial_number"),
            authority.get("fixed_trial_budget"),
        )
    except Exception as error:
        raise GovernanceError("M102_FAILED_EXECUTION_SPEC_INVALID") from error
    if (
        family.definition_hash != spec.get("family_definition_hash")
        or registered_variant.variant_id != spec.get("variant_id")
        or registered_variant.definition_hash != spec.get("variant_definition_hash")
        or registered_variant.core() != variant
    ):
        raise GovernanceError("M102_FAILED_EXECUTION_SPEC_INVALID")
    authority_core = dict(authority)
    authority_hash = authority_core.pop("authority_snapshot_hash", None)
    if canonical_hash(authority_core) != authority_hash:
        raise GovernanceError("M102_FAILED_EXECUTION_SPEC_INVALID")
    cost_execution = {
        "fee_bps": variant.get("fee_model", {}).get("bps") if isinstance(variant.get("fee_model"), dict) else None,
        "slippage_bps": variant.get("slippage_model", {}).get("bps") if isinstance(variant.get("slippage_model"), dict) else None,
        "fill_model": spec.get("fill_model"), "target_exposure_model": spec.get("target_exposure_model"),
        "position_effective_time_model": spec.get("position_effective_time_model"),
        "variant_definition_hash": spec.get("variant_definition_hash"),
    }
    risk = {
        "initial_research_nav": variant.get("initial_research_nav"),
        "max_gross_research_exposure": variant.get("max_gross_research_exposure"),
        "max_net_research_exposure": variant.get("max_net_research_exposure"),
        "per_instrument_bounds": variant.get("per_instrument_bounds"),
    }
    return {"spec": spec, "authority": authority, "variant": variant,
        "cost_execution_hash": canonical_hash(cost_execution), "risk_hash": canonical_hash(risk)}


def _verify_failed_m102_source(source: M102ResultSource) -> dict[str, Any]:
    """Derive a genuine M102 failure from M94 terminalization and a claimed spec."""

    claimed = _verify_claimed_execution_spec(source)
    spec = claimed["spec"]; authority = claimed["authority"]; variant = claimed["variant"]
    try:
        path = _trial_ledger_path(source.ledger_path, must_exist=True)
        _verify_trial_ledger_file(path)
        conn = sqlite3.connect(
            "file:" + quote(str(path), safe="/") + "?mode=ro", uri=True,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON"); conn.execute("BEGIN")
            reservation = conn.execute("SELECT * FROM trial_reservations WHERE trial_id=?", (source.trial_id,)).fetchone()
            if reservation is None:
                raise GovernanceError("M94_TERMINAL_EVIDENCE_INVALID")
            budget = conn.execute("SELECT * FROM trial_budgets WHERE budget_id=?", (reservation["budget_id"],)).fetchone()
            events = conn.execute("SELECT * FROM trial_events WHERE trial_id=? ORDER BY sequence_number", (source.trial_id,)).fetchall()
            links = conn.execute("SELECT * FROM trial_result_links WHERE trial_id=?", (source.trial_id,)).fetchall()
            if budget is None or len(events) != 3 or links or events[2]["status_token"] != "FAILED" or events[2]["reason_token"] != M102_FAILURE_REASON:
                raise GovernanceError("M102_FAILED_TERMINAL_EVIDENCE_INVALID")
            failure_timestamp = events[2]["event_timestamp"]
            budget_core = {key: budget[key] for key in (
                "budget_id", "controlling_contract_id", "controlling_contract_hash",
                "experiment_family", "total_trial_budget", "created_at",
            )}
            if budget["canonical_budget_hash"] != m94_hash(budget_core):
                raise GovernanceError("M102_FAILED_TERMINAL_EVIDENCE_INVALID")
        finally:
            conn.close()
    except GovernanceError:
        raise
    except Exception as error:
        raise GovernanceError("M102_FAILED_TERMINAL_EVIDENCE_INVALID") from error
    return freeze_json({
        "terminal_status": "FAILED", "trial_id": source.trial_id,
        "request_hash": authority.get("request_hash"), "budget_id": authority.get("budget_id"),
        "budget_hash": budget["canonical_budget_hash"],
        "declared_trial_number": authority.get("declared_trial_number"),
        "fixed_trial_budget": authority.get("fixed_trial_budget"),
        "permit_id": authority.get("permit_id"), "permit_hash": authority.get("permit_hash"),
        "dataset_id": authority.get("dataset_id"), "descriptor_hash": authority.get("dataset_descriptor_hash"),
        "release_id": authority.get("release_id"), "release_core_hash": authority.get("release_core_hash"),
        "release_certificate_hash": authority.get("release_certificate_hash"),
        "execution_spec_id": spec.get("execution_spec_id"),
        "execution_spec_hash": spec.get("canonical_execution_spec_hash"),
        "authority_decision_time": authority.get("authority_decision_time"),
        "failure_timestamp": failure_timestamp,
        "registry_snapshot_hash": spec.get("registry_snapshot_hash"),
        "repository_commit": authority.get("repository_commit"),
        "family_id": spec.get("family_id"), "family_hash": spec.get("family_definition_hash"),
        "variant_id": spec.get("variant_id"), "variant_hash": spec.get("variant_definition_hash"),
        "parameters": variant.get("strategy_parameters"),
        "cost_execution_id": M102_COST_EXECUTION_ID,
        "cost_execution_hash": claimed["cost_execution_hash"],
        "risk_id": M102_RISK_ID, "risk_hash": claimed["risk_hash"],
        "result_link_absent": True,
    })


def _verify_terminal_m102_source(source: M102ResultSource) -> dict[str, Any]:
    if type(source) is not M102ResultSource:
        raise GovernanceError("M102_RESULT_SOURCE_INVALID")
    status = _terminal_trial_state(source)
    if status == "COMPLETED":
        return _verify_finalized_m102_source(source)
    if status == "FAILED":
        return _verify_failed_m102_source(source)
    raise GovernanceError("M102_ATTEMPT_NONTERMINAL")


def _iso_from_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _verify_cutoff_completeness(
    release_directory: str | Path, exact_pairs: set[str], spec: Mapping[str, Any],
) -> str:
    backup = Path(release_directory) / "source-backup.zip"
    try:
        with _verified_materialization(backup) as (runtime, manifest, _manifest_hash):
            if parse_utc(manifest["created_at"], "manifest_created_at") <= parse_utc(spec["availability_cutoff"], "availability_cutoff"):
                raise GovernanceError("PROTECTED_CUSTODY_SNAPSHOT_STALE")
            with Journal.open(runtime, readonly=True) as journal:
                rows = {(row["stream"], row["symbol"]): int(row["next_event_time_ms"])
                    for row in journal.conn.execute("SELECT stream,symbol,next_event_time_ms FROM checkpoints")}
                for pair in exact_pairs:
                    stream, symbol = pair.split(":", 1)
                    checkpoint = rows.get((stream, symbol))
                    cutoff_ms = int(parse_utc(spec["availability_cutoff"], "availability_cutoff").timestamp() * 1000)
                    if checkpoint is None or checkpoint <= cutoff_ms:
                        raise GovernanceError("PROTECTED_CUSTODY_SNAPSHOT_INCOMPLETE")
    except GovernanceError:
        raise
    except Exception as error:
        raise GovernanceError("PROTECTED_CUSTODY_COMPLETENESS_UNPROVEN") from error
    return canonical_hash({"policy": "M100_CHECKPOINT_THROUGH_FROZEN_CUTOFF_V1",
        "pairs": sorted(exact_pairs), "scoring_end": spec["scoring_end"],
        "availability_cutoff": spec["availability_cutoff"]})


def _materialize_verified_custody(
    source: ProtectedCustodySource, spec: Mapping[str, Any], policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Recertify M99/M100/M101 and derive exact context/scored sets internally."""

    if type(source) is not ProtectedCustodySource:
        raise GovernanceError("PROTECTED_CUSTODY_SOURCE_INVALID")
    try:
        resolved_root = str(Path(source.custody_runtime_root).resolve(strict=True))
        if canonical_hash(resolved_root) != policy["custody_runtime_root_hash"]:
            raise GovernanceError("PROTECTED_CUSTODY_ROOT_UNAUTHORIZED")
        envelope = verify_release_envelope_without_values(
            source.release_directory, custody_runtime_root=source.custody_runtime_root
        )
        exact_pairs = set(spec["stream_symbols"])
        streams: set[str] = set(); symbols: set[str] = set()
        for instrument in spec["stream_symbols"]:
            stream, symbol = instrument.split(":", 1); streams.add(stream); symbols.add(symbol)
        if any(STREAM_INTERVALS.get(stream) != spec["stream_intervals"][stream] for stream in streams):
            raise GovernanceError("PROTECTED_FREQUENCY_BINDING_MISMATCH")
        completeness_hash = _verify_cutoff_completeness(source.release_directory, exact_pairs, spec)
        descriptor = build_development_dataset_descriptor(
            source.release_directory, runtime_root=source.custody_runtime_root,
            provider="BINANCE_PUBLIC", symbols=symbols, streams=streams,
            temporal_start=_iso_from_ms(spec["context_start"]),
            temporal_end_as_of=_iso_from_ms(spec["scoring_end"]),
            causal_availability_cutoff=spec["availability_cutoff"],
            provenance_reference=f"M103_{spec['stage']}_PROTECTED_MATERIALIZATION",
        )
    except GovernanceError:
        raise
    except Exception as error:
        raise GovernanceError("PROTECTED_CUSTODY_VERIFICATION_FAILED") from error
    records = {row["custody_record_hash"]: row for row in envelope["release_core"]["custody_records"]}
    selected = [digest for digest in descriptor["selected_custody_record_hashes"]
        if f"{records[digest]['stream']}:{records[digest]['symbol']}" in exact_pairs]
    causal_key = lambda digest: (parse_utc(records[digest]["available_at"], "available_at"), digest)
    context_end = spec["scoring_start"] - spec["gap_ms"] - spec["purge_ms"] - spec["forward_horizon_ms"]
    scored_end = spec["scoring_end"] - spec["forward_horizon_ms"]
    scoring_start_utc = datetime.fromtimestamp(spec["scoring_start"] / 1000, timezone.utc)
    ordered_context = sorted((digest for digest in selected
        if spec["context_start"] <= records[digest]["event_time_ms"] < context_end
        and parse_utc(records[digest]["available_at"], "available_at") < scoring_start_utc), key=causal_key)
    ordered_scored = sorted((digest for digest in selected if spec["scoring_start"] <= records[digest]["event_time_ms"] <= scored_end), key=causal_key)
    context = sorted(ordered_context); scored = sorted(ordered_scored)
    if not context or not scored or set(context) & set(scored) or len(set(selected)) != len(selected):
        raise GovernanceError("PROTECTED_RECORD_PARTITION_INVALID")
    present_observable_inputs = sorted({
        f"{records[digest]['stream']}:{records[digest]['symbol']}"
        for digest in context + scored
    })
    if not set(present_observable_inputs) <= exact_pairs:
        raise GovernanceError("PROTECTED_MATERIALIZATION_INTEGRITY_INVALID")
    core = {
        "stage": spec["stage"], "specification_hash": spec["specification_hash"],
        "release_id": envelope["release_id"], "release_core_hash": envelope["release_core_hash"],
        "certificate_hash": envelope["certificate_hash"], "descriptor": descriptor,
        "exact_observable_inputs": sorted(exact_pairs),
        "present_observable_inputs": present_observable_inputs,
        "completeness_proof_hash": completeness_hash,
        "context_record_hashes": context, "context_record_set_hash": canonical_hash(context),
        "scored_record_hashes": scored, "scored_record_set_hash": canonical_hash(scored),
        "ordered_context_record_hashes": ordered_context, "ordered_context_hash": canonical_hash(ordered_context),
        "ordered_scored_record_hashes": ordered_scored, "ordered_scored_hash": canonical_hash(ordered_scored),
        "context_count": len(context), "scored_count": len(scored),
        "release_directory": str(Path(source.release_directory).resolve()),
        "custody_runtime_root": str(Path(source.custody_runtime_root).resolve()),
    }
    return {**core, "materialization_hash": canonical_hash(core)}


def verify_materialization_integrity(materialization: Mapping[str, Any]) -> None:
    """Recompute the immutable materialization identity and observable scope."""

    if not isinstance(materialization, Mapping):
        raise GovernanceError("PROTECTED_MATERIALIZATION_INTEGRITY_INVALID")
    value = dict(materialization)
    value.pop("materialization_id", None)
    value.pop("metadata_commitment", None)
    supplied_hash = value.pop("materialization_hash", None)
    exact = value.get("exact_observable_inputs")
    present = value.get("present_observable_inputs")
    if (
        not isinstance(exact, list)
        or not isinstance(present, list)
        or any(type(item) is not str or item.count(":") != 1 for item in exact + present)
    ):
        raise GovernanceError("PROTECTED_MATERIALIZATION_INTEGRITY_INVALID")
    if (
        exact != sorted(set(exact))
        or present != sorted(set(present))
        or not set(present) <= set(exact)
        or supplied_hash != canonical_hash(value)
    ):
        raise GovernanceError("PROTECTED_MATERIALIZATION_INTEGRITY_INVALID")


def _load_protected_input(materialization: Mapping[str, Any], execution: Mapping[str, Any]) -> dict[str, Any]:
    """Open only the exact recertified materialization after durable OPENED."""

    verify_materialization_integrity(materialization)
    if execution.get("materialization_hash") != materialization.get("materialization_hash"):
        raise GovernanceError("EXACT_PROTECTED_INPUT_REQUIRED")
    try:
        context_hashes = tuple(materialization["ordered_context_record_hashes"])
        scored_hashes = tuple(materialization["ordered_scored_record_hashes"])
        requested = context_hashes + scored_hashes
        events = load_causal_events_by_custody_hashes(
            release_directory=materialization["release_directory"],
            custody_runtime_root=materialization["custody_runtime_root"],
            custody_record_hashes=requested,
            exact_observable_inputs=tuple(materialization["exact_observable_inputs"]),
            expected_release_id=materialization["release_id"],
            expected_release_core_hash=materialization["release_core_hash"],
            expected_release_certificate_hash=materialization["certificate_hash"],
        )
    except Exception as error:
        raise GovernanceError("PROTECTED_INPUT_LOAD_FAILED") from error
    by_hash = {event.custody_record_hash: event for event in events}
    context_hashes = materialization["ordered_context_record_hashes"]
    scored_hashes = materialization["ordered_scored_record_hashes"]
    required = set(context_hashes) | set(scored_hashes)
    if not required <= set(by_hash):
        raise GovernanceError("EXACT_PROTECTED_INPUT_REQUIRED")
    return {
        "input_schema": "DELTAGRID_M103_PROTECTED_INPUT_V1",
        "stage": execution["stage"], "candidate_hash": execution["candidate_hash"],
        "repository_commit": execution["repository_commit"], "program_hash": execution["program_hash"],
        "materialization_hash": materialization["materialization_hash"],
        "protected_start_state": {"position": "FLAT", "cash_fraction": "1"},
        "cost_execution_hash": execution["candidate_execution_hash"],
        "deterministic_randomness": execution["deterministic_randomness"],
        "context_events": tuple(by_hash[digest] for digest in context_hashes),
        "scored_events": tuple(by_hash[digest] for digest in scored_hashes),
    }


__all__ = ["M102ResultSource", "ProtectedCustodySource"]

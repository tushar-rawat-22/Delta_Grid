"""Authoritative exact-candidate protected execution using Mission 102 primitives."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping, Sequence

from offchain.research.development_runtime.core import (
    ACCOUNTING_KERNEL_ID, DECIMAL_CONTEXT_ID, FILL_MODEL_ID,
    POSITION_EFFECTIVE_TIME_ID, TARGET_EXPOSURE_MODEL_ID,
)
from offchain.research.development_runtime.kernel import AccountingKernel, RevealedEvent
from offchain.research.development_runtime.loader import MarketEvent
from offchain.research.development_runtime.registry import production_registry

from .core import GovernanceError, canonical_hash, freeze_json


PROTECTED_EXECUTOR_ID = "DELTAGRID_M103_M102_EXACT_CANDIDATE_EXECUTOR_V1"


class _RevealCountOffsetAdapter:
    """Delegate to one warmed adapter while offsetting only its reveal count."""

    def __init__(self, underlying: Any, offset: int) -> None:
        self.underlying = underlying
        self.offset = offset

    def on_event(self, event: RevealedEvent, state: Mapping[str, Any]):
        adjusted = dict(state)
        adjusted["revealed_event_count"] = state["revealed_event_count"] + self.offset
        return self.underlying.on_event(event, MappingProxyType(adjusted))


def _resolve_candidate_runtime(candidate: Mapping[str, Any]):
    registry = production_registry()
    if registry.snapshot_hash != candidate["m102"]["registry_snapshot_hash"]:
        raise GovernanceError("PROTECTED_REGISTRY_SNAPSHOT_MISMATCH")
    try:
        family, variant = registry.resolve(
            candidate["family_id"], candidate["m94"]["declared_trial_number"],
            candidate["m94"]["fixed_trial_budget"],
        )
    except Exception as error:
        raise GovernanceError("PROTECTED_CANDIDATE_NOT_REGISTERED") from error
    if (
        family.definition_hash != candidate["family_hash"]
        or variant.variant_id != candidate["variant_id"]
        or variant.definition_hash != candidate["variant_hash"]
        or variant.core()["strategy_parameters"] != candidate["parameters"]
    ):
        raise GovernanceError("PROTECTED_CANDIDATE_RECONSTRUCTION_MISMATCH")
    execution_core = {"fee_bps": variant.fee_bps, "slippage_bps": variant.slippage_bps,
        "fill_model": FILL_MODEL_ID, "target_exposure_model": TARGET_EXPOSURE_MODEL_ID,
        "position_effective_time_model": POSITION_EFFECTIVE_TIME_ID,
        "variant_definition_hash": variant.definition_hash}
    if canonical_hash(execution_core) != candidate["execution_hash"]:
        raise GovernanceError("PROTECTED_COST_EXECUTION_MISMATCH")
    risk_core = {"initial_research_nav": variant.initial_research_nav,
        "max_gross_research_exposure": variant.max_gross_research_exposure,
        "max_net_research_exposure": variant.max_net_research_exposure,
        "per_instrument_bounds": dict(sorted(variant.per_instrument_bounds.items()))}
    if canonical_hash(risk_core) != candidate["risk_identity"]:
        raise GovernanceError("PROTECTED_RISK_BINDING_MISMATCH")
    return family, variant


def _warm_context(adapter: Any, variant: Any, events: Sequence[MarketEvent]) -> int:
    revealed_count = 0
    for event in events:
        if f"{event.stream}:{event.symbol}" not in variant.observable_inputs:
            continue
        flat = MappingProxyType({"cash": variant.initial_research_nav, "equity": variant.initial_research_nav,
            "positions": MappingProxyType({key: "0" for key in sorted(variant.tradable_instruments)}),
            "gross_exposure": "0", "net_exposure": "0", "pending_instruments": (),
            "revealed_event_count": revealed_count})
        view = RevealedEvent(event.event_id, event.stream, event.symbol, event.interval,
            event.event_time_ms, event.available_at, event.revision, event.payload)
        try:
            produced = adapter.on_event(view, flat)
        except Exception as error:
            raise GovernanceError("PROTECTED_CONTEXT_WARMING_FAILED") from error
        if not isinstance(produced, Sequence) or isinstance(produced, (str, bytes, bytearray)):
            raise GovernanceError("PROTECTED_CONTEXT_WARMING_FAILED")
        revealed_count += 1
        # Context intents are intentionally discarded. No context kernel exists,
        # therefore context cannot create fills, positions, costs, funding or PnL.
    return revealed_count


def validate_candidate_observable_scope(candidate: Mapping[str, Any], materialization: Mapping[str, Any]) -> None:
    """Metadata-only proof that the exact selected variant is fully observable."""

    _family, variant = _resolve_candidate_runtime(candidate)
    available = materialization.get("present_observable_inputs")
    if not isinstance(available, list) or not set(variant.observable_inputs) <= set(available):
        raise GovernanceError("PROTECTED_CANDIDATE_OBSERVABLE_SCOPE_INCOMPLETE")


def _one_execution(candidate: Mapping[str, Any], protected_input: Mapping[str, Any]) -> dict[str, Any]:
    family, variant = _resolve_candidate_runtime(candidate)
    context_events = protected_input["context_events"]
    scored_events = protected_input["scored_events"]
    adapter = family.adapter_factory(variant.strategy_parameters)
    context_observable_event_count = _warm_context(adapter, variant, context_events)
    try:
        ledger, metrics = AccountingKernel(
            variant, _RevealCountOffsetAdapter(adapter, context_observable_event_count)
        ).run(scored_events)
    except Exception as error:
        raise GovernanceError("PROTECTED_CANDIDATE_EXECUTION_FAILED") from error
    if metrics["initial_research_nav"] != variant.initial_research_nav:
        raise GovernanceError("PROTECTED_NON_FLAT_START")
    candidate_observable_scored_event_count = len(ledger["event_rows"])
    evidence = {"executor_id": PROTECTED_EXECUTOR_ID, "family_hash": family.definition_hash,
        "variant_hash": variant.definition_hash, "repository_commit": candidate["repository_commit"],
        "context_order_hash": canonical_hash([event.custody_record_hash for event in context_events]),
        "scored_order_hash": canonical_hash([event.custody_record_hash for event in scored_events]),
        "context_event_count": len(context_events), "scored_event_count": len(scored_events),
        "candidate_observable_context_event_count": context_observable_event_count,
        "candidate_observable_scored_event_count": candidate_observable_scored_event_count,
        "context_intents_fills_pnl_counted": False, "scored_start_state": "FLAT_CASH",
        "fill_model": FILL_MODEL_ID, "target_exposure_model": TARGET_EXPOSURE_MODEL_ID,
        "position_effective_time_model": POSITION_EFFECTIVE_TIME_ID,
        "decimal_context": DECIMAL_CONTEXT_ID, "accounting_kernel": ACCOUNTING_KERNEL_ID,
        "ledger_hash": ledger["canonical_event_ledger_hash"], "metrics_hash": canonical_hash(metrics)}
    return {"ledger": ledger, "metrics": metrics, "execution_evidence": evidence,
        "execution_evidence_hash": canonical_hash(evidence)}


def execute_protected_candidate(candidate: Mapping[str, Any], protected_input: Mapping[str, Any]) -> dict[str, Any]:
    """Execute twice and require exact equality, excluding nondeterministic engines."""

    first = freeze_json(_one_execution(candidate, protected_input))
    second = freeze_json(_one_execution(candidate, protected_input))
    if first != second:
        raise GovernanceError("NONDETERMINISTIC_PROTECTED_EXECUTION")
    return first


__all__ = ["PROTECTED_EXECUTOR_ID", "execute_protected_candidate", "validate_candidate_observable_scope"]

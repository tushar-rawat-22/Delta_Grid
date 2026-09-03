from copy import deepcopy

import pytest

from offchain.research.hypothesis_compare import (
    compare_hypothesis_specs,
    verify_hypothesis_comparison,
)
from offchain.research.hypothesis_spec import normalize_hypothesis_spec


def _payload():
    return {
        "hypothesis_id": "founder-pine-001",
        "mechanism": "momentum confirmation with volatility-defined exits",
        "signal_timing": "bar close",
        "fill_timing": "next bar",
        "position_sizing": "fixed cash risk per trade",
        "cost_model": "commission plus spread, slippage and latency stress",
        "exit_semantics": "stop and target evaluated under event-driven fill rules",
        "entry_logic": ["RSI filter", "trend state"],
        "exit_logic": ["ATR stop", "ATR target"],
        "execution_assumptions": ["no same-bar signal fill", "next-bar execution"],
        "risk_assumptions": ["cash risk stays fixed when stop distance changes"],
        "known_contradictions": ["NONE"],
        "source_refs": ["founder-supplied Pine hypothesis"],
    }


def test_identical_declarations_produce_non_authorizing_identity_evidence():
    baseline = normalize_hypothesis_spec(_payload())
    comparison = compare_hypothesis_specs(baseline, deepcopy(baseline))

    assert comparison["status"] == "IDENTICAL_DECLARATION"
    assert comparison["changed_fields"] == []
    assert comparison["deltas"] == []
    assert comparison["authority_effect"] == "NONE"
    assert comparison["research_opened"] is False
    assert comparison["quality_judgement"] == "NOT_EVALUATED"
    assert verify_hypothesis_comparison(comparison)


def test_comparison_is_deterministic_for_same_direction_and_inputs():
    baseline = normalize_hypothesis_spec(_payload())
    proposed_payload = _payload()
    proposed_payload["cost_model"] = "commission, spread and severe slippage plus latency stress"
    proposed = normalize_hypothesis_spec(proposed_payload)

    first = compare_hypothesis_specs(baseline, proposed)
    second = compare_hypothesis_specs(baseline, proposed)

    assert first == second
    assert first["comparison_sha256"] == second["comparison_sha256"]


def test_ordered_rule_change_is_preserved_as_a_real_declaration_delta():
    baseline = normalize_hypothesis_spec(_payload())
    proposed_payload = _payload()
    proposed_payload["entry_logic"] = ["trend state", "RSI filter"]
    proposed = normalize_hypothesis_spec(proposed_payload)

    comparison = compare_hypothesis_specs(baseline, proposed)

    assert comparison["changed_fields"] == ["entry_logic"]
    assert comparison["deltas"][0]["baseline"] == ["RSI filter", "trend state"]
    assert comparison["deltas"][0]["proposed"] == ["trend state", "RSI filter"]
    assert comparison["status"] == "DECLARATION_DELTA"


def test_cost_and_execution_timing_changes_are_explicit_without_ranking():
    baseline = normalize_hypothesis_spec(_payload())
    proposed_payload = _payload()
    proposed_payload["fill_timing"] = "same bar close"
    proposed_payload["cost_model"] = "commission plus spread and doubled slippage with latency stress"
    proposed = normalize_hypothesis_spec(proposed_payload)

    comparison = compare_hypothesis_specs(baseline, proposed)

    assert comparison["changed_fields"] == ["fill_timing", "cost_model"]
    assert comparison["quality_judgement"] == "NOT_EVALUATED"
    assert comparison["authority_effect"] == "NONE"
    assert comparison["research_opened"] is False


def test_distinct_hypothesis_identity_does_not_fake_an_assumption_delta():
    baseline = normalize_hypothesis_spec(_payload())
    proposed_payload = _payload()
    proposed_payload["hypothesis_id"] = "founder-pine-002"
    proposed = normalize_hypothesis_spec(proposed_payload)

    comparison = compare_hypothesis_specs(baseline, proposed)

    assert comparison["baseline_hypothesis_id"] == "founder-pine-001"
    assert comparison["proposed_hypothesis_id"] == "founder-pine-002"
    assert comparison["status"] == "IDENTICAL_DECLARATION"
    assert comparison["changed_fields"] == []


def test_tampered_input_is_rejected_before_comparison():
    baseline = normalize_hypothesis_spec(_payload())
    proposed = normalize_hypothesis_spec(_payload())
    proposed["fill_timing"] = "same bar"

    with pytest.raises(ValueError, match="proposed hypothesis specification failed"):
        compare_hypothesis_specs(baseline, proposed)


def test_authority_or_quality_escalation_invalidates_comparison():
    spec = normalize_hypothesis_spec(_payload())
    comparison = compare_hypothesis_specs(spec, spec)

    escalated = deepcopy(comparison)
    escalated["authority_effect"] = "OPEN_DEVELOPMENT"
    assert verify_hypothesis_comparison(escalated) is False

    opened = deepcopy(comparison)
    opened["research_opened"] = True
    assert verify_hypothesis_comparison(opened) is False

    ranked = deepcopy(comparison)
    ranked["quality_judgement"] = "BETTER"
    assert verify_hypothesis_comparison(ranked) is False


def test_undeclared_top_level_metadata_is_rejected_fail_closed():
    spec = normalize_hypothesis_spec(_payload())
    comparison = compare_hypothesis_specs(spec, spec)

    injected = deepcopy(comparison)
    injected["candidate_selected"] = True

    assert verify_hypothesis_comparison(injected) is False

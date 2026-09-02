from copy import deepcopy

import pytest

from offchain.research.hypothesis_preflight import (
    review_hypothesis_preflight,
    verify_hypothesis_preflight,
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
        "known_contradictions": ["original notes disagree on OR versus aligned entry semantics"],
        "source_refs": ["founder-supplied Pine hypothesis"],
    }


def test_declared_contradiction_blocks_pre_research_without_opening_authority():
    spec = normalize_hypothesis_spec(_payload())

    preflight = review_hypothesis_preflight(spec)

    assert preflight["verdict"] == "BLOCKED_PRE_RESEARCH"
    assert preflight["authority_effect"] == "NONE"
    assert preflight["research_opened"] is False
    assert preflight["hypothesis_spec_sha256"] == spec["spec_sha256"]
    assert preflight["findings"] == [
        {
            "code": "DECLARED_CONTRADICTION",
            "severity": "BLOCKER",
            "detail": "original notes disagree on OR versus aligned entry semantics",
        }
    ]
    assert verify_hypothesis_preflight(preflight)


def test_missing_cost_dimensions_require_review_but_do_not_claim_a_defect():
    payload = _payload()
    payload["known_contradictions"] = ["none declared"]
    payload["cost_model"] = "commission only"
    spec = normalize_hypothesis_spec(payload)

    preflight = review_hypothesis_preflight(spec)

    assert preflight["verdict"] == "BLOCKED_PRE_RESEARCH"
    assert [finding["code"] for finding in preflight["findings"]] == [
        "DECLARED_CONTRADICTION",
        "COST_MODEL_DIMENSIONS_UNSTATED",
    ]
    assert "spread, slippage, latency" in preflight["findings"][1]["detail"]


def test_clean_metadata_reaches_authority_review_only_not_research():
    payload = _payload()
    payload["known_contradictions"] = []
    spec = normalize_hypothesis_spec(payload)

    with pytest.raises(ValueError, match="known_contradictions must not be empty"):
        normalize_hypothesis_spec(payload)

    # The normalized-spec contract intentionally requires a non-empty declaration.
    # A caller must therefore state the absence of known contradictions explicitly.
    payload["known_contradictions"] = ["none known after specification review"]
    spec = normalize_hypothesis_spec(payload)
    preflight = review_hypothesis_preflight(spec)

    assert preflight["verdict"] == "BLOCKED_PRE_RESEARCH"
    assert preflight["research_opened"] is False


def test_identical_signal_and_fill_timing_is_review_evidence():
    payload = _payload()
    payload["known_contradictions"] = ["none known after specification review"]
    payload["signal_timing"] = "bar close"
    payload["fill_timing"] = "bar close"
    spec = normalize_hypothesis_spec(payload)

    preflight = review_hypothesis_preflight(spec)

    assert any(
        finding["code"] == "SIGNAL_FILL_TIMING_IDENTICAL"
        and finding["severity"] == "REVIEW"
        for finding in preflight["findings"]
    )


def test_tampering_or_authority_escalation_invalidates_preflight():
    spec = normalize_hypothesis_spec(_payload())
    preflight = review_hypothesis_preflight(spec)

    tampered = deepcopy(preflight)
    tampered["research_opened"] = True
    assert verify_hypothesis_preflight(tampered) is False

    escalated = deepcopy(preflight)
    escalated["authority_effect"] = "OPEN_DEVELOPMENT"
    assert verify_hypothesis_preflight(escalated) is False


def test_corrupted_spec_is_rejected_before_review():
    spec = normalize_hypothesis_spec(_payload())
    spec["fill_timing"] = "same bar"

    with pytest.raises(ValueError, match="integrity verification"):
        review_hypothesis_preflight(spec)

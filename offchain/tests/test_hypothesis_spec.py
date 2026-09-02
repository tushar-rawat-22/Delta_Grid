from copy import deepcopy

import pytest

from offchain.research.hypothesis_spec import normalize_hypothesis_spec, verify_hypothesis_spec


def _payload():
    return {
        "hypothesis_id": " founder-pine-001 ",
        "mechanism": " momentum confirmation with volatility-defined exits ",
        "signal_timing": "bar close",
        "fill_timing": "next bar",
        "position_sizing": "fixed cash risk per trade",
        "cost_model": "commission plus spread, slippage and latency stress",
        "exit_semantics": "stop and target evaluated under event-driven fill rules",
        "entry_logic": ["RSI filter", "trend state", "RSI filter"],
        "exit_logic": ["ATR stop", "ATR target"],
        "execution_assumptions": ["no same-bar signal fill", "next-bar execution"],
        "risk_assumptions": ["cash risk stays fixed when stop distance changes"],
        "known_contradictions": ["bullish momentum direction differs across supplied revisions"],
        "source_refs": ["docs/research-intake/2026-09-02-pine-strategy-hypotheses.md"],
    }


def test_normalization_is_deterministic_and_non_authorizing():
    first = normalize_hypothesis_spec(_payload())
    second = normalize_hypothesis_spec(dict(reversed(list(_payload().items()))))

    assert first == second
    assert first["status"] == "UNVERIFIED_HYPOTHESIS"
    assert first["authority_effect"] == "NONE"
    assert len(first["spec_sha256"]) == 64
    assert verify_hypothesis_spec(first)


def test_normalization_deduplicates_and_sorts_metadata_lists():
    normalized = normalize_hypothesis_spec(_payload())

    assert normalized["entry_logic"] == ["RSI filter", "trend state"]
    assert normalized["exit_logic"] == ["ATR stop", "ATR target"]


def test_missing_execution_semantics_fail_closed():
    payload = _payload()
    del payload["fill_timing"]

    with pytest.raises(ValueError, match="missing hypothesis fields: fill_timing"):
        normalize_hypothesis_spec(payload)


def test_unknown_fields_cannot_smuggle_results_or_authority():
    payload = _payload()
    payload["paper_trading_authorized"] = True

    with pytest.raises(ValueError, match="unknown hypothesis fields: paper_trading_authorized"):
        normalize_hypothesis_spec(payload)


def test_empty_required_lists_fail_closed():
    payload = _payload()
    payload["known_contradictions"] = []

    with pytest.raises(ValueError, match="known_contradictions must not be empty"):
        normalize_hypothesis_spec(payload)


def test_tampering_breaks_hash_verification():
    normalized = normalize_hypothesis_spec(_payload())
    tampered = deepcopy(normalized)
    tampered["fill_timing"] = "same bar"

    assert not verify_hypothesis_spec(tampered)

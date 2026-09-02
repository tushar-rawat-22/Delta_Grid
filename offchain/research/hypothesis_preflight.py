"""Deterministic, non-authorizing preflight review for strategy hypotheses.

The preflight consumes an intact normalized hypothesis specification and emits
review evidence only. It never opens research, evaluates market data, executes a
strategy, or changes Mission/RAB authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from offchain.research.hypothesis_spec import AUTHORITY_EFFECT, STATUS, verify_hypothesis_spec

PREFLIGHT_VERSION = 1
PREFLIGHT_AUTHORITY_EFFECT = "NONE"
NO_KNOWN_CONTRADICTIONS = "NONE"

_COST_DIMENSIONS = {
    "commission": ("commission", "fee"),
    "spread": ("spread",),
    "slippage": ("slippage",),
    "latency": ("latency",),
}


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(term in lowered for term in terms)


def _finding(code: str, severity: str, detail: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "detail": detail}


def review_hypothesis_preflight(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Return deterministic pre-research review evidence for ``spec``.

    ``known_contradictions`` remains mandatory in the normalized specification.
    The exact value ``NONE`` is the only declaration that means no contradiction
    is currently known; descriptive text is treated as an actual blocker. Missing
    common cost dimensions require review but do not pretend to prove a modelling
    defect. Even a clean result grants no research authority.
    """

    if not verify_hypothesis_spec(spec):
        raise ValueError("hypothesis specification failed integrity verification")
    if spec.get("status") != STATUS or spec.get("authority_effect") != AUTHORITY_EFFECT:
        raise ValueError("hypothesis specification is not non-authorizing")

    contradictions = spec["known_contradictions"]
    has_none_sentinel = NO_KNOWN_CONTRADICTIONS in contradictions
    if has_none_sentinel and len(contradictions) != 1:
        raise ValueError("NONE cannot be combined with declared contradictions")

    findings: list[dict[str, str]] = []
    for contradiction in contradictions:
        if contradiction == NO_KNOWN_CONTRADICTIONS:
            continue
        findings.append(_finding("DECLARED_CONTRADICTION", "BLOCKER", contradiction))

    cost_model = spec["cost_model"]
    missing_cost_dimensions = [
        dimension
        for dimension, terms in _COST_DIMENSIONS.items()
        if not _contains_any(cost_model, terms)
    ]
    if missing_cost_dimensions:
        findings.append(
            _finding(
                "COST_MODEL_DIMENSIONS_UNSTATED",
                "REVIEW",
                "Common cost dimensions not explicitly stated: "
                + ", ".join(missing_cost_dimensions),
            )
        )

    if spec["signal_timing"].casefold() == spec["fill_timing"].casefold():
        findings.append(
            _finding(
                "SIGNAL_FILL_TIMING_IDENTICAL",
                "REVIEW",
                "Signal timing and fill timing are identical; confirm same-event execution is intentional.",
            )
        )

    if any(finding["severity"] == "BLOCKER" for finding in findings):
        verdict = "BLOCKED_PRE_RESEARCH"
    elif findings:
        verdict = "REVIEW_REQUIRED"
    else:
        verdict = "READY_FOR_AUTHORITY_REVIEW"

    body: dict[str, Any] = {
        "preflight_version": PREFLIGHT_VERSION,
        "hypothesis_id": spec["hypothesis_id"],
        "hypothesis_spec_sha256": spec["spec_sha256"],
        "verdict": verdict,
        "findings": findings,
        "authority_effect": PREFLIGHT_AUTHORITY_EFFECT,
        "research_opened": False,
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    body["preflight_sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return body


def verify_hypothesis_preflight(preflight: Mapping[str, Any]) -> bool:
    """Verify deterministic preflight integrity and its fail-closed authority fields."""

    if not isinstance(preflight, Mapping):
        return False
    supplied_hash = preflight.get("preflight_sha256")
    if not isinstance(supplied_hash, str) or len(supplied_hash) != 64:
        return False
    body = dict(preflight)
    body.pop("preflight_sha256", None)
    if body.get("authority_effect") != PREFLIGHT_AUTHORITY_EFFECT:
        return False
    if body.get("research_opened") is not False:
        return False
    if body.get("verdict") not in {
        "BLOCKED_PRE_RESEARCH",
        "REVIEW_REQUIRED",
        "READY_FOR_AUTHORITY_REVIEW",
    }:
        return False
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    expected = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return supplied_hash == expected

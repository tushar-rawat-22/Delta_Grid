"""Deterministic, non-authorizing comparison of hypothesis declarations.

This module compares two intact normalized hypothesis specifications as metadata.
It does not score strategy quality, inspect market data, rank candidates, execute
research, or change Mission/RAB authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from offchain.research.hypothesis_spec import verify_hypothesis_spec

COMPARISON_VERSION = 1
AUTHORITY_EFFECT = "NONE"

_COMPARE_FIELDS = (
    "mechanism",
    "signal_timing",
    "fill_timing",
    "position_sizing",
    "cost_model",
    "exit_semantics",
    "entry_logic",
    "exit_logic",
    "execution_assumptions",
    "risk_assumptions",
    "known_contradictions",
    "source_refs",
)
_ALLOWED_STATUSES = {"IDENTICAL_DECLARATION", "DECLARATION_DELTA"}


def _digest(body: Mapping[str, Any]) -> str:
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compare_hypothesis_specs(
    baseline: Mapping[str, Any],
    proposed: Mapping[str, Any],
) -> dict[str, Any]:
    """Return hash-addressed declaration deltas without evaluating either hypothesis."""

    if not verify_hypothesis_spec(baseline):
        raise ValueError("baseline hypothesis specification failed integrity verification")
    if not verify_hypothesis_spec(proposed):
        raise ValueError("proposed hypothesis specification failed integrity verification")

    deltas: list[dict[str, Any]] = []
    for field in _COMPARE_FIELDS:
        if baseline[field] != proposed[field]:
            deltas.append(
                {
                    "field": field,
                    "baseline": baseline[field],
                    "proposed": proposed[field],
                }
            )

    body: dict[str, Any] = {
        "comparison_version": COMPARISON_VERSION,
        "baseline_hypothesis_id": baseline["hypothesis_id"],
        "baseline_spec_sha256": baseline["spec_sha256"],
        "proposed_hypothesis_id": proposed["hypothesis_id"],
        "proposed_spec_sha256": proposed["spec_sha256"],
        "status": "DECLARATION_DELTA" if deltas else "IDENTICAL_DECLARATION",
        "changed_fields": [delta["field"] for delta in deltas],
        "deltas": deltas,
        "authority_effect": AUTHORITY_EFFECT,
        "research_opened": False,
        "quality_judgement": "NOT_EVALUATED",
    }
    body["comparison_sha256"] = _digest(body)
    return body


def verify_hypothesis_comparison(comparison: Mapping[str, Any]) -> bool:
    """Verify comparison integrity and fail-closed non-authorizing semantics."""

    if not isinstance(comparison, Mapping):
        return False
    supplied_hash = comparison.get("comparison_sha256")
    if not isinstance(supplied_hash, str) or len(supplied_hash) != 64:
        return False

    body = dict(comparison)
    body.pop("comparison_sha256", None)
    if body.get("comparison_version") != COMPARISON_VERSION:
        return False
    if body.get("authority_effect") != AUTHORITY_EFFECT:
        return False
    if body.get("research_opened") is not False:
        return False
    if body.get("quality_judgement") != "NOT_EVALUATED":
        return False
    if body.get("status") not in _ALLOWED_STATUSES:
        return False

    changed_fields = body.get("changed_fields")
    deltas = body.get("deltas")
    if not isinstance(changed_fields, list) or not isinstance(deltas, list):
        return False
    if any(field not in _COMPARE_FIELDS for field in changed_fields):
        return False
    if len(changed_fields) != len(set(changed_fields)):
        return False
    if len(deltas) != len(changed_fields):
        return False
    if [delta.get("field") for delta in deltas if isinstance(delta, Mapping)] != changed_fields:
        return False
    if any(
        not isinstance(delta, Mapping)
        or set(delta) != {"field", "baseline", "proposed"}
        or delta["baseline"] == delta["proposed"]
        for delta in deltas
    ):
        return False
    expected_status = "DECLARATION_DELTA" if deltas else "IDENTICAL_DECLARATION"
    if body["status"] != expected_status:
        return False

    for key in (
        "baseline_hypothesis_id",
        "baseline_spec_sha256",
        "proposed_hypothesis_id",
        "proposed_spec_sha256",
    ):
        if not isinstance(body.get(key), str) or not body[key]:
            return False
    if len(body["baseline_spec_sha256"]) != 64 or len(body["proposed_spec_sha256"]) != 64:
        return False

    return supplied_hash == _digest(body)

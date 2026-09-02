"""Deterministic, non-authorizing normalization for research hypotheses.

This module deliberately stops before research execution. It converts an
already-supplied strategy idea into a stable metadata contract so contradictory
or underspecified assumptions can be rejected before any governed research
stage is opened.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


STATUS = "UNVERIFIED_HYPOTHESIS"
AUTHORITY_EFFECT = "NONE"
SPEC_VERSION = 1

_REQUIRED_TEXT_FIELDS = (
    "hypothesis_id",
    "mechanism",
    "signal_timing",
    "fill_timing",
    "position_sizing",
    "cost_model",
    "exit_semantics",
)
_REQUIRED_LIST_FIELDS = (
    "entry_logic",
    "exit_logic",
    "execution_assumptions",
    "risk_assumptions",
    "known_contradictions",
    "source_refs",
)
_ALLOWED_FIELDS = frozenset(_REQUIRED_TEXT_FIELDS + _REQUIRED_LIST_FIELDS)


def _clean_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return " ".join(value.split())


def _clean_text_list(value: Any, field: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a sequence of non-empty strings")
    cleaned = [_clean_text(item, field) for item in value]
    if not cleaned:
        raise ValueError(f"{field} must not be empty")
    return list(dict.fromkeys(cleaned))


def normalize_hypothesis_spec(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a canonical, hash-addressed hypothesis metadata contract.

    Unknown fields are rejected so executable code, credentials, results or
    authority flags cannot silently enter this pre-research contract. The
    output always carries ``authority_effect=NONE`` and never represents
    permission to run development, validation, holdout, paper or live work.
    List ordering is preserved because entry/exit order may be semantic.
    """

    if not isinstance(payload, Mapping):
        raise ValueError("hypothesis payload must be a mapping")

    unknown = sorted(set(payload) - _ALLOWED_FIELDS)
    missing = sorted(_ALLOWED_FIELDS - set(payload))
    if unknown:
        raise ValueError(f"unknown hypothesis fields: {', '.join(unknown)}")
    if missing:
        raise ValueError(f"missing hypothesis fields: {', '.join(missing)}")

    canonical: dict[str, Any] = {
        "spec_version": SPEC_VERSION,
        "status": STATUS,
        "authority_effect": AUTHORITY_EFFECT,
    }
    for field in _REQUIRED_TEXT_FIELDS:
        canonical[field] = _clean_text(payload[field], field)
    for field in _REQUIRED_LIST_FIELDS:
        canonical[field] = _clean_text_list(payload[field], field)

    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    canonical["spec_sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return canonical


def verify_hypothesis_spec(spec: Mapping[str, Any]) -> bool:
    """Verify that a normalized specification is intact and non-authorizing."""

    if not isinstance(spec, Mapping):
        return False
    supplied_hash = spec.get("spec_sha256")
    if not isinstance(supplied_hash, str) or len(supplied_hash) != 64:
        return False
    body = dict(spec)
    body.pop("spec_sha256", None)
    if body.get("status") != STATUS or body.get("authority_effect") != AUTHORITY_EFFECT:
        return False
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    expected = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return supplied_hash == expected

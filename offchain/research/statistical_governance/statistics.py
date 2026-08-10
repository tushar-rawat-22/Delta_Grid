"""Exact deterministic statistical primitives for Mission 103."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from typing import Any, Iterable, Mapping

from .core import GovernanceError, canonical_hash, freeze_json, require_hash, require_identifier


NULL_SEED_DOMAIN = b"DELTAGRID_M103_NULL_SEED_V1\x00"
PRNG_ID = "SHA256_COUNTER_V1"


def as_fraction(value: Any, field: str = "probability") -> Fraction:
    if isinstance(value, Fraction):
        result = value
    elif type(value) is str:
        try:
            if value.count("/") == 1:
                numerator, denominator = value.split("/", 1)
                if not numerator.isdigit() or not denominator.isdigit() or int(denominator) == 0:
                    raise ValueError
                result = Fraction(int(numerator), int(denominator))
            else:
                result = Fraction(Decimal(value))
        except Exception as error:
            raise GovernanceError("PROBABILITY_INVALID", field) from error
    elif type(value) is int:
        result = Fraction(value)
    else:
        raise GovernanceError("BINARY_FLOAT_PROBABILITY_FORBIDDEN", field)
    if result < 0 or result > 1:
        raise GovernanceError("PROBABILITY_INVALID", field)
    return result


def fraction_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def minimum_repetitions(m: int, alpha: str | Fraction) -> int:
    if type(m) is not int or m < 1 or m > 1_000_000:
        raise GovernanceError("MULTIPLICITY_INVALID")
    probability = as_fraction(alpha, "alpha")
    if probability <= 0:
        raise GovernanceError("ALPHA_INVALID")
    ratio = Fraction(m, 1) / probability
    ceiling = -(-ratio.numerator // ratio.denominator)
    return max(5000, ceiling - 1)


def validate_monte_carlo_resolution(m: int, alpha: str | Fraction, repetitions: int) -> int:
    if type(repetitions) is not int or repetitions < 1 or repetitions > 100_000_000:
        raise GovernanceError("NULL_REPETITIONS_INVALID")
    required = minimum_repetitions(m, alpha)
    if repetitions < required:
        raise GovernanceError("MONTE_CARLO_UNDER_RESOLVED")
    return required


def empirical_p_value(*, favorable_count: int, repetitions: int) -> Fraction:
    if type(repetitions) is not int or repetitions < 1 or type(favorable_count) is not int or not 0 <= favorable_count <= repetitions:
        raise GovernanceError("EMPIRICAL_NULL_COUNT_INVALID")
    return Fraction(1 + favorable_count, repetitions + 1)


def empirical_one_sided(observed: str, null_outcomes: Iterable[str], *, direction: str) -> Fraction:
    try:
        observed_value = Decimal(observed)
        values = [Decimal(item) for item in null_outcomes]
    except Exception as error:
        raise GovernanceError("NULL_STATISTIC_INVALID") from error
    if not observed_value.is_finite() or not values or any(not item.is_finite() for item in values):
        raise GovernanceError("NULL_STATISTIC_INVALID")
    if direction == "GREATER":
        count = sum(item >= observed_value for item in values)
    elif direction == "LESS":
        count = sum(item <= observed_value for item in values)
    else:
        raise GovernanceError("STATISTIC_DIRECTION_INVALID")
    return empirical_p_value(favorable_count=count, repetitions=len(values))


def holm_step_down(p_values: Mapping[str, Any], *, alpha: str | Fraction) -> dict[str, Any]:
    if not isinstance(p_values, Mapping) or not p_values:
        raise GovernanceError("P_VALUE_FAMILY_INVALID")
    if len(p_values) > 1_000_000:
        raise GovernanceError("MULTIPLICITY_INVALID")
    parsed: dict[str, Fraction] = {}
    for hypothesis_id, value in p_values.items():
        require_identifier(hypothesis_id, "hypothesis_id")
        if hypothesis_id in parsed:
            raise GovernanceError("P_VALUE_FAMILY_INVALID")
        parsed[hypothesis_id] = as_fraction(value, "p_value")
    family_alpha = as_fraction(alpha, "alpha")
    if family_alpha <= 0:
        raise GovernanceError("ALPHA_INVALID")
    ordered = sorted(parsed, key=lambda key: (parsed[key], key))
    m = len(ordered)
    running_adjusted = Fraction(0)
    still_rejecting = True
    rows: list[dict[str, Any]] = []
    for index, hypothesis_id in enumerate(ordered):
        factor = m - index
        raw = parsed[hypothesis_id]
        threshold = family_alpha / factor
        running_adjusted = max(running_adjusted, min(Fraction(1), raw * factor))
        rejected = bool(still_rejecting and raw <= threshold)
        if not rejected:
            still_rejecting = False
        rows.append({
            "hypothesis_id": hypothesis_id,
            "rank": index + 1,
            "raw_p_value": fraction_text(raw),
            "holm_threshold": fraction_text(threshold),
            "holm_adjusted_p_value": fraction_text(running_adjusted),
            "rejected": rejected,
        })
    core = {"method": "HOLM_STEP_DOWN_FWER_PROGRAM_WIDE", "m": m, "alpha": fraction_text(family_alpha), "ordered_evidence": rows}
    return {**core, "canonical_holm_hash": canonical_hash(core)}


def derive_null_seed(
    *, founder_nonce_hex: str, proposal_hash: str, program_hash: str,
    hypothesis_hash: str, family_hash: str, variant_hash: str,
    adapter_hash: str, prng_algorithm_version: str,
) -> int:
    if type(founder_nonce_hex) is not str or len(founder_nonce_hex) != 64:
        raise GovernanceError("NONCE_INVALID")
    try:
        nonce = bytes.fromhex(founder_nonce_hex)
    except ValueError as error:
        raise GovernanceError("NONCE_INVALID") from error
    if len(nonce) != 32:
        raise GovernanceError("NONCE_INVALID")
    for field, value in (
        ("proposal_hash", proposal_hash), ("program_hash", program_hash),
        ("hypothesis_hash", hypothesis_hash), ("family_hash", family_hash),
        ("variant_hash", variant_hash), ("adapter_hash", adapter_hash),
    ):
        require_hash(value, field)
    require_identifier(prng_algorithm_version, "prng_algorithm_version")
    core = {
        "proposal_hash": proposal_hash, "program_hash": program_hash,
        "hypothesis_hash": hypothesis_hash, "family_hash": family_hash,
        "variant_hash": variant_hash, "adapter_hash": adapter_hash,
        "prng_algorithm_version": prng_algorithm_version,
    }
    import hashlib
    # The seed preimage is exactly domain || nonce || UTF-8 canonical JSON.
    # It deliberately does not hash the JSON core before constructing the
    # preimage, so the executable definition matches the contract literally.
    from .core import canonical_bytes
    payload = NULL_SEED_DOMAIN + nonce + canonical_bytes(freeze_json(core))
    return int.from_bytes(hashlib.sha256(payload).digest(), "big")


class SHA256CounterPRNG:
    """Small specified deterministic primitive; not a cryptographic entropy source."""

    def __init__(self, seed: int) -> None:
        if type(seed) is not int or not 0 <= seed < 2**256:
            raise GovernanceError("PRNG_SEED_INVALID")
        self._seed = seed.to_bytes(32, "big")
        self._counter = 0

    def next_u256(self) -> int:
        if self._counter >= 2**128:
            raise GovernanceError("PRNG_COUNTER_EXHAUSTED")
        import hashlib
        digest = hashlib.sha256(b"DELTAGRID_M103_SHA256_COUNTER_V1\x00" + self._seed + self._counter.to_bytes(16, "big")).digest()
        self._counter += 1
        return int.from_bytes(digest, "big")

    def randbelow(self, bound: int) -> int:
        if type(bound) is not int or not 1 <= bound <= 2**256:
            raise GovernanceError("PRNG_BOUND_INVALID")
        limit = 2**256 - (2**256 % bound)
        while True:
            value = self.next_u256()
            if value < limit:
                return value % bound


def build_randomization_plan(seed: int, repetitions: int) -> dict[str, Any]:
    """Build the M103-owned immutable ordinal/u256 randomization transcript."""

    if type(repetitions) is not int or not 1 <= repetitions <= 10_000:
        raise GovernanceError("NULL_REPETITIONS_RUNTIME_LIMIT")
    generator = SHA256CounterPRNG(seed)
    entries = [
        {"ordinal": ordinal, "draw_u256_hex": f"{generator.next_u256():064x}"}
        for ordinal in range(repetitions)
    ]
    definition = {"plan_schema": "DELTAGRID_M103_RANDOMIZATION_PLAN_V1",
        "prng": PRNG_ID, "binding": "ORDINAL_AND_U256_DRAW_V1", "repetitions": repetitions}
    core = {"definition": definition, "entries": entries}
    return {**core, "plan_commitment": canonical_hash(core)}


__all__ = [
    "NULL_SEED_DOMAIN", "PRNG_ID", "as_fraction", "fraction_text",
    "minimum_repetitions", "validate_monte_carlo_resolution", "empirical_p_value",
    "empirical_one_sided", "holm_step_down", "derive_null_seed", "SHA256CounterPRNG",
    "build_randomization_plan",
]

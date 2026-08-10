"""Mission 102 identities and fail-closed deterministic primitives."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import (
    Clamped,
    Context,
    Decimal,
    DivisionByZero,
    FloatOperation,
    Inexact,
    InvalidOperation,
    Overflow,
    ROUND_HALF_EVEN,
    Rounded,
    Subnormal,
    Underflow,
    localcontext,
)
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from offchain.market_data_acquisition.core import (
    canonical_hash,
    canonical_json,
    parse_utc,
    require_commit,
    require_hash,
    require_identifier,
    strict_json_load,
)
from offchain.research.reopening.core import get_repository_observation


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
AUTONOMY_V4_PATH = REPOSITORY_ROOT / "contracts" / "DELTAGRID_AUTONOMY_CONSTITUTION_V4.json"
MISSION102_PATH = REPOSITORY_ROOT / "contracts" / "DELTAGRID_DEVELOPMENT_RESEARCH_RUNTIME_V1.json"
AUTONOMY_V4_ID = "deltagrid-autonomy-constitution-v4"
AUTONOMY_V4_HASH = "1ffb9b3fcbf5adae63727a136e2c33a952e646fc1362d1e8dfd9b5482851b9e2"
MISSION102_ID = "deltagrid-development-research-runtime-v1"
MISSION102_HASH = "9bd79130edab59392a5a7f05225de2fbb4ad2b3c84476ddc5be095cffc6851da"
MISSION101_ID = "deltagrid-research-reopening-governance-v1"
MISSION101_HASH = "067e85fa1eb35b4fa81cac40fd036938df300d2b7da2774b163f1e306ce53ce7"
MISSION94_ID = "deltagrid-research-admission-core-v1"
MISSION94_HASH = "e4070b52a0f2dbc8ce34ea00d0a732c2aed25c9c21e5acfccc3f9d791dba6193"
BASE_COMMIT = "38417b1ceab82b381d2535ff146a7e6a843c3815"
DEVELOPMENT_STAGE = "MISSION_102_REAL_MARKET_DEVELOPMENT_RESULT_EXECUTION"
M101_ADMISSION_STAGE = "MISSION_101_DEVELOPMENT_ADMISSION"
DATA_CLASS = "REAL_MARKET_DEVELOPMENT"
EXECUTION_RUNTIME_ID = "DELTAGRID_M102_DEVELOPMENT_EXECUTION_RUNTIME_V1"
SECURE_BINDING_ID = "DELTAGRID_M102_M101_SECURE_BINDING_V1"
CONSUMED_PERMIT_VERIFIER_ID = "DELTAGRID_M102_CONSUMED_PERMIT_VERIFIER_V1"
AUTHORITY_SNAPSHOT_ID = "DELTAGRID_M102_AUTHORITY_SNAPSHOT_V1"
AUTHORITY_HISTORICAL_PROOF_ID = "DELTAGRID_M102_AUTHORITY_HISTORICAL_PROOF_V1"
M94_BINDING_ID = "DELTAGRID_M102_M94_BINDING_V1"
CROSS_STORE_GATE_ID = "DELTAGRID_M102_ORDERED_TWO_DATABASE_GATE_V1"
EXECUTION_SPEC_ID = "DELTAGRID_M102_EXECUTION_SPEC_V1"
CAUSAL_LOADER_ID = "DELTAGRID_M102_CAUSAL_SELECTED_VALUE_LOADER_V1"
EVENT_ORDERING_ID = "AVAILABLE_AT_THEN_CUSTODY_RECORD_HASH_V1"
INSTRUMENT_IDENTITY_ID = "STREAM_COLON_SYMBOL_V1"
REGISTRY_SNAPSHOT_ID = "DELTAGRID_M102_EXPERIMENT_REGISTRY_SNAPSHOT_V1"
FAMILY_DEFINITION_ID = "DELTAGRID_M102_FAMILY_DEFINITION_V1"
VARIANT_DEFINITION_ID = "DELTAGRID_M102_VARIANT_DEFINITION_V1"
INTENT_SCHEMA_ID = "DELTAGRID_M102_TARGET_EXPOSURE_INTENT_V1"
FILL_MODEL_ID = "NEXT_ELIGIBLE_BAR_CLOSE_V1"
TARGET_EXPOSURE_MODEL_ID = "TARGET_NOTIONAL_AT_BENCHMARK_CLOSE_V1"
POSITION_EFFECTIVE_TIME_ID = "MAX_BENCHMARK_CLOSE_AND_FILL_EVIDENCE_AVAILABLE_V1"
DECIMAL_CONTEXT_ID = "DELTAGRID_M102_DECIMAL_CONTEXT_V1"
ACCOUNTING_KERNEL_ID = "DELTAGRID_M102_DECIMAL_ACCOUNTING_KERNEL_V1"
EVENT_LEDGER_ID = "DELTAGRID_M102_EVENT_LEDGER_V1"
RESULT_BUNDLE_ID = "DELTAGRID_M102_RESULT_BUNDLE_V1"
VERIFIER_ID = "DELTAGRID_M102_INDEPENDENT_RESULT_VERIFIER_V1"
FINALIZER_ID = "DELTAGRID_M102_M94_FINALIZER_V1"
ACK_INITIALIZE_RESULTS = "INITIALIZE_M102_DEVELOPMENT_RESULTS_RUNTIME"
ACK_EXECUTE = "EXECUTE_M102_DEVELOPMENT_TRIAL"
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_RESULT_BYTES = 64 * 1024 * 1024


def m102_decimal_context() -> Context:
    """Construct a fresh exact V1 arithmetic context for one operation/run."""

    context = Context(
        prec=50,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
    )
    for signal in (
        Clamped, InvalidOperation, DivisionByZero, Inexact, Rounded,
        Subnormal, Overflow, Underflow, FloatOperation,
    ):
        context.traps[signal] = signal in {
            InvalidOperation, DivisionByZero, Overflow, FloatOperation,
        }
    context.clear_flags()
    return context


class DevelopmentRuntimeError(RuntimeError):
    """Fail-closed Mission 102 exception carrying a stable reason token."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def contract_hash(value: Mapping[str, Any]) -> str:
    core = dict(value)
    core.pop("contract_hash_sha256", None)
    return canonical_hash(core)


def _load_contract(path: Path, expected_id: str, expected_hash: str) -> dict[str, Any]:
    value = strict_json_load(path)
    if not isinstance(value, dict) or value.get("contract_id") != expected_id:
        raise DevelopmentRuntimeError("CONTRACT_ID_MISMATCH", path.name)
    if value.get("contract_hash_sha256") != expected_hash or contract_hash(value) != expected_hash:
        raise DevelopmentRuntimeError("CONTRACT_HASH_MISMATCH", path.name)
    return value


def load_contracts() -> tuple[dict[str, Any], dict[str, Any]]:
    autonomy = _load_contract(AUTONOMY_V4_PATH, AUTONOMY_V4_ID, AUTONOMY_V4_HASH)
    mission = _load_contract(MISSION102_PATH, MISSION102_ID, MISSION102_HASH)
    if (
        autonomy.get("parent_constitution_id") != "deltagrid-autonomy-constitution-v3"
        or autonomy.get("parent_constitution_hash_sha256") != "cdd768ee04693845f9c1dcc4af3a03bad03a62685b24681d1ff8426230c84743"
        or mission.get("autonomy_constitution_id") != AUTONOMY_V4_ID
        or mission.get("autonomy_constitution_hash_sha256") != AUTONOMY_V4_HASH
        or mission.get("mission101_contract_id") != MISSION101_ID
        or mission.get("mission101_contract_hash_sha256") != MISSION101_HASH
        or mission.get("mission94_contract_id") != MISSION94_ID
        or mission.get("mission94_contract_hash_sha256") != MISSION94_HASH
        or mission.get("base_commit") != BASE_COMMIT
    ):
        raise DevelopmentRuntimeError("CONTRACT_LINEAGE_MISMATCH")
    authority = mission.get("authority")
    if not isinstance(authority, dict) or authority.get("real_market_development_result_execution") is not True:
        raise DevelopmentRuntimeError("CONTRACT_AUTHORITY_INVALID")
    forbidden = {
        "validation", "holdout", "model_or_ml", "candidate_promotion", "paper",
        "live", "exchange_access", "credential_access", "signed_exchange_requests",
        "orders", "capital", "self_authorization",
    }
    if any(authority.get(name) is not False for name in forbidden):
        raise DevelopmentRuntimeError("CONTRACT_AUTHORITY_INVALID")
    return autonomy, mission


def decimal_text(value: Any, field: str, *, nonnegative: bool = False, positive: bool = False) -> str:
    if type(value) is not str or not value or len(value) > 128:
        raise DevelopmentRuntimeError("DECIMAL_INVALID", field)
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise DevelopmentRuntimeError("DECIMAL_INVALID", field) from error
    if not number.is_finite() or (nonnegative and number < 0) or (positive and number <= 0):
        raise DevelopmentRuntimeError("DECIMAL_INVALID", field)
    return value


def canonical_decimal(value: Decimal) -> str:
    if type(value) is not Decimal or not value.is_finite():
        raise DevelopmentRuntimeError("ACCOUNTING_OVERFLOW")
    # Formatting the exact coefficient avoids Decimal.normalize(), whose
    # rounding behavior inherits the ambient process context.
    with localcontext(m102_decimal_context()) as context:
        context.clear_flags()
        if value == 0:
            return "0"
        result = format(value, "f")
        return result.rstrip("0").rstrip(".") if "." in result else result


def trusted_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def private_absolute_root(value: str | Path, *, must_exist: bool, label: str) -> Path:
    lexical = Path(value).expanduser()
    if not lexical.is_absolute():
        raise DevelopmentRuntimeError(f"{label}_NOT_ABSOLUTE")
    current = lexical
    while True:
        if current.is_symlink():
            raise DevelopmentRuntimeError(f"{label}_SYMLINK")
        if current == current.parent:
            break
        current = current.parent
    resolved = lexical.resolve(strict=False)
    try:
        resolved.relative_to(REPOSITORY_ROOT.resolve(strict=True))
    except ValueError:
        pass
    else:
        raise DevelopmentRuntimeError(f"{label}_INSIDE_REPOSITORY")
    if must_exist:
        if not resolved.is_dir() or resolved.is_symlink():
            raise DevelopmentRuntimeError(f"{label}_INVALID")
        if stat.S_IMODE(resolved.stat().st_mode) != 0o700:
            raise DevelopmentRuntimeError(f"{label}_MODE_INVALID")
    return resolved


def write_exclusive(path: Path, raw: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, 0o600, follow_symlinks=False)


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def read_canonical(path: Path, *, maximum_bytes: int = MAX_RESULT_BYTES) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum_bytes:
        raise DevelopmentRuntimeError("ARTIFACT_FILE_INVALID", path.name)
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise DevelopmentRuntimeError("ARTIFACT_MODE_INVALID", path.name)
    raw = path.read_bytes()
    value = strict_json_load(raw, maximum_bytes=maximum_bytes)
    if not isinstance(value, dict) or canonical_bytes(value) != raw:
        raise DevelopmentRuntimeError("ARTIFACT_NONCANONICAL", path.name)
    return value, raw


__all__ = [
    "DevelopmentRuntimeError", "canonical_hash", "canonical_json", "parse_utc",
    "require_commit", "require_hash", "require_identifier", "strict_json_load",
    "get_repository_observation",
]

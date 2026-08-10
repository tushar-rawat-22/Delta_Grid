"""Mission 103 identities, strict values, paths, and canonical serialization."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any, Mapping

from offchain.market_data_acquisition.core import canonical_hash, canonical_json, strict_json_load


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
AUTONOMY_V5_PATH = REPOSITORY_ROOT / "contracts" / "DELTAGRID_AUTONOMY_CONSTITUTION_V5.json"
MISSION103_PATH = REPOSITORY_ROOT / "contracts" / "DELTAGRID_INDEPENDENT_RESEARCH_VALIDATION_GOVERNANCE_V1.json"
AUTONOMY_V5_ID = "deltagrid-autonomy-constitution-v5"
AUTONOMY_V5_HASH = "7055bba73f10ebb78f8791511d0b926ef1d8d7dae9099b843fae81d9aa074767"
MISSION103_ID = "deltagrid-independent-research-validation-governance-v1"
MISSION103_HASH = "19cc7af157e6350a736a272dd73c16a407eb42e68368ad84f970896da60d10f4"
MISSION102_ID = "deltagrid-development-research-runtime-v1"
MISSION102_HASH = "9bd79130edab59392a5a7f05225de2fbb4ad2b3c84476ddc5be095cffc6851da"
MISSION101_ID = "deltagrid-research-reopening-governance-v1"
MISSION101_HASH = "067e85fa1eb35b4fa81cac40fd036938df300d2b7da2774b163f1e306ce53ce7"
MISSION94_ID = "deltagrid-research-admission-core-v1"
MISSION94_HASH = "e4070b52a0f2dbc8ce34ea00d0a732c2aed25c9c21e5acfccc3f9d791dba6193"
MISSION99_ID = "deltagrid-temporal-market-data-control-plane-v1"
MISSION99_HASH = "159a822f77e3c6bf6409e04b2c25a61c5c7232cf6e73ea160ffb6cbf167d5d4c"
MISSION100_ID = "deltagrid-forward-market-data-acquisition-v1"
MISSION100_HASH = "42f1ebe86264268763978d6969c2a605924805433a041647f2625dfd297e16e3"
M102_COST_EXECUTION_ID = "DELTAGRID_M102_COST_EXECUTION_IDENTITY_V1"
M102_RISK_ID = "DELTAGRID_M102_RISK_IDENTITY_V1"
MISSION99_PATH = REPOSITORY_ROOT / "contracts" / "DELTAGRID_TEMPORAL_MARKET_DATA_CONTROL_PLANE_V1.json"
MISSION100_PATH = REPOSITORY_ROOT / "contracts" / "DELTAGRID_FORWARD_MARKET_DATA_ACQUISITION_V1.json"
DEFAULT_ROOT = Path("~/.deltagrid/statistical_governance").expanduser()
DATABASE_NAME = "governance.sqlite3"
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,255}\Z")
UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
STAGES = ("REPLICATION", "VALIDATION", "HOLDOUT")
MAX_JSON_BYTES = 8 * 1024 * 1024


class GovernanceError(RuntimeError):
    """Fail-closed Mission 103 error whose string never contains protected values."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def contract_hash(value: Mapping[str, Any]) -> str:
    core = dict(value)
    core.pop("contract_hash_sha256", None)
    return canonical_hash(core)


def load_contracts() -> tuple[dict[str, Any], dict[str, Any]]:
    autonomy = strict_json_load(AUTONOMY_V5_PATH)
    mission = strict_json_load(MISSION103_PATH)
    mission99 = strict_json_load(MISSION99_PATH)
    mission100 = strict_json_load(MISSION100_PATH)
    if not isinstance(autonomy, dict) or autonomy.get("contract_id") != AUTONOMY_V5_ID:
        raise GovernanceError("CONTRACT_ID_MISMATCH")
    if autonomy.get("contract_hash_sha256") != AUTONOMY_V5_HASH or contract_hash(autonomy) != AUTONOMY_V5_HASH:
        raise GovernanceError("CONTRACT_HASH_MISMATCH")
    if (
        autonomy.get("parent_constitution_id") != "deltagrid-autonomy-constitution-v4"
        or autonomy.get("parent_constitution_hash_sha256") != "1ffb9b3fcbf5adae63727a136e2c33a952e646fc1362d1e8dfd9b5482851b9e2"
    ):
        raise GovernanceError("CONTRACT_LINEAGE_MISMATCH")
    if not isinstance(mission, dict) or mission.get("contract_id") != MISSION103_ID:
        raise GovernanceError("CONTRACT_ID_MISMATCH")
    if mission.get("contract_hash_sha256") != MISSION103_HASH or contract_hash(mission) != MISSION103_HASH:
        raise GovernanceError("CONTRACT_HASH_MISMATCH")
    expected = {
        "autonomy_constitution_id": AUTONOMY_V5_ID,
        "autonomy_constitution_hash_sha256": AUTONOMY_V5_HASH,
        "mission94_contract_id": MISSION94_ID,
        "mission94_contract_hash_sha256": MISSION94_HASH,
        "mission101_contract_id": MISSION101_ID,
        "mission101_contract_hash_sha256": MISSION101_HASH,
        "mission102_contract_id": MISSION102_ID,
        "mission102_contract_hash_sha256": MISSION102_HASH,
        "mission99_contract_id": MISSION99_ID,
        "mission99_contract_hash_sha256": MISSION99_HASH,
        "mission100_contract_id": MISSION100_ID,
        "mission100_contract_hash_sha256": MISSION100_HASH,
    }
    if any(mission.get(key) != value for key, value in expected.items()):
        raise GovernanceError("CONTRACT_LINEAGE_MISMATCH")
    for document, identifier, digest in (
        (mission99, MISSION99_ID, MISSION99_HASH),
        (mission100, MISSION100_ID, MISSION100_HASH),
    ):
        if (
            not isinstance(document, dict)
            or document.get("contract_id") != identifier
            or document.get("contract_hash_sha256") != digest
            or contract_hash(document) != digest
        ):
            raise GovernanceError("CONTRACT_LINEAGE_MISMATCH")
    if (
        mission100.get("mission99_contract_id") != MISSION99_ID
        or mission100.get("mission99_contract_hash_sha256") != MISSION99_HASH
    ):
        raise GovernanceError("CONTRACT_LINEAGE_MISMATCH")
    maximum = mission.get("maximum_verdict")
    if not isinstance(maximum, dict) or maximum.get("authority_effect") != "NONE":
        raise GovernanceError("CONTRACT_AUTHORITY_INVALID")
    forbidden = {
        "model_training", "paper_trading", "live_trading", "exchange_access",
        "credential_access", "signed_requests", "orders", "portfolio_allocation",
        "leverage_or_risk_enlargement", "capital_deployment", "self_authorization",
    }
    if any(maximum.get(name) is not False for name in forbidden):
        raise GovernanceError("CONTRACT_AUTHORITY_INVALID")
    return autonomy, mission


def require_identifier(value: Any, field: str) -> str:
    if type(value) is not str or IDENTIFIER_RE.fullmatch(value) is None or "*" in value or ".." in value.split("/"):
        raise GovernanceError("IDENTIFIER_INVALID", field)
    return value


def require_hash(value: Any, field: str) -> str:
    if type(value) is not str or HASH_RE.fullmatch(value) is None:
        raise GovernanceError("HASH_INVALID", field)
    return value


def require_commit(value: Any, field: str = "repository_commit") -> str:
    if type(value) is not str or COMMIT_RE.fullmatch(value) is None:
        raise GovernanceError("COMMIT_INVALID", field)
    return value


def parse_utc(value: Any, field: str) -> datetime:
    if type(value) is not str or UTC_RE.fullmatch(value) is None:
        raise GovernanceError("TIMESTAMP_INVALID", field)
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)
    except ValueError as error:
        raise GovernanceError("TIMESTAMP_INVALID", field) from error


def trusted_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def require_decimal_text(value: Any, field: str, *, minimum: Decimal | None = None, maximum: Decimal | None = None) -> Decimal:
    if type(value) is not str or not value or len(value) > 128:
        raise GovernanceError("DECIMAL_INVALID", field)
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise GovernanceError("DECIMAL_INVALID", field) from error
    if not parsed.is_finite() or (minimum is not None and parsed < minimum) or (maximum is not None and parsed > maximum):
        raise GovernanceError("DECIMAL_INVALID", field)
    return parsed


def freeze_json(value: Any, *, max_depth: int = 24, max_nodes: int = 50_000) -> Any:
    """Copy a bounded JSON tree while rejecting floats, aliases, and custom objects."""

    seen: set[int] = set()
    nodes = 0

    def visit(item: Any, depth: int) -> Any:
        nonlocal nodes
        nodes += 1
        if depth > max_depth or nodes > max_nodes:
            raise GovernanceError("FROZEN_VALUE_LIMIT")
        if item is None or type(item) in {bool, int, str}:
            if type(item) is str and len(item) > 16_384:
                raise GovernanceError("FROZEN_VALUE_LIMIT")
            if type(item) is int and abs(item) > 10**100:
                raise GovernanceError("FROZEN_VALUE_LIMIT")
            return item
        if type(item) is dict:
            if id(item) in seen or len(item) > 10_000:
                raise GovernanceError("FROZEN_VALUE_INVALID")
            seen.add(id(item))
            copied: dict[str, Any] = {}
            for key, nested in item.items():
                if type(key) is not str or not key or len(key) > 256:
                    raise GovernanceError("FROZEN_VALUE_INVALID")
                copied[key] = visit(nested, depth + 1)
            seen.remove(id(item))
            return copied
        if type(item) in {list, tuple}:
            if id(item) in seen or len(item) > 10_000:
                raise GovernanceError("FROZEN_VALUE_INVALID")
            seen.add(id(item))
            copied = [visit(nested, depth + 1) for nested in item]
            seen.remove(id(item))
            return copied
        raise GovernanceError("BINARY_FLOAT_OR_CUSTOM_VALUE_FORBIDDEN")

    return visit(value, 0)


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(freeze_json(value)).encode("utf-8")


def private_root(value: str | Path, *, must_exist: bool) -> Path:
    lexical = Path(value).expanduser()
    if not lexical.is_absolute():
        raise GovernanceError("GOVERNANCE_ROOT_NOT_ABSOLUTE")
    current = lexical
    while True:
        if current.is_symlink():
            raise GovernanceError("GOVERNANCE_ROOT_SYMLINK")
        if current == current.parent:
            break
        current = current.parent
    resolved = lexical.resolve(strict=False)
    try:
        resolved.relative_to(REPOSITORY_ROOT.resolve(strict=True))
    except ValueError:
        pass
    else:
        raise GovernanceError("GOVERNANCE_ROOT_INSIDE_REPOSITORY")
    if must_exist:
        if not resolved.is_dir() or resolved.is_symlink() or stat.S_IMODE(resolved.stat().st_mode) != 0o700:
            raise GovernanceError("GOVERNANCE_ROOT_INVALID")
    return resolved


def secure_nonce() -> bytes:
    value = secrets.token_bytes(32)
    if len(value) != 32:
        raise GovernanceError("NONCE_ENTROPY_FAILURE")
    return value


def write_exclusive(path: Path, raw: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, 0o600, follow_symlinks=False)


def opaque_payload_commitment(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def safe_metadata(value: Any) -> Any:
    """Return only explicitly non-value fields for status and exception-safe output."""

    allowed = {
        "campaign_id", "campaign_hash", "program_id", "program_hash", "candidate_id",
        "candidate_hash", "stage", "status", "reason_token", "specification_id",
        "specification_hash", "materialization_id", "materialization_hash", "coverage_hash",
        "record_count", "closed_at", "execution_id", "authorization_id", "authority_effect",
    }
    if not isinstance(value, Mapping):
        raise GovernanceError("METADATA_MAPPING_REQUIRED")
    return {key: value[key] for key in sorted(value) if key in allowed}


__all__ = [
    "GovernanceError", "canonical_hash", "canonical_json", "strict_json_load",
    "load_contracts", "contract_hash", "require_identifier", "require_hash",
    "require_commit", "parse_utc", "trusted_utc_now", "require_decimal_text",
    "freeze_json", "canonical_bytes", "private_root", "safe_metadata",
]

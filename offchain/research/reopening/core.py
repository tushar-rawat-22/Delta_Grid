"""Mission 101 identities, strict contracts, and metadata-only primitives."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Mapping

from offchain.market_data_acquisition.core import (
    canonical_hash,
    canonical_json,
    deep_freeze,
    deep_thaw,
    strict_json_load,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
AUTONOMY_V3_PATH = REPOSITORY_ROOT / "contracts" / "DELTAGRID_AUTONOMY_CONSTITUTION_V3.json"
MISSION101_PATH = REPOSITORY_ROOT / "contracts" / "DELTAGRID_RESEARCH_REOPENING_GOVERNANCE_V1.json"
AUTONOMY_V3_ID = "deltagrid-autonomy-constitution-v3"
AUTONOMY_V3_HASH = "cdd768ee04693845f9c1dcc4af3a03bad03a62685b24681d1ff8426230c84743"
MISSION101_ID = "deltagrid-research-reopening-governance-v1"
MISSION101_HASH = "067e85fa1eb35b4fa81cac40fd036938df300d2b7da2774b163f1e306ce53ce7"
MISSION100_ID = "deltagrid-forward-market-data-acquisition-v1"
MISSION100_HASH = "42f1ebe86264268763978d6969c2a605924805433a041647f2625dfd297e16e3"
MISSION100_REMEDIATION_ID = "deltagrid-mission100-first-live-activation-remediation-v1"
MISSION100_REMEDIATION_HASH = "e69cf1810a355e5d460d565f432ce7f86ec72f45819f69c33c1c14d86294992f"
MISSION94_ID = "deltagrid-research-admission-core-v1"
MISSION94_HASH = "e4070b52a0f2dbc8ce34ea00d0a732c2aed25c9c21e5acfccc3f9d791dba6193"
FORWARD_PROFILE = "DELTAGRID_M100_FORWARD_CUSTODY_V1"
DEVELOPMENT_STAGE = "MISSION_101_DEVELOPMENT_ADMISSION"
DATA_CLASS = "REAL_MARKET_DEVELOPMENT"
SPLIT_IDENTITY = "REAL_MARKET_DEVELOPMENT"
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,255}\Z")
UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")


class ReopeningError(RuntimeError):
    """Fail-closed Mission 101 error with a stable reason token."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path, *, maximum_bytes: int | None = None) -> str:
    if path.is_symlink() or not path.is_file():
        raise ReopeningError("REGULAR_FILE_REQUIRED")
    if maximum_bytes is not None and path.stat().st_size > maximum_bytes:
        raise ReopeningError("FILE_SIZE_LIMIT")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def contract_hash(value: Mapping[str, Any]) -> str:
    core = deep_thaw(value)
    core.pop("contract_hash_sha256", None)
    return canonical_hash(core)


def _load_contract(path: Path, contract_id: str, expected_hash: str) -> Mapping[str, Any]:
    value = strict_json_load(path)
    if not isinstance(value, Mapping) or value.get("contract_id") != contract_id:
        raise ReopeningError("CONTRACT_ID_MISMATCH", path.name)
    if value.get("contract_hash_sha256") != expected_hash or contract_hash(value) != expected_hash:
        raise ReopeningError("CONTRACT_HASH_MISMATCH", path.name)
    return deep_freeze(value)


def load_contracts() -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    autonomy = _load_contract(AUTONOMY_V3_PATH, AUTONOMY_V3_ID, AUTONOMY_V3_HASH)
    mission = _load_contract(MISSION101_PATH, MISSION101_ID, MISSION101_HASH)
    if (
        mission.get("autonomy_constitution_id") != AUTONOMY_V3_ID
        or mission.get("autonomy_constitution_hash_sha256") != AUTONOMY_V3_HASH
        or mission.get("mission94_contract_id") != MISSION94_ID
        or mission.get("mission94_contract_hash_sha256") != MISSION94_HASH
        or mission.get("mission100_contract_id") != MISSION100_ID
        or mission.get("mission100_contract_hash_sha256") != MISSION100_HASH
        or mission.get("mission100_remediation_contract_id") != MISSION100_REMEDIATION_ID
        or mission.get("mission100_remediation_contract_hash_sha256") != MISSION100_REMEDIATION_HASH
    ):
        raise ReopeningError("CONTRACT_LINEAGE_MISMATCH")
    authority = mission.get("authority")
    if not isinstance(authority, Mapping):
        raise ReopeningError("CONTRACT_AUTHORITY_INVALID")
    required_true = {
        "forward_custody_bridge",
        "development_dataset_descriptor",
        "development_permit_machinery",
        "development_admission_machinery",
    }
    required_false = {
        "result_bearing_research_execution", "validation", "holdout",
        "model_or_ml", "signals", "paper", "live", "exchange_access",
        "credential_access", "orders", "capital", "self_authorization",
    }
    if any(authority.get(key) is not True for key in required_true):
        raise ReopeningError("CONTRACT_AUTHORITY_INVALID")
    if any(authority.get(key) is not False for key in required_false):
        raise ReopeningError("CONTRACT_AUTHORITY_INVALID")
    return autonomy, mission


def require_hash(value: Any, field: str) -> str:
    if type(value) is not str or HASH_RE.fullmatch(value) is None:
        raise ReopeningError("HASH_INVALID", field)
    return value


def require_commit(value: Any, field: str) -> str:
    if type(value) is not str or COMMIT_RE.fullmatch(value) is None:
        raise ReopeningError("COMMIT_INVALID", field)
    return value


def require_identifier(value: Any, field: str) -> str:
    if type(value) is not str or IDENTIFIER_RE.fullmatch(value) is None or "*" in value:
        raise ReopeningError("IDENTIFIER_INVALID", field)
    return value


def parse_utc(value: Any, field: str) -> datetime:
    if type(value) is not str or UTC_RE.fullmatch(value) is None:
        raise ReopeningError("TIMESTAMP_INVALID", field)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ReopeningError("TIMESTAMP_INVALID", field) from error
    return parsed.astimezone(timezone.utc)


def trusted_utc_now() -> str:
    """Return trusted local system UTC for authority write decisions."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _git_output(repository_root: Path, arguments: list[str]) -> str:
    environment = os.environ.copy()
    for name in (
        "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CEILING_DIRECTORIES",
    ):
        environment.pop(name, None)
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=repository_root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ReopeningError("REPOSITORY_IDENTITY_OBSERVATION_FAILED") from error
    return completed.stdout


def validate_repository_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an observed identity, including exact DeltaGrid root binding."""

    if not isinstance(value, Mapping) or set(value) != {"repository_root", "head", "clean"}:
        raise ReopeningError("REPOSITORY_IDENTITY_INVALID")
    if type(value["repository_root"]) is not str or not Path(value["repository_root"]).is_absolute():
        raise ReopeningError("REPOSITORY_IDENTITY_INVALID")
    try:
        root = Path(value["repository_root"]).resolve(strict=True)
    except (OSError, TypeError) as error:
        raise ReopeningError("REPOSITORY_IDENTITY_INVALID") from error
    if root != REPOSITORY_ROOT.resolve(strict=True):
        raise ReopeningError("REPOSITORY_ROOT_MISMATCH")
    head = require_commit(value["head"], "repository_head")
    if type(value["clean"]) is not bool:
        raise ReopeningError("REPOSITORY_IDENTITY_INVALID")
    return {"repository_root": str(root), "head": head, "clean": value["clean"]}


def observe_repository_identity(
    repository_root: str | Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Observe the exact DeltaGrid root, HEAD, and untracked-inclusive status."""

    try:
        root = Path(repository_root).resolve(strict=True)
    except OSError as error:
        raise ReopeningError("REPOSITORY_IDENTITY_OBSERVATION_FAILED") from error
    expected = REPOSITORY_ROOT.resolve(strict=True)
    if root != expected:
        raise ReopeningError("REPOSITORY_ROOT_MISMATCH")
    observed_root = _git_output(root, ["rev-parse", "--show-toplevel"]).strip()
    if not observed_root or not Path(observed_root).is_absolute():
        raise ReopeningError("REPOSITORY_ROOT_MISMATCH")
    try:
        observed = Path(observed_root).resolve(strict=True)
    except OSError as error:
        raise ReopeningError("REPOSITORY_ROOT_MISMATCH") from error
    if observed != expected:
        raise ReopeningError("REPOSITORY_ROOT_MISMATCH")
    head = _git_output(root, ["rev-parse", "HEAD"]).strip()
    require_commit(head, "repository_head")
    status = _git_output(root, ["status", "--porcelain=v1", "--untracked-files=all"])
    return validate_repository_observation(
        {"repository_root": str(expected), "head": head, "clean": status == ""}
    )


def get_repository_observation(
    observer: Callable[[], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Call a production observer or a test-injected observer and validate it."""

    try:
        return validate_repository_observation((observer or observe_repository_identity)())
    except ReopeningError:
        raise
    except Exception as error:
        raise ReopeningError("REPOSITORY_IDENTITY_OBSERVATION_FAILED") from error

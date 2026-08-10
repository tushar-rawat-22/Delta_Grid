"""Strict identities and filesystem boundaries for DeltaGrid public projections."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Mapping

from offchain.market_data_acquisition.core import canonical_hash, canonical_json, strict_json_load


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPOSITORY_ROOT / "contracts" / "DELTAGRID_PUBLIC_PROJECTION_V1.json"
AUTONOMY_V5_PATH = REPOSITORY_ROOT / "contracts" / "DELTAGRID_AUTONOMY_CONSTITUTION_V5.json"
MISSION103_PATH = REPOSITORY_ROOT / "contracts" / "DELTAGRID_INDEPENDENT_RESEARCH_VALIDATION_GOVERNANCE_V1.json"

CONTRACT_ID = "deltagrid-public-projection-v1"
CONTRACT_HASH = "bf288d8b6349c2843b5196fa1857ae9c464773bbcf7cad9d821785ea67dfb6e8"
AUTONOMY_V5_ID = "deltagrid-autonomy-constitution-v5"
AUTONOMY_V5_HASH = "7055bba73f10ebb78f8791511d0b926ef1d8d7dae9099b843fae81d9aa074767"
MISSION103_ID = "deltagrid-independent-research-validation-governance-v1"
MISSION103_HASH = "19cc7af157e6350a736a272dd73c16a407eb42e68368ad84f970896da60d10f4"
BASE_COMMIT = "6e31f3d8ac062feccf91eeeb8c6d71733f4f56b7"

PROJECTION_SCHEMA_ID = "DELTAGRID_PUBLIC_PROJECTION_V1"
MANIFEST_SCHEMA_ID = "DELTAGRID_PUBLIC_PROJECTION_MANIFEST_V1"
PROJECTION_FILENAME = "projection.json"
MANIFEST_FILENAME = "manifest.json"
PACKAGE_FILENAMES = frozenset({PROJECTION_FILENAME, MANIFEST_FILENAME})
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")

ALLOWED_CONTRACT_PATHS = (
    "contracts/DELTAGRID_AUTONOMY_CONSTITUTION_V5.json",
    "contracts/DELTAGRID_INDEPENDENT_RESEARCH_VALIDATION_GOVERNANCE_V1.json",
)
ALLOWED_PUBLIC_DOCUMENT_PATHS = (
    "README.md",
    "docs/RESEARCH_POLICY.md",
    "docs/RISK_POLICY.md",
    "docs/SAFETY_INVARIANTS.md",
)
SOURCE_CLASSES = (
    "REPOSITORY_IDENTITY",
    "CONTRACT_DERIVED",
    "PUBLIC_DOCUMENT_IDENTITY",
)


class ProjectionError(RuntimeError):
    """Fail-closed public-projection error with a stable, non-secret reason."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def contract_hash(value: Mapping[str, Any]) -> str:
    core = dict(value)
    core.pop("contract_hash_sha256", None)
    return canonical_hash(core)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8") + b"\n"


def require_hash(value: Any, field: str) -> str:
    if type(value) is not str or HASH_RE.fullmatch(value) is None:
        raise ProjectionError("HASH_INVALID", field)
    return value


def require_commit(value: Any, field: str = "repository_commit") -> str:
    if type(value) is not str or COMMIT_RE.fullmatch(value) is None:
        raise ProjectionError("COMMIT_INVALID", field)
    return value


def _load_exact_contract(path: Path, identifier: str, digest: str) -> dict[str, Any]:
    try:
        value = strict_json_load(path)
    except Exception as error:
        raise ProjectionError("CONTRACT_READ_FAILED", path.name) from error
    if not isinstance(value, dict) or value.get("contract_id") != identifier:
        raise ProjectionError("CONTRACT_ID_MISMATCH", path.name)
    if value.get("contract_hash_sha256") != digest or contract_hash(value) != digest:
        raise ProjectionError("CONTRACT_HASH_MISMATCH", path.name)
    return value


def load_contracts(repository_root: Path | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    root = (repository_root or REPOSITORY_ROOT).resolve(strict=True)
    contract = _load_exact_contract(root / "contracts" / CONTRACT_PATH.name, CONTRACT_ID, CONTRACT_HASH)
    autonomy = _load_exact_contract(root / "contracts" / AUTONOMY_V5_PATH.name, AUTONOMY_V5_ID, AUTONOMY_V5_HASH)
    mission103 = _load_exact_contract(root / "contracts" / MISSION103_PATH.name, MISSION103_ID, MISSION103_HASH)
    if (
        contract.get("authority_effect") != "NONE"
        or contract.get("autonomy_constitution_id") != AUTONOMY_V5_ID
        or contract.get("autonomy_constitution_hash_sha256") != AUTONOMY_V5_HASH
        or contract.get("mission103_contract_id") != MISSION103_ID
        or contract.get("mission103_contract_hash_sha256") != MISSION103_HASH
    ):
        raise ProjectionError("CONTRACT_LINEAGE_MISMATCH")
    authority = contract.get("authority")
    if not isinstance(authority, dict) or authority.get("public_repository_projection") is not True:
        raise ProjectionError("CONTRACT_AUTHORITY_INVALID")
    forbidden_true = {
        "private_runtime_metadata_projection", "market_value_projection", "protected_value_projection",
        "network_access", "research_execution", "validation_or_holdout_opening", "model_or_ml",
        "paper_trading", "live_trading", "exchange_access", "credential_access", "signed_requests",
        "orders", "portfolio_allocation", "capital_deployment", "self_authorization",
    }
    if any(authority.get(name) is not False for name in forbidden_true):
        raise ProjectionError("CONTRACT_AUTHORITY_INVALID")
    maximum = mission103.get("maximum_verdict")
    if not isinstance(maximum, dict) or maximum.get("authority_effect") != "NONE":
        raise ProjectionError("MISSION103_BOUNDARY_INVALID")
    return contract, autonomy, mission103


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ProjectionError("REPOSITORY_IDENTITY_UNAVAILABLE") from error


def repository_identity(repository_root: Path | None = None) -> str:
    root = (repository_root or REPOSITORY_ROOT).resolve(strict=True)
    commit = _git(root, "rev-parse", "HEAD")
    require_commit(commit)
    try:
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ProjectionError("REPOSITORY_IDENTITY_UNAVAILABLE") from error
    if dirty:
        raise ProjectionError("REPOSITORY_NOT_CLEAN")
    return commit


def _reject_symlink_components(path: Path) -> None:
    current = path
    while True:
        if current.exists() and current.is_symlink():
            raise ProjectionError("PATH_SYMLINK_FORBIDDEN")
        if current == current.parent:
            break
        current = current.parent


def source_file(root: Path, relative: str) -> Path:
    if relative not in {*ALLOWED_CONTRACT_PATHS, *ALLOWED_PUBLIC_DOCUMENT_PATHS}:
        raise ProjectionError("SOURCE_PATH_NOT_ALLOWED", relative)
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ProjectionError("SOURCE_PATH_NOT_ALLOWED", relative)
    path = root / relative
    _reject_symlink_components(path)
    if not path.is_file() or path.is_symlink():
        raise ProjectionError("SOURCE_FILE_INVALID", relative)
    return path


def public_file_sha256(root: Path, relative: str) -> str:
    return sha256_bytes(source_file(root, relative).read_bytes())


def validate_destination(destination: str | Path, repository_root: Path | None = None) -> Path:
    root = (repository_root or REPOSITORY_ROOT).resolve(strict=True)
    lexical = Path(destination).expanduser()
    if not lexical.is_absolute():
        raise ProjectionError("DESTINATION_NOT_ABSOLUTE")
    _reject_symlink_components(lexical)
    resolved = lexical.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError:
        pass
    else:
        raise ProjectionError("DESTINATION_INSIDE_REPOSITORY")
    if resolved.exists():
        if resolved.is_symlink() or not resolved.is_dir():
            raise ProjectionError("DESTINATION_INVALID")
        if any(resolved.iterdir()):
            raise ProjectionError("DESTINATION_NOT_EMPTY")
    return resolved


def prepare_destination(destination: str | Path, repository_root: Path | None = None) -> Path:
    path = validate_destination(destination, repository_root)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700, follow_symlinks=False)
    if stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise ProjectionError("DESTINATION_MODE_INVALID")
    return path


def write_exclusive(path: Path, raw: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise ProjectionError("OUTPUT_CONFLICT", path.name) from error
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, 0o600, follow_symlinks=False)

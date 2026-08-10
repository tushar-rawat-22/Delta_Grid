"""Independent verifier for P1.1 public projection packages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from offchain.market_data_acquisition.core import strict_json_load

from .core import (
    MANIFEST_FILENAME,
    PACKAGE_FILENAMES,
    PROJECTION_FILENAME,
    ProjectionError,
    canonical_bytes,
    sha256_bytes,
)
from .schema import validate_manifest, validate_projection
from .sources import build_projection


def _package_root(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ProjectionError("PACKAGE_PATH_NOT_ABSOLUTE")
    if path.is_symlink() or not path.is_dir():
        raise ProjectionError("PACKAGE_PATH_INVALID")
    for parent in (path, *path.parents):
        if parent.exists() and parent.is_symlink():
            raise ProjectionError("PACKAGE_PATH_SYMLINK")
    names = {item.name for item in path.iterdir()}
    if names != PACKAGE_FILENAMES:
        raise ProjectionError("PACKAGE_FILE_SET_MISMATCH")
    return path.resolve(strict=True)


def _load_canonical(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ProjectionError("PACKAGE_FILE_INVALID", path.name)
    raw = path.read_bytes()
    try:
        value = strict_json_load(raw)
    except Exception as error:
        raise ProjectionError("PACKAGE_JSON_INVALID", path.name) from error
    if not isinstance(value, dict) or raw != canonical_bytes(value):
        raise ProjectionError("PACKAGE_NOT_CANONICAL", path.name)
    return value, raw


def verify_projection_package(
    package_root: str | Path,
    *,
    repository_root: Path | None = None,
    compare_current_repository: bool = True,
) -> dict[str, Any]:
    """Verify package structure, exact bytes, manifest binding, and current source parity."""

    root = _package_root(package_root)
    projection_value, projection_raw = _load_canonical(root / PROJECTION_FILENAME)
    manifest_value, _manifest_raw = _load_canonical(root / MANIFEST_FILENAME)
    projection = validate_projection(projection_value)
    manifest = validate_manifest(manifest_value)

    digest = sha256_bytes(projection_raw)
    if manifest["projection_sha256"] != digest:
        raise ProjectionError("PROJECTION_HASH_MISMATCH")
    if manifest["repository_commit"] != projection["core_identity"]["repository_commit"]:
        raise ProjectionError("PROJECTION_MANIFEST_COMMIT_MISMATCH")

    if compare_current_repository:
        expected = validate_projection(build_projection(repository_root))
        if canonical_bytes(expected) != projection_raw:
            raise ProjectionError("PROJECTION_CURRENT_SOURCE_MISMATCH")

    return {
        "verdict": "PASS",
        "repository_commit": manifest["repository_commit"],
        "projection_sha256": digest,
        "file_count": 2,
    }

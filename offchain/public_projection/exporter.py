"""Exclusive deterministic exporter for P1.1 public projection packages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import (
    CONTRACT_HASH,
    MANIFEST_FILENAME,
    MANIFEST_SCHEMA_ID,
    PROJECTION_FILENAME,
    canonical_bytes,
    prepare_destination,
    sha256_bytes,
    write_exclusive,
)
from .schema import validate_manifest, validate_projection
from .sources import build_projection


def export_projection(destination: str | Path, *, repository_root: Path | None = None) -> dict[str, Any]:
    """Build and write exactly one deterministic projection package."""

    projection = validate_projection(build_projection(repository_root))
    projection_raw = canonical_bytes(projection)
    projection_sha256 = sha256_bytes(projection_raw)
    manifest = validate_manifest(
        {
            "manifest_schema": MANIFEST_SCHEMA_ID,
            "public_projection_contract_hash": CONTRACT_HASH,
            "repository_commit": projection["core_identity"]["repository_commit"],
            "projection_sha256": projection_sha256,
        }
    )
    manifest_raw = canonical_bytes(manifest)

    root = prepare_destination(destination, repository_root)
    write_exclusive(root / PROJECTION_FILENAME, projection_raw)
    write_exclusive(root / MANIFEST_FILENAME, manifest_raw)

    return {
        "verdict": "PASS",
        "repository_commit": projection["core_identity"]["repository_commit"],
        "projection_sha256": projection_sha256,
        "file_count": 2,
    }

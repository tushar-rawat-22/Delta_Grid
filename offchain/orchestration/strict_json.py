"""Strict JSON, timestamp, path, and durable no-clobber publication helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Callable

from offchain.research.admission import canonical_json

from .models import OrchestrationError


MAX_JSON_DEPTH = 64
MAX_PATH_TEXT = 4096
_UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
_SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}\Z")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate_identifier(value: Any, *, reason: str = "WORKFLOW_INPUT_INVALID") -> str:
    if type(value) is not str or _SAFE_ID_RE.fullmatch(value) is None:
        raise OrchestrationError(reason, "identifier is invalid")
    return value


def parse_utc(value: Any, *, reason: str = "WORKFLOW_INPUT_INVALID") -> datetime:
    if type(value) is not str or _UTC_RE.fullmatch(value) is None:
        raise OrchestrationError(reason, "timestamp must be normalized UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise OrchestrationError(reason, "timestamp is invalid") from error
    if parsed.tzinfo != timezone.utc:
        raise OrchestrationError(reason, "timestamp must be UTC")
    if parsed.microsecond:
        base = parsed.strftime("%Y-%m-%dT%H:%M:%S")
        normalized = f"{base}.{parsed.microsecond:06d}".rstrip("0") + "Z"
    else:
        normalized = parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
    if normalized != value:
        raise OrchestrationError(reason, "timestamp is not normalized")
    return parsed


def add_seconds(value: str, seconds: int) -> str:
    from datetime import timedelta

    result = parse_utc(value) + timedelta(seconds=seconds)
    if result.microsecond:
        return (
            f"{result.strftime('%Y-%m-%dT%H:%M:%S')}."
            f"{result.microsecond:06d}".rstrip("0")
            + "Z"
        )
    return result.strftime("%Y-%m-%dT%H:%M:%SZ")


def _reject_constant(token: str) -> None:
    raise ValueError(f"non-finite number: {token}")


def _exact_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate object name")
        value[key] = item
    return value


def _validate_tree(value: Any, depth: int = 0, *, reject_floats: bool = True) -> None:
    if depth > MAX_JSON_DEPTH:
        raise ValueError("maximum JSON depth exceeded")
    if reject_floats and isinstance(value, float):
        raise ValueError("floats are not permitted")
    if type(value) not in (dict, list, str, int, bool, float, type(None)):
        raise ValueError("unsupported JSON value")
    if isinstance(value, dict):
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("JSON object names must be strings")
            _validate_tree(item, depth + 1, reject_floats=reject_floats)
    elif isinstance(value, list):
        for item in value:
            _validate_tree(item, depth + 1, reject_floats=reject_floats)


def decode_json(
    raw: bytes,
    *,
    max_bytes: int,
    reason: str,
    require_canonical: bool = True,
    reject_floats: bool = True,
) -> Any:
    if type(raw) is not bytes or len(raw) > max_bytes:
        raise OrchestrationError(
            "RESOURCE_LIMIT_EXCEEDED" if type(raw) is bytes else reason
        )
    if raw.startswith(b"\xef\xbb\xbf"):
        raise OrchestrationError(reason, "UTF-8 BOM is forbidden")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_exact_object,
            parse_constant=_reject_constant,
        )
        _validate_tree(value, reject_floats=reject_floats)
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise OrchestrationError(reason, "strict JSON validation failed") from error
    if require_canonical and canonical_json(value).encode("utf-8") != raw:
        raise OrchestrationError(reason, "JSON bytes are not canonical")
    return value


def resolve_existing(
    value: Path | str,
    *,
    directory: bool,
    reason: str,
    absolute_required: bool = True,
) -> Path:
    if not isinstance(value, (str, Path)) or len(str(value)) > MAX_PATH_TEXT:
        raise OrchestrationError(reason, "path is invalid")
    candidate = Path(value)
    if absolute_required and not candidate.is_absolute():
        raise OrchestrationError(reason, "path must be absolute")
    current = Path(candidate.anchor)
    try:
        for part in candidate.parts[1:]:
            current = current / part
            metadata = os.lstat(current)
            if stat.S_ISLNK(metadata.st_mode):
                raise OrchestrationError(reason, "path contains a symbolic link")
        resolved = candidate.resolve(strict=True)
        metadata = resolved.stat()
    except OrchestrationError:
        raise
    except OSError as error:
        raise OrchestrationError(reason, "path does not exist") from error
    matches = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not matches:
        raise OrchestrationError(reason, "path has the wrong file type")
    return resolved


def validate_missing_path(value: Path | str, *, reason: str) -> tuple[Path, Path]:
    candidate = Path(value)
    if not candidate.is_absolute() or len(str(candidate)) > MAX_PATH_TEXT:
        raise OrchestrationError(reason, "path must be an absolute bounded path")
    if candidate.exists() or candidate.is_symlink():
        raise OrchestrationError(reason, "path already exists")
    parent = resolve_existing(candidate.parent, directory=True, reason=reason)
    return candidate, parent


def prepare_artifact_path(output_root: Path, run_id: str, step_id: str) -> Path:
    root = resolve_existing(output_root, directory=True, reason="ARTIFACT_PATH_UNSAFE")
    current = root
    try:
        for name in ("runs", run_id, step_id):
            candidate = current / name
            if candidate.exists() or candidate.is_symlink():
                metadata = os.lstat(candidate)
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                    raise OrchestrationError("ARTIFACT_PATH_UNSAFE")
            else:
                try:
                    candidate.mkdir(mode=0o700)
                except FileExistsError:
                    metadata = os.lstat(candidate)
                    if (
                        stat.S_ISLNK(metadata.st_mode)
                        or not stat.S_ISDIR(metadata.st_mode)
                    ):
                        raise OrchestrationError("ARTIFACT_PATH_UNSAFE")
            resolved = candidate.resolve(strict=True)
            if resolved != candidate or not resolved.is_relative_to(root):
                raise OrchestrationError("ARTIFACT_PATH_UNSAFE")
            current = candidate
    except OrchestrationError:
        raise
    except OSError as error:
        raise OrchestrationError("ARTIFACT_PATH_UNSAFE") from error
    final = current / "result.json"
    if len(str(final)) > MAX_PATH_TEXT or final.is_symlink():
        raise OrchestrationError("ARTIFACT_PATH_UNSAFE")
    if final.exists() and not final.is_file():
        raise OrchestrationError("ARTIFACT_PATH_UNSAFE")
    return final


def publish_canonical(
    path: Path,
    value: Any,
    *,
    max_bytes: int,
    validate_existing: Callable[[bytes], None] | None = None,
) -> bytes:
    try:
        _validate_tree(value)
        raw = canonical_json(value).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise OrchestrationError("INTERNAL_INTEGRITY_FAILURE") from error
    if len(raw) > max_bytes:
        raise OrchestrationError("RESOURCE_LIMIT_EXCEEDED")
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise OrchestrationError("ARTIFACT_PATH_UNSAFE")
        try:
            existing = path.read_bytes()
        except OSError as error:
            raise OrchestrationError("ARTIFACT_TEMPORARILY_UNAVAILABLE") from error
        if validate_existing is not None:
            validate_existing(existing)
        if existing != raw:
            raise OrchestrationError("ARTIFACT_CONFLICT")
        return existing
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(raw)
            temporary.flush()
            os.fsync(temporary.fileno())
        try:
            os.link(temporary_name, path)
        except FileExistsError:
            existing = path.read_bytes()
            if validate_existing is not None:
                validate_existing(existing)
            if existing != raw:
                raise OrchestrationError("ARTIFACT_CONFLICT")
            return existing
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return raw
    except OrchestrationError:
        raise
    except OSError as error:
        raise OrchestrationError("ARTIFACT_TEMPORARILY_UNAVAILABLE") from error
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass

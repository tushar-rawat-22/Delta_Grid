"""Strict canonical JSON decoding and safe atomic artifact publication."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any, Callable

from offchain.research.admission import canonical_json

from .models import EngineError


MAX_EVENTS = 512
MAX_ACCOUNTING_VALUE = 9_223_372_036_854_775_807
MAX_FIXTURE_BYTES = 1_048_576
MAX_EVENT_LEDGER_BYTES = 1_048_576
MAX_RESULT_BYTES = 1_048_576


def detached_json_value(value: Any) -> Any:
    """Return a detached value containing JSON-compatible built-in types."""

    if type(value) is bytes:
        return json.loads(value.decode("utf-8"))
    return json.loads(canonical_json(value))


def _reject_constant(_: str) -> None:
    raise ValueError("non-finite number")


def _exact_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result


def decode_canonical_json(
    raw: bytes,
    *,
    invalid_reason: str,
    max_bytes: int,
) -> Any:
    """Decode only compact UTF-8 canonical JSON with unique object keys."""

    if type(raw) is not bytes or len(raw) > max_bytes or raw.startswith(b"\xef\xbb\xbf"):
        raise EngineError(invalid_reason)
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_exact_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise EngineError(invalid_reason) from error
    if canonical_json(value).encode("utf-8") != raw:
        raise EngineError(invalid_reason)
    return value


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def safe_relative_path(relative: str, reason: str) -> PurePosixPath:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise EngineError(reason)
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise EngineError(reason)
    return pure


def resolve_existing_regular_file(
    root: Path,
    relative: str,
    *,
    unsafe_reason: str,
    missing_reason: str,
) -> Path:
    """Resolve an existing non-symlink regular file below a configured root."""

    pure = safe_relative_path(relative, unsafe_reason)
    candidate = root.joinpath(*pure.parts)
    current = root
    try:
        for part in pure.parts:
            current = current / part
            if current.is_symlink():
                raise EngineError(unsafe_reason)
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as error:
        raise EngineError(missing_reason) from error
    except OSError as error:
        raise EngineError(unsafe_reason) from error
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise EngineError(
            unsafe_reason if not resolved.is_relative_to(root) else missing_reason
        )
    return resolved


def prepare_result_directory(root: Path, trial_id: str) -> Path:
    """Create and validate the derived same-trial result directory."""

    try:
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink() or not root.is_dir():
            raise EngineError("RESULT_PATH_UNSAFE")
        resolved_root = root.resolve(strict=True)
        if resolved_root != root:
            raise EngineError("RESULT_PATH_UNSAFE")
        directory = root / trial_id
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
            raise EngineError("RESULT_PATH_UNSAFE")
        directory.mkdir(mode=0o700, exist_ok=True)
        resolved = directory.resolve(strict=True)
    except EngineError:
        raise
    except OSError as error:
        raise EngineError("RESULT_PATH_UNSAFE") from error
    if not resolved.is_relative_to(root) or resolved != directory:
        raise EngineError("RESULT_PATH_UNSAFE")
    return directory


def publish_canonical(
    path: Path,
    value: Any,
    *,
    max_bytes: int,
    validate_existing: Callable[[bytes], None] | None = None,
) -> bytes:
    """Publish exact bytes without overwriting different existing content."""

    raw = canonical_json(value).encode("utf-8")
    if len(raw) > max_bytes:
        raise EngineError("RESULT_WRITE_FAILED")
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as error:
            raise EngineError("RESULT_WRITE_FAILED") from error
        if validate_existing is not None:
            validate_existing(existing)
        if existing != raw:
            raise EngineError("RESULT_WRITE_FAILED")
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
                raise EngineError("RESULT_WRITE_FAILED")
            return existing
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return raw
    except EngineError:
        raise
    except OSError as error:
        raise EngineError("RESULT_WRITE_FAILED") from error
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass

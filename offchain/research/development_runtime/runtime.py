"""Private Mission 102 result runtime, no-clobber artifacts, and trial locks."""

from __future__ import annotations

from contextlib import contextmanager
import errno
import fcntl
import os
from pathlib import Path
import re
import stat
import time
from typing import Any, Iterator, Mapping

from .core import (
    ACK_INITIALIZE_RESULTS,
    DevelopmentRuntimeError,
    canonical_bytes,
    MAX_JSON_BYTES,
    MAX_RESULT_BYTES,
    private_absolute_root,
    read_canonical,
    write_exclusive,
)


MAX_LOCKS = 10_000
TRIAL_ID_PATTERN = re.compile(r"trial-[0-9a-f]{32}\Z")
LOCK_CREATION_COORDINATOR = ".creation.lock"


def validate_trial_id(trial_id: Any) -> str:
    if type(trial_id) is not str or TRIAL_ID_PATTERN.fullmatch(trial_id) is None:
        raise DevelopmentRuntimeError("TRIAL_ID_INVALID")
    return trial_id


def initialize_result_runtime(root: str | Path, *, acknowledgement: str) -> dict[str, Any]:
    if acknowledgement != ACK_INITIALIZE_RESULTS:
        raise DevelopmentRuntimeError("RESULT_RUNTIME_INITIALIZATION_ACKNOWLEDGEMENT_REQUIRED")
    runtime = private_absolute_root(root, must_exist=False, label="RESULT_ROOT")
    if runtime.exists():
        if not runtime.is_dir() or runtime.is_symlink() or stat.S_IMODE(runtime.stat().st_mode) != 0o700:
            raise DevelopmentRuntimeError("RESULT_ROOT_MODE_INVALID")
        if any(runtime.iterdir()):
            raise DevelopmentRuntimeError("RESULT_RUNTIME_NOT_EMPTY")
    else:
        runtime.mkdir(parents=True, mode=0o700)
        os.chmod(runtime, 0o700)
    locks = runtime / ".locks"
    locks.mkdir(mode=0o700)
    os.chmod(locks, 0o700)
    coordinator = locks / LOCK_CREATION_COORDINATOR
    fd = os.open(coordinator, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    return {"runtime_root": str(runtime), "lock_directory": ".locks", "initialized": True}


def validate_result_runtime(root: str | Path) -> Path:
    runtime = private_absolute_root(root, must_exist=True, label="RESULT_ROOT")
    locks = runtime / ".locks"
    if locks.is_symlink() or not locks.is_dir() or stat.S_IMODE(locks.stat().st_mode) != 0o700:
        raise DevelopmentRuntimeError("RESULT_RUNTIME_LAYOUT_INVALID")
    coordinator = locks / LOCK_CREATION_COORDINATOR
    if coordinator.is_symlink() or not coordinator.is_file() or stat.S_IMODE(coordinator.stat().st_mode) != 0o600:
        raise DevelopmentRuntimeError("LOCK_COORDINATOR_INVALID")
    entries = [entry for entry in locks.iterdir() if entry.name != LOCK_CREATION_COORDINATOR]
    if len(entries) > MAX_LOCKS:
        raise DevelopmentRuntimeError("LOCK_COUNT_LIMIT")
    for entry in entries:
        if (
            re.fullmatch(r"trial-[0-9a-f]{32}\.lock", entry.name) is None
            or entry.is_symlink() or not entry.is_file()
            or stat.S_IMODE(entry.stat().st_mode) != 0o600
        ):
            raise DevelopmentRuntimeError("LOCK_FILE_INVALID")
    return runtime


def trial_directory(runtime: Path, trial_id: str, *, create: bool) -> Path:
    validate_trial_id(trial_id)
    path = runtime / trial_id
    if path.parent != runtime or path.resolve(strict=False).parent != runtime.resolve(strict=True):
        raise DevelopmentRuntimeError("TRIAL_ID_INVALID")
    if create and not path.exists():
        path.mkdir(mode=0o700)
        os.chmod(path, 0o700)
    if path.exists() and (path.is_symlink() or not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o700):
        raise DevelopmentRuntimeError("TRIAL_RESULT_DIRECTORY_INVALID")
    return path


@contextmanager
def trial_lock(
    runtime_root: str | Path, trial_id: str, *, ledger_path: str | Path,
    timeout_seconds: float = 10.0,
) -> Iterator[Path]:
    # Validate the exact M94 identity before runtime inspection or any lock-file
    # filesystem operation.  Malformed caller input therefore creates nothing.
    validate_trial_id(trial_id)
    # A syntactically valid identity still receives no filesystem footprint
    # until the hardened, read-only M94 ledger proves that trial exists.
    from .authority import read_trial_binding
    read_trial_binding(ledger_path, trial_id, allow_completed=True)
    runtime = validate_result_runtime(runtime_root)
    locks = runtime / ".locks"
    lock_path = locks / f"{trial_id}.lock"
    if lock_path.parent != locks or lock_path.resolve(strict=False).parent != locks.resolve(strict=True) or lock_path.is_symlink():
        raise DevelopmentRuntimeError("LOCK_FILE_INVALID")
    nofollow = os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0
    fd: int | None = None
    try:
        if lock_path.exists():
            fd = os.open(lock_path, os.O_RDWR | nofollow)
        else:
            coordinator_fd = os.open(locks / LOCK_CREATION_COORDINATOR, os.O_RDWR | nofollow)
            try:
                fcntl.flock(coordinator_fd, fcntl.LOCK_EX)
                # Revalidate and count under the fixed creation coordinator so
                # different-trial creators cannot race beyond MAX_LOCKS.
                validate_result_runtime(runtime)
                if lock_path.exists():
                    fd = os.open(lock_path, os.O_RDWR | nofollow)
                else:
                    count = sum(
                        1 for entry in locks.iterdir()
                        if entry.name != LOCK_CREATION_COORDINATOR
                    )
                    if count >= MAX_LOCKS:
                        raise DevelopmentRuntimeError("LOCK_COUNT_LIMIT")
                    fd = os.open(
                        lock_path,
                        os.O_RDWR | os.O_CREAT | os.O_EXCL | nofollow,
                        0o600,
                    )
            finally:
                fcntl.flock(coordinator_fd, fcntl.LOCK_UN)
                os.close(coordinator_fd)
    except DevelopmentRuntimeError:
        raise
    except OSError as error:
        raise DevelopmentRuntimeError("LOCK_FILE_INVALID") from error
    assert fd is not None
    try:
        os.fchmod(fd, 0o600)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise DevelopmentRuntimeError("LOCK_FILE_INVALID")
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if error.errno not in {errno.EAGAIN, errno.EACCES}:
                    raise DevelopmentRuntimeError("TRIAL_LOCK_FAILED") from error
                if time.monotonic() >= deadline:
                    raise DevelopmentRuntimeError("TRIAL_LOCK_TIMEOUT")
                time.sleep(0.01)
        # Required post-acquisition M94 reread. The orchestration layer performs
        # its own state-specific reread immediately after this generic proof.
        read_trial_binding(ledger_path, trial_id, allow_completed=True)
        yield runtime
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def claim_execution_spec(directory: Path, specification: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    path = directory / "execution-spec.json"
    raw = canonical_bytes(specification)
    if len(raw) > MAX_JSON_BYTES:
        raise DevelopmentRuntimeError("EXECUTION_SPEC_SIZE_LIMIT")
    if path.exists() or path.is_symlink():
        existing, existing_raw = read_canonical(path)
        if existing_raw != raw:
            raise DevelopmentRuntimeError("EXECUTION_SPEC_CONFLICT")
        return existing, True
    try:
        write_exclusive(path, raw)
    except FileExistsError:
        existing, existing_raw = read_canonical(path)
        if existing_raw != raw:
            raise DevelopmentRuntimeError("EXECUTION_SPEC_CONFLICT")
        return existing, True
    return dict(specification), False


def publish_artifact(directory: Path, name: str, value: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    if name not in {"event-ledger.json", "result.json"}:
        raise DevelopmentRuntimeError("ARTIFACT_NAME_INVALID")
    path = directory / name
    raw = canonical_bytes(value)
    if len(raw) > MAX_RESULT_BYTES:
        raise DevelopmentRuntimeError("ARTIFACT_SIZE_LIMIT", name)
    if path.exists() or path.is_symlink():
        existing, existing_raw = read_canonical(path)
        if existing_raw != raw:
            raise DevelopmentRuntimeError("ARTIFACT_PUBLICATION_CONFLICT", name)
        return existing, True
    try:
        write_exclusive(path, raw)
    except FileExistsError:
        existing, existing_raw = read_canonical(path)
        if existing_raw != raw:
            raise DevelopmentRuntimeError("ARTIFACT_PUBLICATION_CONFLICT", name)
        return existing, True
    return dict(value), False

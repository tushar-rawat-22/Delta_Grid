#!/usr/bin/env python3
"""Outbound-only DeltaGrid founder command agent with a fixed action registry."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SCHEMA_VERSION = 1
AUTHORITY_STATE = "NONE"
AGENT_ID = "founder-mac-v1"
KEYCHAIN_ACCOUNT = "deltagrid-founder-agent"
KEYCHAIN_SERVICES = {
    "access_client_id": "deltagrid-agent-access-client-id",
    "access_client_secret": "deltagrid-agent-access-client-secret",
    "hmac_key": "deltagrid-agent-hmac-key",
}
ACTION_IDS = (
    "VERIFY_CORE_STATUS",
    "VERIFY_M100_JOURNAL",
    "CAPTURE_M100_ONCE",
    "EXPORT_M100_BACKUP",
    "VERIFY_M100_BACKUP",
    "REFRESH_PUBLIC_PROJECTION",
    "VERIFY_PUBLIC_PROJECTION",
    "RUN_APPROVED_TEST_PROFILE",
    "SHOW_CONTRACT_IDENTITIES",
    "SHOW_WORKTREE_STATUS",
)
TERMINAL_SUCCESS = "SUCCEEDED"
TERMINAL_FAILURE = "FAILED"
TERMINAL_REJECTED = "REJECTED"


class AgentError(RuntimeError):
    """Fail-closed agent error carrying a stable non-secret code."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hmac_hex(key: str, message: str) -> str:
    return hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise AgentError("AGENT_CONFIG_MISSING")
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        raise AgentError("AGENT_CONFIG_PERMISSIONS_INVALID")
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "endpoint", "core_root", "m100_runtime_root", "projection_root", "backup_root",
        "m100_capture_gate", "m100_capture_config", "provider_runtime_root",
    }
    if set(value) != required:
        raise AgentError("AGENT_CONFIG_SHAPE_INVALID")
    if not isinstance(value["endpoint"], str) or not value["endpoint"].startswith("https://"):
        raise AgentError("AGENT_ENDPOINT_INVALID")
    for name in required - {"endpoint"}:
        if not isinstance(value[name], str) or not value[name].startswith("/"):
            raise AgentError("AGENT_PATH_INVALID")
    return value


def keychain_secret(name: str) -> str:
    service = KEYCHAIN_SERVICES[name]
    result = subprocess.run(
        ["/usr/bin/security", "find-generic-password", "-s", service, "-a", KEYCHAIN_ACCOUNT, "-w"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    value = result.stdout.rstrip("\n")
    if result.returncode != 0 or not value:
        raise AgentError(f"KEYCHAIN_{name.upper()}_MISSING")
    return value


def signed_request(
    endpoint: str,
    path: str,
    payload: dict[str, Any],
    credentials: dict[str, str],
    *,
    timeout: int = 30,
    transport_retries: int = 0,
) -> dict[str, Any]:
    if transport_retries < 0 or transport_retries > 3:
        raise AgentError("REMOTE_RETRY_POLICY_INVALID")
    body = canonical_json(payload).encode("utf-8")
    body_hash = hashlib.sha256(body).hexdigest()
    raw: bytes | None = None
    for attempt in range(transport_retries + 1):
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        message = f"POST\n{path}\n{timestamp}\n{nonce}\n{body_hash}"
        signature = hmac_hex(credentials["hmac_key"], message)
        request = Request(
            f"{endpoint.rstrip('/')}{path}",
            data=body,
            method="POST",
            headers={
                "content-type": "application/json",
                "user-agent": "DeltaGrid-Founder-Agent/1.0",
                "cf-access-client-id": credentials["access_client_id"],
                "cf-access-client-secret": credentials["access_client_secret"],
                "x-dg-agent-id": AGENT_ID,
                "x-dg-timestamp": timestamp,
                "x-dg-nonce": nonce,
                "x-dg-signature": signature,
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310 - endpoint is locally pinned config
                raw = response.read(32_768)
            break
        except HTTPError as error:
            raise AgentError(f"REMOTE_HTTP_{error.code}") from None
        except (URLError, TimeoutError):
            if attempt >= transport_retries:
                raise AgentError("REMOTE_UNAVAILABLE") from None
            time.sleep(0.2 * (attempt + 1))
    if raw is None:
        raise AgentError("REMOTE_UNAVAILABLE")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        raise AgentError("REMOTE_RESPONSE_INVALID") from None
    if not isinstance(value, dict):
        raise AgentError("REMOTE_RESPONSE_INVALID")
    return value


def git_output(core_root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(core_root), *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"},
    )
    if result.returncode != 0:
        raise AgentError("CORE_GIT_CHECK_FAILED")
    return result.stdout.strip()


def validate_command(command: dict[str, Any], config: dict[str, Any], hmac_key: str) -> None:
    required = {
        "command_id", "schema_version", "requested_action_id", "founder_user_id", "requested_at",
        "expires_at", "one_use_nonce", "expected_core_commit", "expected_authority_state",
        "parameter_json", "parameter_hash", "canonical_request_hash", "integrity_proof",
    }
    if set(command) != required:
        raise AgentError("COMMAND_SHAPE_INVALID")
    if command["schema_version"] != SCHEMA_VERSION:
        raise AgentError("COMMAND_SCHEMA_INVALID")
    if command["requested_action_id"] not in ACTION_IDS:
        raise AgentError("COMMAND_ACTION_INVALID")
    if command["expected_authority_state"] != AUTHORITY_STATE:
        raise AgentError("COMMAND_AUTHORITY_INVALID")
    if command["parameter_json"] != "{}" or command["parameter_hash"] != sha256_text("{}"):
        raise AgentError("COMMAND_PARAMETERS_INVALID")
    if not isinstance(command["expires_at"], str) or command["expires_at"] <= command["requested_at"]:
        raise AgentError("COMMAND_TIME_INVALID")
    if command["expires_at"] <= utc_now():
        raise AgentError("COMMAND_EXPIRED")

    core_root = Path(config["core_root"]).resolve(strict=True)
    actual_commit = git_output(core_root, "rev-parse", "HEAD")
    if actual_commit != command["expected_core_commit"]:
        raise AgentError("CORE_COMMIT_MISMATCH")
    if git_output(core_root, "status", "--porcelain=v1", "--untracked-files=normal"):
        raise AgentError("CORE_WORKTREE_DIRTY")

    request_fields = {
        key: command[key]
        for key in (
            "command_id", "schema_version", "requested_action_id", "founder_user_id", "requested_at",
            "expires_at", "one_use_nonce", "expected_core_commit", "expected_authority_state",
            "parameter_json", "parameter_hash",
        )
    }
    expected_request_hash = sha256_text(canonical_json(request_fields))
    if not hmac.compare_digest(expected_request_hash, str(command["canonical_request_hash"])):
        raise AgentError("COMMAND_CANONICAL_HASH_INVALID")
    proof_fields = {**request_fields, "canonical_request_hash": command["canonical_request_hash"]}
    expected_proof = hmac_hex(hmac_key, canonical_json(proof_fields))
    if not hmac.compare_digest(expected_proof, str(command["integrity_proof"])):
        raise AgentError("COMMAND_INTEGRITY_INVALID")


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def action_argv(action: str, config: dict[str, Any]) -> list[list[str]]:
    core = config["core_root"]
    python = str(Path(core) / "offchain/.venv/bin/python")
    runtime = config["m100_runtime_root"]
    backup_root = Path(config["backup_root"])
    projection_root = Path(config["projection_root"])
    if action == "VERIFY_CORE_STATUS":
        return [["/usr/bin/git", "-C", core, "status", "--short", "--branch"]]
    if action == "VERIFY_M100_JOURNAL":
        return [[python, "-m", "offchain.market_data_acquisition", "verify-journal", "--runtime-root", runtime]]
    if action == "CAPTURE_M100_ONCE":
        return [[
            "/usr/bin/python3", config["m100_capture_gate"], "--config",
            config["m100_capture_config"], "--source", "FOUNDER_AGENT",
        ]]
    if action == "EXPORT_M100_BACKUP":
        destination = backup_root / f"m100-{int(time.time())}.zip"
        return [[python, "-m", "offchain.market_data_acquisition", "export-backup", "--runtime-root", runtime, "--destination", str(destination), "--acknowledge", "EXPORT_ACQUISITION_BACKUP"]]
    if action == "VERIFY_M100_BACKUP":
        backups = sorted(backup_root.glob("m100-*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not backups:
            raise AgentError("M100_BACKUP_MISSING")
        return [[python, "-m", "offchain.market_data_acquisition", "verify-backup", "--path", str(backups[0])]]
    if action == "REFRESH_PUBLIC_PROJECTION":
        destination = projection_root / "snapshots" / f"projection-{int(time.time())}"
        return [[python, "-m", "offchain.public_projection", "export", "--destination", str(destination)]]
    if action == "VERIFY_PUBLIC_PROJECTION":
        snapshots = sorted((projection_root / "snapshots").glob("projection-*"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not snapshots:
            raise AgentError("PUBLIC_PROJECTION_MISSING")
        return [[python, "-m", "offchain.public_projection", "verify", "--path", str(snapshots[0])]]
    if action == "RUN_APPROVED_TEST_PROFILE":
        return [[python, "-m", "pytest", "-p", "no:cacheprovider", "offchain/tests", "-q"]]
    if action == "SHOW_CONTRACT_IDENTITIES":
        return [
            [python, "-m", "offchain.market_data_acquisition", "show-contract"],
            [python, "-m", "offchain.public_projection", "show-contract"],
        ]
    if action == "SHOW_WORKTREE_STATUS":
        return [["/usr/bin/git", "-C", core, "worktree", "list", "--porcelain"]]
    raise AgentError("COMMAND_ACTION_INVALID")


def run_action(action: str, config: dict[str, Any]) -> tuple[str, str, int, str]:
    outputs: list[bytes] = []
    started = time.monotonic()
    for argv in action_argv(action, config):
        result = subprocess.run(
            argv,
            cwd=config["core_root"],
            check=False,
            capture_output=True,
            timeout=3600,
            env={
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        outputs.extend((result.stdout, result.stderr))
        if result.returncode != 0:
            duration = int((time.monotonic() - started) * 1000)
            return TERMINAL_FAILURE, "ACTION_PROCESS_FAILED", duration, hashlib.sha256(b"".join(outputs)).hexdigest()
    duration = int((time.monotonic() - started) * 1000)
    return TERMINAL_SUCCESS, "ACTION_COMPLETED", duration, hashlib.sha256(b"".join(outputs)).hexdigest()


def receipt_directories(config: dict[str, Any]) -> tuple[Path, Path]:
    operator = Path(config["projection_root"]).parent / "operator"
    pending = operator / "pending-completions"
    history = operator / "history"
    for directory in (pending, history):
        if directory.exists() and directory.is_symlink():
            raise AgentError("AGENT_RECEIPT_DIRECTORY_INVALID")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return pending, history


def write_pending_receipt(config: dict[str, Any], receipt: dict[str, Any]) -> tuple[str, Path]:
    pending, _history = receipt_directories(config)
    raw = (canonical_json(receipt) + "\n").encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    destination = pending / f"{receipt['command_id']}.json"
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return digest, destination


def pending_completion(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 8192:
        raise AgentError("PENDING_RECEIPT_INVALID")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        raise AgentError("PENDING_RECEIPT_INVALID") from None
    required = {
        "agent_id", "command_id", "requested_action_id", "status", "terminal_code",
        "started_at", "completed_at", "duration_ms", "output_sha256", "authority_state",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise AgentError("PENDING_RECEIPT_INVALID")
    if value["agent_id"] != AGENT_ID or value["authority_state"] != AUTHORITY_STATE:
        raise AgentError("PENDING_RECEIPT_INVALID")
    if value["command_id"] != path.stem or value["requested_action_id"] not in ACTION_IDS:
        raise AgentError("PENDING_RECEIPT_INVALID")
    if value["status"] not in {TERMINAL_SUCCESS, TERMINAL_FAILURE, TERMINAL_REJECTED}:
        raise AgentError("PENDING_RECEIPT_INVALID")
    if not isinstance(value["duration_ms"], int) or not 0 <= value["duration_ms"] <= 86_400_000:
        raise AgentError("PENDING_RECEIPT_INVALID")
    if not isinstance(value["output_sha256"], str) or len(value["output_sha256"]) != 64:
        raise AgentError("PENDING_RECEIPT_INVALID")
    for field in ("terminal_code", "started_at", "completed_at"):
        if not isinstance(value[field], str) or not value[field]:
            raise AgentError("PENDING_RECEIPT_INVALID")
    return {
        "command_id": value["command_id"],
        "status": value["status"],
        "terminal_code": value["terminal_code"],
        "started_at": value["started_at"],
        "completed_at": value["completed_at"],
        "duration_ms": value["duration_ms"],
        "output_sha256": value["output_sha256"],
        "local_receipt_sha256": hashlib.sha256(raw).hexdigest(),
    }


def archive_pending_receipt(config: dict[str, Any], path: Path) -> None:
    pending, history = receipt_directories(config)
    if path.parent != pending or path.is_symlink():
        raise AgentError("PENDING_RECEIPT_INVALID")
    destination = history / path.name
    if destination.exists():
        raise AgentError("RECEIPT_HISTORY_CONFLICT")
    os.replace(path, destination)


def reconcile_pending_completions(config: dict[str, Any], credentials: dict[str, str]) -> None:
    pending, _history = receipt_directories(config)
    for path in sorted(pending.glob("*.json")):
        completion = pending_completion(path)
        remote = signed_request(
            config["endpoint"],
            "/agent/v1/complete",
            completion,
            credentials,
            transport_retries=2,
        )
        if remote.get("status") != completion["status"]:
            raise AgentError("COMMAND_RECEIPT_REJECTED")
        archive_pending_receipt(config, path)


def run_once(config_path: Path) -> dict[str, str]:
    config = load_config(config_path)
    credentials = {name: keychain_secret(name) for name in KEYCHAIN_SERVICES}
    reconcile_pending_completions(config, credentials)
    core_commit = git_output(Path(config["core_root"]), "rev-parse", "HEAD")
    response = signed_request(
        config["endpoint"],
        "/agent/v1/claim",
        {"authority_state": AUTHORITY_STATE, "core_commit": core_commit},
        credentials,
    )
    command = response.get("command")
    if command is None:
        return {"status": "IDLE"}
    if not isinstance(command, dict):
        raise AgentError("COMMAND_RESPONSE_INVALID")

    started_at = utc_now()
    try:
        validate_command(command, config, credentials["hmac_key"])
    except AgentError as error:
        status, code, duration_ms, output_sha = TERMINAL_REJECTED, str(error), 0, hashlib.sha256(b"").hexdigest()
    else:
        status = code = output_sha = ""
        duration_ms = 0

    start_response = signed_request(
        config["endpoint"],
        "/agent/v1/start",
        {"command_id": command["command_id"]},
        credentials,
        transport_retries=2,
    )
    if start_response.get("status") != "EXECUTING":
        return {"status": "REJECTED_LOCALLY", "code": "COMMAND_START_REJECTED"}

    if not status:
        try:
            status, code, duration_ms, output_sha = run_action(command["requested_action_id"], config)
        except (AgentError, OSError, subprocess.SubprocessError):
            status, code, duration_ms, output_sha = (
                TERMINAL_FAILURE,
                "ACTION_RUNTIME_FAILED",
                0,
                hashlib.sha256(b"").hexdigest(),
            )

    completed_at = utc_now()
    local = {
        "agent_id": AGENT_ID,
        "command_id": command["command_id"],
        "requested_action_id": command["requested_action_id"],
        "status": status,
        "terminal_code": code,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "output_sha256": output_sha,
        "authority_state": AUTHORITY_STATE,
    }
    _local_hash, _pending_path = write_pending_receipt(config, local)
    reconcile_pending_completions(config, credentials)
    return {"status": status, "code": code}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one outbound DeltaGrid founder-agent poll.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path.home() / ".deltagrid/operator/agent-config.json",
    )
    arguments = parser.parse_args()
    try:
        result = run_once(arguments.config)
    except (AgentError, json.JSONDecodeError, OSError, subprocess.SubprocessError):
        print('{"status":"FAILED_CLOSED"}')
        return 1
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())

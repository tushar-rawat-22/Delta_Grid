from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import sys
from unittest import mock
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import deltagrid_agent as agent


def test_action_registry_is_exact_and_contains_no_generic_executor() -> None:
    assert len(agent.ACTION_IDS) == 10
    assert "SHELL" not in agent.ACTION_IDS
    assert "PYTHON" not in agent.ACTION_IDS
    assert "SQL" not in agent.ACTION_IDS


def test_canonical_json_and_hmac_are_deterministic() -> None:
    value = {"z": 2, "a": {"y": 1, "x": 0}}
    assert agent.canonical_json(value) == '{"a":{"x":0,"y":1},"z":2}'
    expected = hmac.new(b"key", b"message", hashlib.sha256).hexdigest()
    assert agent.hmac_hex("key", "message") == expected


def test_config_requires_private_permissions_and_exact_shape(tmp_path: Path) -> None:
    path = tmp_path / "agent.json"
    value = {
        "endpoint": "https://founder.example.test",
        "core_root": "/core",
        "m100_runtime_root": "/runtime",
        "projection_root": "/projection",
        "backup_root": "/backups",
        "m100_capture_gate": "/release/m100_capture_gate.py",
        "m100_capture_config": "/capture-gate.json",
        "provider_runtime_root": "/provider-runtime",
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)
    assert agent.load_config(path) == value
    path.chmod(0o644)
    try:
        agent.load_config(path)
    except agent.AgentError as error:
        assert str(error) == "AGENT_CONFIG_PERMISSIONS_INVALID"
    else:
        raise AssertionError("public config permissions were accepted")


def test_action_argv_never_uses_a_command_value_as_executable_input(tmp_path: Path) -> None:
    core = tmp_path / "core"
    (core / "offchain/.venv/bin").mkdir(parents=True)
    config = {
        "core_root": str(core),
        "m100_runtime_root": str(tmp_path / "runtime"),
        "projection_root": str(tmp_path / "projection"),
        "backup_root": str(tmp_path / "backups"),
        "m100_capture_gate": str(tmp_path / "release/m100_capture_gate.py"),
        "m100_capture_config": str(tmp_path / "capture-gate.json"),
        "provider_runtime_root": str(tmp_path / "provider-runtime"),
    }
    for action in agent.ACTION_IDS:
        if action == "VERIFY_M100_BACKUP":
            (tmp_path / "backups").mkdir()
            (tmp_path / "backups/m100-1.zip").touch()
        if action == "VERIFY_PUBLIC_PROJECTION":
            (tmp_path / "projection/snapshots/projection-1").mkdir(parents=True)
        for argv in agent.action_argv(action, config):
            assert isinstance(argv, list)
            assert argv[0] in {
                "/usr/bin/git", "/usr/bin/python3", str(core / "offchain/.venv/bin/python"),
            }


def test_journal_and_capture_actions_use_the_correct_shared_gates(tmp_path: Path) -> None:
    core = tmp_path / "core"
    (core / "offchain/.venv/bin").mkdir(parents=True)
    config = {
        "core_root": str(core),
        "m100_runtime_root": str(tmp_path / "runtime"),
        "projection_root": str(tmp_path / "projection"),
        "backup_root": str(tmp_path / "backups"),
        "m100_capture_gate": str(tmp_path / "release/m100_capture_gate.py"),
        "m100_capture_config": str(tmp_path / "capture-gate.json"),
        "provider_runtime_root": str(tmp_path / "provider-runtime"),
    }
    journal = agent.action_argv("VERIFY_M100_JOURNAL", config)[0]
    assert "verify-journal" in journal
    assert "verify-runtime" not in journal
    capture = agent.action_argv("CAPTURE_M100_ONCE", config)[0]
    assert capture == [
        "/usr/bin/python3", config["m100_capture_gate"], "--config",
        config["m100_capture_config"], "--source", "FOUNDER_AGENT",
    ]
    assert "capture-once" not in capture


def test_stale_or_wrong_authority_command_fails_closed() -> None:
    command = {
        "command_id": "00000000-0000-4000-8000-000000000000",
        "schema_version": 1,
        "requested_action_id": "VERIFY_CORE_STATUS",
        "founder_user_id": "0" * 64,
        "requested_at": "2026-01-01T00:00:00.000Z",
        "expires_at": "2026-01-01T00:05:00.000Z",
        "one_use_nonce": "0" * 32,
        "expected_core_commit": "0" * 40,
        "expected_authority_state": "TRADING",
        "parameter_json": "{}",
        "parameter_hash": agent.sha256_text("{}"),
        "canonical_request_hash": "0" * 64,
        "integrity_proof": "0" * 64,
    }
    with mock.patch.object(agent, "git_output", return_value="0" * 40):
        try:
            agent.validate_command(command, {"core_root": "/"}, "k" * 32)
        except agent.AgentError as error:
            assert str(error) == "COMMAND_AUTHORITY_INVALID"
        else:
            raise AssertionError("authority expansion was accepted")


def test_signed_request_uses_explicit_non_browser_agent_identity() -> None:
    captured: list[Request] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit: int) -> bytes:
            return b'{"command":null}'

    def fake_open(request: Request, timeout: int):
        assert timeout == 30
        captured.append(request)
        return Response()

    credentials = {
        "access_client_id": "client-id",
        "access_client_secret": "client-secret",
        "hmac_key": "k" * 32,
    }
    with mock.patch.object(agent, "urlopen", side_effect=fake_open):
        result = agent.signed_request(
            "https://founder.example.test",
            "/agent/v1/claim",
            {"authority_state": "NONE", "core_commit": "0" * 40},
            credentials,
        )
    assert result == {"command": None}
    assert len(captured) == 1
    assert captured[0].get_header("User-agent") == "DeltaGrid-Founder-Agent/1.0"

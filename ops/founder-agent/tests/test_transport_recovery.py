from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from unittest import mock
from urllib.error import HTTPError, URLError
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import deltagrid_agent as agent


CREDENTIALS = {
    "access_client_id": "client-id",
    "access_client_secret": "client-secret",
    "hmac_key": "k" * 32,
}


class JsonResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def request_header(request: Request, name: str) -> str | None:
    wanted = name.lower()
    return next((value for key, value in request.header_items() if key.lower() == wanted), None)


def test_transport_retry_uses_fresh_nonce_after_network_failure() -> None:
    requests: list[Request] = []

    def fake_open(request: Request, timeout: int):
        assert timeout == 30
        requests.append(request)
        if len(requests) == 1:
            raise URLError("temporary outage")
        return JsonResponse({"status": "EXECUTING"})

    with (
        mock.patch.object(agent, "urlopen", side_effect=fake_open),
        mock.patch.object(agent.time, "sleep"),
        mock.patch.object(agent.secrets, "token_hex", side_effect=["a" * 32, "b" * 32]),
    ):
        result = agent.signed_request(
            "https://founder.example.test",
            "/agent/v1/start",
            {"command_id": "command-1"},
            CREDENTIALS,
            transport_retries=1,
        )

    assert result == {"status": "EXECUTING"}
    assert len(requests) == 2
    assert request_header(requests[0], "x-dg-nonce") == "a" * 32
    assert request_header(requests[1], "x-dg-nonce") == "b" * 32
    assert requests[0].data == requests[1].data


def test_http_error_is_not_blindly_retried() -> None:
    calls = 0

    def fake_open(_request: Request, timeout: int):
        nonlocal calls
        assert timeout == 30
        calls += 1
        raise HTTPError("https://founder.example.test", 409, "conflict", None, None)

    with mock.patch.object(agent, "urlopen", side_effect=fake_open):
        try:
            agent.signed_request(
                "https://founder.example.test",
                "/agent/v1/start",
                {"command_id": "command-1"},
                CREDENTIALS,
                transport_retries=3,
            )
        except agent.AgentError as error:
            assert str(error) == "REMOTE_HTTP_409"
        else:
            raise AssertionError("HTTP conflict was unexpectedly accepted")

    assert calls == 1


def local_receipt() -> dict[str, object]:
    return {
        "agent_id": agent.AGENT_ID,
        "command_id": "00000000-0000-4000-8000-000000000001",
        "requested_action_id": "VERIFY_CORE_STATUS",
        "status": agent.TERMINAL_SUCCESS,
        "terminal_code": "ACTION_COMPLETED",
        "started_at": "2026-08-23T17:00:00.000Z",
        "completed_at": "2026-08-23T17:00:01.000Z",
        "duration_ms": 1000,
        "output_sha256": "1" * 64,
        "authority_state": agent.AUTHORITY_STATE,
    }


def test_pending_completion_survives_failure_and_reconciles_before_archive(tmp_path: Path) -> None:
    config = {
        "projection_root": str(tmp_path / "projection"),
        "endpoint": "https://founder.example.test",
    }
    receipt = local_receipt()
    digest, pending_path = agent.write_pending_receipt(config, receipt)
    history_path = tmp_path / "operator" / "history" / pending_path.name
    assert pending_path.is_file()
    assert not history_path.exists()

    with mock.patch.object(agent, "signed_request", side_effect=agent.AgentError("REMOTE_UNAVAILABLE")):
        try:
            agent.reconcile_pending_completions(config, CREDENTIALS)
        except agent.AgentError as error:
            assert str(error) == "REMOTE_UNAVAILABLE"
        else:
            raise AssertionError("transport failure did not stop reconciliation")

    assert pending_path.is_file()
    assert not history_path.exists()

    seen: list[dict[str, object]] = []

    def acknowledge(_endpoint: str, path: str, payload: dict[str, object], _credentials: dict[str, str], **kwargs):
        assert path == "/agent/v1/complete"
        assert kwargs == {"transport_retries": 2}
        seen.append(payload)
        return {"status": agent.TERMINAL_SUCCESS}

    with mock.patch.object(agent, "signed_request", side_effect=acknowledge):
        agent.reconcile_pending_completions(config, CREDENTIALS)

    assert len(seen) == 1
    assert seen[0]["command_id"] == receipt["command_id"]
    assert seen[0]["local_receipt_sha256"] == digest
    assert not pending_path.exists()
    assert history_path.is_file()
    assert hashlib.sha256(history_path.read_bytes()).hexdigest() == digest


def test_history_collision_fails_closed_without_overwrite(tmp_path: Path) -> None:
    config = {"projection_root": str(tmp_path / "projection")}
    _digest, pending_path = agent.write_pending_receipt(config, local_receipt())
    _pending, history = agent.receipt_directories(config)
    destination = history / pending_path.name
    destination.write_text("preserved-history\n", encoding="utf-8")

    try:
        agent.archive_pending_receipt(config, pending_path)
    except agent.AgentError as error:
        assert str(error) == "RECEIPT_HISTORY_CONFLICT"
    else:
        raise AssertionError("history collision was overwritten")

    assert pending_path.is_file()
    assert destination.read_text(encoding="utf-8") == "preserved-history\n"

from __future__ import annotations

from email.message import Message
import json
from pathlib import Path
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import deltagrid_agent as agent
import private_provider_collector as collector


class Response:
    def __init__(self, raw: bytes):
        self.raw = raw
        self.headers = Message()
        self.headers["content-type"] = "application/json"

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit: int) -> bytes:
        return self.raw[:limit]


def config_file(tmp_path: Path) -> Path:
    value = {
        "endpoint": "https://founder.example.test",
        "core_root": str(tmp_path / "core"),
        "m100_runtime_root": str(tmp_path / "m100"),
        "projection_root": str(tmp_path / "projection"),
        "backup_root": str(tmp_path / "backups"),
        "m100_capture_gate": str(tmp_path / "release/m100_capture_gate.py"),
        "m100_capture_config": str(tmp_path / "capture-gate.json"),
        "provider_runtime_root": str(tmp_path / "providers"),
    }
    path = tmp_path / "agent.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)
    return path


def payloads() -> list[bytes]:
    sec = {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "dei": {
                "EntityPublicFloat": {
                    "units": {"USD": [{"filed": "2026-08-01", "val": 100}]},
                },
            },
            "us-gaap": {
                "Assets": {
                    "units": {"USD": [{"filed": "2026-08-02", "val": 200}]},
                },
            },
        },
    }
    treasury = {
        "data": [{
            "record_date": "2026-08-12",
            "debt_held_public_amt": "100.00",
            "intragov_hold_amt": "20.00",
            "tot_pub_debt_out_amt": "120.00",
        }],
        "meta": {"count": 1},
        "links": {"self": "fixed"},
    }
    return [json.dumps(sec).encode(), json.dumps(treasury).encode()]


def test_daily_collection_is_fixed_bounded_private_and_metadata_only(tmp_path: Path) -> None:
    responses = payloads()
    requested_urls: list[str] = []
    remote_calls: list[tuple[str, dict[str, object]]] = []

    def fake_open(request, timeout: int):
        assert timeout == 30
        requested_urls.append(request.full_url)
        expected_agent = (
            "DeltaGrid/1.0 operator@example.test"
            if request.full_url == collector.PROVIDERS[0]["url"]
            else collector.USER_AGENT
        )
        assert request.get_header("User-agent") == expected_agent
        return Response(responses[len(requested_urls) - 1])

    evidence_seen: set[str] = set()

    def fake_signed(_endpoint: str, path: str, payload: dict[str, object], _credentials: dict[str, str]):
        remote_calls.append((path, payload))
        if path == "/agent/v1/evidence":
            envelope_id = str(payload["envelope_id"])
            if envelope_id in evidence_seen:
                raise agent.AgentError("REMOTE_HTTP_409")
            evidence_seen.add(envelope_id)
            return {"status": "EVIDENCE_RECORDED", "envelope_id": envelope_id}
        return {"status": "PROVIDER_STATUS_RECORDED", "receipt_id": payload["receipt_id"]}

    path = config_file(tmp_path)
    with mock.patch.object(collector, "urlopen", side_effect=fake_open), mock.patch.object(
        collector, "remote_credentials", return_value={"hmac_key": "k" * 32},
    ), mock.patch.object(
        collector, "sec_user_agent", return_value="DeltaGrid/1.0 operator@example.test",
    ), mock.patch.object(agent, "signed_request", side_effect=fake_signed):
        first = collector.run_daily(path, capture_day="2026-08-13")
        second = collector.run_daily(path, capture_day="2026-08-13")

    assert [row["status"] for row in first] == ["OPERATIONAL", "OPERATIONAL"]
    assert [row["status"] for row in second] == ["ALREADY_ATTEMPTED_TODAY", "ALREADY_ATTEMPTED_TODAY"]
    assert requested_urls == [provider["url"] for provider in collector.PROVIDERS]
    assert len([call for call in remote_calls if call[0] == "/agent/v1/evidence"]) == 4
    assert len([call for call in remote_calls if call[0] == "/agent/v1/status"]) == 2
    for path_name, payload in remote_calls:
        transmitted = collector.canonical_json(payload)
        assert "100.00" not in transmitted
        assert "120.00" not in transmitted
        assert "val" not in payload
        assert payload["authority_state"] == "NONE"
        assert path_name in {"/agent/v1/evidence", "/agent/v1/status"}
    objects = list((tmp_path / "providers/raw-objects").glob("*/*.json"))
    assert len(objects) == 2
    assert any(b'"val": 200' in item.read_bytes() for item in objects)
    assert any(b'"120.00"' in item.read_bytes() for item in objects)


def test_strict_schema_rejects_wrong_sec_identity() -> None:
    provider = collector.PROVIDERS[0]
    raw = json.dumps({"cik": 1, "entityName": "Wrong", "facts": {}}).encode()
    try:
        collector.validate_payload(provider, raw)
    except collector.CollectorError as error:
        assert str(error) == "SEC_COMPANY_IDENTITY_INVALID"
    else:
        raise AssertionError("wrong SEC identity was accepted")


def test_sec_user_agent_is_private_identified_and_strict() -> None:
    completed = mock.Mock(returncode=0, stdout="DeltaGrid/1.0 operator@example.test\n")
    with mock.patch.object(collector.subprocess, "run", return_value=completed):
        assert collector.sec_user_agent() == "DeltaGrid/1.0 operator@example.test"
    completed.stdout = "browser-like-agent\n"
    with mock.patch.object(collector.subprocess, "run", return_value=completed):
        try:
            collector.sec_user_agent()
        except collector.CollectorError as error:
            assert str(error) == "SEC_IDENTIFIED_USER_AGENT_MISSING"
        else:
            raise AssertionError("unidentified SEC user agent was accepted")


def test_provider_failure_writes_local_and_remote_health_receipts(tmp_path: Path) -> None:
    path = config_file(tmp_path)
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_signed(_endpoint: str, route: str, payload: dict[str, object], _credentials: dict[str, str]):
        calls.append((route, payload))
        return {"status": "PROVIDER_STATUS_RECORDED", "receipt_id": payload["receipt_id"]}

    with mock.patch.object(collector, "fetch_provider", side_effect=collector.CollectorError("PROVIDER_HTTP_403")), mock.patch.object(
        collector, "remote_credentials", return_value={"hmac_key": "k" * 32},
    ), mock.patch.object(agent, "signed_request", side_effect=fake_signed):
        results = collector.run_daily(path, capture_day="2026-08-14")

    assert [result["code"] for result in results] == ["PROVIDER_HTTP_403", "PROVIDER_HTTP_403"]
    assert len(calls) == 2
    for route, payload in calls:
        assert route == "/agent/v1/status"
        assert payload["status"] == "FAILED"
        assert payload["latest_envelope_id"] is None
        assert payload["payload_sha256"] is None

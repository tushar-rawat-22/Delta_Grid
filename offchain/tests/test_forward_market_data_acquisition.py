from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
from types import MappingProxyType
from urllib.parse import parse_qs, urlsplit

import pytest

from offchain.market_data_acquisition import backup, core, journal, network, service


M100_HASH = "a" * 64
COMMIT = "b" * 40


def fake_contracts():
    return (
        MappingProxyType({"contract_id": "deltagrid-autonomy-constitution-v1"}),
        MappingProxyType({"contract_id": "deltagrid-autonomy-constitution-v2"}),
        MappingProxyType({"contract_id": "deltagrid-temporal-market-data-control-plane-v1"}),
        MappingProxyType(
            {
                "contract_id": "deltagrid-forward-market-data-acquisition-v1",
                "contract_hash_sha256": M100_HASH,
            }
        ),
    )


@pytest.fixture
def mocked_contracts(monkeypatch):
    monkeypatch.setattr(core, "load_contracts", fake_contracts)
    monkeypatch.setattr(journal, "load_contracts", fake_contracts)
    monkeypatch.setattr(service, "load_contracts", fake_contracts)
    monkeypatch.setattr(backup, "load_contracts", fake_contracts)
    return fake_contracts


class FakeResponse:
    def __init__(self, url: str, payload, status: int = 200, headers=None):
        self._url = url
        self._body = json.dumps(payload, separators=(",", ":")).encode()
        self._status = status
        self.headers = headers or {"Content-Type": "application/json", "X-MBX-USED-WEIGHT-1M": "5"}
        self._offset = 0

    def getcode(self):
        return self._status

    def geturl(self):
        return self._url

    def read(self, size=-1):
        if size is None or size < 0:
            size = len(self._body) - self._offset
        chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


class FakeOpener:
    def __init__(self, *, correction: bool = False, fail_path: str | None = None):
        self.calls: list[str] = []
        self.correction = correction
        self.fail_path = fail_path

    def open(self, request, timeout=None):
        url = request.full_url
        self.calls.append(url)
        parsed = urlsplit(url)
        params = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
        if self.fail_path and parsed.path == self.fail_path:
            raise OSError("synthetic transport failure")
        now_ms = int(time.time() * 1000)
        if parsed.path.endswith("/time"):
            return FakeResponse(url, {"serverTime": now_ms})
        if parsed.path == "/fapi/v1/fundingInfo":
            assert params == {}
            return FakeResponse(
                url,
                [
                    {
                        "symbol": symbol,
                        "adjustedFundingRateCap": "0.0075",
                        "adjustedFundingRateFloor": "-0.0075",
                        "fundingIntervalHours": 8,
                        "disclaimer": False,
                        "updateTime": now_ms if symbol != core.SYMBOLS[-1] else None,
                    }
                    for symbol in core.SYMBOLS
                ],
            )
        start = int(params.get("startTime", "0"))
        end = int(params.get("endTime", str(start + core.INTERVAL_MS - 1)))
        if parsed.path == "/fapi/v1/fundingRate":
            # A funding event only when one is naturally inside the requested range.
            event = start + min(8 * core.INTERVAL_MS, max(0, end - start))
            if event > end:
                return FakeResponse(url, [])
            return FakeResponse(
                url,
                [
                    {
                        "symbol": params["symbol"],
                        "fundingTime": event,
                        "fundingRate": "0.00010000" if not self.correction else "0.00020000",
                        "markPrice": "60000.0",
                        "rateType": "Regular",
                    }
                ],
            )
        close = min(start + core.INTERVAL_MS - 1, end)
        price = "100.0" if not self.correction else "101.0"
        row = [start, price, "110.0", "90.0", price, "12.0", close, "1200.0", 7, "6.0", "600.0", "0"]
        return FakeResponse(url, [row])


def _init(tmp_path: Path, mocked_contracts, monkeypatch) -> Path:
    root = tmp_path / "runtime"
    monkeypatch.setattr(journal, "repository_identity", lambda repository_root=None: COMMIT)
    monkeypatch.setattr(service, "repository_identity", lambda repository_root=None: COMMIT)
    journal.initialize_runtime(root)
    return root


def test_canonical_json_is_stable_and_strict():
    assert core.canonical_json({"b": 1, "a": [True, None]}) == '{"a":[true,null],"b":1}'
    assert core.canonical_hash({"a": 1}) == core.canonical_hash({"a": 1})
    with pytest.raises(core.AcquisitionError, match="JSON_DUPLICATE_KEY"):
        core.strict_json_load('{"a":1,"a":2}')


def test_deep_freeze_blocks_nested_mutation():
    source = {"a": [{"b": 1}]}
    frozen = core.deep_freeze(source)
    source["a"][0]["b"] = 2
    assert frozen["a"][0]["b"] == 1
    with pytest.raises(TypeError):
        frozen["a"][0]["b"] = 3


def test_response_receipt_hash_binds_nested_values():
    receipt = core.ResponseReceipt.create(
        request_id="req-1",
        host=core.SPOT_HOST,
        path="/api/v3/time",
        params={},
        requested_at="2026-08-08T10:00:00.000Z",
        received_at="2026-08-08T10:00:00.010Z",
        wall_start_ms=1,
        wall_end_ms=11,
        monotonic_duration_ms=10,
        clock_status=core.ClockStatus.HEALTHY,
        http_status=200,
        headers={"content-type": "application/json"},
        attempt_number=1,
        retry_exhausted=False,
        body_sha256="1" * 64,
        object_sha256="2" * 64,
        response_hash="3" * 64,
    )
    assert len(receipt.receipt_hash) == 64
    assert receipt.as_dict()["clock_status"] == "HEALTHY"


def test_unknown_endpoint_and_parameter_rejected():
    with pytest.raises(core.AcquisitionError, match="ENDPOINT_NOT_ALLOWED"):
        network.perform_request("trade", {}, opener=FakeOpener(), request_id="r", clock_status=core.ClockStatus.HEALTHY)
    with pytest.raises(core.AcquisitionError, match="REQUEST_PARAMETER_NOT_ALLOWED"):
        network.perform_request(
            "spot_time",
            {"apiKey": "x"},
            opener=FakeOpener(),
            request_id="r",
            clock_status=core.ClockStatus.HEALTHY,
        )


def test_endpoint_registry_contains_only_public_get_paths():
    assert set(network.ENDPOINTS) == {
        "spot_time",
        "spot_ohlcv",
        "futures_time",
        "perpetual_ohlcv",
        "mark_price_ohlcv",
        "index_price_ohlcv",
        "funding_rates",
        "funding_info",
    }
    assert {spec.host for spec in network.ENDPOINTS.values()} == {core.SPOT_HOST, core.FUTURES_HOST}
    assert all(spec.path.startswith("/") for spec in network.ENDPOINTS.values())



def test_public_capture_api_has_no_transport_injection_parameter():
    signature = inspect.signature(service.capture_once)
    assert "opener" not in signature.parameters
    assert "_capture_once_with_transport" not in __import__(
        "offchain.market_data_acquisition", fromlist=["__all__"]
    ).__all__


def test_provider_json_rejects_duplicate_keys_and_non_finite_numbers():
    with pytest.raises(core.AcquisitionError, match="JSON_DUPLICATE_KEY"):
        network.decode_json(b'{"serverTime":1,"serverTime":2}')
    with pytest.raises(core.AcquisitionError, match="JSON_NON_FINITE_NUMBER"):
        network.decode_json(b'{"serverTime":NaN}')


def test_runtime_inside_repository_is_rejected(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    inside = repo / "runtime"
    with pytest.raises(core.AcquisitionError, match="RUNTIME_ROOT_INSIDE_REPOSITORY"):
        journal.validate_runtime_root(inside, repository_root=repo)


def test_runtime_symlink_parent_is_rejected(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(core.AcquisitionError, match="RUNTIME_PARENT_SYMLINK"):
        journal.validate_runtime_root(link / "runtime", repository_root=tmp_path / "other")


def test_initialize_runtime_schema_and_modes(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    assert root.is_dir()
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    db = root / journal.JOURNAL_NAME
    assert stat.S_IMODE(db.stat().st_mode) == 0o600
    for relative in journal.RUNTIME_SUBDIRS:
        assert stat.S_IMODE((root / relative).stat().st_mode) == 0o700
    result = journal.verify_journal(root)
    assert result["verdict"] == "PASS"
    assert result["counts"]["capture_batches"] == 0


def test_nonempty_runtime_refused(tmp_path, mocked_contracts):
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "x").write_text("x")
    with pytest.raises(core.AcquisitionError, match="RUNTIME_NOT_EMPTY"):
        journal.initialize_runtime(root)


def test_raw_object_is_gzip_content_addressed_and_idempotent(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    with journal.Journal.open(root) as j:
        first = j.store_raw_body(b'{"a":1}', created_at="2026-08-08T10:00:00.000Z")
        second = j.store_raw_body(b'{"a":1}', created_at="2026-08-08T10:00:01.000Z")
        j.conn.commit()
        assert first[:2] == second[:2]
    verified = journal.verify_journal(root)
    assert verified["counts"]["raw_objects"] == 1


def test_orphan_raw_object_is_reported_not_deleted(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    orphan_dir = root / "objects" / "sha256" / "aa"
    orphan_dir.mkdir(mode=0o700)
    import gzip
    data = gzip.compress(b"orphan", mtime=0)
    orphan = orphan_dir / ("a" * 64 + ".gz")
    orphan.write_bytes(data)
    result = journal.verify_journal(root)
    assert result["orphan_object_count"] == 1
    assert orphan.exists()


def test_capture_requires_explicit_ack(tmp_path):
    with pytest.raises(core.AcquisitionError, match="CAPTURE_ACKNOWLEDGEMENT_REQUIRED"):
        service.capture_once(tmp_path / "x", acknowledgement="NO")



def test_capture_refuses_incomplete_prior_batch(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    with journal.Journal.open(root) as j:
        j.begin_batch("stale-batch", M100_HASH, COMMIT)
    with pytest.raises(core.AcquisitionError, match="INCOMPLETE_CAPTURE_BATCH_PRESENT"):
        service._capture_once_with_transport(
            root,
            acknowledgement=service.ACK_CAPTURE,
            opener=FakeOpener(),
        )


def test_capture_once_success_is_bounded_and_forward_only(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    opener = FakeOpener()
    summary = service._capture_once_with_transport(root, acknowledgement=service.ACK_CAPTURE, opener=opener)
    assert summary.status == "COMPLETE"
    assert summary.requests == 18
    assert len(opener.calls) == 18
    assert all(url.startswith("https://") for url in opener.calls)
    assert all("apiKey" not in url and "signature" not in url for url in opener.calls)
    with journal.Journal.open(root, readonly=True) as j:
        statuses = [row[0] for row in j.conn.execute("SELECT status FROM capture_batches")]
        assert statuses == ["COMPLETE"]
        assert j.conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] >= 12
        assert j.conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] == 15
        assert not list(j.conn.execute("SELECT * FROM observations WHERE available_at IS NULL"))


def test_first_run_does_not_backfill_old_history(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    opener = FakeOpener()
    summary = service._capture_once_with_transport(root, acknowledgement=service.ACK_CAPTURE, opener=opener)
    assert summary.end_event_time_exclusive_ms - summary.start_event_time_ms == core.INTERVAL_MS


def test_second_capture_revision_sweep_never_precedes_origin(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    first = service._capture_once_with_transport(root, acknowledgement=service.ACK_CAPTURE, opener=FakeOpener())
    second = service._capture_once_with_transport(root, acknowledgement=service.ACK_CAPTURE, opener=FakeOpener())
    assert second.start_event_time_ms >= first.start_event_time_ms


def test_provider_correction_appends_revision(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    service._capture_once_with_transport(root, acknowledgement=service.ACK_CAPTURE, opener=FakeOpener())
    service._capture_once_with_transport(root, acknowledgement=service.ACK_CAPTURE, opener=FakeOpener(correction=True))
    with journal.Journal.open(root, readonly=True) as j:
        rows = j.conn.execute(
            "SELECT logical_id,MAX(revision_number) AS r FROM observations GROUP BY logical_id"
        ).fetchall()
        assert any(int(row["r"]) >= 2 for row in rows)
        revised = j.conn.execute(
            "SELECT revision_number,supersedes_record_hash,available_at FROM observations WHERE revision_number=2 LIMIT 1"
        ).fetchone()
        assert revised is not None
        assert revised["supersedes_record_hash"] is not None


def test_failed_batch_receipts_survive_but_observations_do_not_poison_chain(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    failing = FakeOpener(fail_path="/fapi/v1/markPriceKlines")
    with pytest.raises(core.AcquisitionError):
        service._capture_once_with_transport(root, acknowledgement=service.ACK_CAPTURE, opener=failing)
    with journal.Journal.open(root, readonly=True) as j:
        assert j.conn.execute("SELECT status FROM capture_batches").fetchone()[0] == "FAILED"
        assert j.conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] > 0
        assert j.conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
    success = service._capture_once_with_transport(root, acknowledgement=service.ACK_CAPTURE, opener=FakeOpener())
    assert success.status == "COMPLETE"
    with journal.Journal.open(root, readonly=True) as j:
        assert j.conn.execute("SELECT MIN(revision_number) FROM observations").fetchone()[0] == 1



def test_observation_phase_failure_rolls_back_partial_authoritative_state(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    original = journal.Journal.add_observation
    triggered = {"value": False}

    def fail_after_insert(self, batch_id, candidate):
        result = original(self, batch_id, candidate)
        if not triggered["value"]:
            triggered["value"] = True
            raise core.AcquisitionError("SYNTHETIC_OBSERVATION_PHASE_FAILURE")
        return result

    monkeypatch.setattr(journal.Journal, "add_observation", fail_after_insert)
    with pytest.raises(core.AcquisitionError, match="SYNTHETIC_OBSERVATION_PHASE_FAILURE"):
        service._capture_once_with_transport(
            root,
            acknowledgement=service.ACK_CAPTURE,
            opener=FakeOpener(),
        )

    with journal.Journal.open(root, readonly=True) as j:
        batch = j.conn.execute(
            "SELECT status,observation_count FROM capture_batches"
        ).fetchone()
        assert batch["status"] == "FAILED"
        assert batch["observation_count"] == 0
        assert j.conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0
        assert j.conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] > 0


def test_unhealthy_provider_clock_fails_before_data_observations(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)

    class BadClock(FakeOpener):
        def open(self, request, timeout=None):
            parsed = urlsplit(request.full_url)
            if parsed.path.endswith("/time"):
                return FakeResponse(request.full_url, {"serverTime": int(time.time() * 1000) + 60_000})
            return super().open(request, timeout)

    with pytest.raises(core.AcquisitionError, match="PROVIDER_CLOCK_UNHEALTHY"):
        service._capture_once_with_transport(root, acknowledgement=service.ACK_CAPTURE, opener=BadClock())
    with journal.Journal.open(root, readonly=True) as j:
        assert j.conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0


def test_unknown_funding_rate_type_fails_closed():
    receipt = core.ResponseReceipt.create(
        request_id="r",
        host=core.FUTURES_HOST,
        path="/fapi/v1/fundingRate",
        params={"symbol": "BTCUSDT"},
        requested_at="2026-08-08T10:00:00.000Z",
        received_at="2026-08-08T10:00:00.010Z",
        wall_start_ms=1,
        wall_end_ms=11,
        monotonic_duration_ms=10,
        clock_status=core.ClockStatus.HEALTHY,
        http_status=200,
        headers={},
        attempt_number=1,
        retry_exhausted=False,
        body_sha256="1" * 64,
        object_sha256="2" * 64,
        response_hash="3" * 64,
    )
    with pytest.raises(core.AcquisitionError, match="FUNDING_RATE_TYPE_UNKNOWN"):
        service._normalize_funding(
            "BTCUSDT",
            {"symbol": "BTCUSDT", "fundingTime": 1000, "fundingRate": "0", "markPrice": "1", "rateType": "Mystery"},
            receipt=receipt,
            provider_as_of_ms=2000,
        )


def test_open_bar_is_excluded():
    receipt = core.ResponseReceipt.create(
        request_id="r",
        host=core.SPOT_HOST,
        path="/api/v3/klines",
        params={},
        requested_at="2026-08-08T10:00:00.000Z",
        received_at="2026-08-08T10:00:00.010Z",
        wall_start_ms=1,
        wall_end_ms=11,
        monotonic_duration_ms=10,
        clock_status=core.ClockStatus.HEALTHY,
        http_status=200,
        headers={},
        attempt_number=1,
        retry_exhausted=False,
        body_sha256="1" * 64,
        object_sha256="2" * 64,
        response_hash="3" * 64,
    )
    now = 10_000_000
    row = [now - 1000, "1", "1", "1", "1", "1", now - 100, "1", 1, "1", "1", "0"]
    assert service._normalize_bar(
        "spot_ohlcv", "BTCUSDT", row, receipt=receipt, provider_as_of_ms=now
    ) is None


def test_funding_interval_is_not_hardcoded():
    rows = service._funding_config_rows(
        [{"symbol": "BTCUSDT", "fundingIntervalHours": 4}], "BTCUSDT"
    )
    assert rows[0]["funding_interval_hours"] == 4


def test_backup_round_trip(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    service._capture_once_with_transport(root, acknowledgement=service.ACK_CAPTURE, opener=FakeOpener())
    destination = tmp_path / "backup.zip"
    result = backup.export_backup(root, destination, acknowledgement=backup.ACK_BACKUP)
    assert result["file_count"] >= 2
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    verified = backup.verify_backup(destination)
    assert verified["verdict"] == "PASS"


def test_backup_refuses_destination_inside_runtime(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    with pytest.raises(core.AcquisitionError, match="BACKUP_DESTINATION_INSIDE_RUNTIME"):
        backup.export_backup(
            root, root / "backups" / "x.zip", acknowledgement=backup.ACK_BACKUP
        )



def test_backup_refuses_destination_inside_repository(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(backup, "REPOSITORY_ROOT", repo)
    with pytest.raises(core.AcquisitionError, match="BACKUP_DESTINATION_INSIDE_REPOSITORY"):
        backup.export_backup(
            root,
            repo / "forward-evidence.zip",
            acknowledgement=backup.ACK_BACKUP,
        )


def test_backup_refuses_symlink_parent(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    target = tmp_path / "backup-target"
    target.mkdir()
    link = tmp_path / "backup-link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(core.AcquisitionError, match="BACKUP_DESTINATION_SYMLINK"):
        backup.export_backup(
            root,
            link / "forward-evidence.zip",
            acknowledgement=backup.ACK_BACKUP,
        )


def test_schema_rejects_extra_view(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    conn = sqlite3.connect(root / journal.JOURNAL_NAME)
    conn.execute("CREATE VIEW bad AS SELECT 1 AS x")
    conn.commit()
    conn.close()
    with pytest.raises(core.AcquisitionError, match="JOURNAL_UNEXPECTED_SCHEMA_OBJECT"):
        journal.Journal.open(root, readonly=True)


def test_verify_rejects_raw_corruption(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    with journal.Journal.open(root) as j:
        _, _, rel = j.store_raw_body(b"abc", created_at="2026-08-08T10:00:00.000Z")
        j.conn.commit()
    (root / rel).write_bytes(b"not gzip")
    with pytest.raises(core.AcquisitionError):
        journal.verify_journal(root)


def test_public_package_has_no_trading_or_credential_surface():
    import offchain.market_data_acquisition as package

    names = {name.lower() for name in package.__all__}
    prohibited = {"order", "trade", "credential", "account", "portfolio", "signal", "strategy"}
    assert not any(any(token in name for token in prohibited) for name in names)


def test_actual_contracts_load_when_repository_contracts_are_present():
    # In the generated package sandbox Mission 99 source contracts are absent.
    # In the real repository this becomes a mandatory lineage/hash test.
    if not core.AUTONOMY_V1_PATH.exists() or not core.MISSION99_PATH.exists():
        pytest.skip("base repository contracts not present in package-only sandbox")
    _, v2, m99, m100 = core.load_contracts()
    assert v2["authority_version"] == 2
    assert m100["authorization_state"]["public_market_data_collection"] is True
    assert m100["authorization_state"]["real_data_research_resolution"] is False
    assert m99["resolver"]["real_data_research_resolution"] is False


def test_required_request_parameters_are_enforced():
    with pytest.raises(core.AcquisitionError, match="REQUEST_PARAMETER_MISSING"):
        network.perform_request(
            "spot_ohlcv",
            {"symbol": "BTCUSDT"},
            opener=FakeOpener(),
            request_id="r",
            clock_status=core.ClockStatus.HEALTHY,
        )


def test_rate_limit_retry_attempts_are_returned_as_evidence(monkeypatch):
    class SequenceOpener:
        def __init__(self):
            self.count = 0

        def open(self, request, timeout=None):
            self.count += 1
            if self.count == 1:
                return FakeResponse(
                    request.full_url,
                    {"code": -1003, "msg": "rate limit"},
                    status=429,
                    headers={"Retry-After": "0.1", "Content-Type": "application/json"},
                )
            return FakeResponse(request.full_url, {"serverTime": int(time.time() * 1000)})

    body, receipt, _, attempts = network.perform_request(
        "spot_time",
        {},
        opener=SequenceOpener(),
        request_id="rate-limit-test",
        clock_status=core.ClockStatus.UNKNOWN,
        sleep=lambda seconds: None,
    )
    assert receipt.http_status == 200
    assert [item.receipt.http_status for item in attempts] == [429, 200]
    assert attempts[0].receipt.retry_exhausted is False


def test_http_418_stops_without_retry_and_retains_attempt_object():
    class BanOpener:
        def open(self, request, timeout=None):
            return FakeResponse(
                request.full_url,
                {"code": -1003, "msg": "banned"},
                status=418,
                headers={"Retry-After": "60"},
            )

    with pytest.raises(network.RequestFailed) as exc:
        network.perform_request(
            "spot_time",
            {},
            opener=BanOpener(),
            request_id="ban-test",
            clock_status=core.ClockStatus.UNKNOWN,
            sleep=lambda seconds: None,
        )
    assert exc.value.reason == "BINANCE_IP_BANNED"
    assert len(exc.value.attempts) == 1
    assert exc.value.attempts[0].receipt.http_status == 418


def test_receipt_rejects_time_regression():
    with pytest.raises(core.AcquisitionError, match="RECEIPT_TIME_REGRESSION"):
        core.ResponseReceipt.create(
            request_id="r",
            host=core.SPOT_HOST,
            path="/api/v3/time",
            params={},
            requested_at="2026-08-08T10:00:01.000Z",
            received_at="2026-08-08T10:00:00.000Z",
            wall_start_ms=1,
            wall_end_ms=2,
            monotonic_duration_ms=1,
            clock_status=core.ClockStatus.HEALTHY,
            http_status=200,
            headers={},
            attempt_number=1,
            retry_exhausted=False,
            body_sha256="1" * 64,
            object_sha256="2" * 64,
            response_hash="3" * 64,
        )


def test_funding_info_endpoint_has_no_query_parameters():
    assert network.ENDPOINTS["funding_info"].parameter_names == frozenset()
    assert network.ENDPOINTS["funding_info"].required_names == frozenset()
    url = network._request_url(network.ENDPOINTS["funding_info"], {})
    assert url == "https://fapi.binance.com/fapi/v1/fundingInfo"


def test_network_boundary_rejects_non_universe_symbol_and_interval():
    spec = network.ENDPOINTS["spot_ohlcv"]
    base = {"symbol": "BTCUSDT", "interval": "1h", "startTime": 0, "endTime": 1, "limit": 1}
    bad_symbol = dict(base, symbol="BNBUSDT")
    with pytest.raises(core.AcquisitionError, match="REQUEST_SYMBOL_NOT_ALLOWED"):
        network._request_url(spec, bad_symbol)
    bad_interval = dict(base, interval="5m")
    with pytest.raises(core.AcquisitionError, match="REQUEST_INTERVAL_NOT_ALLOWED"):
        network._request_url(spec, bad_interval)


def test_bar_schema_requires_exact_documented_tuple_and_numeric_strings():
    receipt = core.ResponseReceipt.create(
        request_id="r", host=core.SPOT_HOST, path="/api/v3/klines", params={},
        requested_at="2026-08-08T10:00:00.000Z", received_at="2026-08-08T10:00:00.010Z",
        wall_start_ms=1, wall_end_ms=11, monotonic_duration_ms=10,
        clock_status=core.ClockStatus.HEALTHY, http_status=200, headers={}, attempt_number=1,
        retry_exhausted=False, body_sha256="1"*64, object_sha256="2"*64, response_hash="3"*64,
    )
    with pytest.raises(core.AcquisitionError, match="BAR_SCHEMA_INVALID"):
        service._normalize_bar("spot_ohlcv", "BTCUSDT", [1, "1", "1", "1", "1", "1", 2], receipt=receipt, provider_as_of_ms=10_000)
    bad = [0, {"x": 1}, "2", "0.5", "1", "1", 3_599_999, "1", 1, "1", "1", "0"]
    with pytest.raises(core.AcquisitionError, match="PROVIDER_DECIMAL_INVALID"):
        service._normalize_bar("spot_ohlcv", "BTCUSDT", bad, receipt=receipt, provider_as_of_ms=10_000_000)



def test_verify_journal_rejects_self_consistent_unallowlisted_receipt(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    service._capture_once_with_transport(
        root, acknowledgement=service.ACK_CAPTURE, opener=FakeOpener()
    )
    db = root / journal.JOURNAL_NAME
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM receipts WHERE path='/api/v3/time' LIMIT 1"
    ).fetchone()
    assert row is not None
    core_value = {
        "request_id": row["request_id"],
        "host": row["host"],
        "path": "/api/v3/account",
        "params": json.loads(row["params_json"]),
        "requested_at": row["requested_at"],
        "received_at": row["received_at"],
        "wall_start_ms": row["wall_start_ms"],
        "wall_end_ms": row["wall_end_ms"],
        "monotonic_duration_ms": row["monotonic_duration_ms"],
        "clock_status": row["clock_status"],
        "http_status": row["http_status"],
        "headers": json.loads(row["headers_json"]),
        "attempt_number": row["attempt_number"],
        "retry_exhausted": bool(row["retry_exhausted"]),
        "body_sha256": row["body_sha256"],
        "object_sha256": row["object_sha256"],
        "response_hash": core.canonical_hash(
            {
                "method": "GET",
                "host": row["host"],
                "path": "/api/v3/account",
                "params": json.loads(row["params_json"]),
                "body_sha256": row["body_sha256"],
            }
        ),
    }
    new_receipt_hash = core.canonical_hash(core_value)
    conn.execute(
        "UPDATE receipts SET path=?,response_hash=?,receipt_hash=? WHERE receipt_hash=?",
        (
            core_value["path"],
            core_value["response_hash"],
            new_receipt_hash,
            row["receipt_hash"],
        ),
    )
    conn.commit()
    conn.close()
    with pytest.raises(core.AcquisitionError, match="RECEIPT_ENDPOINT_NOT_ALLOWED"):
        journal.verify_journal(root)


def test_verify_journal_rejects_batch_count_and_checkpoint_corruption(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    service._capture_once_with_transport(
        root, acknowledgement=service.ACK_CAPTURE, opener=FakeOpener()
    )
    db = root / journal.JOURNAL_NAME

    conn = sqlite3.connect(db)
    conn.execute("UPDATE capture_batches SET request_count=request_count+1")
    conn.commit()
    conn.close()
    with pytest.raises(core.AcquisitionError, match="BATCH_REQUEST_COUNT_MISMATCH"):
        journal.verify_journal(root)

    root2 = tmp_path / "runtime2"
    journal.initialize_runtime(root2)
    service._capture_once_with_transport(
        root2, acknowledgement=service.ACK_CAPTURE, opener=FakeOpener()
    )
    conn = sqlite3.connect(root2 / journal.JOURNAL_NAME)
    key = conn.execute(
        "SELECT stream,symbol FROM checkpoints ORDER BY stream,symbol LIMIT 1"
    ).fetchone()
    assert key is not None
    conn.execute(
        "UPDATE checkpoints SET next_event_time_ms=-1 WHERE stream=? AND symbol=?",
        key,
    )
    conn.commit()
    conn.close()
    with pytest.raises(core.AcquisitionError, match="CHECKPOINT_VALUE_INVALID"):
        journal.verify_journal(root2)


def test_verify_journal_recomputes_receipt_and_funding_config_hashes(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    service._capture_once_with_transport(root, acknowledgement=service.ACK_CAPTURE, opener=FakeOpener())
    db = root / journal.JOURNAL_NAME
    conn = sqlite3.connect(db)
    receipt_hash = conn.execute("SELECT receipt_hash FROM receipts LIMIT 1").fetchone()[0]
    conn.execute("UPDATE receipts SET response_hash=? WHERE receipt_hash=?", ("f"*64, receipt_hash))
    conn.commit(); conn.close()
    with pytest.raises(core.AcquisitionError, match="RECEIPT_HASH_MISMATCH"):
        journal.verify_journal(root)

    # Build a fresh runtime to isolate derived funding-config tampering.
    root2 = tmp_path / "runtime2"
    journal.initialize_runtime(root2)
    service._capture_once_with_transport(root2, acknowledgement=service.ACK_CAPTURE, opener=FakeOpener())
    conn = sqlite3.connect(root2 / journal.JOURNAL_NAME)
    key = conn.execute("SELECT symbol,observed_at,receipt_hash FROM funding_configs LIMIT 1").fetchone()
    conn.execute("UPDATE funding_configs SET payload_json='{}' WHERE symbol=? AND observed_at=? AND receipt_hash=?", key)
    conn.commit(); conn.close()
    with pytest.raises(core.AcquisitionError, match="FUNDING_CONFIG_HASH_MISMATCH"):
        journal.verify_journal(root2)


def test_verify_journal_rejects_observation_attached_to_failed_batch(tmp_path, mocked_contracts, monkeypatch):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    service._capture_once_with_transport(root, acknowledgement=service.ACK_CAPTURE, opener=FakeOpener())
    conn = sqlite3.connect(root / journal.JOURNAL_NAME)
    batch = conn.execute("SELECT batch_id FROM capture_batches LIMIT 1").fetchone()[0]
    conn.execute("UPDATE capture_batches SET status='FAILED' WHERE batch_id=?", (batch,))
    conn.commit(); conn.close()
    with pytest.raises(core.AcquisitionError, match="FAILED_BATCH_OBSERVATION_PRESENT"):
        journal.verify_journal(root)

def test_funding_info_update_time_is_narrowly_accepted_and_preserved():
    rows = service._funding_config_rows(
        [
            {
                "symbol": "BTCUSDT",
                "adjustedFundingRateCap": "0.0075",
                "adjustedFundingRateFloor": "-0.0075",
                "fundingIntervalHours": 8,
                "disclaimer": False,
                "updateTime": 1760000000000,
            },
            {
                "symbol": "ETHUSDT",
                "adjustedFundingRateCap": "0.0075",
                "adjustedFundingRateFloor": "-0.0075",
                "fundingIntervalHours": 8,
                "disclaimer": False,
                "updateTime": None,
            },
        ],
        "BTCUSDT",
    )
    assert rows == [
        {
            "symbol": "BTCUSDT",
            "funding_interval_hours": 8,
            "funding_rate_cap": "0.0075",
            "funding_rate_floor": "-0.0075",
            "disclaimer": False,
            "provider_update_time_ms": 1760000000000,
        }
    ]

    null_rows = service._funding_config_rows(
        [{"symbol": "BTCUSDT", "fundingIntervalHours": 8, "updateTime": None}],
        "BTCUSDT",
    )
    assert null_rows[0]["provider_update_time_ms"] is None

    with pytest.raises(core.AcquisitionError, match="FUNDING_INFO_UPDATE_TIME_INVALID"):
        service._funding_config_rows(
            [{"symbol": "BTCUSDT", "fundingIntervalHours": 8, "updateTime": "bad"}],
            "BTCUSDT",
        )

    with pytest.raises(core.AcquisitionError, match="FUNDING_INFO_SCHEMA_INVALID"):
        service._funding_config_rows(
            [{"symbol": "BTCUSDT", "fundingIntervalHours": 8, "mysteryField": 1}],
            "BTCUSDT",
        )


def test_runtime_directory_mode_drift_fails_closed(
    tmp_path,
    mocked_contracts,
    monkeypatch,
):
    root = _init(tmp_path, mocked_contracts, monkeypatch)
    os.chmod(root / "objects", 0o755)
    with pytest.raises(core.AcquisitionError, match="RUNTIME_DIRECTORY_MODE_INVALID"):
        journal.Journal.open(root, readonly=True)


def test_actual_activation_remediation_contract_is_bound_when_present():
    if (
        not core.AUTONOMY_V1_PATH.exists()
        or not core.MISSION99_PATH.exists()
        or not core.MISSION100_REMEDIATION_PATH.exists()
    ):
        pytest.skip("base repository contracts not present in package-only sandbox")
    core.load_contracts()
    assert (
        core.MISSION100_REMEDIATION_HASH
        == "e69cf1810a355e5d460d565f432ce7f86ec72f45819f69c33c1c14d86294992f"
    )

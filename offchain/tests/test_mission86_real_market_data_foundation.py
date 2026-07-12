from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path

import pytest

from offchain.backtest.mission86_real_market_data_foundation import (
    DEFAULT_FUTURES_BASE_URL,
    DEFAULT_SPOT_BASE_URL,
    EXPECTED_CONTRACT_HASH,
    MISSION86_STATUS_COMPLETE,
    MISSION87_STATUS_READY,
    build_request_spec,
    load_authoritative_contract,
    normalize_bar,
    normalize_funding,
    request_json_page,
    run_foundation,
)
from offchain.research.funding_carry_research_contract import (
    CONTRACT_STATUS,
    MISSION85_CONTRACT,
    contract_hash,
)


START_MS = 1704067200000


class FakeResponse:
    def __init__(
        self,
        payload: object,
        status_code: int = 200,
    ) -> None:
        self.status_code = status_code
        self.headers = {
            "Content-Type": "application/json",
        }
        self.content = json.dumps(
            payload,
            separators=(",", ":"),
        ).encode("utf-8")


class FakeSession:
    def __init__(
        self,
        *,
        status_code: int = 200,
        fail_if_called: bool = False,
    ) -> None:
        self.status_code = status_code
        self.fail_if_called = fail_if_called
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.headers: dict[str, str] = {}

    def get(
        self,
        url: str,
        params: dict[str, object],
        timeout: float,
    ) -> FakeResponse:
        if self.fail_if_called:
            raise AssertionError(
                "network should not be called after completed checkpoints"
            )

        self.calls.append((url, dict(params)))

        if self.status_code != 200:
            return FakeResponse(
                {"error": "blocked"},
                status_code=self.status_code,
            )

        start_time = int(params["startTime"])

        if start_time != START_MS:
            return FakeResponse([])

        if url.endswith("/fundingRate"):
            symbol = str(params["symbol"])
            return FakeResponse(
                [
                    {
                        "symbol": symbol,
                        "fundingTime": START_MS,
                        "fundingRate": "0.00010000",
                        "markPrice": "100.0",
                    }
                ]
            )

        return FakeResponse(
            [
                [
                    START_MS,
                    "100.0",
                    "102.0",
                    "99.0",
                    "101.0",
                    "10.0",
                    START_MS + 3599999,
                    "1005.0",
                    20,
                    "4.0",
                    "402.0",
                    "0",
                ]
            ]
        )


def write_contract(path: Path) -> None:
    value = contract_hash(MISSION85_CONTRACT)

    assert value == EXPECTED_CONTRACT_HASH

    envelope = {
        "contract": MISSION85_CONTRACT,
        "contract_hash_sha256": value,
        "contract_status": CONTRACT_STATUS,
        "locked_at": "2026-07-12T00:00:00+00:00",
    }

    path.write_text(
        json.dumps(
            envelope,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_authoritative_contract_loads(
    tmp_path: Path,
) -> None:
    path = tmp_path / "contract.json"
    write_contract(path)

    contract = load_authoritative_contract(path)

    assert contract["universe"]["symbols"] == [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
    ]


def test_tampered_contract_is_rejected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "contract.json"
    write_contract(path)

    envelope = json.loads(
        path.read_text(encoding="utf-8")
    )
    envelope["contract"]["universe"]["symbols"].append(
        "XRPUSDT"
    )
    path.write_text(
        json.dumps(envelope),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="hash verification failed",
    ):
        load_authoritative_contract(path)


def test_spot_request_uses_public_market_endpoint() -> None:
    spec = build_request_spec(
        "spot_ohlcv",
        "BTCUSDT",
        START_MS,
        START_MS + 3600000,
    )

    assert spec.url == (
        f"{DEFAULT_SPOT_BASE_URL}/api/v3/klines"
    )
    assert spec.params["symbol"] == "BTCUSDT"
    assert "apiKey" not in spec.params
    assert "signature" not in spec.params


def test_index_request_uses_pair_parameter() -> None:
    spec = build_request_spec(
        "index_price_ohlcv",
        "ETHUSDT",
        START_MS,
        START_MS + 3600000,
    )

    assert spec.url == (
        f"{DEFAULT_FUTURES_BASE_URL}/"
        "fapi/v1/indexPriceKlines"
    )
    assert spec.params["pair"] == "ETHUSDT"
    assert "symbol" not in spec.params


def test_normalize_market_bar() -> None:
    row = normalize_bar(
        "spot_ohlcv",
        "BTCUSDT",
        [
            START_MS,
            "1",
            "2",
            "0.5",
            "1.5",
            "10",
            START_MS + 3599999,
            "15",
            5,
            "4",
            "6",
            "0",
        ],
    )

    assert row["open_time_ms"] == START_MS
    assert row["close_price"] == "1.5"
    assert row["volume"] == "10"
    assert row["trade_count"] == 5


def test_normalize_funding_rate() -> None:
    row = normalize_funding(
        "SOLUSDT",
        {
            "symbol": "SOLUSDT",
            "fundingTime": START_MS,
            "fundingRate": "-0.00005000",
            "markPrice": "150.0",
        },
    )

    assert row["funding_time_ms"] == START_MS
    assert row["funding_rate"] == "-0.00005000"
    assert row["mark_price"] == "150.0"


def test_http_451_fails_closed() -> None:
    session = FakeSession(status_code=451)
    spec = build_request_spec(
        "funding_rates",
        "BTCUSDT",
        START_MS,
        START_MS + 3600000,
    )

    with pytest.raises(
        RuntimeError,
        match="HTTP 451",
    ):
        request_json_page(
            session,
            spec,
            maximum_retries=0,
        )


def test_foundation_run_with_fake_public_data(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mission86.db"
    contract_path = tmp_path / "contract.json"
    data_root = tmp_path / "data"
    write_contract(contract_path)

    session = FakeSession()

    summary = run_foundation(
        db_path=db_path,
        contract_path=contract_path,
        data_root=data_root,
        run_label="mission86-test",
        session=session,
        request_delay_seconds=0,
        maximum_retries=0,
    )

    assert summary["run_status"] == (
        MISSION86_STATUS_COMPLETE
    )
    assert summary["mission87_status"] == (
        MISSION87_STATUS_READY
    )
    assert summary["stream_symbol_count"] == 15
    assert summary["market_bar_count"] == 12
    assert summary["funding_rate_count"] == 3
    assert summary["fail_check_count"] == 0
    assert summary["safety_breach_count"] == 0
    assert summary["certification_status"] == (
        "UNCERTIFIED_PENDING_MISSION87"
    )


def test_completed_run_resumes_without_network(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mission86.db"
    contract_path = tmp_path / "contract.json"
    data_root = tmp_path / "data"
    write_contract(contract_path)

    run_foundation(
        db_path=db_path,
        contract_path=contract_path,
        data_root=data_root,
        run_label="mission86-first",
        session=FakeSession(),
        request_delay_seconds=0,
        maximum_retries=0,
    )

    summary = run_foundation(
        db_path=db_path,
        contract_path=contract_path,
        data_root=data_root,
        run_label="mission86-second",
        session=FakeSession(fail_if_called=True),
        request_delay_seconds=0,
        maximum_retries=0,
    )

    assert summary["run_status"] == (
        MISSION86_STATUS_COMPLETE
    )


def test_raw_payloads_are_gzipped_and_linked(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mission86.db"
    contract_path = tmp_path / "contract.json"
    data_root = tmp_path / "data"
    write_contract(contract_path)

    run_foundation(
        db_path=db_path,
        contract_path=contract_path,
        data_root=data_root,
        run_label="mission86-test",
        session=FakeSession(),
        request_delay_seconds=0,
        maximum_retries=0,
    )

    with sqlite3.connect(db_path) as conn:
        raw_path, body_hash = conn.execute(
            """
            SELECT raw_path, body_sha256
            FROM mission86_raw_responses
            ORDER BY response_hash
            LIMIT 1
            """
        ).fetchone()

        missing_links = conn.execute(
            """
            SELECT COUNT(*)
            FROM mission86_market_bars AS bars
            LEFT JOIN mission86_raw_responses AS raw
              ON raw.response_hash = bars.response_hash
            WHERE raw.response_hash IS NULL
            """
        ).fetchone()[0]

    payload = gzip.decompress(
        Path(raw_path).read_bytes()
    )

    import hashlib

    assert hashlib.sha256(payload).hexdigest() == body_hash
    assert missing_links == 0


def test_manifest_does_not_claim_certification(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mission86.db"
    contract_path = tmp_path / "contract.json"
    data_root = tmp_path / "data"
    write_contract(contract_path)

    summary = run_foundation(
        db_path=db_path,
        contract_path=contract_path,
        data_root=data_root,
        run_label="mission86-test",
        session=FakeSession(),
        request_delay_seconds=0,
        maximum_retries=0,
    )

    envelope = json.loads(
        Path(summary["manifest_path"]).read_text(
            encoding="utf-8"
        )
    )

    manifest = envelope["manifest"]

    assert manifest["certification_status"] == (
        "UNCERTIFIED_PENDING_MISSION87"
    )
    assert (
        manifest["safety"]["backtesting_performed"]
        is False
    )
    assert (
        manifest["safety"]["holdout_evaluated"]
        is False
    )
    assert (
        manifest["safety"]["profitability_analyzed"]
        is False
    )


def test_mission86_documentation_is_authoritative() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    required_docs = (
        "README.md",
        "docs/PROJECT_SOURCE_OF_TRUTH.md",
        "docs/ROADMAP.md",
        "docs/MISSION_INDEX.md",
        "docs/ARCHITECTURE_STATE.md",
        "docs/INSTITUTIONAL_ALPHA_RESEARCH_PLAN.md",
        "docs/DECISION_LOG.md",
        "docs/CHANGELOG.md",
        "docs/DELTA_AUTONOMOUS_BOT_ROADMAP.md",
    )

    for relative_path in required_docs:
        text = (repo_root / relative_path).read_text(
            encoding="utf-8"
        )

        assert (
            "<!-- MISSION-86-DATA-FOUNDATION:START -->"
            in text
        )
        assert (
            "<!-- MISSION-86-DATA-FOUNDATION:END -->"
            in text
        )
        assert (
            "Mission 86 Real-Market Data Foundation"
            in text
        )
        assert (
            "Mission 87 Dataset Certification and Quality Gate"
            in text
        )
        assert "UNCERTIFIED_PENDING_MISSION87" in text

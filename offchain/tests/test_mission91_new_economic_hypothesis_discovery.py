from __future__ import annotations

import json
from pathlib import Path

from offchain.backtest.mission91_new_economic_hypothesis_discovery import (
    build_payload,
    selected_contract,
    write_artifacts,
)


def make_source(path: Path, variant: str, family: str) -> None:
    path.write_text(
        (
            "VARIANTS = [\n"
            "    {\n"
            f"        'variant_id': '{variant}',\n"
            f"        'family': '{family}',\n"
            "        'signal_type': 'TEST_SIGNAL',\n"
            "    }\n"
            "]\n"
        ),
        encoding="utf-8",
    )


def make_manifest(path: Path) -> None:
    payload = {
        "status": "PASS",
        "reference_trade_count": 54,
        "freqtrade_trade_count": 54,
        "total_mismatches": 0,
        "max_open_trades": 1,
        "safety_contract_preserved": True,
        "original_decision_preserved": True,
        "profitability_evaluated": False,
        "promotion_eligible": False,
        "validation_rows_read": 0,
        "holdout_rows_read": 0,
        "live_trading": False,
        "capital_deployment": False,
        "next_workstream": (
            "NEW_ECONOMIC_HYPOTHESIS_DISCOVERY"
        ),
    }

    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_selected_contract_is_frozen_and_small_account_safe() -> None:
    contract = selected_contract()

    assert contract["family"] == (
        "SESSION_CONDITIONAL_SPOT_EXPOSURE"
    )

    assert contract["primary_pair"] == "BTC/USDT"
    assert contract["variant_count"] == 6
    assert contract["maximum_position_count"] == 1
    assert contract["maximum_round_trips_per_day"] == 1
    assert contract["price_signal_independent"] is True
    assert contract["hyperopt"] is False
    assert contract["freqai"] is False
    assert contract["leverage"] == 1
    assert contract["shorting"] is False
    assert contract["futures"] is False
    assert contract["validation_rows_authorized"] == 0
    assert contract["holdout_rows_authorized"] == 0
    assert contract["live_trading_authorized"] is False


def test_build_payload_selects_exactly_one_family(
    tmp_path: Path,
) -> None:
    mission89 = tmp_path / "mission89.py"
    mission90 = tmp_path / "mission90.py"
    manifest = tmp_path / "manifest.json"

    make_source(
        mission89,
        "FUNDING_TEST",
        "FUNDING_CARRY",
    )

    make_source(
        mission90,
        "BREAKOUT_TEST",
        "VOLATILITY_BREAKOUT",
    )

    make_manifest(manifest)

    payload = build_payload(
        mission89_source=mission89,
        mission90_source=mission90,
        f4c3_manifest_path=manifest,
    )

    assert payload["status"] == (
        "COMPLETE_NEW_ECONOMIC_HYPOTHESIS_FAMILY_LOCKED"
    )

    assert payload["candidate_count"] == 6
    assert payload["selected_candidate_count"] == 1

    assert payload["selected_contract"]["family"] == (
        "SESSION_CONDITIONAL_SPOT_EXPOSURE"
    )

    assert payload["market_returns_evaluated"] is False
    assert payload["freqtrade_strategy_created"] is False
    assert payload["freqtrade_backtest_run"] is False
    assert payload["profitability_evaluated"] is False
    assert payload["promotion_eligible"] is False
    assert payload["validation_rows_read"] == 0
    assert payload["holdout_rows_read"] == 0

    assert "FUNDING_TEST" in (
        payload["prior_work_overlap_audit"][
            "mission89"
        ]["variant_ids"]
    )

    assert "BREAKOUT_TEST" in (
        payload["prior_work_overlap_audit"][
            "mission90"
        ]["variant_ids"]
    )


def test_write_artifacts_is_non_overwriting(
    tmp_path: Path,
) -> None:
    mission89 = tmp_path / "mission89.py"
    mission90 = tmp_path / "mission90.py"
    manifest = tmp_path / "manifest.json"

    make_source(
        mission89,
        "FUNDING_TEST",
        "FUNDING_CARRY",
    )

    make_source(
        mission90,
        "BREAKOUT_TEST",
        "VOLATILITY_BREAKOUT",
    )

    make_manifest(manifest)

    payload = build_payload(
        mission89_source=mission89,
        mission90_source=mission90,
        f4c3_manifest_path=manifest,
    )

    output = tmp_path / "output"

    report, decision = write_artifacts(
        payload,
        output,
    )

    assert report.is_file()
    assert decision.is_file()

    written = json.loads(
        report.read_text(encoding="utf-8")
    )

    assert written["protocol_hash"] == (
        payload["protocol_hash"]
    )

    assert "Mission 92" in decision.read_text(
        encoding="utf-8"
    )

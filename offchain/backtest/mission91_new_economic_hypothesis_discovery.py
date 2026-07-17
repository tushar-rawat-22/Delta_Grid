from __future__ import annotations

import argparse
import ast
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MISSION_ID = 91

MISSION_STATUS = (
    "COMPLETE_NEW_ECONOMIC_HYPOTHESIS_FAMILY_LOCKED"
)

DECISION = (
    "SELECT_SESSION_CONDITIONAL_SPOT_EXPOSURE_"
    "FOR_MISSION92_FALSIFICATION"
)

NEXT_WORKSTREAM = (
    "MISSION92_SESSION_PREMIUM_DEVELOPMENT_FALSIFICATION"
)


SESSION_WINDOWS = (
    {
        "variant_id": "UTC_SESSION_00_04",
        "entry_hour_utc": 0,
        "exit_hour_utc": 4,
    },
    {
        "variant_id": "UTC_SESSION_04_08",
        "entry_hour_utc": 4,
        "exit_hour_utc": 8,
    },
    {
        "variant_id": "UTC_SESSION_08_12",
        "entry_hour_utc": 8,
        "exit_hour_utc": 12,
    },
    {
        "variant_id": "UTC_SESSION_12_16",
        "entry_hour_utc": 12,
        "exit_hour_utc": 16,
    },
    {
        "variant_id": "UTC_SESSION_16_20",
        "entry_hour_utc": 16,
        "exit_hour_utc": 20,
    },
    {
        "variant_id": "UTC_SESSION_20_24",
        "entry_hour_utc": 20,
        "exit_hour_utc": 24,
    },
)


CANDIDATES = (
    {
        "candidate_id": "SESSION_CONDITIONAL_SPOT_EXPOSURE",
        "economic_basis": (
            "Recurring global participation, liquidity and "
            "information-arrival regimes may concentrate returns "
            "inside stable intraday windows."
        ),
        "decision": "SELECT_FOR_FALSIFICATION",
        "overlap_status": "DISTINCT_PRICE_INDEPENDENT_CLOCK_SIGNAL",
        "data_status": "AVAILABLE_CERTIFIED_1H_OHLCV",
        "small_account_status": "COMPATIBLE_LOW_TURNOVER",
    },
    {
        "candidate_id": "CROSS_SECTIONAL_RELATIVE_STRENGTH_ROTATION",
        "economic_basis": "Inter-asset momentum and leadership persistence.",
        "decision": "REJECT",
        "overlap_status": "OVERLAPS_MISSION90_MOMENTUM_DIRECTIONAL",
        "data_status": "AVAILABLE",
        "small_account_status": "TURNOVER_AND_SELECTION_RISK",
    },
    {
        "candidate_id": "LIQUIDITY_SHOCK_REBOUND",
        "economic_basis": (
            "Temporary order-flow and liquidity shocks may reverse."
        ),
        "decision": "REJECT",
        "overlap_status": "OVERLAPS_MISSION90_MEAN_REVERSION",
        "data_status": "OHLCV_PROXY_ONLY",
        "small_account_status": "HIGH_TURNOVER_AND_SLIPPAGE_RISK",
    },
    {
        "candidate_id": "VOLATILITY_MANAGED_MARKET_BETA",
        "economic_basis": (
            "Risk-adjusted exposure may improve through volatility scaling."
        ),
        "decision": "REJECT",
        "overlap_status": "OVERLAPS_MISSION90_VOLATILITY_TARGETING",
        "data_status": "AVAILABLE",
        "small_account_status": "RESIZING_TURNOVER_RISK",
    },
    {
        "candidate_id": "SCHEDULED_MACRO_EVENT_RESPONSE",
        "economic_basis": (
            "Scheduled macro announcements may concentrate volatility "
            "and information arrival."
        ),
        "decision": "DEFER",
        "overlap_status": "DISTINCT_EVENT_DRIVEN",
        "data_status": "EXTERNAL_CALENDAR_NOT_CERTIFIED",
        "small_account_status": "SPARSE_SAMPLE_AND_GAP_RISK",
    },
    {
        "candidate_id": "QUARTER_HOUR_ORDER_FLOW_EFFECT",
        "economic_basis": (
            "Periodic algorithmic order flow may create short-horizon "
            "predictability."
        ),
        "decision": "DEFER",
        "overlap_status": "DISTINCT_MICROSTRUCTURE",
        "data_status": "REQUIRES_SUB_HOURLY_ORDER_FLOW_OR_FUTURES_DATA",
        "small_account_status": "INCOMPATIBLE_WITH_CURRENT_COST_BUDGET",
    },
)


FORBIDDEN_DEPENDENCIES = (
    "funding_rate",
    "spot_perpetual_basis",
    "moving_average_crossover",
    "momentum_rank",
    "breakout_channel",
    "mean_reversion_oscillator",
    "rsi",
    "macd",
    "machine_learning",
    "freqai",
    "leverage",
    "shorting",
    "futures",
    "external_event_calendar",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def extract_prior_catalog(path: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    catalog: dict[str, set[str]] = {
        "variant_ids": set(),
        "families": set(),
        "signal_types": set(),
    }

    key_to_catalog = {
        "variant_id": "variant_ids",
        "family": "families",
        "signal_type": "signal_types",
    }

    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue

        for key, value in zip(node.keys, node.values):
            if not (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
            ):
                continue

            destination = key_to_catalog.get(key.value)

            if destination is None:
                continue

            if (
                isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                catalog[destination].add(value.value)

    return {
        "file": str(path),
        "sha256": sha256_file(path),
        "variant_ids": sorted(catalog["variant_ids"]),
        "families": sorted(catalog["families"]),
        "signal_types": sorted(catalog["signal_types"]),
    }


def validate_f4c3_manifest(
    manifest: dict[str, Any],
) -> None:
    required = {
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

    for key, expected in required.items():
        actual = manifest.get(key)

        if actual != expected:
            raise RuntimeError(
                f"F4C-3 manifest mismatch for {key}: "
                f"expected={expected!r}, actual={actual!r}"
            )


def selected_contract() -> dict[str, Any]:
    contract = {
        "contract_id": (
            "mission91-session-conditioned-spot-exposure-v1"
        ),
        "family": "SESSION_CONDITIONAL_SPOT_EXPOSURE",
        "economic_hypothesis": (
            "A stable four-hour UTC session may contain a "
            "repeatable positive spot return premium after costs "
            "because global participation, liquidity and "
            "information arrival vary systematically through the day."
        ),
        "claim_status": "UNTESTED_HYPOTHESIS_NOT_PROFITABILITY_CLAIM",
        "primary_pair": "BTC/USDT",
        "replication_pairs": [
            "ETH/USDT",
            "SOL/USDT",
        ],
        "timeframe": "1h",
        "variant_count": len(SESSION_WINDOWS),
        "variants": list(SESSION_WINDOWS),
        "entry_semantics": (
            "Enter at the session start open using a signal "
            "generated on the immediately preceding closed candle."
        ),
        "exit_semantics": (
            "Exit at the session end open using a signal "
            "generated on the immediately preceding closed candle."
        ),
        "position_model": "SPOT_LONG_OR_CASH",
        "maximum_position_count": 1,
        "maximum_round_trips_per_day": 1,
        "stake_model": "FIXED_SMALL_RESEARCH_NOTIONAL",
        "price_signal_independent": True,
        "clock_signal_only": True,
        "day_filter": "NONE_ALL_CALENDAR_DAYS",
        "parameter_optimization": False,
        "hyperopt": False,
        "freqai": False,
        "external_calendar": False,
        "leverage": 1,
        "shorting": False,
        "futures": False,
        "forbidden_dependencies": list(
            FORBIDDEN_DEPENDENCIES
        ),
        "cost_policy": {
            "authority": "MISSION88_EXECUTION_COST_MODEL",
            "normal_required": True,
            "conservative_required": True,
            "severe_required": True,
            "promotion_authority": "CONSERVATIVE",
            "severe_role": "DIAGNOSTIC_SURVIVABILITY",
        },
        "mission92_evaluation_protocol": {
            "development_only": True,
            "chronological_internal_split": "50_PERCENT_50_PERCENT",
            "primary_selection_asset": "BTC/USDT",
            "replication_assets": [
                "ETH/USDT",
                "SOL/USDT",
            ],
            "selected_variant_limit": 1,
            "minimum_primary_trade_count": 200,
            "primary_conservative_net_positive_both_halves": True,
            "primary_conservative_profit_factor_minimum": 1.15,
            "primary_conservative_max_drawdown_pct": 8.0,
            "replication_same_sign_minimum_assets": 1,
            "positive_calendar_quarter_fraction_minimum": 0.60,
            "single_quarter_profit_concentration_maximum": 0.35,
            "normal_cost_positive_required": True,
            "conservative_cost_positive_required": True,
            "severe_cost_positive_required": False,
            "lookahead_analysis_required_before_dry_run": True,
            "recursive_analysis_required_before_dry_run": True,
            "dry_run_authorized_by_mission91": False,
        },
        "validation_rows_authorized": 0,
        "holdout_rows_authorized": 0,
        "live_trading_authorized": False,
        "capital_deployment_authorized": False,
    }

    contract["contract_hash"] = canonical_hash(contract)
    return contract


def build_payload(
    *,
    mission89_source: Path,
    mission90_source: Path,
    f4c3_manifest_path: Path,
) -> dict[str, Any]:
    manifest = json.loads(
        f4c3_manifest_path.read_text(
            encoding="utf-8"
        )
    )

    validate_f4c3_manifest(manifest)

    prior_catalog = {
        "mission89": extract_prior_catalog(
            mission89_source
        ),
        "mission90": extract_prior_catalog(
            mission90_source
        ),
    }

    selected = selected_contract()

    selected_candidates = [
        item
        for item in CANDIDATES
        if item["decision"] == "SELECT_FOR_FALSIFICATION"
    ]

    if len(selected_candidates) != 1:
        raise RuntimeError(
            "Mission 91 must select exactly one family."
        )

    payload = {
        "schema_id": (
            "deltagrid-mission91-new-economic-"
            "hypothesis-discovery-v1"
        ),
        "mission_id": MISSION_ID,
        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "status": MISSION_STATUS,
        "decision": DECISION,
        "candidate_count": len(CANDIDATES),
        "selected_candidate_count": 1,
        "candidate_matrix": list(CANDIDATES),
        "selected_contract": selected,
        "prior_work_overlap_audit": prior_catalog,
        "selection_rationale": [
            (
                "Uses existing certified hourly spot data and "
                "requires no new paid or private data source."
            ),
            (
                "Clock-only signals are structurally distinct from "
                "funding carry, momentum, trend, breakout, "
                "mean-reversion and volatility-targeting families."
            ),
            (
                "One four-hour exposure per day limits turnover and "
                "is operationally compatible with a small account."
            ),
            (
                "The economic premise is plausible but empirical "
                "persistence remains unproven, so falsification is "
                "required before strategy or dry-run authorization."
            ),
        ],
        "f4c3_prerequisite": {
            "path": str(f4c3_manifest_path),
            "sha256": sha256_file(
                f4c3_manifest_path
            ),
            "status": manifest["status"],
            "trade_count": (
                manifest["freqtrade_trade_count"]
            ),
            "mismatch_count": (
                manifest["total_mismatches"]
            ),
            "mission90_decision_preserved": (
                manifest[
                    "original_decision_preserved"
                ]
            ),
        },
        "market_returns_evaluated": False,
        "freqtrade_strategy_created": False,
        "freqtrade_backtest_run": False,
        "profitability_evaluated": False,
        "promotion_eligible": False,
        "validation_rows_read": 0,
        "holdout_rows_read": 0,
        "live_trading": False,
        "capital_deployment": False,
        "next_workstream": NEXT_WORKSTREAM,
    }

    payload["protocol_hash"] = canonical_hash(
        {
            "candidate_matrix": payload[
                "candidate_matrix"
            ],
            "selected_contract": payload[
                "selected_contract"
            ],
            "selection_rationale": payload[
                "selection_rationale"
            ],
            "next_workstream": NEXT_WORKSTREAM,
        }
    )

    return payload


def write_artifacts(
    payload: dict[str, Any],
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    report_path = (
        output_dir
        / "MISSION91_HYPOTHESIS_DISCOVERY.json"
    )

    decision_path = (
        output_dir
        / "MISSION91_DECISION.md"
    )

    report_path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    contract = payload["selected_contract"]

    decision_path.write_text(
        "\n".join(
            [
                "# Mission 91 Decision",
                "",
                f"Status: `{payload['status']}`",
                "",
                f"Decision: `{payload['decision']}`",
                "",
                "## Selected family",
                "",
                f"`{contract['family']}`",
                "",
                (
                    "Primary research pair: "
                    f"`{contract['primary_pair']}`"
                ),
                "",
                (
                    "Replication pairs: "
                    + ", ".join(
                        f"`{pair}`"
                        for pair in contract[
                            "replication_pairs"
                        ]
                    )
                ),
                "",
                (
                    "Preregistered UTC windows: "
                    f"{contract['variant_count']}"
                ),
                "",
                "## Boundary",
                "",
                (
                    "No market returns were evaluated. "
                    "No Freqtrade strategy or backtest was run. "
                    "No validation or holdout rows were read."
                ),
                "",
                (
                    "Mission 92 is authorized only for "
                    "development-data falsification of the "
                    "frozen session family."
                ),
                "",
                (
                    "Next workstream: "
                    f"`{payload['next_workstream']}`"
                ),
                "",
                (
                    "Protocol hash: "
                    f"`{payload['protocol_hash']}`"
                ),
                "",
                (
                    "Contract hash: "
                    f"`{contract['contract_hash']}`"
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )

    return report_path, decision_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--mission89-source",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--mission90-source",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--f4c3-manifest",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    payload = build_payload(
        mission89_source=args.mission89_source,
        mission90_source=args.mission90_source,
        f4c3_manifest_path=args.f4c3_manifest,
    )

    report_path, decision_path = write_artifacts(
        payload,
        args.output_dir,
    )

    contract = payload["selected_contract"]

    print("MISSION91_FINAL_GATE_PASS")
    print(f"status={payload['status']}")
    print(f"decision={payload['decision']}")
    print(
        "selected_family="
        f"{contract['family']}"
    )
    print(
        "primary_pair="
        f"{contract['primary_pair']}"
    )
    print(
        "replication_pair_count="
        f"{len(contract['replication_pairs'])}"
    )
    print(
        "preregistered_variant_count="
        f"{contract['variant_count']}"
    )
    print(
        "candidate_count="
        f"{payload['candidate_count']}"
    )
    print(
        "selected_candidate_count="
        f"{payload['selected_candidate_count']}"
    )
    print("market_returns_evaluated=false")
    print("freqtrade_strategy_created=false")
    print("freqtrade_backtest_run=false")
    print("profitability_evaluated=false")
    print("promotion_eligible=false")
    print("validation_rows_read=0")
    print("holdout_rows_read=0")
    print("live_trading=false")
    print("capital_deployment=false")
    print(
        "protocol_hash="
        f"{payload['protocol_hash']}"
    )
    print(
        "contract_hash="
        f"{contract['contract_hash']}"
    )
    print(
        "next_workstream="
        f"{payload['next_workstream']}"
    )
    print(f"report={report_path}")
    print(f"decision_document={decision_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


MISSION_ID = 92

PRIMARY_PAIR = "BTC/USDT"

REPLICATION_PAIRS = (
    "ETH/USDT",
    "SOL/USDT",
)

PAIR_FILES = {
    "BTC/USDT": "BTC_USDT-1h.feather",
    "ETH/USDT": "ETH_USDT-1h.feather",
    "SOL/USDT": "SOL_USDT-1h.feather",
}

VARIANTS = (
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

RESEARCH_NOTIONAL_USD = 100.0

MINIMUM_TOTAL_PRIMARY_TRADES = 200
MINIMUM_HALF_PRIMARY_TRADES = 100

MINIMUM_PROFIT_FACTOR = 1.15
MAXIMUM_DRAWDOWN_PCT = 8.0

MINIMUM_POSITIVE_QUARTER_FRACTION = 0.60
MAXIMUM_SINGLE_QUARTER_CONCENTRATION = 0.35

MINIMUM_POSITIVE_REPLICATION_ASSETS = 1

BOOTSTRAP_REPETITIONS = 5000
BOOTSTRAP_BLOCK_DAYS = 7
BOOTSTRAP_BASE_SEED = 920_000


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
        allow_nan=False,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def load_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_feather(path)

    required = {
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }

    missing = required.difference(frame.columns)

    if missing:
        raise RuntimeError(
            f"{path} missing columns: {sorted(missing)}"
        )

    frame = frame.copy()

    frame["date"] = pd.to_datetime(
        frame["date"],
        utc=True,
    )

    frame = (
        frame
        .sort_values("date")
        .reset_index(drop=True)
    )

    if frame.empty:
        raise RuntimeError(
            f"{path} has no rows"
        )

    if frame["date"].duplicated().any():
        raise RuntimeError(
            f"{path} contains duplicate timestamps"
        )

    for column in (
        "open",
        "high",
        "low",
        "close",
        "volume",
    ):
        frame[column] = pd.to_numeric(
            frame[column],
            errors="raise",
        )

    if (
        frame[
            ["open", "high", "low", "close"]
        ]
        <= 0
    ).any().any():
        raise RuntimeError(
            f"{path} contains non-positive prices"
        )

    return frame


def load_pair_costs(
    snapshot: dict[str, Any],
) -> dict[str, dict[str, float]]:
    if snapshot["status"] != "PASS":
        raise RuntimeError(
            "Cost snapshot did not pass."
        )

    if snapshot["instrument"] != "SPOT_ONLY":
        raise RuntimeError(
            "Mission 92 requires spot-only costs."
        )

    if snapshot[
        "combined_spot_perpetual_cost_used"
    ] is not False:
        raise RuntimeError(
            "Combined spot-perpetual costs are prohibited."
        )

    result: dict[str, dict[str, float]] = {}

    for pair in PAIR_FILES:
        source = snapshot["pair_costs"][pair]

        costs = {
            "normal": float(
                source[
                    "normal_round_trip_cost_bps"
                ]
            ),
            "conservative": float(
                source[
                    "conservative_round_trip_cost_bps"
                ]
            ),
            "severe": float(
                source[
                    "severe_round_trip_cost_bps"
                ]
            ),
        }

        if not (
            0.0
            < costs["normal"]
            <= costs["conservative"]
            <= costs["severe"]
            < 1000.0
        ):
            raise RuntimeError(
                f"Invalid cost ordering for {pair}: "
                f"{costs}"
            )

        result[pair] = costs

    return result


def utc_midnight(session_date: date) -> pd.Timestamp:
    return pd.Timestamp(session_date).tz_localize(
        "UTC"
    )


def complete_common_dates(
    frames: dict[str, pd.DataFrame],
) -> list[date]:
    timestamps = {
        pair: set(frame["date"])
        for pair, frame in frames.items()
    }

    primary_midnights = sorted(
        {
            timestamp.date()
            for timestamp in timestamps[PRIMARY_PAIR]
            if (
                timestamp.hour == 0
                and timestamp.minute == 0
                and timestamp.second == 0
            )
        }
    )

    required_offsets = (
        0,
        4,
        8,
        12,
        16,
        20,
        24,
    )

    eligible: list[date] = []

    for session_date in primary_midnights:
        base = utc_midnight(session_date)

        required = [
            base + pd.Timedelta(hours=hours)
            for hours in required_offsets
        ]

        if all(
            all(
                timestamp in timestamps[pair]
                for timestamp in required
            )
            for pair in PAIR_FILES
        ):
            eligible.append(session_date)

    return eligible


def build_returns(
    *,
    pair: str,
    frame: pd.DataFrame,
    dates: list[date],
    variant: dict[str, Any],
    costs: dict[str, float],
) -> pd.DataFrame:
    opens = (
        frame
        .set_index("date")["open"]
        .astype(float)
        .to_dict()
    )

    rows: list[dict[str, Any]] = []

    for session_date in dates:
        base = utc_midnight(session_date)

        entry_time = base + pd.Timedelta(
            hours=int(
                variant["entry_hour_utc"]
            )
        )

        exit_time = base + pd.Timedelta(
            hours=int(
                variant["exit_hour_utc"]
            )
        )

        entry_price = float(opens[entry_time])
        exit_price = float(opens[exit_time])

        gross_return = (
            exit_price / entry_price
        ) - 1.0

        rows.append(
            {
                "pair": pair,
                "variant_id": (
                    variant["variant_id"]
                ),
                "session_date": session_date,
                "entry_time_utc": entry_time,
                "exit_time_utc": exit_time,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "gross_return": gross_return,
                "normal_return": (
                    gross_return
                    - costs["normal"] / 10_000.0
                ),
                "conservative_return": (
                    gross_return
                    - costs["conservative"]
                    / 10_000.0
                ),
                "severe_return": (
                    gross_return
                    - costs["severe"] / 10_000.0
                ),
            }
        )

    return pd.DataFrame(rows)


def profit_factor_metrics(
    values: np.ndarray,
) -> tuple[float | None, bool]:
    positive = float(
        values[values > 0].sum()
    )

    negative = float(
        -values[values < 0].sum()
    )

    if negative == 0.0:
        return (
            None,
            positive > 0.0,
        )

    return (
        positive / negative,
        False,
    )


def maximum_drawdown_pct(
    values: np.ndarray,
) -> float:
    if len(values) == 0:
        return 0.0

    equity = (
        1.0
        + np.cumsum(values)
    )

    peaks = np.maximum.accumulate(
        np.concatenate(
            (
                np.asarray([1.0]),
                equity,
            )
        )
    )[1:]

    drawdowns = (
        peaks - equity
    ) / peaks

    return float(
        100.0 * np.max(drawdowns)
    )


def quarter_label(session_date: date) -> str:
    quarter = (
        (session_date.month - 1) // 3
    ) + 1

    return (
        f"{session_date.year}Q{quarter}"
    )


def summarize(
    trades: pd.DataFrame,
    scenario: str,
) -> dict[str, Any]:
    column = f"{scenario}_return"

    values = trades[column].to_numpy(
        dtype=float
    )

    factor, unbounded = (
        profit_factor_metrics(values)
    )

    quarter_totals: dict[str, float] = {}

    for session_date, value in zip(
        trades["session_date"],
        values,
        strict=True,
    ):
        quarter = quarter_label(
            session_date
        )

        quarter_totals[quarter] = (
            quarter_totals.get(
                quarter,
                0.0,
            )
            + float(value)
        )

    positive_quarters = [
        value
        for value in quarter_totals.values()
        if value > 0.0
    ]

    positive_fraction = (
        len(positive_quarters)
        / len(quarter_totals)
        if quarter_totals
        else 0.0
    )

    positive_total = float(
        sum(positive_quarters)
    )

    concentration: float | None

    if positive_total > 0.0:
        concentration = (
            max(positive_quarters)
            / positive_total
        )
    else:
        concentration = None

    total = float(values.sum())

    return {
        "trade_count": int(len(values)),
        "net_pnl_usd": float(
            RESEARCH_NOTIONAL_USD * total
        ),
        "total_net_return_pct": float(
            100.0 * total
        ),
        "mean_net_return_bps": float(
            10_000.0 * values.mean()
        ),
        "median_net_return_bps": float(
            10_000.0 * np.median(values)
        ),
        "win_rate": float(
            np.mean(values > 0.0)
        ),
        "profit_factor": factor,
        "profit_factor_unbounded": (
            unbounded
        ),
        "maximum_drawdown_pct": (
            maximum_drawdown_pct(values)
        ),
        "positive_calendar_quarter_fraction": (
            float(positive_fraction)
        ),
        "single_quarter_profit_concentration": (
            concentration
        ),
        "quarter_net_returns_pct": {
            quarter: float(
                100.0 * value
            )
            for quarter, value in sorted(
                quarter_totals.items()
            )
        },
    }


def profit_factor_pass(
    metrics: dict[str, Any],
) -> bool:
    if metrics["profit_factor_unbounded"]:
        return True

    value = metrics["profit_factor"]

    return bool(
        value is not None
        and value >= MINIMUM_PROFIT_FACTOR
    )


def concentration_pass(
    metrics: dict[str, Any],
) -> bool:
    value = metrics[
        "single_quarter_profit_concentration"
    ]

    return bool(
        value is not None
        and value
        <= MAXIMUM_SINGLE_QUARTER_CONCENTRATION
    )


def half_one_eligible(
    summaries: dict[str, dict[str, Any]],
) -> bool:
    normal = summaries["normal"]
    conservative = summaries[
        "conservative"
    ]

    return all(
        (
            conservative["trade_count"]
            >= MINIMUM_HALF_PRIMARY_TRADES,
            normal["total_net_return_pct"]
            > 0.0,
            conservative[
                "total_net_return_pct"
            ]
            > 0.0,
            profit_factor_pass(
                conservative
            ),
            conservative[
                "maximum_drawdown_pct"
            ]
            <= MAXIMUM_DRAWDOWN_PCT,
        )
    )


def choose_candidate(
    summaries: dict[
        str,
        dict[str, dict[str, Any]],
    ],
) -> str | None:
    eligible = [
        variant_id
        for variant_id, metrics
        in summaries.items()
        if half_one_eligible(metrics)
    ]

    if not eligible:
        return None

    return max(
        eligible,
        key=lambda variant_id: (
            summaries[variant_id][
                "conservative"
            ]["mean_net_return_bps"],
            variant_id,
        ),
    )


def moving_block_bootstrap_pvalue(
    values: np.ndarray,
    *,
    seed: int,
) -> float:
    values = np.asarray(
        values,
        dtype=float,
    )

    if (
        len(values)
        < 2 * BOOTSTRAP_BLOCK_DAYS
    ):
        return 1.0

    observed = float(values.mean())
    centered = values - observed
    length = len(centered)

    rng = np.random.default_rng(seed)

    block_count = math.ceil(
        length / BOOTSTRAP_BLOCK_DAYS
    )

    offsets = np.arange(
        BOOTSTRAP_BLOCK_DAYS
    )

    bootstrap_means = np.empty(
        BOOTSTRAP_REPETITIONS,
        dtype=float,
    )

    for index in range(
        BOOTSTRAP_REPETITIONS
    ):
        starts = rng.integers(
            0,
            length,
            size=block_count,
        )

        indices = (
            starts[:, None]
            + offsets[None, :]
        ) % length

        sample = centered[
            indices.reshape(-1)[:length]
        ]

        bootstrap_means[index] = float(
            sample.mean()
        )

    return float(
        (
            1
            + np.sum(
                bootstrap_means
                >= observed
            )
        )
        / (BOOTSTRAP_REPETITIONS + 1)
    )


def holm_adjust(
    pvalues: dict[str, float],
) -> dict[str, float]:
    ordered = sorted(
        pvalues.items(),
        key=lambda item: (
            item[1],
            item[0],
        ),
    )

    count = len(ordered)
    adjusted: dict[str, float] = {}
    running = 0.0

    for rank, (name, value) in enumerate(
        ordered
    ):
        candidate = min(
            1.0,
            (count - rank) * value,
        )

        running = max(
            running,
            candidate,
        )

        adjusted[name] = float(running)

    return adjusted


def metric_row(
    *,
    pair: str,
    variant_id: str,
    segment: str,
    scenario: str,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "pair": pair,
        "variant_id": variant_id,
        "development_segment": segment,
        "scenario": scenario,
        **{
            key: value
            for key, value in metrics.items()
            if key
            != "quarter_net_returns_pct"
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--mission91-report",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--cost-snapshot",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--bridge-manifest",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--data-dir",
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

    if args.output_dir.exists():
        raise RuntimeError(
            f"Output exists: {args.output_dir}"
        )

    work_dir = args.output_dir.with_name(
        "." + args.output_dir.name + ".work"
    )

    if work_dir.exists():
        raise RuntimeError(
            f"Work output exists: {work_dir}"
        )

    mission91 = load_json(
        args.mission91_report
    )

    contract = mission91[
        "selected_contract"
    ]

    if contract["family"] != (
        "SESSION_CONDITIONAL_SPOT_EXPOSURE"
    ):
        raise RuntimeError(
            "Mission 91 family mismatch."
        )

    if contract["variant_count"] != 6:
        raise RuntimeError(
            "Mission 91 variant count changed."
        )

    cost_snapshot = load_json(
        args.cost_snapshot
    )

    pair_costs = load_pair_costs(
        cost_snapshot
    )

    work_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    protocol = {
        "schema_id": (
            "deltagrid-mission92-"
            "pair-specific-session-protocol-v2"
        ),
        "mission_id": MISSION_ID,
        "family": (
            "SESSION_CONDITIONAL_SPOT_EXPOSURE"
        ),
        "primary_pair": PRIMARY_PAIR,
        "replication_pairs": list(
            REPLICATION_PAIRS
        ),
        "variants": list(VARIANTS),
        "research_notional_usd": (
            RESEARCH_NOTIONAL_USD
        ),
        "development_split": (
            "FIRST_HALF_SELECTION_"
            "SECOND_HALF_CONFIRMATION"
        ),
        "selection_asset": PRIMARY_PAIR,
        "selected_variant_limit": 1,
        "pair_specific_costs_bps": (
            pair_costs
        ),
        "conservative_scenario_controls_promotion": (
            True
        ),
        "severe_scenario_role": (
            "DIAGNOSTIC_ONLY"
        ),
        "multiple_testing_diagnostic": {
            "method": (
                "MOVING_BLOCK_BOOTSTRAP_"
                "ONE_SIDED_HOLM_ADJUSTED"
            ),
            "repetitions": (
                BOOTSTRAP_REPETITIONS
            ),
            "block_days": (
                BOOTSTRAP_BLOCK_DAYS
            ),
            "promotion_gate": False,
        },
        "validation_rows_authorized": 0,
        "holdout_rows_authorized": 0,
        "freqtrade_strategy_authorized": False,
        "freqtrade_backtest_authorized": False,
        "dry_run_authorized": False,
        "live_trading_authorized": False,
        "capital_deployment_authorized": False,
    }

    protocol["protocol_hash"] = (
        canonical_hash(protocol)
    )

    protocol_path = (
        work_dir
        / "MISSION92_PROTOCOL_LOCK.json"
    )

    protocol_path.write_text(
        json.dumps(
            protocol,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    # Data access begins only after the protocol lock
    # and pair-specific costs are written.
    frames = {
        pair: load_frame(
            args.data_dir / filename
        )
        for pair, filename
        in PAIR_FILES.items()
    }

    data_hashes = {
        pair: sha256_file(
            args.data_dir / filename
        )
        for pair, filename
        in PAIR_FILES.items()
    }

    common_dates = complete_common_dates(
        frames
    )

    if len(common_dates) < (
        MINIMUM_TOTAL_PRIMARY_TRADES
    ):
        raise RuntimeError(
            "Insufficient complete development sessions: "
            f"{len(common_dates)}"
        )

    split_index = len(common_dates) // 2

    half_one_dates = (
        common_dates[:split_index]
    )

    half_two_dates = (
        common_dates[split_index:]
    )

    if (
        len(half_one_dates)
        < MINIMUM_HALF_PRIMARY_TRADES
        or len(half_two_dates)
        < MINIMUM_HALF_PRIMARY_TRADES
    ):
        raise RuntimeError(
            "Each chronological half must contain "
            "at least 100 complete sessions."
        )

    half_one_summaries: dict[
        str,
        dict[str, dict[str, Any]],
    ] = {}

    raw_pvalues: dict[str, float] = {}
    metric_rows: list[dict[str, Any]] = []

    for index, variant in enumerate(
        VARIANTS
    ):
        variant_id = str(
            variant["variant_id"]
        )

        trades = build_returns(
            pair=PRIMARY_PAIR,
            frame=frames[PRIMARY_PAIR],
            dates=half_one_dates,
            variant=variant,
            costs=pair_costs[PRIMARY_PAIR],
        )

        summaries = {
            scenario: summarize(
                trades,
                scenario,
            )
            for scenario in (
                "normal",
                "conservative",
                "severe",
            )
        }

        half_one_summaries[
            variant_id
        ] = summaries

        raw_pvalues[variant_id] = (
            moving_block_bootstrap_pvalue(
                trades[
                    "conservative_return"
                ].to_numpy(dtype=float),
                seed=(
                    BOOTSTRAP_BASE_SEED
                    + index
                ),
            )
        )

        for scenario, metrics in (
            summaries.items()
        ):
            metric_rows.append(
                metric_row(
                    pair=PRIMARY_PAIR,
                    variant_id=variant_id,
                    segment=(
                        "HALF_ONE_SELECTION"
                    ),
                    scenario=scenario,
                    metrics=metrics,
                )
            )

    adjusted_pvalues = holm_adjust(
        raw_pvalues
    )

    selected_variant_id = (
        choose_candidate(
            half_one_summaries
        )
    )

    selected_variant = next(
        (
            variant
            for variant in VARIANTS
            if variant["variant_id"]
            == selected_variant_id
        ),
        None,
    )

    confirmation: dict[str, Any] = {}
    replication: dict[str, Any] = {}
    final_gate_checks: dict[str, bool] = {}

    if selected_variant is None:
        decision = (
            "REJECT_ALL_SESSION_WINDOWS_"
            "DEVELOPMENT_HALF_ONE"
        )

        status = (
            "COMPLETE_SESSION_PREMIUM_"
            "DEVELOPMENT_FALSIFICATION_REJECTED"
        )

        promotion_eligible = False

        next_workstream = (
            "NEW_ECONOMIC_HYPOTHESIS_DISCOVERY_"
            "AFTER_SESSION_REJECTION"
        )

    else:
        variant_id = str(
            selected_variant["variant_id"]
        )

        half_two_trades = build_returns(
            pair=PRIMARY_PAIR,
            frame=frames[PRIMARY_PAIR],
            dates=half_two_dates,
            variant=selected_variant,
            costs=pair_costs[PRIMARY_PAIR],
        )

        full_primary_trades = build_returns(
            pair=PRIMARY_PAIR,
            frame=frames[PRIMARY_PAIR],
            dates=common_dates,
            variant=selected_variant,
            costs=pair_costs[PRIMARY_PAIR],
        )

        half_two_metrics = {
            scenario: summarize(
                half_two_trades,
                scenario,
            )
            for scenario in (
                "normal",
                "conservative",
                "severe",
            )
        }

        full_primary_metrics = {
            scenario: summarize(
                full_primary_trades,
                scenario,
            )
            for scenario in (
                "normal",
                "conservative",
                "severe",
            )
        }

        for segment, summaries in (
            (
                "HALF_TWO_CONFIRMATION",
                half_two_metrics,
            ),
            (
                "FULL_DEVELOPMENT",
                full_primary_metrics,
            ),
        ):
            for scenario, metrics in (
                summaries.items()
            ):
                metric_rows.append(
                    metric_row(
                        pair=PRIMARY_PAIR,
                        variant_id=variant_id,
                        segment=segment,
                        scenario=scenario,
                        metrics=metrics,
                    )
                )

        positive_replication_assets = 0

        for pair in REPLICATION_PAIRS:
            trades = build_returns(
                pair=pair,
                frame=frames[pair],
                dates=common_dates,
                variant=selected_variant,
                costs=pair_costs[pair],
            )

            summaries = {
                scenario: summarize(
                    trades,
                    scenario,
                )
                for scenario in (
                    "normal",
                    "conservative",
                    "severe",
                )
            }

            replication[pair] = {
                "costs_bps": pair_costs[pair],
                "metrics": summaries,
            }

            if (
                summaries["conservative"][
                    "total_net_return_pct"
                ]
                > 0.0
            ):
                positive_replication_assets += 1

            for scenario, metrics in (
                summaries.items()
            ):
                metric_rows.append(
                    metric_row(
                        pair=pair,
                        variant_id=variant_id,
                        segment=(
                            "FULL_DEVELOPMENT_"
                            "REPLICATION"
                        ),
                        scenario=scenario,
                        metrics=metrics,
                    )
                )

        half_one = half_one_summaries[
            variant_id
        ]

        half_two = half_two_metrics
        full = full_primary_metrics

        full_conservative = full[
            "conservative"
        ]

        final_gate_checks = {
            "minimum_primary_trade_count": (
                full_conservative[
                    "trade_count"
                ]
                >= MINIMUM_TOTAL_PRIMARY_TRADES
            ),
            "normal_positive_full_development": (
                full["normal"][
                    "total_net_return_pct"
                ]
                > 0.0
            ),
            "conservative_positive_half_one": (
                half_one["conservative"][
                    "total_net_return_pct"
                ]
                > 0.0
            ),
            "conservative_positive_half_two": (
                half_two["conservative"][
                    "total_net_return_pct"
                ]
                > 0.0
            ),
            "conservative_positive_full": (
                full_conservative[
                    "total_net_return_pct"
                ]
                > 0.0
            ),
            "conservative_profit_factor": (
                profit_factor_pass(
                    full_conservative
                )
            ),
            "conservative_maximum_drawdown": (
                full_conservative[
                    "maximum_drawdown_pct"
                ]
                <= MAXIMUM_DRAWDOWN_PCT
            ),
            "positive_calendar_quarter_fraction": (
                full_conservative[
                    "positive_calendar_quarter_fraction"
                ]
                >= MINIMUM_POSITIVE_QUARTER_FRACTION
            ),
            "single_quarter_profit_concentration": (
                concentration_pass(
                    full_conservative
                )
            ),
            "replication_same_sign": (
                positive_replication_assets
                >= MINIMUM_POSITIVE_REPLICATION_ASSETS
            ),
        }

        promotion_eligible = all(
            final_gate_checks.values()
        )

        confirmation = {
            "half_one_metrics": half_one,
            "half_two_metrics": half_two,
            "full_primary_metrics": (
                full_primary_metrics
            ),
            "positive_replication_asset_count": (
                positive_replication_assets
            ),
        }

        if promotion_eligible:
            decision = (
                "LOCK_PROVISIONAL_SESSION_WINDOW_"
                "DEVELOPMENT_CANDIDATE"
            )

            status = (
                "COMPLETE_SESSION_PREMIUM_"
                "DEVELOPMENT_CANDIDATE_LOCKED"
            )

            next_workstream = (
                "MISSION93_SESSION_ENGINE_TRANSLATION_"
                "AND_BIAS_GATES"
            )

        else:
            decision = (
                "REJECT_SELECTED_SESSION_WINDOW_"
                "DEVELOPMENT_CONFIRMATION"
            )

            status = (
                "COMPLETE_SESSION_PREMIUM_"
                "DEVELOPMENT_FALSIFICATION_REJECTED"
            )

            next_workstream = (
                "NEW_ECONOMIC_HYPOTHESIS_DISCOVERY_"
                "AFTER_SESSION_REJECTION"
            )

    pd.DataFrame(metric_rows).to_csv(
        work_dir
        / "MISSION92_VARIANT_METRICS.csv",
        index=False,
    )

    shutil.copy2(
        args.cost_snapshot,
        work_dir
        / "MISSION92_COST_SNAPSHOT.json",
    )

    report = {
        "schema_id": (
            "deltagrid-mission92-session-"
            "premium-falsification-v2"
        ),
        "mission_id": MISSION_ID,
        "created_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "status": status,
        "decision": decision,
        "family": (
            "SESSION_CONDITIONAL_SPOT_EXPOSURE"
        ),
        "protocol_hash": (
            protocol["protocol_hash"]
        ),
        "mission91_contract_hash": (
            contract["contract_hash"]
        ),
        "mission91_protocol_hash": (
            mission91["protocol_hash"]
        ),
        "mission91_report_sha256": (
            sha256_file(
                args.mission91_report
            )
        ),
        "bridge_manifest_sha256": (
            sha256_file(
                args.bridge_manifest
            )
        ),
        "cost_snapshot_sha256": (
            sha256_file(
                args.cost_snapshot
            )
        ),
        "pair_specific_costs_bps": (
            pair_costs
        ),
        "data_hashes": data_hashes,
        "research_notional_usd": (
            RESEARCH_NOTIONAL_USD
        ),
        "variant_count": len(VARIANTS),
        "complete_common_session_count": (
            len(common_dates)
        ),
        "half_one_session_count": (
            len(half_one_dates)
        ),
        "half_two_session_count": (
            len(half_two_dates)
        ),
        "development_first_session": (
            common_dates[0].isoformat()
        ),
        "development_last_session": (
            common_dates[-1].isoformat()
        ),
        "half_one_summaries": (
            half_one_summaries
        ),
        "multiple_testing_diagnostic": {
            "method": (
                "MOVING_BLOCK_BOOTSTRAP_"
                "ONE_SIDED_HOLM_ADJUSTED"
            ),
            "promotion_gate": False,
            "raw_pvalues": raw_pvalues,
            "holm_adjusted_pvalues": (
                adjusted_pvalues
            ),
            "repetitions": (
                BOOTSTRAP_REPETITIONS
            ),
            "block_days": (
                BOOTSTRAP_BLOCK_DAYS
            ),
        },
        "selected_variant_id": (
            selected_variant_id
        ),
        "selected_variant_limit": 1,
        "confirmation": confirmation,
        "replication": replication,
        "final_gate_checks": (
            final_gate_checks
        ),
        "promotion_eligible": (
            promotion_eligible
        ),
        "market_returns_evaluated": True,
        "development_rows_read": int(
            sum(
                len(frame)
                for frame in frames.values()
            )
        ),
        "validation_rows_read": 0,
        "holdout_rows_read": 0,
        "freqtrade_strategy_created": False,
        "freqtrade_backtest_run": False,
        "lookahead_analysis_run": False,
        "recursive_analysis_run": False,
        "dry_run": False,
        "live_trading": False,
        "capital_deployment": False,
        "profitability_claim": False,
        "next_workstream": (
            next_workstream
        ),
    }

    report["report_hash"] = (
        canonical_hash(report)
    )

    (
        work_dir
        / "MISSION92_SESSION_PREMIUM_FALSIFICATION.json"
    ).write_text(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    selected_text = (
        selected_variant_id
        if selected_variant_id is not None
        else "None"
    )

    (
        work_dir
        / "MISSION92_DECISION.md"
    ).write_text(
        "\n".join(
            (
                "# Mission 92 Decision",
                "",
                f"Status: `{status}`",
                "",
                f"Decision: `{decision}`",
                "",
                (
                    "Selected development variant: "
                    f"`{selected_text}`"
                ),
                "",
                (
                    "Promotion eligible: "
                    f"`{str(promotion_eligible).lower()}`"
                ),
                "",
                (
                    "Pair-specific Mission 88 spot costs "
                    "were applied."
                ),
                "",
                (
                    "Only certified development data was "
                    "read. Validation and holdout remained "
                    "sealed."
                ),
                "",
                (
                    "No Freqtrade strategy, dry-run, live "
                    "order or capital deployment was used."
                ),
                "",
                f"Next: `{next_workstream}`",
                "",
                (
                    "Protocol hash: "
                    f"`{protocol['protocol_hash']}`"
                ),
                "",
                (
                    "Report hash: "
                    f"`{report['report_hash']}`"
                ),
                "",
            )
        ),
        encoding="utf-8",
    )

    work_dir.replace(
        args.output_dir
    )

    print("MISSION92_FINAL_GATE_PASS")
    print(f"status={status}")
    print(f"decision={decision}")
    print(
        "selected_variant_id="
        f"{selected_text}"
    )
    print(
        "promotion_eligible="
        f"{str(promotion_eligible).lower()}"
    )
    print(
        "complete_common_session_count="
        f"{len(common_dates)}"
    )
    print(
        "half_one_session_count="
        f"{len(half_one_dates)}"
    )
    print(
        "half_two_session_count="
        f"{len(half_two_dates)}"
    )
    print(
        "development_rows_read="
        f"{report['development_rows_read']}"
    )
    print("validation_rows_read=0")
    print("holdout_rows_read=0")
    print("freqtrade_strategy_created=false")
    print("freqtrade_backtest_run=false")
    print("dry_run=false")
    print("live_trading=false")
    print("capital_deployment=false")
    print("profitability_claim=false")
    print(
        "protocol_hash="
        f"{protocol['protocol_hash']}"
    )
    print(
        "report_hash="
        f"{report['report_hash']}"
    )
    print(
        "next_workstream="
        f"{next_workstream}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

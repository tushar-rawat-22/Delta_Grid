"""
Mission 35: Shadow Candidate Replay Harness.

This module creates deterministic shadow-mode candidate scenarios and feeds them
into the Mission 33 research pipeline runner.

It is designed for safe local research only.

It never:
- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- requires paid APIs
- requires real capital
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from offchain.backtest.research_pipeline_runner import (
    LIVE_TRADING_STATUS,
    PipelineConfig,
    ResearchPipelineRunner,
)
from offchain.backtest.research_run_history_inspector import inspect_research_run_history


REPLAY_LIVE_TRADING_STATUS = "DISABLED"

REPLAY_APPROVED_VERDICT = "SHADOW_REPLAY_GENERATED_APPROVED_AND_REJECTED_CASES_NO_LIVE_TRADING"
REPLAY_REJECTIONS_ONLY_VERDICT = "SHADOW_REPLAY_ONLY_REJECTIONS_NO_LIVE_TRADING"
REPLAY_SAFETY_BREACH_VERDICT = "SHADOW_REPLAY_SAFETY_BREACH_DETECTED"

REPLAY_RUNS_TABLE = "shadow_candidate_replay_runs"
REPLAY_SCENARIOS_TABLE = "shadow_candidate_replay_scenarios"


@dataclass(frozen=True)
class ReplayScenario:
    name: str
    description: str
    candidates: list[dict[str, Any]] | None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_replay_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission35-replay-{stamp}-{uuid.uuid4().hex[:8]}"


def scenario_catalog() -> dict[str, ReplayScenario]:
    return {
        "fail_closed_baseline": ReplayScenario(
            name="fail_closed_baseline",
            description="Default conservative Mission 33 behavior. Expected to reject all candidates.",
            candidates=None,
        ),
        "approved_shadow_btc": ReplayScenario(
            name="approved_shadow_btc",
            description="One strong BTCUSDT candidate that should open a shadow paper position only.",
            candidates=[
                {
                    "symbol": "BTCUSDT",
                    "funding_rate": 0.001,
                    "annualized_funding": 0.42,
                    "basis_bps": 12.0,
                    "expected_funding_edge_bps": 120.0,
                    "total_round_trip_cost_bps": 30.0,
                    "spread_bps": 2.0,
                    "estimated_slippage_bps": 3.0,
                    "stressed_liquidation_buffer": 0.50,
                    "liquidity_score": 95.0,
                }
            ],
        ),
        "mixed_shadow_set": ReplayScenario(
            name="mixed_shadow_set",
            description="Mixed BTC, ETH, and SOL candidates with one approval and multiple controlled rejections.",
            candidates=[
                {
                    "symbol": "BTCUSDT",
                    "funding_rate": 0.001,
                    "annualized_funding": 0.40,
                    "basis_bps": 10.0,
                    "expected_funding_edge_bps": 125.0,
                    "total_round_trip_cost_bps": 30.0,
                    "spread_bps": 2.0,
                    "estimated_slippage_bps": 3.0,
                    "stressed_liquidation_buffer": 0.52,
                    "liquidity_score": 98.0,
                },
                {
                    "symbol": "ETHUSDT",
                    "funding_rate": 0.00002,
                    "annualized_funding": 0.04,
                    "basis_bps": 18.0,
                    "expected_funding_edge_bps": 8.0,
                    "total_round_trip_cost_bps": 30.0,
                    "spread_bps": 2.5,
                    "estimated_slippage_bps": 3.5,
                    "stressed_liquidation_buffer": 0.48,
                    "liquidity_score": 90.0,
                },
                {
                    "symbol": "SOLUSDT",
                    "funding_rate": -0.0001,
                    "annualized_funding": -0.12,
                    "basis_bps": 55.0,
                    "expected_funding_edge_bps": -10.0,
                    "total_round_trip_cost_bps": 35.0,
                    "spread_bps": 7.0,
                    "estimated_slippage_bps": 9.0,
                    "stressed_liquidation_buffer": 0.22,
                    "liquidity_score": 70.0,
                },
            ],
        ),
        "non_universe_rejection": ReplayScenario(
            name="non_universe_rejection",
            description="High-quality DOGEUSDT-style candidate rejected because it is outside the approved universe.",
            candidates=[
                {
                    "symbol": "DOGEUSDT",
                    "funding_rate": 0.002,
                    "annualized_funding": 0.60,
                    "basis_bps": 8.0,
                    "expected_funding_edge_bps": 150.0,
                    "total_round_trip_cost_bps": 30.0,
                    "spread_bps": 2.0,
                    "estimated_slippage_bps": 3.0,
                    "stressed_liquidation_buffer": 0.55,
                    "liquidity_score": 95.0,
                }
            ],
        ),
    }


def ensure_schema(db_path: str | Path) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_candidate_replay_runs (
                replay_label TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                scenario_count INTEGER NOT NULL,
                pipeline_run_count INTEGER NOT NULL,
                total_approved_count INTEGER NOT NULL,
                total_rejected_count INTEGER NOT NULL,
                total_paper_positions_count INTEGER NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                scenarios_json TEXT NOT NULL,
                history_summary_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_candidate_replay_scenarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                replay_label TEXT NOT NULL,
                scenario_name TEXT NOT NULL,
                run_label TEXT NOT NULL,
                description TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                approved_count INTEGER NOT NULL,
                rejected_count INTEGER NOT NULL,
                paper_positions_count INTEGER NOT NULL,
                verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                alerts_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        conn.commit()


def resolve_scenarios(requested: list[str] | None) -> list[ReplayScenario]:
    catalog = scenario_catalog()

    if requested is None or len(requested) == 0 or "all" in requested:
        return list(catalog.values())

    unknown = [name for name in requested if name not in catalog]
    if unknown:
        raise ValueError(f"Unknown replay scenario(s): {', '.join(unknown)}")

    return [catalog[name] for name in requested]


def persist_replay_result(
    db_path: str | Path,
    replay_label: str,
    result: dict[str, Any],
) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM shadow_candidate_replay_scenarios WHERE replay_label = ?",
            (replay_label,),
        )

        for scenario_result in result["scenario_results"]:
            conn.execute(
                """
                INSERT INTO shadow_candidate_replay_scenarios (
                    replay_label,
                    scenario_name,
                    run_label,
                    description,
                    live_trading,
                    approved_count,
                    rejected_count,
                    paper_positions_count,
                    verdict,
                    recommended_action,
                    alerts_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    replay_label,
                    scenario_result["scenario_name"],
                    scenario_result["run_label"],
                    scenario_result["description"],
                    scenario_result["live_trading"],
                    scenario_result["approved_count"],
                    scenario_result["rejected_count"],
                    scenario_result["paper_positions_count"],
                    scenario_result["verdict"],
                    scenario_result["recommended_action"],
                    json.dumps(scenario_result["alerts"], sort_keys=True),
                    scenario_result["created_at"],
                ),
            )

        conn.execute(
            """
            INSERT OR REPLACE INTO shadow_candidate_replay_runs (
                replay_label,
                created_at,
                live_trading,
                scenario_count,
                pipeline_run_count,
                total_approved_count,
                total_rejected_count,
                total_paper_positions_count,
                global_verdict,
                recommended_action,
                scenarios_json,
                history_summary_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                replay_label,
                result["created_at"],
                result["live_trading"],
                result["scenario_count"],
                result["pipeline_run_count"],
                result["total_approved_count"],
                result["total_rejected_count"],
                result["total_paper_positions_count"],
                result["global_verdict"],
                result["recommended_action"],
                json.dumps(result["scenario_results"], sort_keys=True),
                json.dumps(result["history_summary"], sort_keys=True),
            ),
        )

        conn.commit()


def run_shadow_candidate_replay(
    db_path: str | Path = "offchain/deltagrid.db",
    replay_label: str | None = None,
    scenario_names: list[str] | None = None,
) -> dict[str, Any]:
    label = replay_label or new_replay_label()
    scenarios = resolve_scenarios(scenario_names)

    ensure_schema(db_path)

    runner = ResearchPipelineRunner(
        db_path=db_path,
        config=PipelineConfig(symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT")),
    )

    scenario_results: list[dict[str, Any]] = []

    for scenario in scenarios:
        run_label = f"{label}-{scenario.name}"
        pipeline_result = runner.run(
            run_label=run_label,
            candidates=scenario.candidates,
        )

        scenario_results.append(
            {
                "scenario_name": scenario.name,
                "description": scenario.description,
                "run_label": run_label,
                "created_at": pipeline_result["created_at"],
                "live_trading": pipeline_result["live_trading"],
                "approved_count": pipeline_result["approved_count"],
                "rejected_count": pipeline_result["rejected_count"],
                "paper_positions_count": pipeline_result["paper_positions_count"],
                "verdict": pipeline_result["verdict"],
                "recommended_action": pipeline_result["recommended_action"],
                "alerts": pipeline_result["alerts"],
            }
        )

    total_approved = sum(item["approved_count"] for item in scenario_results)
    total_rejected = sum(item["rejected_count"] for item in scenario_results)
    total_paper_positions = sum(item["paper_positions_count"] for item in scenario_results)

    live_trading_breaches = [
        item["run_label"]
        for item in scenario_results
        if item["live_trading"] != REPLAY_LIVE_TRADING_STATUS
    ]

    history = inspect_research_run_history(
        db_path=db_path,
        limit=max(len(scenario_results), 1),
    )

    if live_trading_breaches:
        global_verdict = REPLAY_SAFETY_BREACH_VERDICT
        recommended_action = "STOP_AND_REVIEW_REPLAY_SAFETY_BREACH"
    elif total_approved > 0:
        global_verdict = REPLAY_APPROVED_VERDICT
        recommended_action = "USE_REPLAY_HISTORY_FOR_SHADOW_RESEARCH_VALIDATION"
    else:
        global_verdict = REPLAY_REJECTIONS_ONLY_VERDICT
        recommended_action = "KEEP_REPLAYING_STRONGER_SHADOW_CANDIDATES"

    result = {
        "replay_label": label,
        "created_at": utc_now(),
        "live_trading": REPLAY_LIVE_TRADING_STATUS,
        "scenario_count": len(scenario_results),
        "pipeline_run_count": len(scenario_results),
        "total_approved_count": total_approved,
        "total_rejected_count": total_rejected,
        "total_paper_positions_count": total_paper_positions,
        "live_trading_breach_count": len(live_trading_breaches),
        "live_trading_breach_run_labels": live_trading_breaches,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
        "scenario_results": scenario_results,
        "history_summary": {
            "total_runs": history["total_runs"],
            "latest_run_label": history["latest_run_label"],
            "latest_verdict": history["latest_verdict"],
            "live_trading_disabled_all": history["safety"]["live_trading_disabled_all"],
            "breach_count": history["safety"]["breach_count"],
            "global_verdict": history["global_verdict"],
        },
    }

    persist_replay_result(
        db_path=db_path,
        replay_label=label,
        result=result,
    )

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run deterministic DeltaGrid shadow candidate replay scenarios."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--replay-label", default=None)
    parser.add_argument(
        "--scenario",
        action="append",
        default=None,
        help="Replay scenario name. Use multiple times or use 'all'.",
    )
    parser.add_argument("--list-scenarios", action="store_true")

    args = parser.parse_args()

    if args.list_scenarios:
        print(json.dumps(
            {
                name: {
                    "description": scenario.description,
                    "candidate_count": None if scenario.candidates is None else len(scenario.candidates),
                }
                for name, scenario in scenario_catalog().items()
            },
            indent=2,
            sort_keys=True,
        ))
        return

    result = run_shadow_candidate_replay(
        db_path=args.db,
        replay_label=args.replay_label,
        scenario_names=args.scenario,
    )

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

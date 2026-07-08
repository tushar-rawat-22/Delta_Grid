"""
Mission 33: Unified Free Shadow Research Runner.

This module provides a zero-capital, no-live-trading orchestration layer for
DeltaGrid's research pipeline.

It deliberately runs in SHADOW_MODE only:
- no private keys
- no signing
- no exchange order placement
- no live execution
- SQLite-only local persistence
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LIVE_TRADING_STATUS = "DISABLED"
DEFAULT_VERDICT = "RESEARCH_PIPELINE_NO_GO_WAIT_FOR_EDGE_NO_LIVE_TRADING"
SHADOW_APPROVED_VERDICT = "SHADOW_PIPELINE_OBSERVE_APPROVED_CANDIDATES_NO_LIVE_TRADING"


@dataclass(frozen=True)
class PipelineConfig:
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
    mode: str = "SHADOW_MODE"
    min_annualized_funding: float = 0.18
    max_basis_bps_entry: float = 35.0
    max_spread_bps: float = 4.0
    max_slippage_bps: float = 6.0
    min_edge_to_cost_ratio: float = 3.0
    min_stressed_liquidation_buffer: float = 0.35
    min_liquidity_score: float = 80.0


@dataclass(frozen=True)
class ShadowCandidate:
    symbol: str
    funding_rate: float
    annualized_funding: float
    basis_bps: float
    expected_funding_edge_bps: float
    total_round_trip_cost_bps: float
    spread_bps: float
    estimated_slippage_bps: float
    stressed_liquidation_buffer: float
    liquidity_score: float


class ResearchPipelineRunner:
    """
    Unified Mission 33 runner.

    The runner can accept explicit candidates for testing/research. If no
    candidates are supplied, it generates conservative local shadow candidates
    that are expected to be rejected. This makes the default behavior safe.
    """

    STAGES = (
        "funding_scanner",
        "candidate_ranking",
        "execution_cost_slippage_simulator",
        "liquidation_leverage_risk_model",
        "paper_trading_engine",
        "ai_learning_registry",
        "research_dashboard_alerts",
    )

    def __init__(
        self,
        db_path: str | Path = "offchain/deltagrid.db",
        config: PipelineConfig | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.config = config or PipelineConfig()

    def ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_pipeline_runs (
                    run_label TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    live_trading TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    recommended_action TEXT NOT NULL,
                    symbols_json TEXT NOT NULL,
                    approved_count INTEGER NOT NULL,
                    rejected_count INTEGER NOT NULL,
                    paper_positions_count INTEGER NOT NULL,
                    alerts_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_pipeline_stage_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_label TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    stage_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details_json TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_pipeline_reports (
                    run_label TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    markdown_report TEXT NOT NULL
                )
                """
            )

            conn.commit()

    def run(
        self,
        run_label: str | None = None,
        candidates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if self.config.mode != "SHADOW_MODE":
            raise ValueError("Mission 33 runner only supports SHADOW_MODE.")

        self.ensure_schema()

        label = run_label or self._new_run_label()
        created_at = self._utc_now()
        candidate_objects = self._build_candidates(candidates)

        approved: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []

        for candidate in candidate_objects:
            evaluation = self._evaluate_candidate(candidate)
            if evaluation["approved"]:
                approved.append(evaluation)
            else:
                rejected.append(evaluation)

        paper_positions = self._open_shadow_paper_positions(approved)
        alerts = self._build_alerts(approved, rejected, paper_positions)

        if approved and paper_positions:
            verdict = SHADOW_APPROVED_VERDICT
            recommended_action = "CONTINUE_SHADOW_PAPER_OBSERVATION"
        else:
            verdict = DEFAULT_VERDICT
            recommended_action = "KEEP_SCANNING_FOR_STRONGER_FUNDING_EDGE"

        stage_results = self._build_stage_results(
            approved=approved,
            rejected=rejected,
            paper_positions=paper_positions,
            alerts=alerts,
        )

        result = {
            "run_label": label,
            "created_at": created_at,
            "mode": self.config.mode,
            "live_trading": LIVE_TRADING_STATUS,
            "symbols": list(self.config.symbols),
            "approved_count": len(approved),
            "rejected_count": len(rejected),
            "paper_positions_count": len(paper_positions),
            "alerts": alerts,
            "verdict": verdict,
            "recommended_action": recommended_action,
            "stage_results": stage_results,
        }

        report = self._build_markdown_report(result, approved, rejected, paper_positions)
        self._persist_result(result, report)

        return result

    def _build_candidates(
        self,
        raw_candidates: list[dict[str, Any]] | None,
    ) -> list[ShadowCandidate]:
        if raw_candidates is None:
            return [
                ShadowCandidate(
                    symbol=symbol,
                    funding_rate=0.00005,
                    annualized_funding=0.055,
                    basis_bps=42.0,
                    expected_funding_edge_bps=12.0,
                    total_round_trip_cost_bps=30.0,
                    spread_bps=5.5,
                    estimated_slippage_bps=8.0,
                    stressed_liquidation_buffer=0.31,
                    liquidity_score=75.0,
                )
                for symbol in self.config.symbols
            ]

        candidates: list[ShadowCandidate] = []
        for row in raw_candidates:
            candidates.append(
                ShadowCandidate(
                    symbol=str(row["symbol"]),
                    funding_rate=float(row["funding_rate"]),
                    annualized_funding=float(row["annualized_funding"]),
                    basis_bps=float(row["basis_bps"]),
                    expected_funding_edge_bps=float(row["expected_funding_edge_bps"]),
                    total_round_trip_cost_bps=float(row["total_round_trip_cost_bps"]),
                    spread_bps=float(row["spread_bps"]),
                    estimated_slippage_bps=float(row["estimated_slippage_bps"]),
                    stressed_liquidation_buffer=float(row["stressed_liquidation_buffer"]),
                    liquidity_score=float(row["liquidity_score"]),
                )
            )

        return candidates

    def _evaluate_candidate(self, candidate: ShadowCandidate) -> dict[str, Any]:
        cfg = self.config
        edge_to_cost_ratio = candidate.expected_funding_edge_bps / max(
            candidate.total_round_trip_cost_bps,
            1.0,
        )

        rejection_reasons: list[str] = []

        if candidate.symbol not in cfg.symbols:
            rejection_reasons.append("symbol_not_in_approved_universe")

        if candidate.funding_rate <= 0:
            rejection_reasons.append("funding_not_positive")

        if candidate.annualized_funding < cfg.min_annualized_funding:
            rejection_reasons.append("annualized_funding_too_low")

        if abs(candidate.basis_bps) > cfg.max_basis_bps_entry:
            rejection_reasons.append("basis_too_wide")

        if candidate.spread_bps > cfg.max_spread_bps:
            rejection_reasons.append("spread_too_wide")

        if candidate.estimated_slippage_bps > cfg.max_slippage_bps:
            rejection_reasons.append("slippage_too_high")

        if edge_to_cost_ratio < cfg.min_edge_to_cost_ratio:
            rejection_reasons.append("edge_to_cost_ratio_too_low")

        if candidate.stressed_liquidation_buffer < cfg.min_stressed_liquidation_buffer:
            rejection_reasons.append("liquidation_buffer_too_low")

        if candidate.liquidity_score < cfg.min_liquidity_score:
            rejection_reasons.append("liquidity_score_too_low")

        return {
            "candidate": asdict(candidate),
            "approved": not rejection_reasons,
            "edge_to_cost_ratio": round(edge_to_cost_ratio, 4),
            "rejection_reasons": rejection_reasons,
            "position_model": "long_spot_short_perp",
            "execution_model": "spot_taker_perp_post_only_shadow",
        }

    def _open_shadow_paper_positions(
        self,
        approved: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        positions: list[dict[str, Any]] = []

        for item in approved:
            candidate = item["candidate"]
            positions.append(
                {
                    "symbol": candidate["symbol"],
                    "mode": "SHADOW_PAPER",
                    "live_order_sent": False,
                    "notional_usd": 1000.0,
                    "spot_leg": "LONG",
                    "perp_leg": "SHORT",
                    "leverage": 1.0,
                    "status": "OPEN_SHADOW_ONLY",
                }
            )

        return positions

    def _build_alerts(
        self,
        approved: list[dict[str, Any]],
        rejected: list[dict[str, Any]],
        paper_positions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        alerts = [
            {
                "level": "BLOCKING",
                "code": "LIVE_TRADING_DISABLED",
                "message": "Mission 33 is shadow-only. No live orders are allowed.",
            }
        ]

        if not approved:
            alerts.append(
                {
                    "level": "BLOCKING",
                    "code": "NO_SHADOW_APPROVED_CANDIDATES",
                    "message": "No candidates passed strict free shadow-mode filters.",
                }
            )

        if rejected:
            alerts.append(
                {
                    "level": "INFO",
                    "code": "REJECTIONS_RECORDED",
                    "message": f"{len(rejected)} rejected candidates were stored with reasons.",
                }
            )

        if not paper_positions:
            alerts.append(
                {
                    "level": "BLOCKING",
                    "code": "PAPER_TRADING_NOT_TRIGGERED",
                    "message": "No shadow paper positions opened because no candidate passed.",
                }
            )

        return alerts

    def _build_stage_results(
        self,
        approved: list[dict[str, Any]],
        rejected: list[dict[str, Any]],
        paper_positions: list[dict[str, Any]],
        alerts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "stage_name": "funding_scanner",
                "status": "COMPLETE",
                "details": {
                    "symbols_scanned": list(self.config.symbols),
                    "candidate_count": len(approved) + len(rejected),
                },
            },
            {
                "stage_name": "candidate_ranking",
                "status": "COMPLETE",
                "details": {
                    "approved_count": len(approved),
                    "rejected_count": len(rejected),
                },
            },
            {
                "stage_name": "execution_cost_slippage_simulator",
                "status": "COMPLETE",
                "details": {
                    "max_spread_bps": self.config.max_spread_bps,
                    "max_slippage_bps": self.config.max_slippage_bps,
                },
            },
            {
                "stage_name": "liquidation_leverage_risk_model",
                "status": "COMPLETE",
                "details": {
                    "min_stressed_liquidation_buffer": self.config.min_stressed_liquidation_buffer,
                    "leverage": 1.0,
                },
            },
            {
                "stage_name": "paper_trading_engine",
                "status": "COMPLETE",
                "details": {
                    "paper_positions_count": len(paper_positions),
                    "live_order_sent": False,
                },
            },
            {
                "stage_name": "ai_learning_registry",
                "status": "COMPLETE",
                "details": {
                    "examples_ready": len(approved) + len(rejected),
                    "approval_for_live_trading": False,
                },
            },
            {
                "stage_name": "research_dashboard_alerts",
                "status": "COMPLETE",
                "details": {
                    "alert_count": len(alerts),
                    "blocking_alert_count": sum(1 for alert in alerts if alert["level"] == "BLOCKING"),
                },
            },
        ]

    def _persist_result(self, result: dict[str, Any], markdown_report: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO research_pipeline_runs (
                    run_label,
                    created_at,
                    mode,
                    live_trading,
                    verdict,
                    recommended_action,
                    symbols_json,
                    approved_count,
                    rejected_count,
                    paper_positions_count,
                    alerts_json,
                    summary_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result["run_label"],
                    result["created_at"],
                    result["mode"],
                    result["live_trading"],
                    result["verdict"],
                    result["recommended_action"],
                    json.dumps(result["symbols"], sort_keys=True),
                    result["approved_count"],
                    result["rejected_count"],
                    result["paper_positions_count"],
                    json.dumps(result["alerts"], sort_keys=True),
                    json.dumps(
                        {
                            "stage_results": result["stage_results"],
                            "safe_free_mode": True,
                        },
                        sort_keys=True,
                    ),
                ),
            )

            conn.execute(
                "DELETE FROM research_pipeline_stage_results WHERE run_label = ?",
                (result["run_label"],),
            )

            for stage in result["stage_results"]:
                conn.execute(
                    """
                    INSERT INTO research_pipeline_stage_results (
                        run_label,
                        created_at,
                        stage_name,
                        status,
                        details_json
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        result["run_label"],
                        result["created_at"],
                        stage["stage_name"],
                        stage["status"],
                        json.dumps(stage["details"], sort_keys=True),
                    ),
                )

            conn.execute(
                """
                INSERT OR REPLACE INTO research_pipeline_reports (
                    run_label,
                    created_at,
                    markdown_report
                )
                VALUES (?, ?, ?)
                """,
                (
                    result["run_label"],
                    result["created_at"],
                    markdown_report,
                ),
            )

            conn.commit()

    def _build_markdown_report(
        self,
        result: dict[str, Any],
        approved: list[dict[str, Any]],
        rejected: list[dict[str, Any]],
        paper_positions: list[dict[str, Any]],
    ) -> str:
        alert_lines = "\n".join(
            f"- {alert['level']}: {alert['code']} — {alert['message']}"
            for alert in result["alerts"]
        )

        rejection_lines = "\n".join(
            f"- {item['candidate']['symbol']}: {', '.join(item['rejection_reasons'])}"
            for item in rejected
        ) or "- None"

        approved_lines = "\n".join(
            f"- {item['candidate']['symbol']}: edge_to_cost_ratio={item['edge_to_cost_ratio']}"
            for item in approved
        ) or "- None"

        return f"""# DeltaGrid Mission 33 Shadow Research Report

Run label: `{result['run_label']}`
Created at: `{result['created_at']}`
Mode: `{result['mode']}`
Live trading: `{result['live_trading']}`

## Verdict

`{result['verdict']}`

Recommended action: `{result['recommended_action']}`

## Symbols

{", ".join(result["symbols"])}

## Candidate Summary

Approved: {len(approved)}
Rejected: {len(rejected)}
Shadow paper positions: {len(paper_positions)}

## Approved Candidates

{approved_lines}

## Rejected Candidates

{rejection_lines}

## Alerts

{alert_lines}

## Safety

No private keys were read.
No signatures were produced.
No exchange orders were sent.
No live capital was used.
"""

    @staticmethod
    def _new_run_label() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"mission33-shadow-{stamp}-{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DeltaGrid Mission 33 shadow research pipeline.")
    parser.add_argument("--db", default="offchain/deltagrid.db", help="SQLite database path.")
    parser.add_argument("--run-label", default=None, help="Optional deterministic run label.")
    args = parser.parse_args()

    runner = ResearchPipelineRunner(db_path=args.db)
    result = runner.run(run_label=args.run_label)

    printable = {
        "run_label": result["run_label"],
        "mode": result["mode"],
        "live_trading": result["live_trading"],
        "symbols": result["symbols"],
        "approved_count": result["approved_count"],
        "rejected_count": result["rejected_count"],
        "paper_positions_count": result["paper_positions_count"],
        "verdict": result["verdict"],
        "recommended_action": result["recommended_action"],
        "alerts": result["alerts"],
    }

    print(json.dumps(printable, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, getcontext
from pathlib import Path

from dotenv import load_dotenv


getcontext().prec = 40

OFFCHAIN_ROOT = Path(__file__).resolve().parents[1]

if str(OFFCHAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(OFFCHAIN_ROOT))

from db.schema import init_market_database, utc_now

from backtest.funding_basis_model import (
    ensure_schema as ensure_funding_basis_schema,
    resolve_db_path,
    to_decimal,
)

from backtest.candidate_ranking_engine import (
    ensure_schema as ensure_candidate_ranking_schema,
)


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def safe_decimal(value, default="0"):
    if value is None:
        return Decimal(default)

    return to_decimal(value)


def safe_div(numerator, denominator):
    numerator = safe_decimal(numerator)
    denominator = safe_decimal(denominator)

    if denominator == 0:
        return Decimal("0")

    return numerator / denominator


def utc_future_days(days):
    return (
        datetime.now(timezone.utc) + timedelta(days=int(days))
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_schema(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS paper_trading_positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_ranking_run_label TEXT NOT NULL,
        candidate_result_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        allocation_usd TEXT NOT NULL,
        gross_notional_usd TEXT NOT NULL,
        spot_notional_usd TEXT NOT NULL,
        perp_notional_usd TEXT NOT NULL,
        annualized_funding_rate_pct TEXT NOT NULL,
        expected_holding_days INTEGER NOT NULL,
        expected_funding_return_pct TEXT NOT NULL,
        expected_cost_pct TEXT NOT NULL,
        expected_net_return_pct TEXT NOT NULL,
        entry_time_utc TEXT NOT NULL,
        planned_exit_time_utc TEXT NOT NULL,
        status TEXT NOT NULL,
        final_verdict TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS paper_trading_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_ranking_run_label TEXT NOT NULL,
        position_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        side_description TEXT NOT NULL,
        entry_time_utc TEXT NOT NULL,
        exit_time_utc TEXT NOT NULL,
        holding_days INTEGER NOT NULL,
        allocation_usd TEXT NOT NULL,
        gross_notional_usd TEXT NOT NULL,
        gross_funding_pnl_usd TEXT NOT NULL,
        execution_cost_usd TEXT NOT NULL,
        simulated_net_pnl_usd TEXT NOT NULL,
        simulated_net_return_pct TEXT NOT NULL,
        trade_verdict TEXT NOT NULL,
        exit_reason TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS paper_trading_equity_curve (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_ranking_run_label TEXT NOT NULL,
        day_index INTEGER NOT NULL,
        timestamp_utc TEXT NOT NULL,
        starting_equity_usd TEXT NOT NULL,
        daily_pnl_usd TEXT NOT NULL,
        ending_equity_usd TEXT NOT NULL,
        drawdown_pct TEXT NOT NULL,
        open_positions INTEGER NOT NULL,
        closed_trades INTEGER NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS paper_trading_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_ranking_run_label TEXT NOT NULL,
        candidates_seen INTEGER NOT NULL,
        eligible_candidates INTEGER NOT NULL,
        positions_created INTEGER NOT NULL,
        trades_created INTEGER NOT NULL,
        starting_equity_usd TEXT NOT NULL,
        ending_equity_usd TEXT NOT NULL,
        total_pnl_usd TEXT NOT NULL,
        total_return_pct TEXT NOT NULL,
        max_drawdown_pct TEXT NOT NULL,
        win_rate_pct TEXT NOT NULL,
        avg_trade_return_pct TEXT NOT NULL,
        profit_factor TEXT NOT NULL,
        final_verdict TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def prepare_database(db_path):
    db_path = resolve_db_path(db_path)

    init_market_database(db_path)
    ensure_funding_basis_schema(db_path)
    ensure_candidate_ranking_schema(db_path)
    ensure_schema(db_path)

    return db_path


def load_ranked_candidates(db_path, ranking_run_label):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    rows = cur.execute("""
    SELECT
        id,
        symbol,
        annualized_funding_rate_pct,
        net_expected_edge_pct,
        edge_to_cost_ratio,
        composite_score,
        final_verdict,
        combined_cost_pct,
        net_execution_edge_pct,
        rejection_reasons_json
    FROM candidate_ranking_results
    WHERE run_label = ?
    ORDER BY CAST(composite_score AS REAL) DESC
    """, (
        ranking_run_label,
    )).fetchall()

    conn.close()

    candidates = []

    for row in rows:
        try:
            reasons = json.loads(row[9])
        except Exception:
            reasons = []

        candidates.append({
            "candidate_result_id": int(row[0]),
            "symbol": row[1],
            "annualized_funding_rate_pct": safe_decimal(row[2]),
            "net_expected_edge_pct": safe_decimal(row[3]),
            "edge_to_cost_ratio": safe_decimal(row[4]),
            "composite_score": safe_decimal(row[5]),
            "final_verdict": row[6],
            "combined_cost_pct": safe_decimal(row[7]),
            "net_execution_edge_pct": safe_decimal(row[8]),
            "rejection_reasons": reasons,
        })

    return candidates


def expected_funding_return_pct(annualized_funding_rate_pct, holding_days, perp_weight):
    annualized_funding_rate_pct = safe_decimal(annualized_funding_rate_pct)
    perp_weight = safe_decimal(perp_weight)

    return annualized_funding_rate_pct * Decimal(int(holding_days)) / Decimal("365") * perp_weight


def expected_cost_pct(candidate_cost_pct, default_cost_pct):
    candidate_cost_pct = safe_decimal(candidate_cost_pct)
    default_cost_pct = safe_decimal(default_cost_pct)

    if candidate_cost_pct > 0:
        return candidate_cost_pct

    return default_cost_pct


def profit_factor(pnls):
    gains = sum(
        [pnl for pnl in pnls if pnl > 0],
        Decimal("0"),
    )

    losses = abs(sum(
        [pnl for pnl in pnls if pnl < 0],
        Decimal("0"),
    ))

    if gains == 0 and losses == 0:
        return Decimal("0")

    if losses == 0:
        return Decimal("999")

    return gains / losses


def win_rate_pct(pnls):
    if not pnls:
        return Decimal("0")

    wins = len([
        pnl
        for pnl in pnls
        if pnl > 0
    ])

    return Decimal(wins) / Decimal(len(pnls)) * Decimal("100")


def avg_trade_return_pct(returns):
    if not returns:
        return Decimal("0")

    return sum(returns, Decimal("0")) / Decimal(len(returns))


def is_candidate_eligible(
    candidate,
    min_composite_score,
    min_net_expected_edge_pct,
    min_edge_to_cost_ratio,
    allow_no_go_candidates,
):
    if not allow_no_go_candidates and candidate["final_verdict"] != "GO_FOR_RESEARCH_RANKED":
        return False

    if candidate["annualized_funding_rate_pct"] <= 0:
        return False

    if candidate["composite_score"] < min_composite_score:
        return False

    if candidate["net_expected_edge_pct"] < min_net_expected_edge_pct:
        return False

    if candidate["edge_to_cost_ratio"] < min_edge_to_cost_ratio:
        return False

    return True


def build_paper_position(
    candidate,
    starting_equity_usd,
    allocation_pct,
    max_allocation_usd,
    gross_notional_multiplier,
    holding_days,
    perp_weight,
    default_cost_pct,
    min_position_net_return_pct,
):
    allocation = starting_equity_usd * allocation_pct / Decimal("100")

    if max_allocation_usd > 0:
        allocation = min(allocation, max_allocation_usd)

    gross_notional = allocation * gross_notional_multiplier
    perp_notional = gross_notional * perp_weight
    spot_notional = gross_notional - perp_notional

    funding_return = expected_funding_return_pct(
        annualized_funding_rate_pct=candidate["annualized_funding_rate_pct"],
        holding_days=holding_days,
        perp_weight=perp_weight,
    )

    cost = expected_cost_pct(
        candidate_cost_pct=candidate["combined_cost_pct"],
        default_cost_pct=default_cost_pct,
    )

    net_return = funding_return - cost

    if net_return < min_position_net_return_pct:
        verdict = "NO_GO_PAPER_EDGE_TOO_SMALL"
        action = "KEEP_ON_WATCHLIST"
        status = "REJECTED"
    else:
        verdict = "GO_PAPER_POSITION"
        action = "SIMULATE_PAPER_TRADE"
        status = "OPEN_SIMULATED"

    return {
        "candidate_result_id": candidate["candidate_result_id"],
        "symbol": candidate["symbol"],
        "allocation_usd": allocation,
        "gross_notional_usd": gross_notional,
        "spot_notional_usd": spot_notional,
        "perp_notional_usd": perp_notional,
        "annualized_funding_rate_pct": candidate["annualized_funding_rate_pct"],
        "expected_holding_days": int(holding_days),
        "expected_funding_return_pct": funding_return,
        "expected_cost_pct": cost,
        "expected_net_return_pct": net_return,
        "entry_time_utc": utc_now(),
        "planned_exit_time_utc": utc_future_days(holding_days),
        "status": status,
        "final_verdict": verdict,
        "recommended_action": action,
    }


def simulate_trade_from_position(position):
    allocation = position["allocation_usd"]

    gross_funding_pnl = (
        allocation
        * position["expected_funding_return_pct"]
        / Decimal("100")
    )

    execution_cost = (
        allocation
        * position["expected_cost_pct"]
        / Decimal("100")
    )

    net_pnl = gross_funding_pnl - execution_cost

    net_return_pct = safe_div(
        net_pnl,
        allocation,
    ) * Decimal("100")

    if net_pnl > 0:
        verdict = "PAPER_TRADE_WIN"
        exit_reason = "PLANNED_HOLDING_PERIOD_COMPLETE"
    elif net_pnl < 0:
        verdict = "PAPER_TRADE_LOSS"
        exit_reason = "COST_EXCEEDED_FUNDING"
    else:
        verdict = "PAPER_TRADE_FLAT"
        exit_reason = "ZERO_NET_EDGE"

    return {
        "symbol": position["symbol"],
        "side_description": "SIMULATED_LONG_SPOT_SHORT_PERP",
        "entry_time_utc": position["entry_time_utc"],
        "exit_time_utc": position["planned_exit_time_utc"],
        "holding_days": position["expected_holding_days"],
        "allocation_usd": allocation,
        "gross_notional_usd": position["gross_notional_usd"],
        "gross_funding_pnl_usd": gross_funding_pnl,
        "execution_cost_usd": execution_cost,
        "simulated_net_pnl_usd": net_pnl,
        "simulated_net_return_pct": net_return_pct,
        "trade_verdict": verdict,
        "exit_reason": exit_reason,
    }


def insert_position(
    db_path,
    run_label,
    source_ranking_run_label,
    position,
    assumptions,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO paper_trading_positions (
        run_label,
        source_ranking_run_label,
        candidate_result_id,
        symbol,
        allocation_usd,
        gross_notional_usd,
        spot_notional_usd,
        perp_notional_usd,
        annualized_funding_rate_pct,
        expected_holding_days,
        expected_funding_return_pct,
        expected_cost_pct,
        expected_net_return_pct,
        entry_time_utc,
        planned_exit_time_utc,
        status,
        final_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        source_ranking_run_label,
        position["candidate_result_id"],
        position["symbol"],
        format(position["allocation_usd"], "f"),
        format(position["gross_notional_usd"], "f"),
        format(position["spot_notional_usd"], "f"),
        format(position["perp_notional_usd"], "f"),
        format(position["annualized_funding_rate_pct"], "f"),
        position["expected_holding_days"],
        format(position["expected_funding_return_pct"], "f"),
        format(position["expected_cost_pct"], "f"),
        format(position["expected_net_return_pct"], "f"),
        position["entry_time_utc"],
        position["planned_exit_time_utc"],
        position["status"],
        position["final_verdict"],
        position["recommended_action"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def insert_trade(
    db_path,
    run_label,
    source_ranking_run_label,
    position_id,
    trade,
    assumptions,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO paper_trading_trades (
        run_label,
        source_ranking_run_label,
        position_id,
        symbol,
        side_description,
        entry_time_utc,
        exit_time_utc,
        holding_days,
        allocation_usd,
        gross_notional_usd,
        gross_funding_pnl_usd,
        execution_cost_usd,
        simulated_net_pnl_usd,
        simulated_net_return_pct,
        trade_verdict,
        exit_reason,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        source_ranking_run_label,
        position_id,
        trade["symbol"],
        trade["side_description"],
        trade["entry_time_utc"],
        trade["exit_time_utc"],
        trade["holding_days"],
        format(trade["allocation_usd"], "f"),
        format(trade["gross_notional_usd"], "f"),
        format(trade["gross_funding_pnl_usd"], "f"),
        format(trade["execution_cost_usd"], "f"),
        format(trade["simulated_net_pnl_usd"], "f"),
        format(trade["simulated_net_return_pct"], "f"),
        trade["trade_verdict"],
        trade["exit_reason"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def build_equity_curve(starting_equity_usd, trades, holding_days):
    rows = []
    equity = starting_equity_usd
    peak = starting_equity_usd

    if holding_days <= 0:
        holding_days = 1

    total_pnl = sum(
        [trade["simulated_net_pnl_usd"] for trade in trades],
        Decimal("0"),
    )

    daily_pnl = total_pnl / Decimal(holding_days)

    for day_index in range(holding_days + 1):
        if day_index == 0:
            day_pnl = Decimal("0")
        else:
            day_pnl = daily_pnl

        starting = equity
        ending = equity + day_pnl
        peak = max(peak, ending)

        drawdown = safe_div(
            peak - ending,
            peak,
        ) * Decimal("100")

        rows.append({
            "day_index": day_index,
            "timestamp_utc": utc_future_days(day_index),
            "starting_equity_usd": starting,
            "daily_pnl_usd": day_pnl,
            "ending_equity_usd": ending,
            "drawdown_pct": drawdown,
            "open_positions": len(trades) if day_index < holding_days else 0,
            "closed_trades": 0 if day_index < holding_days else len(trades),
        })

        equity = ending

    return rows


def insert_equity_row(
    db_path,
    run_label,
    source_ranking_run_label,
    row,
    assumptions,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO paper_trading_equity_curve (
        run_label,
        source_ranking_run_label,
        day_index,
        timestamp_utc,
        starting_equity_usd,
        daily_pnl_usd,
        ending_equity_usd,
        drawdown_pct,
        open_positions,
        closed_trades,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        source_ranking_run_label,
        row["day_index"],
        row["timestamp_utc"],
        format(row["starting_equity_usd"], "f"),
        format(row["daily_pnl_usd"], "f"),
        format(row["ending_equity_usd"], "f"),
        format(row["drawdown_pct"], "f"),
        row["open_positions"],
        row["closed_trades"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def final_summary_verdict(
    eligible_candidates,
    trades_created,
    total_return_pct,
    max_drawdown_pct,
    profit_factor_value,
    min_trades,
    min_total_return_pct,
    max_drawdown_limit_pct,
    min_profit_factor,
):
    if eligible_candidates == 0:
        return "NO_GO_NO_ELIGIBLE_PAPER_CANDIDATES"

    if trades_created < min_trades:
        return "NO_GO_INSUFFICIENT_PAPER_TRADES"

    if total_return_pct < min_total_return_pct:
        return "NO_GO_WEAK_PAPER_RETURN"

    if max_drawdown_pct > max_drawdown_limit_pct:
        return "NO_GO_PAPER_DRAWDOWN"

    if profit_factor_value < min_profit_factor:
        return "NO_GO_WEAK_PAPER_PROFIT_FACTOR"

    return "GO_PAPER_TRADING_VALIDATED"


def recommended_action(verdict):
    if verdict == "GO_PAPER_TRADING_VALIDATED":
        return "PROMOTE_TO_DASHBOARD_AND_ALERTING"

    if verdict == "NO_GO_NO_ELIGIBLE_PAPER_CANDIDATES":
        return "KEEP_SCANNING_AND_WAIT_FOR_RANKED_CANDIDATES"

    if verdict == "NO_GO_INSUFFICIENT_PAPER_TRADES":
        return "COLLECT_MORE_PAPER_TRADES"

    if verdict == "NO_GO_WEAK_PAPER_RETURN":
        return "WAIT_FOR_STRONGER_EDGE"

    if verdict == "NO_GO_PAPER_DRAWDOWN":
        return "REDUCE_ALLOCATION_OR_REWORK_RISK"

    if verdict == "NO_GO_WEAK_PAPER_PROFIT_FACTOR":
        return "REWORK_CANDIDATE_SELECTION"

    return "OBSERVE_ONLY"


def summarize_paper_trading(
    candidates_seen,
    eligible_candidates,
    positions,
    trades,
    equity_curve,
    starting_equity_usd,
    min_trades,
    min_total_return_pct,
    max_drawdown_limit_pct,
    min_profit_factor,
):
    ending_equity = equity_curve[-1]["ending_equity_usd"] if equity_curve else starting_equity_usd

    total_pnl = ending_equity - starting_equity_usd

    total_return = safe_div(
        total_pnl,
        starting_equity_usd,
    ) * Decimal("100")

    max_drawdown = max(
        [row["drawdown_pct"] for row in equity_curve],
        default=Decimal("0"),
    )

    pnls = [
        trade["simulated_net_pnl_usd"]
        for trade in trades
    ]

    returns = [
        trade["simulated_net_return_pct"]
        for trade in trades
    ]

    pf = profit_factor(pnls)

    verdict = final_summary_verdict(
        eligible_candidates=eligible_candidates,
        trades_created=len(trades),
        total_return_pct=total_return,
        max_drawdown_pct=max_drawdown,
        profit_factor_value=pf,
        min_trades=min_trades,
        min_total_return_pct=min_total_return_pct,
        max_drawdown_limit_pct=max_drawdown_limit_pct,
        min_profit_factor=min_profit_factor,
    )

    return {
        "candidates_seen": candidates_seen,
        "eligible_candidates": eligible_candidates,
        "positions_created": len(positions),
        "trades_created": len(trades),
        "starting_equity_usd": starting_equity_usd,
        "ending_equity_usd": ending_equity,
        "total_pnl_usd": total_pnl,
        "total_return_pct": total_return,
        "max_drawdown_pct": max_drawdown,
        "win_rate_pct": win_rate_pct(pnls),
        "avg_trade_return_pct": avg_trade_return_pct(returns),
        "profit_factor": pf,
        "final_verdict": verdict,
        "recommended_action": recommended_action(verdict),
    }


def insert_summary(
    db_path,
    run_label,
    source_ranking_run_label,
    summary,
    assumptions,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO paper_trading_summary (
        run_label,
        source_ranking_run_label,
        candidates_seen,
        eligible_candidates,
        positions_created,
        trades_created,
        starting_equity_usd,
        ending_equity_usd,
        total_pnl_usd,
        total_return_pct,
        max_drawdown_pct,
        win_rate_pct,
        avg_trade_return_pct,
        profit_factor,
        final_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        source_ranking_run_label,
        summary["candidates_seen"],
        summary["eligible_candidates"],
        summary["positions_created"],
        summary["trades_created"],
        format(summary["starting_equity_usd"], "f"),
        format(summary["ending_equity_usd"], "f"),
        format(summary["total_pnl_usd"], "f"),
        format(summary["total_return_pct"], "f"),
        format(summary["max_drawdown_pct"], "f"),
        format(summary["win_rate_pct"], "f"),
        format(summary["avg_trade_return_pct"], "f"),
        format(summary["profit_factor"], "f"),
        summary["final_verdict"],
        summary["recommended_action"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def clean_decimal_dict(item):
    cleaned = {}

    for key, value in item.items():
        if isinstance(value, Decimal):
            cleaned[key] = format(value, "f")
        elif isinstance(value, list):
            cleaned[key] = value
        else:
            cleaned[key] = value

    return cleaned


def run_paper_trading_engine(
    db_path,
    ranking_run_label,
    run_label,
    starting_equity_usd,
    allocation_pct,
    max_allocation_usd,
    max_positions,
    gross_notional_multiplier,
    holding_days,
    perp_weight,
    default_cost_pct,
    min_composite_score,
    min_net_expected_edge_pct,
    min_edge_to_cost_ratio,
    min_position_net_return_pct,
    min_trades,
    min_total_return_pct,
    max_drawdown_limit_pct,
    min_profit_factor,
    allow_no_go_candidates,
):
    db_path = prepare_database(db_path)

    starting_equity_usd = to_decimal(starting_equity_usd)
    allocation_pct = to_decimal(allocation_pct)
    max_allocation_usd = to_decimal(max_allocation_usd)
    gross_notional_multiplier = to_decimal(gross_notional_multiplier)
    perp_weight = to_decimal(perp_weight)
    default_cost_pct = to_decimal(default_cost_pct)
    min_composite_score = to_decimal(min_composite_score)
    min_net_expected_edge_pct = to_decimal(min_net_expected_edge_pct)
    min_edge_to_cost_ratio = to_decimal(min_edge_to_cost_ratio)
    min_position_net_return_pct = to_decimal(min_position_net_return_pct)
    min_total_return_pct = to_decimal(min_total_return_pct)
    max_drawdown_limit_pct = to_decimal(max_drawdown_limit_pct)
    min_profit_factor = to_decimal(min_profit_factor)

    assumptions = {
        "research_only": True,
        "paper_trading_only": True,
        "no_private_keys": True,
        "no_signing": True,
        "no_real_trades": True,
        "no_order_execution": True,
        "ranking_run_label": ranking_run_label,
        "run_label": run_label,
        "starting_equity_usd": format(starting_equity_usd, "f"),
        "allocation_pct": format(allocation_pct, "f"),
        "max_allocation_usd": format(max_allocation_usd, "f"),
        "max_positions": int(max_positions),
        "gross_notional_multiplier": format(gross_notional_multiplier, "f"),
        "holding_days": int(holding_days),
        "perp_weight": format(perp_weight, "f"),
        "default_cost_pct": format(default_cost_pct, "f"),
        "min_composite_score": format(min_composite_score, "f"),
        "min_net_expected_edge_pct": format(min_net_expected_edge_pct, "f"),
        "min_edge_to_cost_ratio": format(min_edge_to_cost_ratio, "f"),
        "min_position_net_return_pct": format(min_position_net_return_pct, "f"),
        "min_trades": int(min_trades),
        "min_total_return_pct": format(min_total_return_pct, "f"),
        "max_drawdown_limit_pct": format(max_drawdown_limit_pct, "f"),
        "min_profit_factor": format(min_profit_factor, "f"),
        "allow_no_go_candidates": bool(allow_no_go_candidates),
    }

    candidates = load_ranked_candidates(
        db_path=db_path,
        ranking_run_label=ranking_run_label,
    )

    eligible = [
        candidate
        for candidate in candidates
        if is_candidate_eligible(
            candidate=candidate,
            min_composite_score=min_composite_score,
            min_net_expected_edge_pct=min_net_expected_edge_pct,
            min_edge_to_cost_ratio=min_edge_to_cost_ratio,
            allow_no_go_candidates=bool(allow_no_go_candidates),
        )
    ][:int(max_positions)]

    positions = []
    trades = []

    for candidate in eligible:
        position = build_paper_position(
            candidate=candidate,
            starting_equity_usd=starting_equity_usd,
            allocation_pct=allocation_pct,
            max_allocation_usd=max_allocation_usd,
            gross_notional_multiplier=gross_notional_multiplier,
            holding_days=int(holding_days),
            perp_weight=perp_weight,
            default_cost_pct=default_cost_pct,
            min_position_net_return_pct=min_position_net_return_pct,
        )

        position_id = insert_position(
            db_path=db_path,
            run_label=run_label,
            source_ranking_run_label=ranking_run_label,
            position=position,
            assumptions=assumptions,
        )

        positions.append({
            "id": position_id,
            **position,
        })

        if position["final_verdict"] == "GO_PAPER_POSITION":
            trade = simulate_trade_from_position(position)

            trade_id = insert_trade(
                db_path=db_path,
                run_label=run_label,
                source_ranking_run_label=ranking_run_label,
                position_id=position_id,
                trade=trade,
                assumptions=assumptions,
            )

            trades.append({
                "id": trade_id,
                "position_id": position_id,
                **trade,
            })

    equity_curve = build_equity_curve(
        starting_equity_usd=starting_equity_usd,
        trades=trades,
        holding_days=int(holding_days),
    )

    for row in equity_curve:
        insert_equity_row(
            db_path=db_path,
            run_label=run_label,
            source_ranking_run_label=ranking_run_label,
            row=row,
            assumptions=assumptions,
        )

    summary = summarize_paper_trading(
        candidates_seen=len(candidates),
        eligible_candidates=len(eligible),
        positions=positions,
        trades=trades,
        equity_curve=equity_curve,
        starting_equity_usd=starting_equity_usd,
        min_trades=int(min_trades),
        min_total_return_pct=min_total_return_pct,
        max_drawdown_limit_pct=max_drawdown_limit_pct,
        min_profit_factor=min_profit_factor,
    )

    summary_id = insert_summary(
        db_path=db_path,
        run_label=run_label,
        source_ranking_run_label=ranking_run_label,
        summary=summary,
        assumptions=assumptions,
    )

    ranked_positions = sorted(
        positions,
        key=lambda item: item["expected_net_return_pct"],
        reverse=True,
    )

    ranked_trades = sorted(
        trades,
        key=lambda item: item["simulated_net_pnl_usd"],
        reverse=True,
    )

    return {
        "run_label": run_label,
        "source_ranking_run_label": ranking_run_label,
        "summary_id": summary_id,
        "candidates_seen": len(candidates),
        "eligible_candidates": len(eligible),
        "positions_created": len(positions),
        "trades_created": len(trades),
        "equity_rows_created": len(equity_curve),
        "summary": clean_decimal_dict(summary),
        "top_positions": [
            clean_decimal_dict(item)
            for item in ranked_positions[:10]
        ],
        "top_trades": [
            clean_decimal_dict(item)
            for item in ranked_trades[:10]
        ],
        "global_verdict": summary["final_verdict"],
        "recommended_action": summary["recommended_action"],
    }


def parse_bool(value):
    text = str(value).strip().lower()

    return text in {"1", "true", "yes", "y", "on"}


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--ranking-run-label", default="mission_30_candidate_ranking_engine")
    parser.add_argument("--run-label", default="mission_31_paper_trading_engine")
    parser.add_argument("--starting-equity-usd", default="10000")
    parser.add_argument("--allocation-pct", default="10")
    parser.add_argument("--max-allocation-usd", default="1000")
    parser.add_argument("--max-positions", type=int, default=5)
    parser.add_argument("--gross-notional-multiplier", default="2")
    parser.add_argument("--holding-days", type=int, default=7)
    parser.add_argument("--perp-weight", default="0.5")
    parser.add_argument("--default-cost-pct", default="0.0755")
    parser.add_argument("--min-composite-score", default="75")
    parser.add_argument("--min-net-expected-edge-pct", default="0.02")
    parser.add_argument("--min-edge-to-cost-ratio", default="1.50")
    parser.add_argument("--min-position-net-return-pct", default="0.02")
    parser.add_argument("--min-trades", type=int, default=1)
    parser.add_argument("--min-total-return-pct", default="0.01")
    parser.add_argument("--max-drawdown-limit-pct", default="5")
    parser.add_argument("--min-profit-factor", default="1.20")
    parser.add_argument("--allow-no-go-candidates", default="false")

    args = parser.parse_args()

    print("DeltaGrid Paper Trading Engine")
    print("Mode: paper-trading only")
    print("No private keys. No signing. No real trades.")

    result = run_paper_trading_engine(
        db_path=args.db_path,
        ranking_run_label=args.ranking_run_label,
        run_label=args.run_label,
        starting_equity_usd=Decimal(args.starting_equity_usd),
        allocation_pct=Decimal(args.allocation_pct),
        max_allocation_usd=Decimal(args.max_allocation_usd),
        max_positions=args.max_positions,
        gross_notional_multiplier=Decimal(args.gross_notional_multiplier),
        holding_days=args.holding_days,
        perp_weight=Decimal(args.perp_weight),
        default_cost_pct=Decimal(args.default_cost_pct),
        min_composite_score=Decimal(args.min_composite_score),
        min_net_expected_edge_pct=Decimal(args.min_net_expected_edge_pct),
        min_edge_to_cost_ratio=Decimal(args.min_edge_to_cost_ratio),
        min_position_net_return_pct=Decimal(args.min_position_net_return_pct),
        min_trades=args.min_trades,
        min_total_return_pct=Decimal(args.min_total_return_pct),
        max_drawdown_limit_pct=Decimal(args.max_drawdown_limit_pct),
        min_profit_factor=Decimal(args.min_profit_factor),
        allow_no_go_candidates=parse_bool(args.allow_no_go_candidates),
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

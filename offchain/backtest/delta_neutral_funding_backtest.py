import argparse
import json
import os
import sqlite3
import sys
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


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def avg(values):
    if not values:
        return Decimal("0")

    return sum(values, Decimal("0")) / Decimal(len(values))


def percent_ratio(part, total):
    if total == 0:
        return Decimal("0")

    return Decimal(part) / Decimal(total) * Decimal("100")


def bps_to_pct(bps):
    return to_decimal(bps) / Decimal("100")


def profit_factor(trade_returns):
    wins = [
        value
        for value in trade_returns
        if value > 0
    ]

    losses = [
        abs(value)
        for value in trade_returns
        if value < 0
    ]

    gross_profit = sum(wins, Decimal("0"))
    gross_loss = sum(losses, Decimal("0"))

    if gross_loss == 0:
        if gross_profit > 0:
            return Decimal("999")

        return Decimal("0")

    return gross_profit / gross_loss


def win_rate_pct(trade_returns):
    if not trade_returns:
        return Decimal("0")

    wins = sum(
        1
        for value in trade_returns
        if value > 0
    )

    return Decimal(wins) / Decimal(len(trade_returns)) * Decimal("100")


def max_drawdown_pct(equity_curve):
    if not equity_curve:
        return Decimal("0")

    peak = equity_curve[0]
    worst = Decimal("0")

    for equity in equity_curve:
        if equity > peak:
            peak = equity

        if peak == 0:
            continue

        drawdown = (peak - equity) / peak * Decimal("100")

        if drawdown > worst:
            worst = drawdown

    return worst


def ensure_schema(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS delta_neutral_funding_backtest_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_run_label TEXT NOT NULL,
        symbol TEXT NOT NULL,
        entry_time_utc TEXT NOT NULL,
        exit_time_utc TEXT NOT NULL,
        funding_windows INTEGER NOT NULL,
        entry_basis_pct TEXT NOT NULL,
        exit_basis_pct TEXT NOT NULL,
        gross_funding_return_pct TEXT NOT NULL,
        basis_pnl_pct TEXT NOT NULL,
        execution_cost_pct TEXT NOT NULL,
        net_return_pct TEXT NOT NULL,
        min_annualized_funding_pct TEXT NOT NULL,
        max_annualized_funding_pct TEXT NOT NULL,
        exit_reason TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS delta_neutral_funding_backtest_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_run_label TEXT NOT NULL,
        symbol TEXT NOT NULL,
        funding_observations INTEGER NOT NULL,
        trades_count INTEGER NOT NULL,
        net_return_pct TEXT NOT NULL,
        avg_trade_return_pct TEXT NOT NULL,
        gross_funding_return_pct TEXT NOT NULL,
        basis_pnl_pct TEXT NOT NULL,
        execution_cost_pct TEXT NOT NULL,
        win_rate_pct TEXT NOT NULL,
        max_drawdown_pct TEXT NOT NULL,
        profit_factor TEXT NOT NULL,
        positive_funding_ratio_pct TEXT NOT NULL,
        avg_annualized_funding_pct TEXT NOT NULL,
        min_annualized_funding_pct TEXT NOT NULL,
        max_annualized_funding_pct TEXT NOT NULL,
        final_verdict TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS delta_neutral_funding_backtest_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_run_label TEXT NOT NULL,
        symbol TEXT NOT NULL,
        results_created INTEGER NOT NULL,
        trades_created INTEGER NOT NULL,
        go_count INTEGER NOT NULL,
        no_go_count INTEGER NOT NULL,
        best_result_id INTEGER,
        best_net_return_pct TEXT NOT NULL,
        global_verdict TEXT NOT NULL,
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
    ensure_schema(db_path)

    return db_path


def load_funding_rows(db_path, symbol, source_run_label):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    rows = cur.execute("""
    SELECT
        funding_time_utc,
        funding_rate,
        annualized_rate_pct
    FROM funding_rates
    WHERE symbol = ?
    AND source = ?
    ORDER BY funding_time_utc ASC
    """, (
        symbol.upper(),
        source_run_label,
    )).fetchall()

    conn.close()

    return [
        {
            "funding_time_utc": row[0],
            "funding_rate": to_decimal(row[1]),
            "annualized_rate_pct": to_decimal(row[2]),
        }
        for row in rows
    ]


def load_basis_rows(db_path, symbol, source_run_label):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    rows = cur.execute("""
    SELECT
        timestamp_utc,
        basis_pct,
        annualized_funding_rate_pct,
        open_interest,
        verdict
    FROM spot_perp_basis_snapshots
    WHERE symbol = ?
    AND source = ?
    ORDER BY timestamp_utc ASC, id ASC
    """, (
        symbol.upper(),
        source_run_label,
    )).fetchall()

    conn.close()

    return [
        {
            "timestamp_utc": row[0],
            "basis_pct": to_decimal(row[1]),
            "annualized_funding_rate_pct": to_decimal(row[2]),
            "open_interest": None if row[3] is None else to_decimal(row[3]),
            "basis_verdict": row[4],
        }
        for row in rows
    ]


def basis_for_time(basis_rows, timestamp_utc):
    if not basis_rows:
        raise ValueError("No basis rows available")

    selected = basis_rows[0]

    for row in basis_rows:
        if row["timestamp_utc"] <= timestamp_utc:
            selected = row
        else:
            break

    return selected


def funding_path_statistics(funding_rows):
    if not funding_rows:
        raise ValueError("No funding rows available")

    funding_rates = [
        row["funding_rate"]
        for row in funding_rows
    ]

    annualized_rates = [
        row["annualized_rate_pct"]
        for row in funding_rows
    ]

    positive_count = sum(
        1
        for rate in funding_rates
        if rate > 0
    )

    return {
        "funding_observations": len(funding_rows),
        "positive_funding_ratio_pct": percent_ratio(
            positive_count,
            len(funding_rows),
        ),
        "avg_annualized_funding_pct": avg(annualized_rates),
        "min_annualized_funding_pct": min(annualized_rates),
        "max_annualized_funding_pct": max(annualized_rates),
    }


def should_enter(row, basis_row, entry_annualized_pct, min_basis_pct, max_basis_pct):
    if row["funding_rate"] <= 0:
        return False

    if row["annualized_rate_pct"] < entry_annualized_pct:
        return False

    if basis_row["basis_pct"] < min_basis_pct:
        return False

    if basis_row["basis_pct"] > max_basis_pct:
        return False

    if basis_row["open_interest"] is None or basis_row["open_interest"] <= 0:
        return False

    return True


def exit_reason_for_row(
    row,
    basis_row,
    holding_windows,
    max_holding_windows,
    exit_annualized_pct,
    min_basis_pct,
    max_basis_pct,
):
    if row["funding_rate"] <= 0:
        return "NON_POSITIVE_FUNDING_EXIT"

    if row["annualized_rate_pct"] < exit_annualized_pct:
        return "LOW_FUNDING_EXIT"

    if basis_row["basis_pct"] < min_basis_pct:
        return "BASIS_BELOW_RANGE_EXIT"

    if basis_row["basis_pct"] > max_basis_pct:
        return "BASIS_ABOVE_RANGE_EXIT"

    if holding_windows >= max_holding_windows:
        return "MAX_HOLDING_WINDOWS_EXIT"

    return None


def simulate_delta_neutral_backtest(
    funding_rows,
    basis_rows,
    entry_annualized_pct,
    exit_annualized_pct,
    min_basis_pct,
    max_basis_pct,
    max_holding_windows,
    execution_cost_bps,
):
    if not funding_rows:
        raise ValueError("No funding rows available")

    if not basis_rows:
        raise ValueError("No basis rows available")

    execution_cost_pct = bps_to_pct(execution_cost_bps)

    in_position = False
    entry_time = None
    entry_basis_pct = None
    gross_funding_return_pct = Decimal("0")
    funding_windows = 0
    min_trade_annualized = None
    max_trade_annualized = None

    trades = []

    for index, row in enumerate(funding_rows):
        basis_row = basis_for_time(
            basis_rows,
            row["funding_time_utc"],
        )

        if not in_position:
            if should_enter(
                row=row,
                basis_row=basis_row,
                entry_annualized_pct=entry_annualized_pct,
                min_basis_pct=min_basis_pct,
                max_basis_pct=max_basis_pct,
            ):
                in_position = True
                entry_time = row["funding_time_utc"]
                entry_basis_pct = basis_row["basis_pct"]
                gross_funding_return_pct = Decimal("0")
                funding_windows = 0
                min_trade_annualized = row["annualized_rate_pct"]
                max_trade_annualized = row["annualized_rate_pct"]
            else:
                continue

        gross_funding_return_pct += row["funding_rate"] * Decimal("100")
        funding_windows += 1

        min_trade_annualized = min(
            min_trade_annualized,
            row["annualized_rate_pct"],
        )

        max_trade_annualized = max(
            max_trade_annualized,
            row["annualized_rate_pct"],
        )

        reason = exit_reason_for_row(
            row=row,
            basis_row=basis_row,
            holding_windows=funding_windows,
            max_holding_windows=max_holding_windows,
            exit_annualized_pct=exit_annualized_pct,
            min_basis_pct=min_basis_pct,
            max_basis_pct=max_basis_pct,
        )

        if index == len(funding_rows) - 1 and reason is None:
            reason = "END_OF_SAMPLE_EXIT"

        if reason is not None:
            exit_basis_pct = basis_row["basis_pct"]
            basis_pnl_pct = entry_basis_pct - exit_basis_pct

            net_return_pct = (
                gross_funding_return_pct
                + basis_pnl_pct
                - execution_cost_pct
            )

            trades.append({
                "entry_time_utc": entry_time,
                "exit_time_utc": row["funding_time_utc"],
                "funding_windows": funding_windows,
                "entry_basis_pct": entry_basis_pct,
                "exit_basis_pct": exit_basis_pct,
                "gross_funding_return_pct": gross_funding_return_pct,
                "basis_pnl_pct": basis_pnl_pct,
                "execution_cost_pct": execution_cost_pct,
                "net_return_pct": net_return_pct,
                "min_annualized_funding_pct": min_trade_annualized,
                "max_annualized_funding_pct": max_trade_annualized,
                "exit_reason": reason,
            })

            in_position = False
            entry_time = None
            entry_basis_pct = None
            gross_funding_return_pct = Decimal("0")
            funding_windows = 0
            min_trade_annualized = None
            max_trade_annualized = None

    return trades


def summarize_backtest(
    funding_rows,
    trades,
    min_observations,
    min_trades,
    min_avg_annualized_pct,
    min_net_return_pct,
    max_drawdown_limit_pct,
    min_profit_factor,
):
    stats = funding_path_statistics(funding_rows)

    trade_returns = [
        trade["net_return_pct"]
        for trade in trades
    ]

    equity = Decimal("100")
    equity_curve = [equity]

    for trade_return in trade_returns:
        equity = equity * (Decimal("1") + trade_return / Decimal("100"))
        equity_curve.append(equity)

    net_return_pct = equity - Decimal("100")

    gross_funding_return_pct = sum(
        [
            trade["gross_funding_return_pct"]
            for trade in trades
        ],
        Decimal("0"),
    )

    basis_pnl_pct = sum(
        [
            trade["basis_pnl_pct"]
            for trade in trades
        ],
        Decimal("0"),
    )

    execution_cost_pct = sum(
        [
            trade["execution_cost_pct"]
            for trade in trades
        ],
        Decimal("0"),
    )

    pf = profit_factor(trade_returns)
    max_dd = max_drawdown_pct(equity_curve)

    result = {
        **stats,
        "trades_count": len(trades),
        "net_return_pct": net_return_pct,
        "avg_trade_return_pct": avg(trade_returns),
        "gross_funding_return_pct": gross_funding_return_pct,
        "basis_pnl_pct": basis_pnl_pct,
        "execution_cost_pct": execution_cost_pct,
        "win_rate_pct": win_rate_pct(trade_returns),
        "max_drawdown_pct": max_dd,
        "profit_factor": pf,
    }

    result["final_verdict"] = final_verdict(
        funding_observations=result["funding_observations"],
        trades_count=result["trades_count"],
        avg_annualized_funding_pct=result["avg_annualized_funding_pct"],
        net_return_pct=result["net_return_pct"],
        max_drawdown=result["max_drawdown_pct"],
        pf=result["profit_factor"],
        min_observations=min_observations,
        min_trades=min_trades,
        min_avg_annualized_pct=min_avg_annualized_pct,
        min_net_return_pct=min_net_return_pct,
        max_drawdown_limit_pct=max_drawdown_limit_pct,
        min_profit_factor=min_profit_factor,
    )

    result["recommended_action"] = recommended_action(result["final_verdict"])

    return result


def final_verdict(
    funding_observations,
    trades_count,
    avg_annualized_funding_pct,
    net_return_pct,
    max_drawdown,
    pf,
    min_observations,
    min_trades,
    min_avg_annualized_pct,
    min_net_return_pct,
    max_drawdown_limit_pct,
    min_profit_factor,
):
    if funding_observations < min_observations:
        return "INSUFFICIENT_FUNDING_HISTORY"

    if avg_annualized_funding_pct < min_avg_annualized_pct:
        return "NO_GO_LOW_AVG_FUNDING"

    if trades_count < min_trades:
        return "INSUFFICIENT_TRADES"

    if net_return_pct < min_net_return_pct:
        return "NO_GO_WEAK_NET_RETURN"

    if max_drawdown > max_drawdown_limit_pct:
        return "NO_GO_DRAWDOWN_TOO_HIGH"

    if pf < min_profit_factor:
        return "NO_GO_WEAK_PROFIT_FACTOR"

    return "GO_FOR_RESEARCH"


def recommended_action(verdict):
    if verdict == "GO_FOR_RESEARCH":
        return "PROMOTE_TO_WALK_FORWARD_FUNDING_VALIDATION"

    if verdict == "INSUFFICIENT_FUNDING_HISTORY":
        return "COLLECT_MORE_FUNDING_HISTORY"

    if verdict == "NO_GO_LOW_AVG_FUNDING":
        return "WAIT_FOR_HIGHER_AVERAGE_FUNDING"

    if verdict == "INSUFFICIENT_TRADES":
        return "BROADEN_SAMPLE_OR_LOWER_THRESHOLDS"

    if verdict == "NO_GO_WEAK_NET_RETURN":
        return "REJECT_WEAK_CARRY"

    if verdict == "NO_GO_DRAWDOWN_TOO_HIGH":
        return "TIGHTEN_BASIS_AND_EXIT_RISK"

    if verdict == "NO_GO_WEAK_PROFIT_FACTOR":
        return "REWORK_ENTRY_EXIT_RULES"

    return "OBSERVE_ONLY"


def insert_trade(
    db_path,
    run_label,
    source_run_label,
    symbol,
    trade,
    assumptions,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO delta_neutral_funding_backtest_trades (
        run_label,
        source_run_label,
        symbol,
        entry_time_utc,
        exit_time_utc,
        funding_windows,
        entry_basis_pct,
        exit_basis_pct,
        gross_funding_return_pct,
        basis_pnl_pct,
        execution_cost_pct,
        net_return_pct,
        min_annualized_funding_pct,
        max_annualized_funding_pct,
        exit_reason,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        source_run_label,
        symbol.upper(),
        trade["entry_time_utc"],
        trade["exit_time_utc"],
        trade["funding_windows"],
        format(trade["entry_basis_pct"], "f"),
        format(trade["exit_basis_pct"], "f"),
        format(trade["gross_funding_return_pct"], "f"),
        format(trade["basis_pnl_pct"], "f"),
        format(trade["execution_cost_pct"], "f"),
        format(trade["net_return_pct"], "f"),
        format(trade["min_annualized_funding_pct"], "f"),
        format(trade["max_annualized_funding_pct"], "f"),
        trade["exit_reason"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def insert_result(
    db_path,
    run_label,
    source_run_label,
    symbol,
    result,
    assumptions,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO delta_neutral_funding_backtest_results (
        run_label,
        source_run_label,
        symbol,
        funding_observations,
        trades_count,
        net_return_pct,
        avg_trade_return_pct,
        gross_funding_return_pct,
        basis_pnl_pct,
        execution_cost_pct,
        win_rate_pct,
        max_drawdown_pct,
        profit_factor,
        positive_funding_ratio_pct,
        avg_annualized_funding_pct,
        min_annualized_funding_pct,
        max_annualized_funding_pct,
        final_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        source_run_label,
        symbol.upper(),
        result["funding_observations"],
        result["trades_count"],
        format(result["net_return_pct"], "f"),
        format(result["avg_trade_return_pct"], "f"),
        format(result["gross_funding_return_pct"], "f"),
        format(result["basis_pnl_pct"], "f"),
        format(result["execution_cost_pct"], "f"),
        format(result["win_rate_pct"], "f"),
        format(result["max_drawdown_pct"], "f"),
        format(result["profit_factor"], "f"),
        format(result["positive_funding_ratio_pct"], "f"),
        format(result["avg_annualized_funding_pct"], "f"),
        format(result["min_annualized_funding_pct"], "f"),
        format(result["max_annualized_funding_pct"], "f"),
        result["final_verdict"],
        result["recommended_action"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def insert_summary(
    db_path,
    run_label,
    source_run_label,
    symbol,
    result_id,
    result,
    trades_count,
    assumptions,
):
    go_count = 1 if result["final_verdict"] == "GO_FOR_RESEARCH" else 0
    no_go_count = 1 - go_count

    if go_count:
        global_verdict = "DELTA_NEUTRAL_FUNDING_BACKTEST_GO_NO_LIVE_TRADING"
        action = "PROMOTE_TO_WALK_FORWARD_FUNDING_VALIDATION"
    else:
        global_verdict = "REJECT_DELTA_NEUTRAL_FUNDING_BACKTEST_NO_LIVE_TRADING"
        action = result["recommended_action"]

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO delta_neutral_funding_backtest_summary (
        run_label,
        source_run_label,
        symbol,
        results_created,
        trades_created,
        go_count,
        no_go_count,
        best_result_id,
        best_net_return_pct,
        global_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        source_run_label,
        symbol.upper(),
        1,
        trades_count,
        go_count,
        no_go_count,
        result_id,
        format(result["net_return_pct"], "f"),
        global_verdict,
        action,
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id), global_verdict, action


def run_delta_neutral_funding_backtest(
    db_path,
    symbol,
    source_run_label,
    run_label,
    entry_annualized_pct,
    exit_annualized_pct,
    min_basis_pct,
    max_basis_pct,
    max_holding_windows,
    execution_cost_bps,
    min_observations,
    min_trades,
    min_avg_annualized_pct,
    min_net_return_pct,
    max_drawdown_limit_pct,
    min_profit_factor,
):
    db_path = prepare_database(db_path)
    symbol = symbol.upper()

    assumptions = {
        "research_only": True,
        "no_private_keys": True,
        "no_signing": True,
        "no_real_trades": True,
        "no_order_execution": True,
        "symbol": symbol,
        "source_run_label": source_run_label,
        "run_label": run_label,
        "entry_annualized_pct": format(to_decimal(entry_annualized_pct), "f"),
        "exit_annualized_pct": format(to_decimal(exit_annualized_pct), "f"),
        "min_basis_pct": format(to_decimal(min_basis_pct), "f"),
        "max_basis_pct": format(to_decimal(max_basis_pct), "f"),
        "max_holding_windows": int(max_holding_windows),
        "execution_cost_bps": format(to_decimal(execution_cost_bps), "f"),
        "min_observations": int(min_observations),
        "min_trades": int(min_trades),
        "min_avg_annualized_pct": format(to_decimal(min_avg_annualized_pct), "f"),
        "min_net_return_pct": format(to_decimal(min_net_return_pct), "f"),
        "max_drawdown_limit_pct": format(to_decimal(max_drawdown_limit_pct), "f"),
        "min_profit_factor": format(to_decimal(min_profit_factor), "f"),
    }

    funding_rows = load_funding_rows(
        db_path=db_path,
        symbol=symbol,
        source_run_label=source_run_label,
    )

    basis_rows = load_basis_rows(
        db_path=db_path,
        symbol=symbol,
        source_run_label=source_run_label,
    )

    trades = simulate_delta_neutral_backtest(
        funding_rows=funding_rows,
        basis_rows=basis_rows,
        entry_annualized_pct=to_decimal(entry_annualized_pct),
        exit_annualized_pct=to_decimal(exit_annualized_pct),
        min_basis_pct=to_decimal(min_basis_pct),
        max_basis_pct=to_decimal(max_basis_pct),
        max_holding_windows=int(max_holding_windows),
        execution_cost_bps=to_decimal(execution_cost_bps),
    )

    trade_ids = [
        insert_trade(
            db_path=db_path,
            run_label=run_label,
            source_run_label=source_run_label,
            symbol=symbol,
            trade=trade,
            assumptions=assumptions,
        )
        for trade in trades
    ]

    result = summarize_backtest(
        funding_rows=funding_rows,
        trades=trades,
        min_observations=int(min_observations),
        min_trades=int(min_trades),
        min_avg_annualized_pct=to_decimal(min_avg_annualized_pct),
        min_net_return_pct=to_decimal(min_net_return_pct),
        max_drawdown_limit_pct=to_decimal(max_drawdown_limit_pct),
        min_profit_factor=to_decimal(min_profit_factor),
    )

    result_id = insert_result(
        db_path=db_path,
        run_label=run_label,
        source_run_label=source_run_label,
        symbol=symbol,
        result=result,
        assumptions=assumptions,
    )

    summary_id, global_verdict, summary_action = insert_summary(
        db_path=db_path,
        run_label=run_label,
        source_run_label=source_run_label,
        symbol=symbol,
        result_id=result_id,
        result=result,
        trades_count=len(trades),
        assumptions=assumptions,
    )

    return {
        "run_label": run_label,
        "source_run_label": source_run_label,
        "symbol": symbol,
        "result_id": result_id,
        "summary_id": summary_id,
        "trade_ids": trade_ids,
        "funding_observations": result["funding_observations"],
        "trades_count": result["trades_count"],
        "net_return_pct": format(result["net_return_pct"], "f"),
        "avg_trade_return_pct": format(result["avg_trade_return_pct"], "f"),
        "gross_funding_return_pct": format(result["gross_funding_return_pct"], "f"),
        "basis_pnl_pct": format(result["basis_pnl_pct"], "f"),
        "execution_cost_pct": format(result["execution_cost_pct"], "f"),
        "win_rate_pct": format(result["win_rate_pct"], "f"),
        "max_drawdown_pct": format(result["max_drawdown_pct"], "f"),
        "profit_factor": format(result["profit_factor"], "f"),
        "positive_funding_ratio_pct": format(result["positive_funding_ratio_pct"], "f"),
        "avg_annualized_funding_pct": format(result["avg_annualized_funding_pct"], "f"),
        "min_annualized_funding_pct": format(result["min_annualized_funding_pct"], "f"),
        "max_annualized_funding_pct": format(result["max_annualized_funding_pct"], "f"),
        "final_verdict": result["final_verdict"],
        "recommended_action": result["recommended_action"],
        "results_created": 1,
        "trades_created": len(trades),
        "summary_results_created": 1,
        "global_verdict": global_verdict,
        "summary_recommended_action": summary_action,
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--source-run-label", default="mission_23_funding_basis_ingestion")
    parser.add_argument("--run-label", default="mission_25_delta_neutral_funding_backtest")
    parser.add_argument("--entry-annualized-pct", default="8")
    parser.add_argument("--exit-annualized-pct", default="4")
    parser.add_argument("--min-basis-pct", default="-0.30")
    parser.add_argument("--max-basis-pct", default="2.00")
    parser.add_argument("--max-holding-windows", type=int, default=20)
    parser.add_argument("--execution-cost-bps", default="20")
    parser.add_argument("--min-observations", type=int, default=10)
    parser.add_argument("--min-trades", type=int, default=1)
    parser.add_argument("--min-avg-annualized-pct", default="8")
    parser.add_argument("--min-net-return-pct", default="0.10")
    parser.add_argument("--max-drawdown-limit-pct", default="5")
    parser.add_argument("--min-profit-factor", default="1.10")

    args = parser.parse_args()

    print("DeltaGrid Delta-Neutral Funding Backtest Engine")
    print("Mode: research-only")
    print("No private keys. No signing. No real trades.")

    result = run_delta_neutral_funding_backtest(
        db_path=args.db_path,
        symbol=args.symbol,
        source_run_label=args.source_run_label,
        run_label=args.run_label,
        entry_annualized_pct=Decimal(args.entry_annualized_pct),
        exit_annualized_pct=Decimal(args.exit_annualized_pct),
        min_basis_pct=Decimal(args.min_basis_pct),
        max_basis_pct=Decimal(args.max_basis_pct),
        max_holding_windows=args.max_holding_windows,
        execution_cost_bps=Decimal(args.execution_cost_bps),
        min_observations=args.min_observations,
        min_trades=args.min_trades,
        min_avg_annualized_pct=Decimal(args.min_avg_annualized_pct),
        min_net_return_pct=Decimal(args.min_net_return_pct),
        max_drawdown_limit_pct=Decimal(args.max_drawdown_limit_pct),
        min_profit_factor=Decimal(args.min_profit_factor),
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

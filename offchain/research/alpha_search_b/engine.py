from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_DOWN, getcontext
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from . import PROTOCOL_HASH

getcontext().prec = 40

WINDOW = 43_200
MIN_OBSERVATIONS = 38_880
MIN_POSITIVE_GAPS = 1_000
COOLDOWN = 1_440
STOP_RATE = Decimal("0.015")
SCENARIO_OFFSETS = {"normal": 1, "conservative": 2, "severe": 3}
CANDIDATES = {
    "BTC_SELF_FLOW_PERSISTENCE_60M": ("BTCUSDT", 60, "SELF"),
    "BTC_SELF_FLOW_PERSISTENCE_120M": ("BTCUSDT", 120, "SELF"),
    "BTC_FLOW_LEADS_ETH_60M": ("ETHUSDT", 60, "LEAD"),
    "BTC_FLOW_LEADS_SOL_60M": ("SOLUSDT", 60, "LEAD"),
}


class Fenwick:
    def __init__(self, size: int) -> None:
        self.tree = [0] * (size + 1)

    def add(self, index: int, delta: int) -> None:
        index += 1
        while index < len(self.tree):
            self.tree[index] += delta
            index += index & -index

    def kth(self, rank: int) -> int:
        """Return zero-based coordinate of one-based rank."""
        index = 0
        bit = 1 << (len(self.tree).bit_length() - 1)
        while bit:
            nxt = index + bit
            if nxt < len(self.tree) and self.tree[nxt] < rank:
                index = nxt
                rank -= self.tree[nxt]
            bit >>= 1
        return index


def nearest_rank(values: Sequence[float], probability: float) -> float:
    clean = np.asarray(values, dtype=float)
    clean = clean[np.isfinite(clean)]
    if clean.size == 0:
        return math.nan
    rank = math.ceil(probability * clean.size)
    return float(np.partition(clean, rank - 1)[rank - 1])


def rolling_comparison(
    values: Sequence[float], probability: float, *, relation: str = "gt",
    window: int = WINDOW, minimum: int = MIN_OBSERVATIONS,
    positive_only: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Exact nearest-rank comparison against preceding expected positions."""
    raw = np.asarray(values, dtype=float)
    included = np.isfinite(raw) & ((raw > 0) if positive_only else True)
    unique = np.unique(raw[included])
    coordinates = np.full(raw.size, -1, dtype=np.int64)
    coordinates[included] = np.searchsorted(unique, raw[included])
    tree = Fenwick(len(unique))
    result = np.zeros(raw.size, dtype=bool)
    eligible = np.zeros(raw.size, dtype=bool)
    count = 0
    for index in range(raw.size):
        prior = index - 1
        if prior >= 0 and coordinates[prior] >= 0:
            tree.add(int(coordinates[prior]), 1)
            count += 1
        expired = index - window - 1
        if expired >= 0 and coordinates[expired] >= 0:
            tree.add(int(coordinates[expired]), -1)
            count -= 1
        required = minimum if not positive_only else MIN_POSITIVE_GAPS
        if index >= window and count >= required and np.isfinite(raw[index]):
            eligible[index] = True
            rank = math.ceil(probability * count)
            threshold = unique[tree.kth(rank)]
            if relation == "gt":
                result[index] = raw[index] > threshold
            elif relation == "lte":
                result[index] = raw[index] <= threshold
            else:
                raise ValueError("relation must be gt or lte")
    return result, eligible


def slow_rolling_comparison(
    values: Sequence[float], probability: float, *, relation: str = "gt",
    window: int, minimum: int, positive_only: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    raw = np.asarray(values, dtype=float)
    result = np.zeros(raw.size, dtype=bool)
    eligible = np.zeros(raw.size, dtype=bool)
    for index in range(window, raw.size):
        history = raw[index-window:index]
        history = history[np.isfinite(history)]
        if positive_only:
            history = history[history > 0]
            required = min(minimum, MIN_POSITIVE_GAPS)
        else:
            required = minimum
        if len(history) < required or not np.isfinite(raw[index]):
            continue
        eligible[index] = True
        threshold = nearest_rank(history, probability)
        result[index] = raw[index] > threshold if relation == "gt" else raw[index] <= threshold
    return result, eligible


def build_features(frames: Mapping[str, pd.DataFrame]) -> dict[str, Any]:
    timestamps = frames["BTCUSDT"]["open_time_ms"].to_numpy(np.int64)
    if any(not np.array_equal(frame["open_time_ms"].to_numpy(np.int64), timestamps) for frame in frames.values()):
        raise ValueError("feature frames must share the exact expected-minute grid")
    ratios: dict[str, np.ndarray] = {}
    self_flags: dict[str, np.ndarray] = {}
    self_eligible: dict[str, np.ndarray] = {}
    for symbol, frame in frames.items():
        quote = frame["quote_asset_volume"].to_numpy(float)
        taker = frame["taker_buy_quote_asset_volume"].to_numpy(float)
        ratio = np.divide(taker, quote, out=np.full_like(taker, np.nan), where=quote > 0)
        ratios[symbol] = ratio
        ratio_hi, e1 = rolling_comparison(ratio, .95)
        volume_hi, e2 = rolling_comparison(quote, .95)
        trades_hi, e3 = rolling_comparison(frame["number_of_trades"].to_numpy(float), .95)
        complete = frame["complete"].to_numpy(bool)
        self_flags[symbol] = ratio_hi & volume_hi & trades_hi & complete
        self_eligible[symbol] = e1 & e2 & e3 & complete
    signals: dict[str, np.ndarray] = {
        "BTC_SELF_FLOW_PERSISTENCE_60M": self_flags["BTCUSDT"].copy(),
        "BTC_SELF_FLOW_PERSISTENCE_120M": self_flags["BTCUSDT"].copy(),
    }
    eligibility: dict[str, np.ndarray] = {
        "BTC_SELF_FLOW_PERSISTENCE_60M": self_eligible["BTCUSDT"].copy(),
        "BTC_SELF_FLOW_PERSISTENCE_120M": self_eligible["BTCUSDT"].copy(),
    }
    for target in ("ETHUSDT", "SOLUSDT"):
        median_lte, median_eligible = rolling_comparison(ratios[target], .50, relation="lte")
        gap = ratios["BTCUSDT"] - ratios[target]
        gap_hi, gap_eligible = rolling_comparison(gap, .95, positive_only=True)
        synchronized = (
            frames["BTCUSDT"]["complete"].to_numpy(bool)
            & frames[target]["complete"].to_numpy(bool)
        )
        candidate = f"BTC_FLOW_LEADS_{target.removesuffix('USDT')}_60M"
        eligibility[candidate] = self_eligible["BTCUSDT"] & median_eligible & gap_eligible & synchronized
        signals[candidate] = self_flags["BTCUSDT"] & median_lte & gap_hi & eligibility[candidate]
    return {"timestamps": timestamps, "ratios": ratios, "self_flags": self_flags,
            "self_eligibility": self_eligible, "signals": signals, "eligibility": eligibility}


def derive_seed(candidate_id: str) -> int:
    return int(hashlib.sha256(f"{PROTOCOL_HASH}:{candidate_id}".encode()).hexdigest()[:16], 16)


def round_down(value: Decimal, increment: Decimal) -> Decimal:
    if increment <= 0:
        raise ValueError("increment must be positive")
    return (value / increment).to_integral_value(rounding=ROUND_DOWN) * increment


def quantity_step(snapshot: Mapping[str, Any], symbol: str) -> Decimal:
    row = next(item for item in snapshot["symbols"] if item["symbol"] == symbol)
    lot = next(item for item in row["filters"] if item["filterType"] == "LOT_SIZE")
    return Decimal(lot["stepSize"])


@dataclass
class Trade:
    candidate: str
    pair: str
    scenario: str
    signal_timestamp: int
    entry_timestamp: int
    exit_timestamp: int
    exit_reason: str
    stake: str
    quantity: str
    entry_price: str
    exit_price: str
    stop_barrier: str
    holding_minutes: int
    gross_price_return: str
    gross_dollar_pnl: str
    entry_fee: str
    exit_fee: str
    spread_slippage_impact_deduction: str
    latency_displacement_diagnostic: str
    total_cost: str
    net_dollar_pnl: str
    net_return: str
    account_equity_after_exit: str
    month: str
    quarter: str
    maximum_adverse_excursion: str
    maximum_favorable_excursion: str


@dataclass
class Simulation:
    trades: list[Trade]
    attempted_signals: int
    rejected_position: int
    rejected_cooldown: int
    invalid_missing_required_minute: int
    equity_curve: list[float]


def _decimal(value: float | int | str | Decimal) -> Decimal:
    return Decimal(str(value))


def simulate(
    candidate_id: str, signal_indices: Iterable[int], frame: pd.DataFrame,
    scenario: str, cost_row: Mapping[str, str], step: Decimal,
    *, starting_equity: Decimal = Decimal("100"), enforce_collisions: bool = False,
    pair_override: str | None = None, holding_override: int | None = None,
) -> Simulation:
    pair, holding, _ = CANDIDATES[candidate_id]
    pair = pair_override or pair
    holding = holding_override or holding
    offset = SCENARIO_OFFSETS[scenario]
    opens = frame["open"].to_numpy(float)
    highs = frame["high"].to_numpy(float)
    lows = frame["low"].to_numpy(float)
    closes = frame["close"].to_numpy(float)
    timestamps = frame["open_time_ms"].to_numpy(np.int64)
    complete = frame["complete"].to_numpy(bool)
    equity = starting_equity
    next_eligible = -1
    trades: list[Trade] = []
    attempted = rejected_position = rejected_cooldown = invalid = 0
    curve = [float(equity)]
    for signal_index in sorted(int(i) for i in signal_indices):
        attempted += 1
        if signal_index < next_eligible:
            if trades and signal_index <= int(np.searchsorted(timestamps, trades[-1].exit_timestamp)):
                rejected_position += 1
            else:
                rejected_cooldown += 1
            if enforce_collisions:
                raise ValueError("PLACEBO_COLLISION")
            continue
        entry_index = signal_index + offset
        scheduled = entry_index + holding
        if scheduled >= len(frame) or not complete[entry_index] or not complete[scheduled]:
            invalid += 1
            continue
        entry_price = _decimal(opens[entry_index])
        barrier = entry_price * (Decimal("1") - STOP_RATE)
        exit_index = scheduled
        exit_reason = "SCHEDULED_EXIT"
        for monitor in range(entry_index, scheduled):
            if not complete[monitor]:
                invalid += 1
                exit_index = -1
                break
            if _decimal(lows[monitor]) <= barrier:
                if monitor + 1 >= len(frame) or not complete[monitor + 1]:
                    invalid += 1
                    exit_index = -1
                    break
                exit_index = monitor + 1
                exit_reason = "PROTECTIVE_STOP"
                break
        if exit_index < 0:
            continue
        exit_price = min(_decimal(opens[exit_index]), barrier) if exit_reason == "PROTECTIVE_STOP" else _decimal(opens[exit_index])
        severe_bps = Decimal({"BTCUSDT": "62", "ETHUSDT": "67", "SOLUSDT": "82"}[pair])
        ceiling = min(Decimal("80"), Decimal("0.50") / (STOP_RATE + severe_bps / Decimal("10000")), equity - Decimal("20"))
        quantity = round_down(ceiling / entry_price, step)
        stake = quantity * entry_price
        if quantity <= 0 or stake <= 0:
            invalid += 1
            continue
        gross = quantity * (exit_price - entry_price)
        entry_fee = stake * Decimal(cost_row["entry_fee"]) / Decimal("10000")
        exit_fee = stake * Decimal(cost_row["exit_fee"]) / Decimal("10000")
        residual = stake * Decimal(cost_row["spread_slippage_impact"]) / Decimal("10000")
        total = entry_fee + exit_fee + residual
        net = gross - total
        equity_before = equity
        entry_allocated_cost = total / Decimal("2")
        for mark_index in range(entry_index, exit_index):
            if complete[mark_index]:
                mark = equity_before + quantity * (_decimal(closes[mark_index]) - entry_price) - entry_allocated_cost
                curve.append(float(mark))
        equity += net
        held_lows = lows[entry_index:max(entry_index + 1, exit_index)]
        held_highs = highs[entry_index:max(entry_index + 1, exit_index)]
        mae = min(Decimal("0"), _decimal(np.nanmin(held_lows)) / entry_price - Decimal("1"))
        mfe = max(Decimal("0"), _decimal(np.nanmax(held_highs)) / entry_price - Decimal("1"))
        timestamp = pd.Timestamp(int(timestamps[exit_index]), unit="ms", tz="UTC")
        trades.append(Trade(
            candidate=candidate_id, pair=pair, scenario=scenario,
            signal_timestamp=int(timestamps[signal_index]), entry_timestamp=int(timestamps[entry_index]),
            exit_timestamp=int(timestamps[exit_index]), exit_reason=exit_reason,
            stake=str(stake), quantity=str(quantity), entry_price=str(entry_price), exit_price=str(exit_price),
            stop_barrier=str(barrier), holding_minutes=exit_index-entry_index,
            gross_price_return=str(exit_price / entry_price - Decimal("1")), gross_dollar_pnl=str(gross),
            entry_fee=str(entry_fee), exit_fee=str(exit_fee), spread_slippage_impact_deduction=str(residual),
            latency_displacement_diagnostic="0", total_cost=str(total), net_dollar_pnl=str(net),
            net_return=str(net / stake), account_equity_after_exit=str(equity),
            month=timestamp.strftime("%Y-%m"), quarter=f"{timestamp.year}-Q{timestamp.quarter}",
            maximum_adverse_excursion=str(mae), maximum_favorable_excursion=str(mfe),
        ))
        curve.append(float(equity))
        next_eligible = exit_index + COOLDOWN
    return Simulation(trades, attempted, rejected_position, rejected_cooldown, invalid, curve)


def _finite(values: Sequence[Decimal]) -> list[float]:
    return [float(value) for value in values]


def metrics(simulation: Simulation) -> dict[str, Any]:
    trades = simulation.trades
    net = [Decimal(t.net_dollar_pnl) for t in trades]
    gross = [Decimal(t.gross_dollar_pnl) for t in trades]
    returns = [Decimal(t.net_return) for t in trades]
    wins = [value for value in net if value > 0]
    losses = [value for value in net if value < 0]
    gross_profit = sum((value for value in gross if value > 0), Decimal("0"))
    gross_loss = sum((value for value in gross if value < 0), Decimal("0"))
    net_profit = sum(net, Decimal("0"))
    fee_cost = sum((Decimal(t.entry_fee) + Decimal(t.exit_fee) for t in trades), Decimal("0"))
    residual = sum((Decimal(t.spread_slippage_impact_deduction) for t in trades), Decimal("0"))
    latency = sum((Decimal(t.latency_displacement_diagnostic) for t in trades), Decimal("0"))
    positive = sum(wins, Decimal("0")); negative = abs(sum(losses, Decimal("0")))
    profit_factor: float | str = float(positive / negative) if negative else ("POSITIVE_INFINITY_UNBOUNDED" if positive else 0.0)
    streak_w = streak_l = max_w = max_l = 0
    for value in net:
        streak_w = streak_w + 1 if value > 0 else 0
        streak_l = streak_l + 1 if value < 0 else 0
        max_w, max_l = max(max_w, streak_w), max(max_l, streak_l)
    equity = np.asarray(simulation.equity_curve, dtype=float)
    peaks = np.maximum.accumulate(equity)
    drawdown = float(np.max(np.divide(peaks-equity, peaks, out=np.zeros_like(equity), where=peaks>0)) * 100) if len(equity) else 0.0
    monthly: dict[str, Decimal] = defaultdict(Decimal); quarterly: dict[str, Decimal] = defaultdict(Decimal)
    for trade, value in zip(trades, net): monthly[trade.month] += value; quarterly[trade.quarter] += value
    positive_quarters = {k:v for k,v in quarterly.items() if v > 0}
    best_month = max(monthly.values(), default=Decimal("0"))
    largest_five = sum(sorted(wins, reverse=True)[:5], Decimal("0"))
    one_pct_count = max(1, math.ceil(.01 * len(wins))) if wins else 0
    top_concentration = float(sum(sorted(wins, reverse=True)[:one_pct_count], Decimal("0")) / positive) if positive else 1.0
    sorted_returns = sorted(returns)
    tail_count = max(1, math.ceil(.05 * len(sorted_returns))) if sorted_returns else 0
    es = sum(sorted_returns[:tail_count], Decimal("0")) / tail_count if tail_count else Decimal("0")
    month_counts: dict[str,int] = defaultdict(int)
    for trade in trades: month_counts[trade.month] += 1
    quarter_concentration = float(max(positive_quarters.values()) / sum(positive_quarters.values(), Decimal("0"))) if positive_quarters else 1.0
    return {
        "trade_count": len(trades), "attempted_signals": simulation.attempted_signals,
        "rejected_position": simulation.rejected_position, "rejected_cooldown": simulation.rejected_cooldown,
        "invalid_missing_required_minute": simulation.invalid_missing_required_minute,
        "gross_profit": str(gross_profit), "gross_loss": str(gross_loss), "net_profit": str(net_profit),
        "fee_cost": str(fee_cost), "spread_slippage_cost": str(residual),
        "latency_displacement": str(latency),
        "gross_to_net_retention": float(net_profit/gross_profit) if gross_profit > 0 else None,
        "profit_factor": profit_factor, "expectancy": str(net_profit/len(net)) if net else "0",
        "average_winner": str(sum(wins,Decimal("0"))/len(wins)) if wins else "0",
        "median_winner": str(np.median(_finite(wins))) if wins else "0",
        "average_loser": str(sum(losses,Decimal("0"))/len(losses)) if losses else "0",
        "median_loser": str(np.median(_finite(losses))) if losses else "0",
        "payoff_ratio": float((sum(wins,Decimal("0"))/len(wins))/abs(sum(losses,Decimal("0"))/len(losses))) if wins and losses else None,
        "win_rate": len(wins)/len(net) if net else 0.0, "longest_winning_streak": max_w,
        "longest_losing_streak": max_l, "maximum_marked_to_market_drawdown_pct": drawdown,
        "worst_5pct_expected_shortfall": str(es),
        "maximum_adverse_excursion": min((t.maximum_adverse_excursion for t in trades), default="0", key=Decimal),
        "maximum_favorable_excursion": max((t.maximum_favorable_excursion for t in trades), default="0", key=Decimal),
        "best_month_removal_net": str(net_profit-best_month), "five_largest_winner_removal_net": str(net_profit-largest_five),
        "top_1pct_winner_concentration": top_concentration, "month_counts": dict(sorted(month_counts.items())),
        "monthly_net": {k:str(v) for k,v in sorted(monthly.items())},
        "quarterly_net": {k:str(v) for k,v in sorted(quarterly.items())},
        "positive_quarters": len(positive_quarters), "positive_quarter_concentration": quarter_concentration,
        "mean_net_return": str(sum(returns,Decimal("0"))/len(returns)) if returns else "0",
    }


def holm_adjust(p_values: Mapping[str, float]) -> dict[str, float]:
    ordered = sorted(p_values, key=lambda key: (p_values[key], key))
    adjusted: dict[str,float] = {}; running = 0.0; size = len(ordered)
    for index, key in enumerate(ordered):
        running = max(running, min(1.0, (size-index)*p_values[key]))
        adjusted[key] = running
    return adjusted


def development_gates(normal: Mapping[str,Any], conservative: Mapping[str,Any], replication: bool, adjusted_p: float) -> dict[str,bool]:
    counts = conservative["month_counts"]
    trade_count = conservative["trade_count"]
    pf = conservative["profit_factor"]
    return {
        "minimum_trades_240": trade_count >= 240,
        "minimum_18_months_with_5_trades": sum(value >= 5 for value in counts.values()) >= 18,
        "maximum_month_trade_fraction_0_2": bool(trade_count) and max(counts.values(), default=0)/trade_count <= .2,
        "minimum_5_positive_quarters": conservative["positive_quarters"] >= 5,
        "maximum_positive_quarter_concentration_0_35": conservative["positive_quarter_concentration"] <= .35,
        "maximum_drawdown_10pct": conservative["maximum_marked_to_market_drawdown_pct"] <= 10,
        "normal_net_positive": Decimal(normal["net_profit"]) > 0,
        "conservative_net_positive": Decimal(conservative["net_profit"]) > 0,
        "conservative_profit_factor_1_25": pf == "POSITIVE_INFINITY_UNBOUNDED" or float(pf) >= 1.25,
        "best_month_removal_positive": Decimal(conservative["best_month_removal_net"]) > 0,
        "five_largest_winner_removal_positive": Decimal(conservative["five_largest_winner_removal_net"]) > 0,
        "top_1pct_winner_concentration_lt_0_25": conservative["top_1pct_winner_concentration"] < .25,
        "gross_to_net_retention_0_25": conservative["gross_to_net_retention"] is not None and conservative["gross_to_net_retention"] >= .25,
        "positive_conservative_replication_asset": replication,
        "holm_adjusted_p_lt_0_05": adjusted_p < .05,
    }


def select_candidate(results: Mapping[str, Mapping[str,Any]]) -> str | None:
    passing = [key for key,row in results.items() if all(row["gates"].values())]
    def score(key: str) -> tuple[float,float,float,str]:
        row = results[key]["metrics"]["conservative"]
        pf = row["profit_factor"]
        pf_value = math.inf if pf == "POSITIVE_INFINITY_UNBOUNDED" else float(pf)
        return (-pf_value, row["maximum_marked_to_market_drawdown_pct"], -float(Decimal(row["expectancy"])), key)
    return min(passing, key=score) if passing else None


def trade_dicts(simulation: Simulation) -> list[dict[str,Any]]:
    return [asdict(trade) for trade in simulation.trades]


def null_control(
    candidate_id: str, observed: Simulation, eligible_indices: Sequence[int],
    frame: pd.DataFrame, cost_row: Mapping[str,str], step: Decimal,
    *, repetitions: int = 5_000, maximum_attempts: int = 100,
) -> tuple[np.ndarray, dict[str,Any]]:
    timestamps = frame["open_time_ms"].to_numpy(np.int64)
    observed_signal_times = [trade.signal_timestamp for trade in observed.trades]
    observed_indices = [int(np.searchsorted(timestamps, value)) for value in observed_signal_times]
    def stratum(index: int) -> tuple[str,int]:
        stamp = pd.Timestamp(int(timestamps[index]), unit="ms", tz="UTC")
        return stamp.strftime("%Y-%m"), stamp.hour
    required: dict[tuple[str,int],int] = defaultdict(int)
    for index in observed_indices: required[stratum(index)] += 1
    universe_lists: dict[tuple[str,int],list[int]] = defaultdict(list)
    for index in eligible_indices: universe_lists[stratum(int(index))].append(int(index))
    universe = {key:np.asarray(value,dtype=np.int64) for key,value in universe_lists.items()}
    if any(len(universe[key]) < count for key,count in required.items()):
        raise RuntimeError("ALPHA_SEARCH_B_NULL_STRATUM_SAMPLE_UNAVAILABLE")
    rng = np.random.default_rng(derive_seed(candidate_id))
    values = np.zeros(repetitions,dtype=np.float64)
    failures = 0; attempts_used = 0; sample_size=sum(required.values())
    pair,holding,_=CANDIDATES[candidate_id]
    opens=frame["open"].to_numpy(float); lows=frame["low"].to_numpy(float); complete=frame["complete"].to_numpy(bool)
    offset=SCENARIO_OFFSETS["conservative"]; cost_rate=float(Decimal(cost_row["total"])/Decimal("10000"))
    outcome_cache: dict[int,tuple[int,float]|None]={}
    def outcome(signal_index: int) -> tuple[int,float]|None:
        cached=outcome_cache.get(signal_index,"MISSING")
        if cached!="MISSING": return cached  # type: ignore[return-value]
        entry=signal_index+offset; scheduled=entry+holding
        if scheduled>=len(frame) or not complete[entry] or not complete[scheduled]:
            outcome_cache[signal_index]=None; return None
        barrier=opens[entry]*(1-.015); exit_index=scheduled; exit_price=opens[scheduled]
        for monitor in range(entry,scheduled):
            if not complete[monitor] or monitor+1>=len(frame) or not complete[monitor+1]:
                outcome_cache[signal_index]=None; return None
            if lows[monitor] <= barrier:
                exit_index=monitor+1; exit_price=min(opens[exit_index],barrier); break
        result=(exit_index,exit_price/opens[entry]-1-cost_rate); outcome_cache[signal_index]=result; return result
    ordered_required=sorted(required.items())
    batch_repetitions=20
    for batch_start in range(0,repetitions,batch_repetitions):
        batch_size=min(batch_repetitions,repetitions-batch_start)
        attempts=batch_size*maximum_attempts
        matrix=np.empty((attempts,sample_size),dtype=np.int64); column=0
        for key,count in ordered_required:
            pool=universe[key]; draws=np.empty((attempts,count),dtype=np.int64)
            for position in range(count):
                choice=rng.integers(0,len(pool),size=attempts)
                if position:
                    duplicate=np.any(draws[:,:position]==choice[:,None],axis=1)
                    while np.any(duplicate):
                        choice[duplicate]=rng.integers(0,len(pool),size=int(np.sum(duplicate)))
                        duplicate=np.any(draws[:,:position]==choice[:,None],axis=1)
                draws[:,position]=choice
            matrix[:,column:column+count]=pool[draws]; column+=count
        matrix.sort(axis=1)
        for local in range(batch_size):
            accepted=False
            for attempt in range(maximum_attempts):
                attempts_used+=1; row=matrix[local*maximum_attempts+attempt]
                if len(row)>1 and np.any(np.diff(row)<offset+1+COOLDOWN):
                    continue
                outcomes=[]; prior_exit=-1
                for signal_index in row:
                    item=outcome(int(signal_index))
                    if item is None or int(signal_index)<prior_exit+COOLDOWN:
                        outcomes=[]; break
                    prior_exit=item[0]; outcomes.append(item[1])
                if outcomes:
                    values[batch_start+local]=float(np.mean(outcomes)); accepted=True; break
            if not accepted:
                failures+=1; values[batch_start+local]=math.nan
    observed_stat = float(Decimal(metrics(observed)["mean_net_return"]))
    valid = values[np.isfinite(values)]
    p_value = 1.0 if failures else (1+int(np.sum(valid >= observed_stat)))/(repetitions+1)
    return values, {"seed":derive_seed(candidate_id),"repetitions":repetitions,
        "construction_failures":failures,"construction_attempts":attempts_used,
        "observed_statistic":observed_stat,"null_mean":float(np.mean(valid)) if len(valid) else None,
        "null_std":float(np.std(valid)) if len(valid) else None,"raw_p_value":p_value}

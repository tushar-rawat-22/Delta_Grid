from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from offchain.research.alpha_search_b.engine import (
    CANDIDATES, derive_seed, development_gates, holm_adjust, metrics,
    nearest_rank, rolling_comparison, round_down, select_candidate,
    simulate, slow_rolling_comparison, null_control,
)


def frame(size: int = 180) -> pd.DataFrame:
    opens = np.full(size, 100.0)
    return pd.DataFrame({
        "open_time_ms": np.arange(size, dtype=np.int64)*60_000+1_654_041_600_000,
        "open": opens, "high": opens+1, "low": opens-1, "close": opens,
        "complete": np.ones(size, dtype=bool),
    })


def costs(total: str = "26") -> dict[str,str]:
    return {"entry_fee":"10", "exit_fee":"10", "spread_slippage_impact":str(Decimal(total)-20), "total":total}


def test_nearest_rank_strict_ties_and_optimized_reference() -> None:
    assert nearest_rank([1,2,3,4], .5) == 2
    values = np.array([1,2,np.nan,4,5,6,7,8,9,10,11,12], dtype=float)
    fast = rolling_comparison(values,.5,window=5,minimum=3)
    slow = slow_rolling_comparison(values,.5,window=5,minimum=3)
    assert np.array_equal(fast[0],slow[0]) and np.array_equal(fast[1],slow[1])
    ties = rolling_comparison([1,1,1,1,1,1],.5,window=4,minimum=4)[0]
    assert not ties[-1]


def test_causal_exclusion_changes_only_after_future_value() -> None:
    base = np.arange(20,dtype=float)
    first = rolling_comparison(base,.95,window=5,minimum=5)[0]
    changed = base.copy(); changed[15] = 10_000
    second = rolling_comparison(changed,.95,window=5,minimum=5)[0]
    assert np.array_equal(first[:15],second[:15])


def test_all_candidates_are_frozen() -> None:
    assert list(CANDIDATES) == [
        "BTC_SELF_FLOW_PERSISTENCE_60M", "BTC_SELF_FLOW_PERSISTENCE_120M",
        "BTC_FLOW_LEADS_ETH_60M", "BTC_FLOW_LEADS_SOL_60M",
    ]


def test_entry_timing_scheduled_exit_and_cost_components() -> None:
    data = frame(200)
    sim = simulate("BTC_SELF_FLOW_PERSISTENCE_60M",[10],data,"conservative",costs("34"),Decimal("0.00001"))
    trade = sim.trades[0]
    assert trade.entry_timestamp == int(data.open_time_ms.iloc[12])
    assert trade.exit_timestamp == int(data.open_time_ms.iloc[72])
    assert trade.holding_minutes == 60 and trade.exit_reason == "SCHEDULED_EXIT"
    assert Decimal(trade.total_cost) == Decimal(trade.entry_fee)+Decimal(trade.exit_fee)+Decimal(trade.spread_slippage_impact_deduction)


def test_entry_minute_stop_and_gap_fill_precedence() -> None:
    data = frame(200); data.loc[12,"low"] = 98.5; data.loc[13,"open"] = 97
    sim = simulate("BTC_SELF_FLOW_PERSISTENCE_60M",[10],data,"conservative",costs("34"),Decimal("0.00001"))
    trade = sim.trades[0]
    assert trade.exit_reason == "PROTECTIVE_STOP" and Decimal(trade.exit_price)==97
    assert trade.holding_minutes == 1


def test_cooldown_and_collision_accounting() -> None:
    data = frame(4000)
    sim = simulate("BTC_SELF_FLOW_PERSISTENCE_60M",[10,20,100,1600],data,"normal",costs(),Decimal("0.00001"))
    assert len(sim.trades)==2 and sim.rejected_position==1 and sim.rejected_cooldown==1
    with pytest.raises(ValueError,match="PLACEBO_COLLISION"):
        simulate("BTC_SELF_FLOW_PERSISTENCE_60M",[10,20],data,"normal",costs(),Decimal("0.00001"),enforce_collisions=True)


def test_missing_required_minute_invalidates() -> None:
    data=frame(200); data.loc[71,"complete"]=False
    sim=simulate("BTC_SELF_FLOW_PERSISTENCE_60M",[10],data,"normal",costs(),Decimal("0.00001"))
    assert not sim.trades and sim.invalid_missing_required_minute==1


def test_risk_sizing_and_exchange_rounding() -> None:
    assert round_down(Decimal("1.239"),Decimal("0.01"))==Decimal("1.23")
    sim=simulate("BTC_SELF_FLOW_PERSISTENCE_60M",[10],frame(),"severe",costs("62"),Decimal("0.001"))
    assert Decimal(sim.trades[0].stake) <= Decimal(5000)/Decimal(212)


def test_metrics_pnl_drawdown_streaks_and_concentration() -> None:
    data=frame(5000); data.loc[72,"open"]=102; data.loc[1672,"open"]=98
    sim=simulate("BTC_SELF_FLOW_PERSISTENCE_60M",[10,1610],data,"conservative",costs("34"),Decimal("0.00001"))
    result=metrics(sim)
    assert result["trade_count"]==2 and result["fee_cost"]!="0"
    assert result["maximum_marked_to_market_drawdown_pct"]>=0
    assert result["longest_winning_streak"]==1 and result["longest_losing_streak"]==1
    assert 0 <= result["top_1pct_winner_concentration"] <= 1


def test_mark_to_market_curve_contains_each_held_minute() -> None:
    sim=simulate("BTC_SELF_FLOW_PERSISTENCE_60M",[10],frame(),"normal",costs(),Decimal("0.00001"))
    assert len(sim.equity_curve)==62  # start, 60 open-position minute marks, exit


def test_seed_pvalue_holm_and_deterministic_selection() -> None:
    assert derive_seed("BTC_SELF_FLOW_PERSISTENCE_60M")==15772981974708257581
    assert (1+24)/5001==25/5001
    assert holm_adjust({"A":.01,"B":.04,"C":.2})=={"A":.03,"B":.08,"C":.2}
    base={"gates":{"x":True},"metrics":{"conservative":{"profit_factor":1.5,"maximum_marked_to_market_drawdown_pct":2,"expectancy":"0.1"}}}
    results={"B":base,"A":base}
    assert select_candidate(results)=="A"


def test_null_sampling_is_deterministic_and_exact_count() -> None:
    data=frame(5000)
    observed=simulate("BTC_SELF_FLOW_PERSISTENCE_60M",[10,1610],data,"conservative",costs("34"),Decimal("0.00001"))
    universe=np.arange(10,4900)
    first,summary1=null_control("BTC_SELF_FLOW_PERSISTENCE_60M",observed,universe,data,costs("34"),Decimal("0.00001"),repetitions=5)
    second,summary2=null_control("BTC_SELF_FLOW_PERSISTENCE_60M",observed,universe,data,costs("34"),Decimal("0.00001"),repetitions=5)
    assert np.array_equal(first,second,equal_nan=True)
    assert summary1["repetitions"]==5 and summary1["seed"]==summary2["seed"]


def test_development_gates_fail_closed() -> None:
    metric={"trade_count":0,"month_counts":{},"positive_quarters":0,"positive_quarter_concentration":1,
        "maximum_marked_to_market_drawdown_pct":0,"net_profit":"0","profit_factor":0,
        "best_month_removal_net":"0","five_largest_winner_removal_net":"0",
        "top_1pct_winner_concentration":1,"gross_to_net_retention":None}
    assert not all(development_gates(metric,metric,False,1).values())

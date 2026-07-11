# ADR-0084.7: Walk-Forward Robustness Gate

Date: 2026-07-11

Status: Accepted

## Context

Mission 84.6 created 72 deterministic local fixture-based backtest results.
Full-period synthetic results alone are insufficient evidence for candidate
promotion because they can hide instability across time.

## Decision

Mission 84.7 implements deterministic expanding-window out-of-sample
robustness evaluation.

For every Mission 84.6 result, the gate:

- loads the persisted synthetic OHLCV fixture;
- preserves the fixed Mission 84.6 strategy logic;
- uses preceding bars as context and evaluates only later test bars;
- runs multiple non-overlapping deterministic test windows;
- includes transaction costs, slippage, spread, funding, and borrow costs;
- compares each window with cash, buy-and-hold, and deterministic-random baselines;
- measures positive-window ratio, median return, dispersion, drawdown, Sharpe,
  and baseline-relative performance;
- classifies candidates as robust-fixture candidates or blocked;
- performs no strategy tuning, parameter fitting, model training, or promotion.

A robustness classification is a synthetic research observation only. It is not
evidence of live profitability and does not authorize Mission 85.

## Safety Boundary

No live trading, capital deployment, private keys, signing, exchange orders,
paid APIs, live signals, model training, model artifacts, model promotion,
capital-linked strategy reweighting, or profitability claims.

## Consequences

Mission 84.8 may review only candidates classified as robust by Mission 84.7.
Mission 85 remains paused until candidates survive the complete institutional
research sequence.

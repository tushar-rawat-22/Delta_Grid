# ADR-0084.6: Multi-Strategy Backtest Pack

Date: 2026-07-11

Status: Accepted

## Context

Mission 84.5 created 72 institutional alpha benchmark plan entries but intentionally executed zero backtests. DeltaGrid needs a controlled first backtest layer before walk-forward robustness, alpha candidate promotion, or model promotion can be considered.

## Decision

Mission 84.6 implements a reusable local/offchain fixture-based backtest runner that:

- reads Mission 84.5 benchmark plan entries;
- creates deterministic synthetic OHLCV fixtures for each asset-group/timeframe pair;
- executes baseline logic for all eight registered strategy families;
- shifts strategy positions by one bar to avoid same-bar lookahead;
- applies commission, slippage, spread, funding, and borrow assumptions;
- compares each result with cash, buy-and-hold, and deterministic-random baselines;
- stores datasets, runs, results, baselines, checks, and reports in SQLite;
- marks all return observations as synthetic, unvalidated, and not profitability claims.

## Safety Boundary

- local/offchain and paper-only;
- no live trading or live signals;
- no real capital or capital deployment;
- no exchange orders, signing, or private keys;
- no paid APIs;
- no model training, model artifacts, or model promotion;
- no strategy reweighting with capital;
- Mission 85 remains paused until robust alpha candidates exist.

## Consequences

Mission 84.6 creates actual local research backtest records, but it does not establish robustness or profitability. Mission 84.7 must apply walk-forward and robustness gates before any alpha candidate can advance.

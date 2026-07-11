# ADR-0084.5: Institutional Alpha Research Benchmark Lab

## Status

Accepted

## Context

Mission 84 created a local offline model training harness, but all training candidates remained locked because the system does not yet have robust alpha evidence.

Mission 85 Model Promotion Engine is paused.

DeltaGrid needs to test varied strategy families across varied assets, timeframes, cost assumptions, and robustness gates before any promotion layer is useful.

## Decision

Add Mission 84.5 Institutional Alpha Research Benchmark Lab.

It reads:

- ai_offline_model_training_harness_runs

It writes:

- ai_institutional_alpha_benchmark_runs
- ai_alpha_strategy_family_registry
- ai_alpha_asset_universe_registry
- ai_alpha_cost_model_registry
- ai_alpha_benchmark_plan_entries
- ai_alpha_benchmark_checks
- ai_alpha_benchmark_reports

## Strategy Families

Mission 84.5 registers:

- time-series momentum / trend following
- cross-sectional momentum / rotation
- Donchian breakout + ATR risk
- mean-reversion z-score
- pairs / statistical arbitrage residual mean reversion
- funding / basis carry
- volatility regime filter
- hybrid ensemble

## Asset Universe

Mission 84.5 registers:

- crypto basket
- FX basket
- ETF / macro proxy basket

## What Mission 84.5 Approves

Mission 84.5 may approve:

- alpha research benchmark registration
- strategy family registry
- asset universe registry
- cost model registry
- benchmark plan entries
- handoff to Mission 84.6 Multi-Strategy Backtest Pack

## What Mission 84.5 Does Not Approve

Mission 84.5 does not approve:

- backtests yet
- model training
- model artifacts
- model promotion
- model deployment
- strategy reweighting
- live trading
- capital deployment
- private key access
- transaction signing
- exchange orders
- paid APIs
- live trading signals
- autonomous live execution
- profitability claims

## Consequence

DeltaGrid now has a formal alpha research benchmark layer.

Mission 85 remains paused until robust alpha candidates exist.

The next mission is Mission 84.6 Multi-Strategy Backtest Pack.

# DeltaGrid Institutional Alpha Research Plan

## Status

Active strategic pivot before Mission 85.

## Decision

Mission 85 Model Promotion Engine is paused.

DeltaGrid will not promote models or strategy candidates until it has tested varied strategy families across varied data, with costs, walk-forward validation, and robustness gates.

## Reason

Missions 80 through 84 created strong governance, safety, paper execution, feedback, and offline training-harness infrastructure.

However, DeltaGrid does not yet have enough alpha evidence.

Mission 84 confirmed:

- actual model training count: 0
- model artifact count: 0
- training ready candidate count: 0
- all current candidates blocked due to insufficient evidence

Therefore, the next priority is alpha research, not model promotion.

## New Mission Sequence

### Mission 84.5: Institutional Alpha Research Benchmark Lab

Purpose:

- Build a local benchmark lab for institutional-style strategy families.
- Test multiple strategy families across multiple assets and regimes.
- Compare each strategy against buy-and-hold, cash, and random baselines.
- Include costs, slippage, turnover, drawdown, and walk-forward validation.

### Mission 84.6: Multi-Strategy Backtest Pack

Purpose:

- Implement multiple strategy families in a consistent framework.
- Standardize inputs, outputs, metrics, and reports.
- Prevent cherry-picking and single-strategy bias.

### Mission 84.7: Walk-Forward Robustness Gate

Purpose:

- Split history into train/test windows.
- Reject unstable strategies.
- Reject strategies that only work in one period or one asset.
- Reject strategies with fragile parameters.

### Mission 84.8: Alpha Candidate Promotion Pack

Purpose:

- Create alpha candidate records only for strategies that survive robustness checks.
- Prepare evidence for Mission 85.

### Mission 85: Model Promotion Engine

Purpose:

- Resume only after robust alpha candidates exist.
- Promotion must be evidence-based, not architecture-based.

## Strategy Families To Test

### 1. Time-Series Momentum / Trend Following

Core idea:

- Trade in the direction of persistent returns.
- Test moving average, volatility-scaled momentum, and lookback momentum variants.

Assets:

- Crypto
- FX
- ETF macro proxies

Reason:

- Public research supports momentum/trend-following across futures, currencies, commodities, and equity indices.

### 2. Cross-Sectional Momentum / Rotation

Core idea:

- Rank assets by recent performance.
- Long strongest assets, avoid or short weakest assets in paper-only mode.

Assets:

- Crypto basket
- ETF basket
- FX basket

### 3. Donchian Breakout + ATR Risk

Core idea:

- Enter on breakout.
- Size/risk using ATR.
- Exit on trailing stop or channel reversal.

Assets:

- Crypto
- FX
- ETFs

### 4. Mean-Reversion Z-Score

Core idea:

- Trade deviation from rolling mean.
- Only activate in range-bound regimes.

Assets:

- ETFs
- FX
- selected crypto pairs

### 5. Pairs / Statistical Arbitrage Residual Mean Reversion

Core idea:

- Build spread or residual between related assets.
- Trade mean reversion after z-score extremes.

Assets:

- ETF pairs
- crypto pairs
- FX crosses where applicable

### 6. Funding / Basis Carry

Core idea:

- Track funding or basis when data is available.
- Separate carry signal from price momentum.

Assets:

- Crypto perpetuals and spot/futures proxies if data exists.

### 7. Volatility Regime Filter

Core idea:

- Detect high-volatility and low-volatility regimes.
- Use as overlay for all strategies.

### 8. Hybrid Ensemble

Core idea:

- Combine only strategy families that survive standalone tests.
- No model training until enough feedback evidence exists.

## Data Universe

### Crypto

- BTC
- ETH
- SOL
- BNB
- XRP
- ADA
- DOGE

### FX

- EURUSD
- GBPUSD
- USDJPY
- AUDUSD
- USDCHF
- USDCAD

### ETF / Macro Proxies

- SPY
- QQQ
- TLT
- GLD
- USO
- UUP
- HYG
- EEM

## Timeframes

Priority order:

1. Daily
2. 4-hour
3. 1-hour

No intraday strategy should be trusted before daily and 4-hour behavior are understood.

## Required Metrics

Each strategy report must include:

- total return
- CAGR where applicable
- Sharpe
- Sortino
- max drawdown
- Calmar
- volatility
- hit rate
- profit factor
- average trade return
- turnover
- cost drag
- slippage sensitivity
- exposure
- number of trades
- longest drawdown
- regime breakdown
- walk-forward score
- random baseline comparison
- buy-and-hold comparison

## Mandatory Rejection Rules

Reject a strategy if:

- it only works on one asset
- it only works on one small date window
- it fails after reasonable transaction costs
- it has high drawdown with weak recovery
- it depends on one fragile parameter
- it fails out-of-sample
- it fails walk-forward validation
- it performs worse than buy-and-hold after risk adjustment
- it performs similarly to random entries
- it requires live execution, leverage, private keys, or paid APIs
- it creates profitability claims without enough evidence

## Promotion Rules

A strategy family can become an alpha candidate only if:

- it passes at least 3 assets or asset groups
- it passes at least 2 market regimes
- it survives costs and slippage
- it passes out-of-sample validation
- it has no leakage or lookahead bias
- it has stable parameters
- it has acceptable drawdown
- it beats random baseline
- it beats or improves risk-adjusted buy-and-hold
- it remains paper-only and local-only

## Safety Boundaries

Still blocked:

- live trading
- real capital
- private keys
- signing
- exchange orders
- paid APIs
- live signal generation
- autonomous live execution
- model deployment
- strategy reweighting with real capital

Allowed:

- local research
- public or local historical data
- paper-only backtests
- synthetic test fixtures
- benchmark reports
- strategy candidate records
- walk-forward validation

## Next Best Action

Build Mission 84.5 Institutional Alpha Research Benchmark Lab.

This mission should create:

- strategy family registry
- asset universe registry
- benchmark configuration
- cost model configuration
- backtest result schema
- robustness gate schema
- benchmark report schema

Mission 85 remains paused until this plan produces at least one robust alpha candidate.

---

## Mission 84.5 Implementation Record

Mission 84.5 creates the Institutional Alpha Research Benchmark Lab.

It registers:

- strategy family registry
- asset universe registry
- cost model registry
- benchmark plan entries
- alpha benchmark checks
- alpha benchmark report

It does not run backtests yet.

It does not train models.

It does not promote models.

It keeps Mission 85 paused until robust alpha candidates exist.

Next:

- Mission 84.6 Multi-Strategy Backtest Pack

<!-- MISSION-84-6:START -->
## Mission 84.6 Multi-Strategy Backtest Pack

Status: implemented for local fixture-based research validation.

The pack reads Mission 84.5 benchmark plans, creates deterministic OHLCV fixtures across CRYPTO, FX, and ETF_MACRO for 1D, 4H, and 1H, runs all eight strategy families, applies conservative costs, and compares against three baselines. No result is eligible for promotion until Mission 84.7 walk-forward robustness checks pass.
<!-- MISSION-84-6:END -->

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

<!-- MISSION-84-7:START -->
## Mission 84.7 Walk-Forward Robustness Gate

The gate consumes Mission 84.6 datasets and results, evaluates later test windows using only preceding context, preserves fixed strategy logic, includes conservative costs, and compares against cash, buy-and-hold, and deterministic-random baselines.

Candidate robustness requires stable positive out-of-sample fixture observations under explicit thresholds. Failed candidates remain blocked. Passing candidates remain unpromoted and may only proceed to Mission 84.8 research review.
<!-- MISSION-84-7:END -->

<!-- MISSION-84-8:START -->
## Mission 84.8 Alpha Candidate Promotion Pack

The pack reviews every Mission 84.7 result and preserves its robustness and safety evidence. Only candidates satisfying the full deterministic rule set may enter the provisional fixture-only alpha registry.

Provisional registration does not unpause Mission 85. Mission 84 is closed. Any future research resumes as the separate crypto-first Real-Market Research Foundation.
<!-- MISSION-84-8:END -->

<!-- MISSION-84-CLOSURE:START -->
## Mission 84 Closure Decision

The synthetic institutional benchmark pipeline is complete as software and research-process infrastructure, but it has not established real-market alpha.

The 35 fixture-screening records are retained and superseded with effective status `FIXTURE_SCREENING_RECORD_ONLY_NOT_REAL_DATA_VALIDATED`.

Recorded limitations include:

- representative-pair sampling instead of full-universe testing;
- invalid funding/basis combinations outside crypto derivatives;
- insufficient legitimate multi-asset historical coverage;
- regime filters requiring overlay treatment;
- hybrid strategies requiring validated standalone components.

Mission 84 is closed. Mission 85 remains paused. Future research begins as the separate crypto-first Real-Market Research Foundation.
<!-- MISSION-84-CLOSURE:END -->

<!-- MISSION-85-CHARTER:START -->
## Mission 85 Crypto Funding-Carry Research Charter

Mission 85 is the falsification-first research-contract lock for a
fully collateralized, delta-neutral, long-spot short-perpetual funding and
basis carry hypothesis.

The earlier planned Mission 85 Model Promotion Engine was never implemented
and is now `RETIRED_UNBUILT_AFTER_MISSION84_CLOSURE`.

Mission 85 locks:

- Binance public market data only;
- BTCUSDT, ETHUSDT, and SOLUSDT only;
- one-hour canonical data with deterministic 4H and 1D derivation;
- spot, perpetual, mark, index, and settled funding streams;
- no synthetic data, sample fallback, or silent substitution;
- twelve predeclared deterministic parameter variants;
- chronological development, validation, and single-use untouched holdout;
- conservative initial transaction costs;
- strict rejection and anti-overfitting rules;
- no ML, model promotion, live trading, orders, or capital.

Mission 85 does not prove profitability.

Next mission: `Mission 86 Real-Market Data Foundation`.
Mission 86 is authorized for public data collection and certification only.
<!-- MISSION-85-CHARTER:END -->

<!-- MISSION-86-DATA-FOUNDATION:START -->
## Mission 86 Real-Market Data Foundation

Mission 86 implements the public real-market data layer authorized by the
locked Mission 85 funding-carry charter.

Scope:

- BTCUSDT, ETHUSDT, and SOLUSDT;
- Binance public spot and USD-M futures market-data endpoints;
- one-hour spot OHLCV;
- one-hour perpetual OHLCV;
- one-hour mark-price OHLC;
- one-hour index-price OHLC;
- settled funding-rate history;
- raw gzip response preservation;
- request, source, and SHA-256 provenance;
- resumable pagination;
- normalized mission-specific database tables;
- deterministic dataset manifest and coverage reporting.

Mission 86 performs no backtesting, holdout evaluation, machine learning,
model promotion, signal generation, order submission, capital deployment, or
profitability analysis.

All Mission 86 data remain:

`UNCERTIFIED_PENDING_MISSION87`

Next mission:

`Mission 87 Dataset Certification and Quality Gate`
<!-- MISSION-86-DATA-FOUNDATION:END -->

<!-- MISSION-87-CERTIFICATION:START -->
## Mission 87 Dataset Certification and Quality Gate

Mission 87 is complete.

- Certification run: `mission87-final-check`
- Source run: `mission86-final-check`
- Contract hash: `b7aec799a1d63dae5441118159d8fea5cafa0b62e69161d0b43e2e6c1a7e2ebf`
- Source manifest hash: `a6cb2ecaea2d02cf30a977436004bda74085db608f6b66500f5922292f650a96`
- Certificate hash: `e4d78b99417c1acb9bd89e7a8ef175cbf0c0e1219c1f71777401be41b8978819`
- Certification status: `CERTIFIED_FOR_RESEARCH_PENDING_EXECUTION_COST_MODEL`
- Bar series certified: 12
- Funding series certified: 3
- Total series certified: 15
- Rejected series: 0
- Raw responses verified: 276
- Market bars verified: 262656
- Funding observations verified: 8208
- Quality checks: 23 passed, 0 failed
- Safety breaches: 0
- Mission 88 status: `READY_FOR_EXECUTION_AND_COST_REALITY_MODEL`

Mission 87 verified raw gzip containment, body and response hashes, exact
raw-to-normalized equivalence, hourly continuity, chronological split
coverage, OHLC integrity, funding settlement schedules, funding mark
references, and cross-stream consistency.

The untouched holdout received structural quality checks only. No strategy
backtest, holdout performance evaluation, model training, signal generation,
capital deployment, or profitability analysis occurred.

Mission 87 performed no strategy backtest, holdout performance evaluation, parameter selection, model training, model promotion, signal generation, order submission, capital deployment, or profitability analysis.

Next mission:

`Mission 88 Execution and Cost Reality Model`<!-- MISSION-87-CERTIFICATION:END -->

<!-- MISSION-88-COST-MODEL:START -->
## Mission 88 Execution and Cost Reality Model

Mission 88 is complete.

- Run: `mission88-final-check`
- Model ID: `mission88-assumption-bounded-execution-cost-v1`
- Model hash: `398cc556614a97767fea36540556442579f195562a9ed16c18cc9561b78fc8a2`
- Model status: `APPROVED_FOR_BASELINE_FALSIFICATION_WITH_UNCERTAINTY`
- Symbols: 3
- Scenarios: 3
- Notional bands: 3
- Cost profiles: 27
- Minimum modeled cost: 50.000000 bps on pair notional
- Maximum modeled cost: 775.000000 bps on pair notional
- Checks: 24 passed, 0 failed
- Safety breaches: 0
- Market-data rows read: 0
- Holdout performance evaluated: 0
- Backtesting performed: 0
- Profitability analyzed: 0
- Mission 89 status: `READY_FOR_BASELINE_STRATEGY_FALSIFICATION`
- Mission 89 scope: `DEVELOPMENT_AND_VALIDATION_BASELINE_FALSIFICATION_ONLY`

The model is assumption-bounded. Historical order-book depth, queue position,
true fill latency, and measured market impact are unavailable.

Mission 88 makes no order-book precision claim.

Mission 88 performed no strategy backtest, holdout evaluation, return
calculation, parameter selection, model training, model promotion, signal
generation, order submission, capital deployment, or profitability analysis.

The untouched holdout remains sealed for Mission 90.

Next mission:

`Mission 89 Baseline Strategy Falsification`
<!-- MISSION-88-COST-MODEL:END -->

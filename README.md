# DeltaGrid

Research-first DeFi execution and risk platform.

Core rule:
No real capital until the system passes local tests, fork tests, testnet simulations, paper/demo validation, and manual promotion gates.

Current phase:
Local + testnet research only.

## DeltaGrid Autonomy Architecture

DeltaGrid is being built toward a fully AI-integrated autonomous trading system with self-learning capabilities.

Current status:

- research-first
- shadow and paper-only
- local SQLite evidence trail
- no live trading
- no real capital
- no private keys
- no exchange orders
- no model training yet

Mission 80 intentionally replaces the earlier Human Approval Gate direction with an Autonomous Policy Gate.

The system should not require human approval before every future action. Instead, it should progress through machine-checkable autonomous policy gates.

Current autonomy path:

research recommendations
  -> autonomous policy gate
  -> autonomous paper signal engine
  -> paper execution agent
  -> self-learning feedback loop
  -> offline training/evaluation/promotion gates
  -> autonomous risk governor
  -> live readiness firewall

Mission 80 approves only autonomous paper-only progression. It does not approve live trading, capital deployment, model training, or exchange execution.

See:

- docs/DELTA_AUTONOMY_ARCHITECTURE.md
- docs/ADR/ADR-0080-autonomous-policy-gate.md

### Mission 81 Autonomous Paper Signal Engine

Mission 81 adds autonomous paper-only signal records after the Mission 80 Autonomous Policy Gate.

These are not live trading signals.

They are:

- paper-only
- observe-only
- no-trade
- no-order
- no-capital
- no-model-training
- no-live-signal

Mission 81 prepares Mission 82 Paper Execution Agent.

Safety remains unchanged:

- live trading disabled
- capital deployment blocked
- no private keys
- no exchange orders
- no real capital
- no model training

## DeltaGrid Autonomous Bot Roadmap

DeltaGrid now has a dedicated full roadmap document:

- docs/DELTA_AUTONOMOUS_BOT_ROADMAP.md

Current verified stage:

- Mission 81 complete
- Autonomous Paper Signal Engine complete
- next mission is Mission 82 Paper Execution Agent

Current honest completion estimate:

- full autonomous AI trading bot: 25 to 30 percent complete
- safe autonomous internal paper-trading system: 40 to 45 percent complete
- live-market paper-trading bot: 25 to 30 percent complete
- real-money autonomous live bot: less than 10 percent complete

Next milestone:

- Mission 82 Paper Execution Agent
- Mission 83 Self-Learning Feedback Loop

Live-market paper trading is planned later, after paper execution, feedback, offline learning, risk governance, and live readiness firewall work.

Real-money live trading is not approved.

### Mission 82 Paper Execution Agent

Mission 82 adds paper execution records after Mission 81 paper-only observe signals.

The agent records paper execution evidence only.

It does not:

- trade live
- deploy capital
- use private keys
- send exchange orders
- train models
- create live trading signals

Next phase:

- Mission 83 Self-Learning Feedback Loop

### Mission 83 Self-Learning Feedback Loop

Mission 83 adds feedback records after Mission 82 paper execution records.

The loop records self-learning evidence only.

It does not:

- train models
- reweight strategies
- trade live
- deploy capital
- use private keys
- send exchange orders
- create live trading signals

Next phase:

- Mission 84 Offline Model Training Harness

### Mission 84 Offline Model Training Harness

Mission 84 adds the offline model training harness after Mission 83 feedback records.

The harness records locked training candidate evidence only.

It does not:

- train models on insufficient data
- create model artifacts
- deploy models
- deploy live systems
- reweight strategies
- trade live
- deploy capital
- use private keys
- send exchange orders
- create live trading signals

Next phase:

- Mission 85 Model Promotion Engine

### Institutional Alpha Research Pivot

Mission 85 is paused until DeltaGrid tests varied strategy families across varied data.

The next active path is:

- Mission 84.5 Institutional Alpha Research Benchmark Lab
- Mission 84.6 Multi-Strategy Backtest Pack
- Mission 84.7 Walk-Forward Robustness Gate
- Mission 84.8 Alpha Candidate Promotion Pack
- Mission 85 Model Promotion Engine

See `docs/INSTITUTIONAL_ALPHA_RESEARCH_PLAN.md`.

### Mission 84.5 Institutional Alpha Research Benchmark Lab

Mission 84.5 creates the alpha research benchmark lab before Mission 85.

It registers:

- strategy families
- crypto, FX, and ETF/macro asset universes
- conservative cost models
- benchmark plan entries
- benchmark safety checks

It does not:

- run backtests yet
- train models
- create model artifacts
- promote models
- reweight strategies
- trade live
- deploy capital
- use private keys
- send exchange orders
- create live trading signals

Next phase:

- Mission 84.6 Multi-Strategy Backtest Pack

<!-- MISSION-84-6:START -->
## Mission 84.6 — Multi-Strategy Backtest Pack

DeltaGrid now includes deterministic local fixture-based paper backtests for all 72 Mission 84.5 benchmark plan entries. Each result includes conservative transaction-cost assumptions and cash, buy-and-hold, and deterministic-random baselines. Results are synthetic research observations only, not profitability claims. Mission 85 remains paused; the next valid phase is Mission 84.7 Walk-Forward Robustness Gate.
<!-- MISSION-84-6:END -->

<!-- MISSION-84-7:START -->
## Mission 84.7 — Walk-Forward Robustness Gate

DeltaGrid now evaluates every Mission 84.6 synthetic-fixture backtest through deterministic expanding-window out-of-sample tests. The gate records per-window performance, baseline comparisons, stability metrics, candidate classifications, governance checks, and reports in SQLite. A robust-fixture classification is not a profitability claim and does not promote a model or strategy. Mission 85 remains paused.
<!-- MISSION-84-7:END -->

<!-- MISSION-84-8:START -->
## Mission 84.8 — Alpha Candidate Promotion Pack

DeltaGrid now performs deterministic review of Mission 84.7 walk-forward results. Eligible results may enter a provisional fixture-only local shadow-research registry. This status does not authorize model training, model promotion, live signals, orders, capital, reweighting, or profitability claims. Mission 85 remains paused.
<!-- MISSION-84-8:END -->

<!-- MISSION-84-CLOSURE:START -->
## Mission 84 Closure and Evidence Correction

Mission 84 is closed.

Missions 84.5 through 84.8 remain preserved as deterministic synthetic-fixture research-pipeline evidence. The 35 provisional records are now authoritatively superseded as `FIXTURE_SCREENING_RECORD_ONLY_NOT_REAL_DATA_VALIDATED`.

Current counts:

- fixture-screening candidates: 35
- real-data validated candidates: 0
- model-training eligible candidates: 0
- model promotions: 0
- live signals: 0
- exchange orders: 0
- capital deployments: 0
- profitability claims: 0

Mission 85 remains paused. There is no Mission 84.9. The next separate workstream is `REAL_MARKET_RESEARCH_FOUNDATION_CRYPTO_FIRST`.
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

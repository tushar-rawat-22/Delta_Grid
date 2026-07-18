# DeltaGrid Architecture State

<!-- deltagrid-document-status: HISTORICAL -->

> **Historical document**
>
> This file is a cumulative record of earlier DeltaGrid phases. Its body is
> preserved for traceability and does not define or authorize current work. See
> the [documentation home](README.md) and
> [final freeze](DELTAGRID_FINAL_FREEZE.md) for the current project state.

## Shadow Research Control Plane

Mission 58 adds the Shadow Research Control Plane.

It orchestrates:

1. public data orchestration
2. shadow ledger tracking updater
3. shadow tracking performance reporter
4. shadow tracking alert and invalidation router
5. documentation registry

## Safety Boundary

The control plane is not an execution engine.

It cannot:

- place orders
- sign transactions
- use private keys
- deploy capital
- enable live trading

## Multi-Strategy Research Factory Layer

Mission 59 adds a strategy research factory layer.

Inputs:

- historical public funding rates
- historical public basis observations

Outputs:

- strategy registry
- strategy candidates
- promotion shortlist
- watchlist
- rejection reasons
- factory report

Safety boundary:

- this layer produces research candidates only
- it does not place trades
- it does not allocate capital

---

## Data Quality and Regime Intelligence Layer

Mission 60 adds the data quality and regime intelligence layer.

Inputs:

- historical public funding rates
- historical public basis observations
- multi-strategy research candidates

Outputs:

- symbol data-quality reports
- market risk state
- candidate regime gates
- regime intelligence report

This layer sits between strategy research and promotion review.

---

## Shadow Portfolio Simulation Layer

Mission 61 adds the portfolio simulation layer.

Inputs:

- Mission 60 candidate regime gates

Outputs:

- portfolio simulation report
- allocation records
- portfolio risk report

This layer sits between regime-gated strategy research and promotion board review.

## Research Promotion Board Layer

Mission 62 adds a governance layer above the shadow portfolio simulator.

Inputs:

- shadow portfolio simulations
- shadow portfolio allocations
- shadow portfolio risk reports

Outputs:

- board review record
- board evidence items
- board decision record

This layer decides whether the portfolio can advance to paper sandbox research only.

---

## Paper Trading Sandbox Layer

Mission 63 adds a paper-only execution simulation layer.

Inputs:

- research promotion board approval
- shadow portfolio allocations
- public reference prices

Outputs:

- paper sandbox session
- paper-only orders
- simulated fills
- paper-only positions
- paper sandbox report

This layer does not connect to exchanges and does not send live orders.

---

## Institutional Risk Control Layer

Mission 64 adds a hard risk-control layer above the paper trading sandbox.

Inputs:

- paper sandbox sessions
- paper-only orders
- paper-only positions

Outputs:

- institutional risk control review
- institutional risk limit checks
- institutional risk decision record

This layer decides whether controlled paper observation can continue.

## Capital Readiness Review Layer

Mission 65 adds a capital-readiness governance layer above institutional risk control.

Inputs:

- institutional risk-control review
- institutional risk-control decision record

Outputs:

- capital-readiness review
- capital-readiness evidence items
- capital-readiness decision record

This layer approves extended paper observation only, not live trading or real capital.

---

## Paper Observation Performance Monitor Layer

Mission 66 adds a paper-only performance monitoring layer above capital readiness.

Inputs:

- capital-readiness review
- capital-readiness decision record
- paper sandbox session
- paper-only orders
- paper-only positions

Outputs:

- paper observation performance run
- position snapshots
- performance alerts
- performance report

This layer monitors paper observation performance only.

---

## Paper Drawdown Kill Switch Layer

Mission 67 adds a paper-only safety layer above paper observation performance monitoring.

Inputs:

- paper observation performance run
- paper position snapshots
- paper performance alerts

Outputs:

- drawdown kill-switch review
- drawdown checks
- kill-switch events
- drawdown kill-switch report

This layer can arm or trigger a paper-only kill switch. It cannot send live orders.

---

## Paper Recovery Stability Monitor Layer

Mission 68 adds a paper-only recovery stability layer above the drawdown kill switch.

Inputs:

- paper drawdown kill-switch review
- paper drawdown kill-switch checks
- paper drawdown kill-switch events
- paper observation performance run
- paper position snapshots

Outputs:

- recovery stability review
- recovery stability checks
- recovery stability events
- recovery stability report

This layer confirms or blocks paper observation continuation. It cannot send live orders.

---

## Multi-Cycle Paper Observation Tracker Layer

Mission 69 adds a paper-only multi-cycle layer above recovery stability monitoring.

Inputs:

- recovery stability reviews

Outputs:

- multi-cycle observation track
- multi-cycle cycle records
- multi-cycle checks
- multi-cycle report

This layer prepares structured paper evidence for AI learning without enabling autonomous trading.

---

## AI Paper Outcome Learning Engine Layer

Mission 70 adds a local AI-learning layer above multi-cycle paper observation tracking.

Inputs:

- multi-cycle paper observation track
- multi-cycle cycle records
- multi-cycle checks

Outputs:

- AI paper outcome learning run
- AI learning features
- AI learning labels
- AI recommendation-only records
- AI learning report

This layer does not train a live trading model and does not perform autonomous trading.

---

## AI Feature Quality and Drift Guard Layer

Mission 71 adds an AI feature quality layer above AI paper outcome learning.

Inputs:

- AI paper outcome learning run
- AI learning features
- AI learning labels
- AI learning recommendations

Outputs:

- AI feature quality and drift guard review
- AI quality checks
- AI feature drift records
- AI feature quality report

This layer validates learning artifacts but does not train a live model and does not perform autonomous trading.

---

## AI Paper Dataset Expansion Scheduler Layer

Mission 72 adds a paper dataset expansion planning layer above AI feature quality and drift guarding.

Inputs:

- AI feature quality drift guard review
- AI feature quality checks
- AI feature drift records

Outputs:

- AI paper dataset expansion schedule
- AI paper dataset expansion schedule items
- AI paper dataset expansion checks
- AI paper dataset expansion report

This layer only plans paper dataset collection and does not execute trades.

---

## AI Outcome Dataset Builder Pack Layer

Mission 73 adds a dataset construction layer above the AI paper dataset expansion scheduler.

Inputs:

- AI paper dataset expansion schedule
- AI paper dataset expansion schedule items
- AI paper dataset expansion checks

Outputs:

- AI outcome dataset build
- AI outcome dataset rows
- AI outcome dataset quality checks
- AI outcome dataset handoff
- AI outcome dataset report

This layer creates paper-only pending rows and does not train, trade, or execute.

---

## AI Feature Store and Training Dataset Registry Layer

Mission 74 adds a feature-store and training registry layer above the AI outcome dataset builder.

Inputs:

- AI outcome dataset build
- AI outcome dataset rows
- AI outcome dataset quality checks
- AI outcome dataset handoff

Outputs:

- Feature-store registry
- Feature-store feature records
- Training dataset registry entries
- Registry checks
- Registry report

This layer does not train, trade, or execute. Training is locked until paper outcomes are collected.

---

## AI Paper Outcome Collection and Label Finalizer Layer

Mission 75 adds a paper-only label finalization layer above the feature-store training registry.

Inputs:

- feature-store training registry
- feature-store feature records
- training dataset registry entries
- feature-store registry checks

Outputs:

- paper outcome collection run
- paper outcome collection records
- final paper outcome labels
- collection checks
- collection report

This layer finalizes labels but does not train, trade, or execute.

---

## AI Label Quality and Leakage Guard Layer

Mission 76 adds a label quality and leakage guard above the paper outcome label finalizer.

Inputs:

- paper outcome collection run
- paper outcome collection records
- final paper labels
- paper outcome collection checks

Outputs:

- label quality and leakage review
- label quality checks
- leakage findings
- label quality report

This layer approves labels for offline evaluation only. It does not train, trade, or execute.

---

## AI Offline Evaluation Governance Board Layer

Mission 78 adds a governance board above the offline evaluation harness.

Inputs:

- offline evaluation run
- offline evaluation cases
- offline evaluation metrics
- offline evaluation checks

Outputs:

- governance review
- governance evidence
- board votes
- governance checks
- governance report

This layer is research governance only. It does not train, trade, or execute.

---

## AI Research Recommendation Engine Layer

Mission 79 adds a research-only recommendation layer above the offline evaluation governance board.

Inputs:

- offline evaluation governance review
- governance evidence
- board votes
- governance checks

Outputs:

- research recommendation run
- research recommendation items
- recommendation checks
- recommendation report

This layer is research-only. It does not train, signal, trade, or execute.

---

## Autonomous Policy Gate Layer

Mission 80 adds an autonomous policy layer above the research recommendation engine.

This replaces the earlier human approval direction.

Inputs:

- research recommendation run
- research recommendation items
- research recommendation checks

Outputs:

- autonomous policy gate run
- policy rules
- policy decisions
- policy checks
- policy report

The gate approves only paper-only autonomous progression.

It does not train, trade, signal live, or execute.

Updated autonomy path:

research recommendations
  -> autonomous policy gate
  -> autonomous paper signal engine
  -> paper execution agent
  -> self-learning feedback loop
  -> offline training/evaluation/promotion gates

---

## Autonomous Paper Signal Engine Layer

Mission 81 adds an autonomous paper signal layer above the Autonomous Policy Gate.

Inputs:

- autonomous policy gate run
- autonomous policy gate rules
- autonomous policy gate decisions
- autonomous policy gate checks
- research recommendation items

Outputs:

- autonomous paper signal run
- autonomous paper signals
- autonomous paper signal checks
- autonomous paper signal report

The layer creates paper-only observe signals.

It does not train, trade, signal live, or execute.

Updated autonomy path:

research recommendations
  -> autonomous policy gate
  -> autonomous paper signal engine
  -> paper execution agent
  -> self-learning feedback loop
  -> offline training/evaluation/promotion gates

---

## Full Roadmap State After Mission 81

Current architecture stage:

- autonomous paper foundation

Completed layers:

- research recommendation engine
- autonomous policy gate
- autonomous paper signal engine

Next layer:

- paper execution agent

Future layers:

- self-learning feedback loop
- offline model training harness
- model promotion engine
- autonomous risk governor
- live readiness firewall
- live market data paper adapter
- real-time paper trading loop
- monitoring and recovery system

Full roadmap:

- docs/DELTA_AUTONOMOUS_BOT_ROADMAP.md

---

## Paper Execution Agent Layer

Mission 82 adds a paper execution layer above the Autonomous Paper Signal Engine.

Inputs:

- autonomous paper signal run
- autonomous paper signals
- autonomous paper signal checks

Outputs:

- paper execution agent run
- paper execution records
- paper execution checks
- paper execution report

The layer records paper-only no-order execution evidence.

It does not train, trade live, signal live, or send exchange orders.

Updated autonomy path:

research recommendations
  -> autonomous policy gate
  -> autonomous paper signal engine
  -> paper execution agent
  -> self-learning feedback loop
  -> offline training/evaluation/promotion gates

---

## Self-Learning Feedback Loop Layer

Mission 83 adds a feedback layer above the Paper Execution Agent.

Inputs:

- paper execution agent run
- paper execution records
- paper execution checks

Outputs:

- self-learning feedback run
- feedback items
- feedback checks
- feedback report

The layer records feedback-only evidence.

It does not train, reweight strategies, trade live, signal live, or send exchange orders.

Updated autonomy path:

research recommendations
  -> autonomous policy gate
  -> autonomous paper signal engine
  -> paper execution agent
  -> self-learning feedback loop
  -> offline model training harness
  -> model promotion engine

---

## Offline Model Training Harness Layer

Mission 84 adds an offline training harness layer above the Self-Learning Feedback Loop.

Inputs:

- self-learning feedback run
- feedback items
- feedback checks

Outputs:

- offline training harness run
- offline training candidate records
- training harness checks
- training harness report

The layer records locked offline training candidates.

It does not train models on insufficient data, create model artifacts, deploy models, reweight strategies, trade live, signal live, or send exchange orders.

Updated autonomy path:

research recommendations
  -> autonomous policy gate
  -> autonomous paper signal engine
  -> paper execution agent
  -> self-learning feedback loop
  -> offline model training harness
  -> model promotion engine
  -> autonomous risk governor

---

## Institutional Alpha Research Benchmark Lab Layer

Mission 84.5 adds a research benchmark layer before model promotion.

Inputs:

- offline model training harness run

Outputs:

- alpha benchmark run
- strategy family registry
- asset universe registry
- cost model registry
- benchmark plan entries
- benchmark checks
- benchmark report

The layer creates research structure only.

It does not run backtests, train models, promote models, reweight strategies, trade live, signal live, or send exchange orders.

Updated autonomy path:

research recommendations
  -> autonomous policy gate
  -> autonomous paper signal engine
  -> paper execution agent
  -> self-learning feedback loop
  -> offline model training harness
  -> institutional alpha research benchmark lab
  -> multi-strategy backtest pack
  -> walk-forward robustness gate
  -> alpha candidate promotion pack
  -> model promotion engine

<!-- MISSION-84-6:START -->
## Architecture State After Mission 84.6

The alpha research path now has a deterministic local backtest execution layer between benchmark planning and robustness validation. Mission 84.6 consumes Mission 84.5 plans and writes synthetic fixture datasets, strategy results, baselines, governance checks, and reports to SQLite. This layer is research-only and cannot emit live signals or place orders.
<!-- MISSION-84-6:END -->

<!-- MISSION-84-7:START -->
## Architecture State After Mission 84.7

The institutional alpha path now contains a deterministic walk-forward robustness layer after multi-strategy backtesting. The layer consumes persisted fixture datasets, evaluates expanding out-of-sample windows, aggregates stability evidence, and blocks insufficient candidates. It cannot tune or promote strategies, train models, emit live signals, place orders, or deploy capital.
<!-- MISSION-84-7:END -->

<!-- MISSION-84-8:START -->
## Architecture State After Mission 84.8

The institutional alpha path now includes deterministic candidate promotion review after walk-forward robustness. It stores complete reviews and a provisional fixture-only registry. Real-data replication remains mandatory before any later promotion discussion.
<!-- MISSION-84-8:END -->

<!-- MISSION-84-CLOSURE:START -->
## Architecture State After Mission 84 Closure

DeltaGrid now contains an append-only Mission 84 closure layer above the original alpha candidate registry.

The original registry remains historical evidence. The authoritative effective view is `ai_alpha_candidate_registry_effective`, which applies the latest supersession status and defaults eligibility fields to zero.

No Mission 84 candidate is:

- real-data validated;
- model-training eligible;
- model-promotion eligible;
- live-signal eligible;
- exchange-order eligible;
- capital-deployment eligible;
- profitability-claim eligible.

Mission 85 remains paused. Future work begins outside Mission 84 with a crypto-first real-market research foundation.
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

# DeltaGrid

## Current project status

DeltaGrid is a completed research-first quantitative research platform. It has no validated profitable strategy and does not authorize live trading or capital deployment.

The final state is `COMPLETED_RESEARCH_PLATFORM_NO_VALIDATED_ALPHA`. Alpha discovery is stopped because every authorized family was rejected. Passing tests establishes software behavior and evidence integrity; it does not establish profitability. Infrastructure maturity does not establish alpha.

## Project purpose

DeltaGrid was built to ask whether trading hypotheses survive causal data rules, realistic costs, chronological evaluation, falsification controls, and explicit promotion gates. Its durable output is the research process and negative evidence, not a trading promise.

## What DeltaGrid is

DeltaGrid is a local-first collection of data-foundation, simulation, execution-cost, risk, statistical, evidence, and governance components. Contracts freeze hypotheses and decision rules; implementations produce deterministic research artifacts; tests protect safety and historical identities.

## What DeltaGrid is not

DeltaGrid is not a profitable bot, a production trading service, an autonomous live trader, or proof of future returns. It has no selected Alpha Search B candidate, current paper-trading authority, live-order authority, or capital authority.

## Architecture

The repository separates:

1. versioned research and closure contracts;
2. off-chain data, simulation, cost, risk, and statistical engines;
3. tracked metadata and evidence, with ignored raw market data outside Git;
4. deterministic tests and safety gates;
5. reports, architecture decisions, and governance documentation;
6. historical on-chain executor, registry, and risk-guard contracts.

The final-freeze contract is additive. It does not rewrite the earlier mission, reset, Alpha Search A, or Alpha Search B records.

## Major research timeline

| Phase | Repository-supported outcome |
|---|---|
| Early platform work | Local monitoring, market schemas, simulators, research governance, paper-only controls, and evidence infrastructure were developed. |
| Mission 84 | Synthetic-fixture pipeline closed with 35 fixture-screening records and zero real-data validated candidates. |
| Mission 85 | A falsification-first funding-carry charter locked the economic question and experiment boundary. |
| Mission 86 | Public real-market data acquisition and provenance infrastructure was created; data remained uncertified pending Mission 87. |
| Mission 87 | Fifteen series were certified for research with structural checks, not performance evaluation. |
| Mission 88 | An assumption-bounded execution and cost model was approved for baseline falsification with uncertainty. |
| Mission 89 | Funding and basis carry was rejected and archived before holdout access. |
| Mission 90 | Twelve directional variants were rejected in development; validation and holdout were not read. |
| Product reset | Open-ended mission numbering was retired and two final alpha-family slots were locked. |
| Alpha Search A | Rejected before strategy construction because required causal first-availability evidence was unavailable. |
| Alpha Search B | All four frozen development candidates were rejected; no candidate was selected. |
| Final freeze | Project closed as a completed research platform with no validated alpha. |

## Strategy-family outcomes

| Family | Outcome | Boundary |
|---|---|---|
| Mission 84 synthetic benchmark families | Fixture screening only; no real-data validated alpha | No model training, promotion, trading, or capital |
| Funding and basis carry | `REJECT_AND_ARCHIVE_FUNDING_CARRY` | Holdout rows read: 0 |
| Conventional directional strategies | `REJECT_ALL_DIRECTIONAL_HYPOTHESES` | Validation rows: 0; holdout rows: 0 |
| Static intraday session exposure | Rejected in the controlling product-reset record | Frozen; no indirect reopening |
| Alpha Search A macro risk regime | `REJECTED_BEFORE_STRATEGY_BUILD` | No strategy, P&L, validation, or holdout evaluation |
| Alpha Search B microstructure liquidity state | `ALPHA_SEARCH_B_REJECTED_DEVELOPMENT` | Four candidates rejected; selected candidate `null`; scoped validation and holdout access both 0 |

## Data acquisition, certification, and provenance

Mission 86 introduced resumable public-data acquisition, raw-response preservation, normalized tables, request provenance, and SHA-256 identities for BTCUSDT, ETHUSDT, and SOLUSDT spot and derivatives streams. Mission 87 certified 12 bar series and three funding series using continuity, OHLC, settlement, split-coverage, raw-to-normalized, and cross-stream checks.

Alpha Search B used official Binance monthly one-minute spot-kline archives and official checksums for BTCUSDT, ETHUSDT, and SOLUSDT. Tracked evidence contains metadata and hashes. Ignored raw and processed data remain outside Git; no raw Alpha Search B data is tracked.

## Execution-cost and risk modelling

Mission 88 produced an assumption-bounded two-leg carry cost model across three symbols, three scenarios, and three notional bands. It explicitly lacks historical order-book depth, queue-position, fill-latency, and measured-impact precision.

Alpha Search B separately froze single-leg normal, conservative, and severe round-trip costs, latency offsets, a 1.5% protective stop, one-position authority, a 24-hour cooldown, Decimal stake sizing, no leverage, and cash-reserve limits. Cost attribution separates fee, spread/slippage, and latency displacement. These controls constrain research; they do not make a rejected strategy profitable.

## Statistical and falsification controls

Controls include immutable protocols, causal feature windows, chronological development/validation/holdout splits, one sealed holdout, deterministic null controls, Holm adjustment across four Alpha Search B candidates, replication assets, minimum-sample gates, drawdown limits, positive-quarter requirements, concentration tests, winner-removal diagnostics, and net-after-cost qualification.

Every Alpha Search B candidate failed required development gates. Validation and holdout therefore remained closed.

## Evidence and reproducibility

Committed controlling evidence consists of versioned contracts, tracked evidence JSON, reports, tests, manifests, and Git identities. Current final-freeze verification is a separate deterministic pre-publication candidate record. Operator-reported terminal metadata is not treated as committed controlling evidence.

The Alpha Search B publication commit is `a31f4da4fc8b52ca2fa6aaad697350d6e9180736`. It is the research-closure base, not a permanent assertion about every future repository HEAD. The final-freeze publication commit does not yet exist.

## Safety boundaries

- No profitability claim.
- No candidate rescue or replacement family.
- No validation or holdout access for Alpha Search B.
- No current Freqtrade translation.
- No dry-run or paper-trading authorization.
- No live trading, orders, or capital deployment.
- No automatic strategy, model, or capital promotion.
- No market-data download or refresh under the final-freeze task.

## Historical Freqtrade boundary

The product-reset record describes a historical pinned and parity-verified Freqtrade runtime and requires exact ledger parity as a future candidate gate. That is infrastructure history, not current strategy authorization. No Alpha Search B candidate was authorized for Freqtrade translation, and no current Freqtrade dry-run, live execution, or capital deployment is authorized.

## Current limitations

The platform has no validated profitable strategy. Historical cost models include explicit assumptions and incomplete microstructure observability. Backtests, synthetic fixtures, statistical significance, model accuracy, passing tests, and infrastructure completeness cannot prove future profitability. Venue, regime, liquidity, impact, and operational behavior can change.

## Future-strategy intake

Future strategy work requires genuinely new information, an overlap audit against rejected families, and an explicit new versioned reopening contract before data-driven research begins. The intake policy requires a frozen experiment budget, causal data proof, chronological stages, realistic cost and stress models, multiple-testing control, parity checks, paper-only evaluation, and separate proof-capital and live-trading authorizations. See [Future Strategy Intake Policy](docs/FUTURE_STRATEGY_INTAKE_POLICY.md).

## Possible future ML research

The documented `DELTAGRID_ML_RESEARCH_ADAPTER` is design policy only and is `DOCUMENTED_NOT_AUTHORIZED`. A future contract could allow small, fixed supervised tabular model families under chronological, purged evaluation. ML may generate forecasts or candidate evidence; it may not promote itself, authorize trading, or authorize capital. See [ML Research Adapter](docs/DELTAGRID_ML_RESEARCH_ADAPTER.md).

## Test baseline and closure tests

Committed pre-freeze evidence records 37 passing Alpha Search B/reset focused tests, 715 passing complete off-chain tests, and one third-party `websockets.legacy` deprecation warning. These are pre-freeze baselines, not the post-change totals. Final closure tests add deterministic checks for the freeze contract, historical identities, public claims, policy boundaries, checksums, and raw-data tracking. Test success verifies those properties only; it does not establish alpha.

## Repository navigation

- [Final Project Report](docs/DELTAGRID_FINAL_PROJECT_REPORT.md)
- [Final Freeze Explanation](docs/DELTAGRID_FINAL_FREEZE.md)
- [Final Freeze Contract](contracts/DELTAGRID_FINAL_FREEZE_V1.json)
- [Future Strategy Intake Policy](docs/FUTURE_STRATEGY_INTAKE_POLICY.md)
- [ML Research Adapter](docs/DELTAGRID_ML_RESEARCH_ADAPTER.md)
- [Product Reset](docs/DELTAGRID_PRODUCT_RESET.md)
- [Alpha Search A Rejection](docs/ALPHA_SEARCH_A_REJECTION.md)
- [Alpha Search B Protocol](docs/ALPHA_SEARCH_B_PROTOCOL.md)
- [Final Freeze Evidence](docs/evidence/deltagrid_final_freeze/FINAL_FREEZE_VERIFICATION.json)
- `offchain/` — implementations and tests
- `contracts/` — on-chain and research contracts
- `docs/evidence/` — tracked evidence and checksum manifests

## Historical authoritative-document markers

The following bounded markers preserve compatibility with the repository's historical documentation-verification tests. Their contents are historical evidence classes and do not override the current final-freeze status above.

<!-- MISSION-84-CLOSURE:START -->
### Mission 84 Closure

Mission 84 closed its deterministic synthetic-fixture pipeline with zero real-data validated alpha candidates. The historical fixture-screening records remain preserved but authorize no model training, strategy promotion, live signal, order, capital, or profitability claim. There is no Mission 84.9.
<!-- MISSION-84-CLOSURE:END -->

<!-- MISSION-85-CHARTER:START -->
### Mission 85 Crypto Funding-Carry Research Charter

Mission 85 locked a falsification-first funding-carry charter before real-market collection. It did not prove profitability and prohibited ML rescue, live trading, orders, and capital. Its next authorized data-only phase was Mission 86 Real-Market Data Foundation.
<!-- MISSION-85-CHARTER:END -->

<!-- MISSION-86-DATA-FOUNDATION:START -->
### Mission 86 Real-Market Data Foundation

Mission 86 implemented public-data acquisition, normalization, provenance, and deterministic manifests. It performed no strategy backtest or profitability analysis. Its output remained `UNCERTIFIED_PENDING_MISSION87` until Mission 87 Dataset Certification and Quality Gate.
<!-- MISSION-86-DATA-FOUNDATION:END -->

<!-- MISSION-87-CERTIFICATION:START -->
### Mission 87 Dataset Certification and Quality Gate

Mission 87 certified structural data quality and lineage. It performed no strategy backtest or holdout performance evaluation. The next historical phase was Mission 88 Execution and Cost Reality Model.
<!-- MISSION-87-CERTIFICATION:END -->

<!-- MISSION-88-COST-MODEL:START -->
### Mission 88 Execution and Cost Reality Model

Mission 88 completed an assumption-bounded cost model with no strategy backtest and no order-book precision claim. Its next historical phase was Mission 89 Baseline Strategy Falsification.
<!-- MISSION-88-COST-MODEL:END -->

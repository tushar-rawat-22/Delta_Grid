# DeltaGrid Research Cockpit v0 charter

## Decision

`STOP_REPOSITORY_INTERFACE_GAPS_FOUND`

Research Cockpit v0 implementation is not authorized. The audit found useful
historical and machine-oriented infrastructure, but it did not find a current,
versioned application-service boundary that a cockpit can call without either
copying research logic or treating historical mission code as present
authority.

The controlling machine record is
[`DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER_V1.json`](../contracts/DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER_V1.json).
Its canonical contract hash is
`b4064f4651730618bf6497e631e913ebde7d6c9db926943d46aa11b3bc223bc1`.

## Purpose

This charter defines the boundary for a possible future local research
cockpit. It records a read-only interface audit; it does not build a dashboard
or reopen research.

A future cockpit is intended to make authority, persisted evidence,
deterministic experiment requests, chronological attempts, and verified result
artifacts easier to inspect. It must remain a thin user interface over
authoritative DeltaGrid interfaces. It must not become another simulator,
accounting engine, risk engine, statistical evaluator, optimizer, autonomous
agent, or trading system.

## Authority boundary

The [DeltaGrid final freeze](DELTAGRID_FINAL_FREEZE.md) and
[`DELTAGRID_FINAL_FREEZE_V1.json`](../contracts/DELTAGRID_FINAL_FREEZE_V1.json)
remain authoritative for research and trading authority.

The following facts remain unchanged:

- no validated profitable strategy exists;
- no candidate is selected;
- research is frozen;
- validation and holdout access are not authorized;
- real-market or historical-market backtesting is not authorized;
- paper trading and live trading are not authorized;
- exchange access and capital deployment are blocked;
- model training, autonomous research, autonomous promotion, and autonomous
  execution are not authorized.

Passing software tests does not establish profitable strategy performance.
The control identifiers in this charter are not alpha candidates. Neither this
document nor the machine contract authorizes their execution.

## Cockpit v0 boundary

A future Cockpit v0 must be:

- local and single-user;
- offline by default;
- read-only by default;
- development and verification tooling;
- evidence controlled;
- reconstructable from persisted artifacts.

It must not be a backtesting engine, strategy optimizer, autonomous agent,
model trainer, trading interface, or source of research authority. UI session
state must never change a contract, trial count, dataset permission, result,
promotion decision, or other research fact. Results must be shown
chronologically by default, never ranked by Sharpe, return, or profitability.

Its possible modules are limited to repository and project authority, a
dataset and evidence registry, deterministic manifest creation, a
chronological run ledger, result inspection with costs and drawdown beside
returns, and hash verification with read-only artifact export.

## Audit method

The audit was performed at commit
`9605c4b294d15f4e1ec4929c9706f1ff9f938072`. It used repository-relative
source and test inventories, Python AST signature inspection, targeted source
review, test-import tracing, documentation-registry classifications,
final-freeze review, and dependency-file review.

No source module was run. No network, raw market data, validation data,
holdout data, exchange, account, credential, model-training, or strategy
operation was used.

The complete temporary audit record is
`/tmp/deltagrid-mission93-interface-manifest.json`, with SHA-256
`e165ad38328399c5e39e4a656779a64697ba060049968ea69a249ce5ae0a398e`.
It records 27 interfaces: 3 current/reusable, 20 historical-only, and 4
machine-only.

## Data and certification interface map

| Path and interface | Inputs and outputs | Side effects and stable fields | Status and cockpit finding |
|---|---|---|---|
| `offchain/backtest/mission86_real_market_data_foundation.py::load_authoritative_contract` | Contract path to validated Mission 85 contract dictionary | None; stable contract ID, hash, universe, data contract, and authorization fields | Historical-only. A current dataset authorization adapter is missing. |
| `offchain/backtest/mission86_real_market_data_foundation.py::build_request_spec` | Stream, symbol, start, and end to `RequestSpec` | None; stable stream, symbol, URL, and parameters | Historical-only. Network acquisition is not authorized. |
| `offchain/backtest/mission86_real_market_data_foundation.py::request_json_page` | HTTP session and `RequestSpec` to decoded public JSON and response metadata | Performs an allowlisted public HTTP request with bounded retry; stable URL, parameters, response body, and retry policy | Historical-only. Network acquisition is not authorized. |
| `offchain/backtest/mission86_real_market_data_foundation.py::preserve_raw_response` | Request/response metadata and body to provenance metadata | Writes gzip and SQLite; stable response hash, body hash, raw path, row count, URL, and parameters | Historical-only. Raw market-data access is not authorized. |
| `offchain/backtest/mission86_real_market_data_foundation.py::normalize_bar` | Raw bar to normalized bar dictionary | None; stable stream, symbol, timestamp, OHLC, and volume fields | Historical-only. Reusable logic exists, but no present processing authority exists. |
| `offchain/backtest/mission86_real_market_data_foundation.py::normalize_funding` | Raw funding row to normalized funding dictionary | None; stable symbol, funding time, rate, and mark price | Historical-only. Reusable logic exists, but no present processing authority exists. |
| `offchain/backtest/mission86_real_market_data_foundation.py::build_manifest` | SQLite provenance and coverage to hashed manifest envelope | Atomically writes `manifest.json` and upserts SQLite; stable contract, coverage, raw-response, safety, and hash fields | Machine-only. It is Mission 86-specific and is not the future experiment-manifest contract. |
| `offchain/backtest/mission87_dataset_certification.py::certify_dataset` | Database, contract, roots, labels, and time to certification summary | Reads raw and normalized data; writes certificate and SQLite results; stable checks, split coverage, hashes, and safety fields | Historical-only. It must not be invoked because protected-data and certification execution are not authorized. |

These implementations cover acquisition, normalization, raw provenance,
dataset-manifest identity, timestamps, continuity, missingness, gaps,
cross-stream consistency, and split structure. They do not expose one current
read-only resolver that can answer “is this dataset and split authorized?” from
metadata alone and fail closed without opening protected content.

## Simulation and accounting interface map

| Path and interface | Inputs and outputs | Side effects and stable fields | Status and cockpit finding |
|---|---|---|---|
| `offchain/research/alpha_search_b/engine.py::simulate` | Candidate, signals, frame, scenario, cost row, and step to `Simulation` | Pure calculation; stable trades, attempted signals, rejection counters, and equity curve | Historical-only. Alpha Search B is closed. A cockpit must not copy this signal, fill, cooldown, or P&L logic. |
| `offchain/backtest/mission89_baseline_strategy_falsification.py::simulate_symbol` | Funding-carry data, variant, costs, exits, and rebalance controls to a symbol result | Pure calculation; stable positions, timing, costs, gross/net P&L, funding, exposure, and equity | Historical-only and family-specific. |
| `offchain/backtest/mission90_directional_strategy_tournament.py::simulate_variant` | Market data, directional variant, costs, scenario, and NAV band to a result | Pure calculation; stable variant, instrument, costs, gross/net P&L, trades, turnover, exposure, and equity | Historical-only and family-specific. |
| `offchain/backtest/mission90_directional_strategy_tournament.py::close_position` | Position, price, exit time/reason, costs, and trade number to closed trade | Pure calculation; stable entry/exit, gross/net P&L, funding, direction, and cost fields | Historical-only. A UI must not reproduce it. |

The repository contains position state, next-bar timing, entries, exits,
cooldowns, funding cash flows, resizing, accounting, and P&L. Those behaviors
are embedded in separate historical family engines. There is no generic
strategy/control request interface and no current engine service returning a
common result bundle.

Older Freqtrade material is historical and is not present execution authority.

## Cost interface map

| Path and interface | Inputs and outputs | Side effects and stable fields | Status and cockpit finding |
|---|---|---|---|
| `offchain/backtest/mission88_execution_cost_model.py::build_cost_profiles` | Mission 85 contract to scenario/symbol/notional cost profiles | None; stable fee, spread, slippage, hedge-delay, partial-fill, rebalance, funding-reconciliation, and operational-buffer fields | Historical-only and funding-carry-specific. |
| `offchain/backtest/mission90_directional_strategy_tournament.py::build_directional_cost_profiles` | Mission 85 contract to directional cost-profile mapping | None; stable fees, spread, slippage, delay, operational, and exit-stress fields | Historical-only and directional-family-specific. |
| `offchain/research/alpha_search_b/engine.py::simulate` | A frozen Alpha Search B cost row is applied during simulation | None; stable fees, spread, slippage, latency displacement, and net P&L attribution | Historical-only and not a general cost-service interface. |

Fees, spread, slippage, latency or delay, funding, partial fills, rebalance
cost, and operational buffers are represented. Historical market-impact claims
remain assumption bounded because depth, queue position, and measured impact
were unavailable. A cockpit must display engine-produced cost components; it
must never calculate them itself.

## Risk and evaluation interface map

| Path and interface | Inputs and outputs | Side effects and stable fields | Status and cockpit finding |
|---|---|---|---|
| `offchain/backtest/mission90_directional_strategy_tournament.py::maximum_drawdown_pct` | Daily equity to maximum drawdown percentage | None | Historical-only helper embedded in a mission engine. |
| `offchain/backtest/mission89_baseline_strategy_falsification.py::calculate_pbo` | Development results to PBO estimate | None | Historical-only, family-specific statistical evaluation. |
| `offchain/backtest/mission89_baseline_strategy_falsification.py::deflated_sharpe_probability` | Validation returns, development Sharpes, and trial count to deflated Sharpe probability | None | Historical-only; validation access is not authorized. |
| `offchain/research/alpha_search_b/engine.py::holm_adjust` | Candidate p-values to adjusted p-values | None | Historical-only Alpha Search B multiple-testing control. |
| `offchain/research/alpha_search_b/engine.py::null_control` | Candidate, observed result, eligible indices, market frame, costs, and deterministic settings to null distribution and summary | Uses deterministic RNG derived from candidate ID | Historical-only; it is not one of the four current chartered controls. |
| `offchain/backtest/mission90_directional_strategy_tournament.py::choose_candidate` | Variants, results, and benchmarks to selection, gates, and eligible IDs | None; stable gate status, observed/required values, reasons, and selection | Historical-only. Promotion is not authorized, and a cockpit must not reproduce the decision. |

The audited engines report drawdown, exposure, concentration, turnover,
benchmarks, chronological splits, replication, null controls, multiple-testing
controls, and rejection or promotion gates. Raw Sharpe, Deflated Sharpe
probability, PBO, Holm correction, and seeded null controls exist in historical
family implementations. No Probabilistic Sharpe Ratio interface was identified.
There is also no current repository-wide statistical evaluation interface.

## Evidence and operator interface map

| Path and interface | Inputs and outputs | Side effects and stable fields | Status and cockpit finding |
|---|---|---|---|
| `offchain/backtest/mission86_real_market_data_foundation.py::canonical_json` | JSON-compatible value to sorted compact ASCII JSON | None; stable canonical serialization convention | Current/reusable for verification. |
| `offchain/research/alpha_search_b/pipeline.py::evidence` | Protocol, costs, results, replications, nulls, adjusted values, decision, and selection to an evidence set | Writes machine and human evidence under the historical Alpha Search B root | Historical-only. Its artifact set is useful evidence, not a current result-bundle interface. |
| `offchain/backtest/mission89_baseline_strategy_falsification.py::write_report` | Report core and timestamp to hash and envelope | Writes JSON report; stable report hash, timestamp, and report fields | Machine-only and Mission 89-specific. |
| `scripts/mission_control.py::run_verification` | Module, tests, command, log path, and flags to verification summary | Runs local verification commands and writes logs | Current/reusable for software verification only; it is not a research runner. |
| `scripts/mission_pack_runner.py::run_mission_pack` | Pack path, repository root, dry-run, Git flags, and clean-start rule to a mission-pack summary | Validates explicit actions; may write listed files and run verification; Git writes require explicit flags | Current/reusable operator tooling only; it is not cockpit or research authority. |
| `contracts/DELTAGRID_FINAL_FREEZE_V1.json` | Machine record | None; stable closure, authority, and canonical-hash fields | Current controlling machine authority. |
| `docs/documentation-status.json` | Machine record | None; stable classifications, treatments, and document metadata | Current machine-only documentation registry. |

Contracts, manifests, result artifacts, hashes, SQLite records, JSON reports,
Markdown reports, and operator verification logs exist. Their schemas and
persistent paths are heterogeneous and mission-specific. A common verified
read-only result loader is missing.

## Exact interface gaps

Five minimal interfaces must be exposed and tested before cockpit
implementation can be reconsidered:

1. **Engine application service.** A current, versioned deterministic service
   must accept a validated experiment manifest and return a result bundle. It
   must call authoritative engine logic without embedding UI behavior.
2. **Dataset and artifact resolver.** A read-only adapter must resolve dataset
   IDs, hashes, splits, artifact paths, and permissions without opening
   protected content. Unknown, mismatched, validation, and holdout requests
   must fail closed.
3. **Trial ledger and budget reservation.** A persistent append-only logical
   ledger must atomically reserve trial budget and count completed, failed,
   stopped, rejected, manual, and superseded outcome-bearing attempts.
4. **Exact control registry.** A current dispatcher must recognize only the
   four frozen non-alpha controls. Seeded random must fail closed without an
   explicit seed.
5. **Result verifier and loader.** A canonical result-bundle schema and
   read-only verifier must expose identities, costs, risk, timing,
   protected-access counts, artifacts, warnings, verification results, and a
   canonical hash without UI recalculation.

These are interface gaps, not permission to implement them in this mission.

## Adapter architecture and duplicate-logic risk

The intended future boundary is:

```text
local cockpit UI
  -> deterministic experiment manifest
  -> thin cockpit application service
  -> authoritative DeltaGrid engine
  -> authoritative simulator, costs, risk, and evaluation
  -> deterministic result bundle
  -> read-only cockpit views
```

The present duplicate-logic risk is high. Without the five interfaces, a
cockpit developer would need to select among mission engines, normalize their
different schemas, determine split authority, track trials, or recalculate
fields. That would create a second source of truth.

The UI and application service must never independently implement signals,
fills, position state, entry or exit processing, stops, cooldowns, portfolio
accounting, P&L, fees, spread, slippage, latency, funding, market impact,
drawdown, exposure, concentration, turnover, statistical decisions, or
promotion decisions.

## Control restrictions

Exactly four future control identifiers are frozen:

- `NO_TRADE_CONTROL`
- `BUY_AND_HOLD_CONTROL`
- `SEEDED_RANDOM_CONTROL`
- `SIMULATOR_STATE_MACHINE_CONTROL`

They exist only to verify accounting, timing, costs, determinism, and
reporting. They are not alpha candidates. `SEEDED_RANDOM_CONTROL` always
requires an explicit seed.

This mission authorizes none of the four controls to run. A later contract may
authorize synthetic-fixture execution only. Real-market execution,
optimization, validation, holdout, and protected-data access remain prohibited.

## Future experiment manifest contract

The future manifest must include:

- schema version, experiment ID, and experiment type;
- controlling contract ID and canonical hash;
- repository commit and cleanliness;
- dataset IDs, dataset hashes, split identity, and protected-data permissions;
- one allowed control identifier and exact allowed parameters;
- deterministic seed policy;
- cost, execution, and risk model identities;
- declared trial number and total trial budget;
- output directory and requested artifacts;
- authorization stage, operator, creation timestamp, and canonical hash.

It must fail closed for a dirty repository, contract or dataset hash mismatch,
unknown dataset, unknown control, unknown parameter, missing required seed,
exhausted budget, unauthorized split, validation request, holdout request,
contract/implementation mismatch, or output path outside the authorized root.

The schema is chartered but not implemented.

## Future result-bundle contract

The future result bundle must include:

- schema, result-bundle, manifest, code, dataset, simulator, cost, execution,
  and risk identities;
- start and end timestamps;
- machine status and reason tokens, an explicit failure/stop/rejection reason,
  and a separate human explanation;
- gross and net result, benchmark, and costs by component;
- drawdown, exposure, turnover, trade count, and concentration;
- timing diagnostics and protected-access counts;
- artifact paths, warnings, verification results, and canonical result hash.

Machine tokens and human explanations must remain separate. A software `PASS`
must never imply profitable strategy performance. The schema is chartered but
not implemented.

## Trial ledger and anti-overfitting

The future ledger must be persistent and append-only in logical history.
Budget reservation must be atomic. Every outcome-bearing attempt counts,
including completed, failed, stopped, rejected, manually initiated, and later
superseded attempts.

It must prevent hidden failures, count resets, provider or split changes after
failure, family relabelling, unlimited feature or parameter search, and
selection from visible winners only. UI session state is not ledger authority.

Existing historical support includes raw Sharpe, Deflated Sharpe probability,
PBO, Holm multiple-testing correction, and seeded null controls. No
Probabilistic Sharpe Ratio interface was identified. This mission implements
no statistical calculation.

## Dependency decision

The repository already has SQLite in the standard library plus pandas, NumPy,
and PyArrow/Parquet capability. Streamlit, Plotly, and DuckDB are not current
dependencies.

If all interface gaps are first closed under separate authority, the smallest
coherent new runtime set is one dependency: Streamlit. Existing SQLite,
pandas, and PyArrow are sufficient for storage and tabular artifact access.
Plotly is optional and is not authorized by default. DuckDB is not needed.

No dependency is authorized for installation now. The future maximum remains
three new runtime dependencies. External database servers, React, Node.js,
Kubernetes, Redis, Celery, and microservices are prohibited.

## Implementation acceptance criteria

Before a later cockpit implementation can be authorized:

- all five gaps must be closed by versioned and tested engine interfaces;
- the cockpit must contain no duplicated domain or decision logic;
- manifests, results, artifact paths, and canonical hashes must verify and fail
  closed;
- the append-only ledger must count and reserve every attempt;
- protected splits and unknown datasets must fail closed without being opened;
- the exact four non-alpha controls must be enforced;
- seeded random must require an explicit seed;
- results must default to chronological order;
- the UI must remain local, offline, read-only, and non-authoritative by
  default;
- tests and human text must distinguish software correctness from strategy
  performance;
- source implementation or dependency changes must have separate authority.

## Final decision and next action

Final decision: `STOP_REPOSITORY_INTERFACE_GAPS_FOUND`.

Next authorized action: `STOP_REPOSITORY_INTERFACE_GAPS_FOUND`.

This is successful completion of the interface audit, not authorization to
close the gaps or implement the cockpit. No dashboard, strategy, market
backtest, model, protected-data access, exchange path, trading capability, or
capital authority was created.

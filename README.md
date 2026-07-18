# DeltaGrid

DeltaGrid is a Python-based quantitative research platform I built to test cryptocurrency trading strategies before allowing them anywhere near real capital. It combines market-data validation, event-driven backtesting, realistic execution-cost assumptions, risk controls, statistical testing, and reproducible evidence.

## Current status

The research infrastructure is complete, but there is **no validated profitable strategy**. This repository **does not authorize live trading or capital deployment**. Infrastructure maturity does not establish alpha.

The final project freeze was published in commit `ce82c5b887a08185b7acceb35480783d02eb0b5d`. None of the tested strategies met the promotion standard, so live trading, paper trading, and capital deployment remain disabled.

That negative strategy result is not a profitability success. The engineering success is that DeltaGrid rejected weak hypotheses instead of overfitting or deploying them.

## Why I built it

Most trading projects begin with indicators and end with a profitable-looking backtest. I wanted to build the process in the opposite order: define the hypothesis, freeze the rules, verify the data, account for costs, test chronologically, and reject the strategy when the evidence is weak.

## How DeltaGrid works

```text
Public market data
        ↓
Acquisition and certification
        ↓
Features and strategy rules
        ↓
Event-driven simulation
        ↓
Costs and risk
        ↓
Statistical evaluation
        ↓
Evidence and decision
```

- **Data acquisition and certification:** Collects public market data with provenance, coverage checks, normalized records, and deterministic identities.
- **Research contracts:** Freezes the hypothesis, data boundaries, candidate count, costs, and decision gates before results can influence the rules.
- **Features and strategy implementation:** Builds causally timed features and fixed strategy logic without looking ahead.
- **Event-driven backtesting:** Simulates signals, entries, exits, stops, cooldowns, and position state in timestamp order.
- **Execution costs:** Applies normal, conservative, and severe assumptions for fees, spread, slippage, and latency.
- **Risk controls:** Measures drawdown and concentration while enforcing position, leverage, reserve, stop, and capital boundaries.
- **Statistical evaluation:** Uses chronological stages, null controls, multiple-testing correction, replication, and robustness checks.
- **Evidence and decision gates:** Writes versioned evidence and promotes nothing unless every frozen requirement passes.

## What it includes

- Public crypto-data acquisition with provenance records
- Deterministic dataset certification for BTC, ETH, and SOL research data
- Event-driven strategy simulation
- Normal, conservative, and severe execution-cost assumptions
- Drawdown and concentration analysis
- Chronological development, validation, and sealed holdout boundaries
- Null controls and Holm multiple-testing correction
- Versioned contracts, evidence files, and SHA-256 identities
- Historical Freqtrade parity infrastructure, without current strategy or trading authorization
- Automated regression tests

## Research completed

| Research area | Outcome |
|---|---|
| Synthetic benchmark pipeline | Infrastructure completed; no real-market validated alpha |
| Funding and basis carry | Rejected |
| Directional strategies | Rejected |
| Macro-regime hypothesis | Rejected before strategy construction |
| Trade-flow and lead-lag hypotheses | Rejected in development |

Alpha Search B was rejected on development data without opening validation or holdout; its committed publication evidence records zero scoped validation access and zero scoped holdout access.

The detailed timeline, candidate results, statistical controls, and decision evidence are in the [Final Project Report](docs/DELTAGRID_FINAL_PROJECT_REPORT.md).

## Engineering highlights

- Python-based research engine
- Deterministic, versioned research contracts
- Causal feature timing and chronological evaluation
- Event-driven execution semantics
- Explicit fees, spread, slippage, latency, and cost stress
- Sealed validation and holdout boundaries
- Historical Freqtrade parity infrastructure; lookahead, recursive, and other bias analyses remain future gates
- 731 passing automated tests in the full suite at the published final freeze
- Reproducible evidence and checksum manifests

Passing tests verify the implementation and repository invariants; they are not evidence that a strategy is profitable.

## Repository structure

```text
contracts/       Research, safety, and freeze contracts
offchain/        Data, simulation, research, and test code
docs/            Architecture, decisions, policies, and reports
docs/evidence/   Tracked research evidence and checksum manifests
scripts/         Verification and operational utilities
```

## Running the tests

The repository does not currently document a verified fresh-clone bootstrap for the complete test environment. For an already configured checkout with the ignored local virtual environment at `offchain/.venv`, run:

```bash
env -u PYTHONPATH \
PYTHONDONTWRITEBYTECODE=1 \
offchain/.venv/bin/python -m pytest \
  -p no:cacheprovider \
  offchain/tests \
  -q
```

The virtual environment is local and ignored; it is not included in a fresh clone.

## Limitations and safety

- There is no validated profitable strategy, no live orders, no current paper-trading authorization, and no capital deployment.
- Cost, slippage, latency, and market-impact models contain assumptions and cannot reproduce every live-market condition.
- Backtests and statistical tests do not guarantee future results.
- Future research requires a new versioned reopening contract before any data-driven strategy work begins.
- Test success verifies those properties only; it does not establish alpha.
- No Alpha Search B candidate was authorized for Freqtrade translation.

The Alpha Search B rejection was published in commit `a31f4da4fc8b52ca2fa6aaad697350d6e9180736`. That commit is the historical research base, **not a permanent assertion about every future repository HEAD**. The later commit `ce82c5b887a08185b7acceb35480783d02eb0b5d` published the final project freeze.

## Documentation

- [Final Project Report](docs/DELTAGRID_FINAL_PROJECT_REPORT.md)
- [Final Freeze Explanation](docs/DELTAGRID_FINAL_FREEZE.md)
- [Final Freeze Contract](contracts/DELTAGRID_FINAL_FREEZE_V1.json)
- [Future Strategy Intake Policy](docs/FUTURE_STRATEGY_INTAKE_POLICY.md)
- [ML Research Adapter](docs/DELTAGRID_ML_RESEARCH_ADAPTER.md)
- [Product Reset](docs/DELTAGRID_PRODUCT_RESET.md)
- [Alpha Search A Rejection](docs/ALPHA_SEARCH_A_REJECTION.md)
- [Alpha Search B Protocol](docs/ALPHA_SEARCH_B_PROTOCOL.md)
- [Final Freeze Evidence](docs/evidence/deltagrid_final_freeze/FINAL_FREEZE_VERIFICATION.json)

## Author

Built by Tushar Rawat as an independent quantitative research and software-engineering project.

<details>
<summary>Historical compatibility notes</summary>

These markers are retained for historical documentation verification. They describe earlier repository phases and do not override the current project status above.

Committed pre-freeze evidence records 37 passing Alpha Search B/reset focused tests and 715 passing complete off-chain tests, with one third-party `websockets.legacy` deprecation warning. These are historical pre-freeze baselines, not the full-suite total at the published final freeze.

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

</details>

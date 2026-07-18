# DeltaGrid Product Reset

## Effective decision

DeltaGrid is no longer managed through an open-ended numbered mission
roadmap.

The project now has one primary objective:

> Find one robust, implementable, after-cost trading edge or stop alpha
> discovery.

Repository growth, additional infrastructure, larger test counts and
more backtests are not substitutes for a qualified strategy.

## Current truth

DeltaGrid has a substantial research, evidence and risk-control
platform. It has a pinned and parity-verified Freqtrade runtime.

It does not currently have a validated profitable strategy.

The following real-data families have been rejected:

- Funding and basis carry
- Conventional directional strategies
- Static intraday session exposure
- Alpha Search A macro risk regime, before strategy construction, because
  required causal first-availability evidence was unavailable under its frozen
  protocol

These decisions remain frozen.

## Infrastructure freeze

No new dashboards, autonomous-agent layers, execution engines, user
interfaces or evidence subsystems are authorized.

Infrastructure may change only when required for:

- a correctness or dependency fix;
- certification of data required by an approved research program;
- translation of an evidence-qualified strategy;
- forward-testing or risk controls for a qualified strategy.

## Final research budget

One of the two budgeted new economic information families remains.

### Alpha Search A — Macro risk regime

Status: `REJECTED_BEFORE_STRATEGY_BUILD`

The frozen feasibility protocol could not establish required causal
first-availability evidence for every required series. No BTC archives, BTC
price fields, returns, signals, P&L, validation performance or holdout
performance were accessed. No rescue or substitution is authorized.

Research whether lagged macro conditions support a low-turnover BTC
spot long-or-cash strategy.

Planned information sources:

- S&P 500 (`SP500`)
- CBOE VIX (`VIXCLS`)
- Broad U.S. dollar index (`DTWEXBGS`)
- U.S. 10-year Treasury yield (`DGS10`)

Rules:

- no more than four preregistered variants;
- weekly or multi-day decisions;
- maximum one round trip per week;
- minimum 24-hour information delay;
- no thresholds selected using BTC returns;
- no raw copyrighted external data committed to the public repository.

### Alpha Search B — Microstructure liquidity state

Status: `PROTOCOL_LOCKED_DATA_NOT_ACCESSED`

This is the only remaining authorized economic family. Its four flow-only
candidates, causal statistics, execution, costs, capital sizing, replication,
null control and qualification gates are frozen in
`contracts/ALPHA_SEARCH_B_PROTOCOL_V1.json`.

The candidates use aggregated spot trade-flow proxies. No entry signal uses a
price-return threshold, and no maker-fill or order-book claim is made.

High-frequency churning is prohibited by one-position authority and a 24-hour
post-exit cooldown. No data, returns or strategy results were accessed by the
protocol lock.

## Promotion sequence

A candidate must pass:

1. Development selection under conservative costs
2. Frozen validation
3. One sealed holdout evaluation
4. Exact Freqtrade ledger parity
5. Lookahead-bias analysis
6. Recursive-stability analysis
7. At least 90 calendar days and 12 closed dry-run trades
8. Restart, recovery and adverse-regime checks

No stage may optimize parameters using the next stage's evidence.

## Capital policy

The first `$100` is verification capital, not income capital.

- Spot only
- No leverage
- One position maximum
- No martingale
- No averaging down
- Maximum risk per trade: `0.5%`
- Weekly drawdown stop: `3%`
- No automatic scaling

Meaningful income requires both a verified edge and more capital.
DeltaGrid will not use leverage to disguise insufficient capital.

## Stop rule

Alpha discovery stops when:

- both final research programs fail;
- the candidate fails holdout;
- the candidate contains lookahead bias;
- recursive instability changes its decisions;
- conservative costs remove the edge;
- forward testing materially disagrees with the backtest.

A stopped project remains a useful completed research platform, but it
will not be represented as a profitable trading system.

## Next action

`ALPHA_SEARCH_B_DATA_FOUNDATION_AND_DEVELOPMENT_FALSIFICATION`

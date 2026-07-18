# Alpha Search B Protocol

## Lock decision

`ALPHA_SEARCH_B_MICROSTRUCTURE_LIQUIDITY_STATE` is locked with status
`PROTOCOL_LOCKED_DATA_NOT_ACCESSED`. It is the final remaining economic family,
with four preregistered candidates and at most one development survivor.

No market data, returns, strategy result, validation evidence, holdout evidence,
or P&L was accessed. The lock authorizes only the next data-foundation and
development-falsification block; it does not authorize Freqtrade code, a
backtest in this block, dry-run, live trading, or capital deployment.

## Data and causal features

The future source is the official Binance monthly one-minute spot-kline archive
and official checksums for BTCUSDT, ETHUSDT, and SOLUSDT. Raw archives remain
outside Git. Ingestion must verify checksums, UTC, millisecond and post-2025
microsecond timestamps, continuous synchronized minutes, and absence of
duplicates.

Taker-buy share is an `AGGREGATED_TRADE_FLOW_PROXY`; it is not order-book or
queue imbalance, complete order flow, or maker-fill evidence. Each feature uses
the preceding 43,200 expected minutes excluding closed minute `t`, requires
38,880 observations, and uses nearest-rank empirical quantiles without
interpolation or backfill. Threshold comparisons are strict.

The splits are warm-up June 2022, 24-month development from July 2022 through
June 2024, 12-month validation through June 2025, and the sealed 12-month
holdout through June 2026.

## Frozen candidates

- `BTC_SELF_FLOW_PERSISTENCE_60M`
- `BTC_SELF_FLOW_PERSISTENCE_120M`
- `BTC_FLOW_LEADS_ETH_60M`
- `BTC_FLOW_LEADS_SOL_60M`

Signals use only taker-buy ratio, quote volume, trade count, and cross-asset
taker-buy-ratio gaps. No entry signal uses a price-return threshold, reversal,
breakout, momentum tail, mean reversion, market making, or machine learning.

Each candidate is evaluated independently with one global position. Signals
during a position or the 24-hour post-exit cooldown are rejected and counted.
The first later eligible signal is used; there is no monthly trade target.

## Execution, cost, and capital

Normal, conservative, and severe entry offsets are one, two, and three minutes
after closed signal minute `t`. Holding time begins at actual entry. Every
candidate has a 1.5% protective stop; a triggered stop exits at the following
minute open, no better than the stop barrier.
The entry-minute candle is monitored: a 60/120-minute trade entered at minute
`e` exits on schedule at the open of `e+60`/`e+120`; a stop due at that same
open takes precedence.

Authoritative normal/conservative/severe round-trip costs are respectively
26/34/62 bps for BTC, 27/36/67 for ETH, and 30/42/82 for SOL. Half is allocated
at entry and half at exit. Equity is marked each minute.

Tracked Mission 88 code exposes components for its two-leg carry model, but it
does not deterministically decompose these later authoritative single-leg
totals. Therefore the protocol records
`COMPONENT_LEVEL_COST_ATTRIBUTION_REQUIRES_SEPARATE_EXTRACTION`; extracting and
locking those components is a hard prerequisite of the future evaluator.

The $100 proof wallet risks at most $0.50 per trade. Decimal stake sizing uses
the 1.5% stop plus the pair's severe cost and remains below the $80 deployed
capital ceiling, with at least $20 cash reserve. The exact ceilings are
`5000/212` BTC, `5000/217` ETH, and `625/29` SOL dollars; exchange rounding is
downward. Two positions are diagnostic only after holdout qualification and
share the same combined $0.50 risk budget.

## Qualification

The reset gates remain authoritative. Development must have 5 of 8 positive
quarters; validation and holdout each require 3 of 4. Every stage caps marked
account drawdown at 10% and positive-quarter concentration at 35%. At least one
unchanged replication asset must be conservative-positive; replication cannot
select, rank, or rescue a candidate. Each replication also requires at least
120 development, 60 validation, and 60 holdout completed trades.

Development additionally requires 240 trades, its monthly distribution gates,
positive normal and conservative P&L, conservative profit factor at least 1.25,
robustness to removal tests, winner concentration below 25%, gross-to-net
retention of at least 25%, and a Holm-adjusted null p-value below 0.05.
Validation and holdout each require 120 trades and their frozen annual gates.

The frequency-matched null uses 5,000 deterministic repetitions, candidate
seeds derived from the protocol hash, pair/month/UTC-hour strata, sampling
without replacement, a 100-attempt collision limit, conservative mean net
return, the finite-sample one-sided p-value, and Holm adjustment across exactly
four candidates.
The null base universe uses completeness, warm-up, causal availability,
nonzero denominators and history minimums only; observed position and cooldown
paths cannot alter it. Promotion metrics use scenario net P&L after costs;
gross P&L is attribution-only except as the positive denominator of gross-to-net
retention, which fails when gross profit is non-positive.

## Next action

`ALPHA_SEARCH_B_DATA_FOUNDATION_AND_DEVELOPMENT_FALSIFICATION`

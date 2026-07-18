# Alpha Search A Rejection

## Decision

`ALPHA_SEARCH_A_REJECTED_BEFORE_STRATEGY_BUILD`

Decision code: `STOP_NO_PROTOCOL_RESCUE`

Alpha Search A stopped because required causal first-availability evidence for
`SP500` was unavailable under the frozen feasibility protocol. The failed
pre-rejection contract hash is
`01cb5891a384d0e2177a53091bc26fda6e3f1c5ee316ae4defe647bd06e96e9f`.

The rejection record is locked by contract hash
`4114319b1ea9313da0815386219b991183d3f7cbb3016a4895a768f44c4af1df`.

## Research interpretation

No conclusion is made about whether macro regimes can predict BTC. The frozen
data-feasibility protocol was rejected; no strategy was constructed or tested.

Before the provider stop, 35 focused offline tests passed. BTC archives were
not accessed. Historical BTC price fields, BTC returns, strategy signals, P&L,
validation performance, and holdout performance all had zero access.

No provider or series substitution, parameter rescue, sample-threshold
reduction, release-policy redesign, or decision-timestamp change is authorized.
Zero rescue cycles were used and no further rescue is allowed.

## Safety status

- Freqtrade strategy created: `false`
- Backtest or dry-run: `false`
- Live trading: `false`
- Capital deployment: `false`
- Secret disclosures: `0`
- Leverage authority: unchanged at `1`
- Maximum open positions: unchanged at `1`

## Product state

Alpha Search B (`ALPHA_SEARCH_B_MICROSTRUCTURE_LIQUIDITY_STATE`) is the only
remaining authorized family. This closure does not define its strategy logic,
data provider, variants, indicators, thresholds, or trading behavior.

Next action:
`ALPHA_SEARCH_B_PREIMPLEMENTATION_RED_TEAM_AND_PROTOCOL_LOCK`.

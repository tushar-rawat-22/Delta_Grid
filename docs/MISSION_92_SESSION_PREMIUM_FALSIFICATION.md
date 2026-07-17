# Mission 92 — Session Premium Development Falsification

## Purpose

Mission 92 tests the frozen Mission 91
`SESSION_CONDITIONAL_SPOT_EXPOSURE` family on certified development
data only.

A rejection is a successful falsification result. A surviving
development candidate is provisional and does not authorize trading.

## Frozen candidates

Six non-overlapping four-hour UTC windows are evaluated:

- `00:00–04:00`
- `04:00–08:00`
- `08:00–12:00`
- `12:00–16:00`
- `16:00–20:00`
- `20:00–24:00`

BTC is the only selection asset. ETH and SOL are replication assets.

## Chronological discipline

The complete common development dates are divided chronologically:

1. First half selects at most one BTC window.
2. Second half confirms or rejects that frozen selection.
3. The second half cannot change the selected window.

## Pair-specific spot costs

Mission 92 applies the recovered Mission 88 spot-only costs:

| Pair | Normal | Conservative | Severe |
|---|---:|---:|---:|
| BTC/USDT | 26 bps | 34 bps | 62 bps |
| ETH/USDT | 27 bps | 36 bps | 67 bps |
| SOL/USDT | 30 bps | 42 bps | 82 bps |

The conservative scenario controls promotion. Severe cost is
diagnostic. Combined spot-perpetual execution costs are prohibited.

## Required gates

A candidate must satisfy all frozen conservative gates:

- at least 200 complete BTC trades;
- positive normal full-development result;
- positive conservative result in both chronological halves;
- positive conservative full-development result;
- conservative profit factor of at least `1.15`;
- conservative maximum drawdown no greater than `8%`;
- at least `60%` positive calendar quarters;
- no single quarter above `35%` of total positive-quarter profit;
- positive conservative replication on at least one of ETH or SOL.

A deterministic moving-block bootstrap with Holm adjustment is
reported as a multiple-testing diagnostic, not as a promotion gate.

## Safety

- Validation rows read: `0`
- Holdout rows read: `0`
- Freqtrade strategy created: `false`
- Freqtrade backtest run: `false`
- Dry-run: `false`
- Live trading: `false`
- Capital deployment: `false`

## Final execution result

- Status: `COMPLETE_SESSION_PREMIUM_DEVELOPMENT_FALSIFICATION_REJECTED`
- Decision: `REJECT_ALL_SESSION_WINDOWS_DEVELOPMENT_HALF_ONE`
- Selected variant: `None`
- Promotion eligible: `false`
- Complete common sessions: `546`
- Development rows read: `39384`
- Validation rows read: `0`
- Holdout rows read: `0`
- PyArrow runtime dependency: `25.0.0`
- Protocol hash: `2d5cb23c61436362a9e7b78308ea157b03b5c2a0bf43bb5a6a33a6c3a62f23f1`
- Report hash: `5d814d4a8788ac179d0e4c606fa5ddee9d6f3e1467d0bc35672c755bbb8f6447`
- Next workstream: `NEW_ECONOMIC_HYPOTHESIS_DISCOVERY_AFTER_SESSION_REJECTION`

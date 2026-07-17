# Mission 91 — New Economic Hypothesis Discovery

## Decision

Mission 91 selects exactly one family for subsequent
development-only falsification:

`SESSION_CONDITIONAL_SPOT_EXPOSURE`

This is an untested economic hypothesis, not a profitability claim.

## Why this family

The family uses a price-independent clock signal rather than funding,
basis, momentum, breakout, trend, mean reversion, volatility targeting,
machine learning or external-event prediction.

It is compatible with the existing certified one-hour spot dataset,
a fixed small research notional, one open position and no leverage.

## Primary and replication assets

- Primary selection asset: `BTC/USDT`
- Replication assets: `ETH/USDT`, `SOL/USDT`

Replication assets cannot independently determine the selected window.

## Frozen variants

The UTC day is partitioned completely into six non-overlapping
four-hour windows:

- `00:00–04:00`
- `04:00–08:00`
- `08:00–12:00`
- `12:00–16:00`
- `16:00–20:00`
- `20:00–24:00`

No alternate window length, shifted boundary, weekday filter, weekend
filter or asset-specific window may be introduced after this lock.

## Execution model

- Spot long or cash only
- One position maximum
- One round trip per day maximum
- Fixed small research notional
- Entry at the window-start open
- Exit at the window-end open
- No shorting
- No leverage
- No futures
- No position adjustment
- No Hyperopt
- No FreqAI

## Mission 92 gate

Mission 92 may use development data only.

It must:

1. Evaluate all six frozen windows once.
2. Use BTC as the only selection asset.
3. Use ETH and SOL only as replication evidence.
4. Apply Mission 88 normal, conservative and severe cost scenarios.
5. Select at most one window.
6. Reject all windows when no candidate passes every conservative gate.
7. Keep validation and holdout data sealed.
8. Run no dry-run, live trading or capital deployment.

Lookahead and recursive analyses become mandatory only after a
development candidate survives and before any future dry-run
authorization.

## Safety status

- Validation rows authorized: `0`
- Holdout rows authorized: `0`
- Live trading: `DISABLED`
- Capital deployment: `BLOCKED`
- Exchange API credentials: `PROHIBITED`

## Next workstream

`MISSION92_SESSION_PREMIUM_DEVELOPMENT_FALSIFICATION`

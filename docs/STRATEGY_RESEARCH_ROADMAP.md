# DeltaGrid Strategy Research Roadmap

## Status

Active

## Purpose

This document records the strategy research direction before Mission 21.

DeltaGrid will not chase random strategies.

The system will evaluate strategy families through:

1. indicator engine
2. regime kernel
3. walk-forward validation
4. failure attribution
5. trade-sample confidence
6. risk-adjusted scoring
7. investment committee verdict

Live trading remains forbidden until strict gates pass.

---

# Research Decision

The next strategy families are ranked as follows.

## 1. Volatility-Targeted Time-Series Momentum

Priority:

- Mission 21

Reason:

- fits current OHLCV architecture immediately
- uses existing indicator engine
- uses existing regime kernel
- replaces failed MA crossover family
- needs no new external data source

Core logic:

- multi-horizon momentum
- EMA trend filter
- ADX trend confirmation
- ATR stop
- ATR trailing exit
- volatility-targeted position sizing
- regime-aware validation

Baseline:

- momentum lookbacks: 21, 63, 126
- EMA trend: 200
- EMA exit: 100
- ADX period: 14
- ADX minimum: 18
- ATR period: 14
- ATR stop multiplier: 3.0
- ATR trail multiplier: 3.0
- target annual volatility: 25%
- max ATR percentile: 85%
- panic ATR percentile: 90%

---

## 2. Crypto Perpetual Funding / Basis Arbitrage

Priority:

- After Mission 21

Reason:

- strong crypto-native structural edge
- requires new funding-rate and perp-mark data tables

Required future tables:

- funding_rates
- perp_mark_prices
- spot_perp_basis_snapshots
- delta_neutral_positions
- funding_strategy_results

---

## 3. Liquidity Sweep + Displacement / FVG

Priority:

- After intraday candle ingestion

Reason:

- retail-popular concept with valid liquidity logic
- must be fully codified
- needs 15m, 1h, or 4h data

Required hard filters:

- objective swing detection
- objective sweep threshold
- displacement threshold
- fair value gap definition
- minimum reward:risk
- panic-volatility rejection

---

## 4. Opening Range Breakout + VWAP

Priority:

- After intraday candle ingestion

Reason:

- useful only on intraday sessions
- not suitable for 1d candles

Required future features:

- session VWAP
- session anchors
- opening range detection
- intraday volume filters

---

# Current Live Trading Status

Live trading:

- NO-GO

Still forbidden:

- private key usage
- transaction signing
- mainnet execution
- real capital
- live order routing

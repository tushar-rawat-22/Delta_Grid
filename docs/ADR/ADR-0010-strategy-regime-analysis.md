# ADR-0010: Strategy Metrics and Regime Analysis

## Status

Accepted

## Date

2026-07-07

---

## Context

DeltaGrid must not judge strategies only by total return.

A strategy can look profitable overall but fail badly in:

- bear markets
- sideways markets
- high-volatility markets
- low-liquidity conditions
- high-cost conditions

Mission 10 adds regime-level analysis so each strategy can be tested by market condition.

---

## Hypothesis

A strategy that performs well across multiple regimes is more robust than a strategy that only performs well in one environment.

Regime analysis improves capital preservation by identifying where a strategy should be disabled.

---

## Decision

Add strategy regime analysis.

Files changed:

- offchain/db/schema.py
- offchain/backtest/regime_analysis.py
- offchain/tests/test_regime_analysis.py

Commit:

- 64644d1 Add strategy regime analysis

---

## Tables Added

- market_regime_labels
- strategy_regime_metrics

---

## Regime Types

Trend regimes:

- bull
- bear
- sideways
- unknown

Volatility regimes:

- high_volatility
- low_volatility
- unknown

---

## Verified Database Output

Regime labels:

- 720

Strategy regime metrics:

- 5

---

## Latest Regime Metrics

### Trend: Bull

Trades:

- 7

Net PnL:

- 1401.95

Profit factor:

- 4.06

Win rate:

- 42.85%

Verdict:

- NO_GO

Reason:

- Positive PnL, but sample is small and win rate is below required threshold.

---

### Trend: Bear

Trades:

- 3

Net PnL:

- -4002.04

Profit factor:

- 0.0

Win rate:

- 0.0%

Verdict:

- INSUFFICIENT_SAMPLE

Reason:

- Too few trades and poor result.

---

### Trend: Sideways

Trades:

- 7

Net PnL:

- -1647.34

Profit factor:

- 0.42

Win rate:

- 28.57%

Verdict:

- NO_GO

Reason:

- Negative performance.

---

### Volatility: High Volatility

Trades:

- 2

Net PnL:

- -369.74

Profit factor:

- 0.0

Win rate:

- 0.0%

Verdict:

- INSUFFICIENT_SAMPLE

Reason:

- Too few trades.

---

### Volatility: Low Volatility

Trades:

- 15

Net PnL:

- -3877.69

Profit factor:

- 0.44

Win rate:

- 33.33%

Verdict:

- NO_GO

Reason:

- Negative performance and weak profit factor.

---

## Recommendation

Framework:

- GO

MA crossover baseline:

- NO-GO

Live trading:

- NO-GO

Reason:

- The framework successfully detects regime weakness.
- The baseline strategy is not robust.
- The strategy fails in too many regimes.
- The only profitable regime still does not pass strict approval rules.

---

## Safety Status

Still safe:

- no private keys
- no signing
- no real trades
- no real capital
- research-only analysis

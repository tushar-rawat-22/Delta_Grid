# ADR-0013: Real Historical Market Data Ingestion

<!-- deltagrid-document-status: HISTORICAL -->

> **Historical architecture decision**
>
> This ADR records a decision accepted for the DeltaGrid phase in which it was
> written. “Accepted” does not grant current research, paper trading, live
> trading, capital, ML, or autonomous authority. See the
> [documentation home](../README.md) and
> [final freeze](../DELTAGRID_FINAL_FREEZE.md) for current status.

## Status

Accepted

## Date

2026-07-08

---

## Context

DeltaGrid previously used synthetic historical data.

Mission 13 adds real historical market data ingestion.

This lets DeltaGrid test strategies on real ETHUSDT candles.

---

## Decision

Add Binance Spot historical candle ingestion.

Files:

- offchain/backtest/binance_historical_data.py
- offchain/tests/test_binance_historical_data.py

---

## Data Source

Source:

- Binance Spot public klines

Symbol:

- ETHUSDT

Timeframe:

- 1d

Date range:

- 2023-01-01 to 2026-06-30

Candles ingested:

- 1277

Database source:

- binance_spot

Market ID:

- chain_id 0

---

## Test Result

Command:

    python -m unittest discover -s tests -v

Result:

    Ran 25 tests
    OK

---

## Backtest Result

Strategy:

- ma_crossover_baseline

Version:

- v1

Symbol:

- ETHUSDT

Timeframe:

- 1d

Net return:

- 30.77%

Max drawdown:

- 44.94%

Sharpe ratio:

- 0.388

Profit factor:

- 1.187

Win rate:

- 33.33%

Trades:

- 24

Status:

- research_only

---

## Regime Result

Bull:

- GO_FOR_RESEARCH

Sideways:

- NO_GO

Bear:

- NO_GO

High volatility:

- NO_GO

Low volatility:

- INSUFFICIENT_SAMPLE

---

## Investment Committee Verdict

Data ingestion framework:

- GO

Current MA crossover strategy:

- RESEARCH_ONLY

Live trading:

- NO-GO

Reason:

- drawdown is too high
- Sharpe ratio is weak
- profit factor is weak
- strategy fails in bear and sideways regimes
- no live execution validation exists yet

---

## Safety Status

Still forbidden:

- no private keys
- no signing
- no real trades
- no real capital
- no mainnet execution

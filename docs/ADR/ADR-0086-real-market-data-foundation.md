# ADR-0086: Real-Market Data Foundation

<!-- deltagrid-document-status: HISTORICAL -->

> **Historical architecture decision**
>
> This ADR records a decision accepted for the DeltaGrid phase in which it was
> written. “Accepted” does not grant current research, paper trading, live
> trading, capital, ML, or autonomous authority. See the
> [documentation home](../README.md) and
> [final freeze](../DELTAGRID_FINAL_FREEZE.md) for current status.

Date: 2026-07-12

Status: Accepted after verification

## Context

Mission 85 locked a falsification-first funding-carry research charter for
BTCUSDT, ETHUSDT, and SOLUSDT.

The charter requires spot OHLCV, perpetual OHLCV, mark-price OHLC,
index-price OHLC, and settled funding-rate history from public Binance market
data.

Existing DeltaGrid market-data tables do not provide this complete contract
with immutable raw-response provenance.

## Decision

Mission 86 creates an isolated, resumable data-foundation layer.

Every public HTTP response is:

- captured without API credentials;
- hashed with SHA-256;
- stored as a gzip file;
- recorded with request parameters and source URL;
- linked to each normalized market row;
- included in a deterministic dataset manifest.

Mission 86 uses only:

- Binance public spot REST market data;
- Binance public USD-M futures REST market data;
- BTCUSDT, ETHUSDT, and SOLUSDT;
- the Mission 85 time window;
- one-hour canonical bars.

## Research Boundary

Mission 86 does not:

- certify dataset quality;
- inspect strategy performance;
- evaluate the untouched holdout;
- run a backtest;
- train or promote a model;
- create signals or orders;
- deploy capital;
- claim profitability.

Every dataset remains:

`UNCERTIFIED_PENDING_MISSION87`

Formal gap analysis, timestamp alignment, OHLC validation, duplicate analysis,
and research certification belong to Mission 87.

## Safety

No private keys, signing, paid APIs, trading credentials, live orders,
leverage, model promotion, or capital deployment are authorized.

# Mission 100 — Forward Market Data Acquisition

Mission 100 starts accumulating forward-observed public market evidence without reopening research.

## Scope

The collector is intentionally small. It can make HTTPS `GET` requests only to the frozen public Binance market-data endpoints for BTCUSDT, ETHUSDT, and SOLUSDT. It records hourly spot, perpetual, mark-price, and index-price bars plus settled funding events. It also records provider clock evidence and current funding configuration metadata.

There is no generic URL input, provider plugin, WebSocket client, API-key path, signed request path, account endpoint, order endpoint, or fallback host.

## Temporal rule

For forward capture, `available_at` means when DeltaGrid actually received the provider response. That is deliberately different from the market event timestamp. A bar is accepted only after its provider close timestamp and the fixed safety margin. Funding events use the settled funding timestamp.

If DeltaGrid is offline, later catch-up records keep their later receipt time. The system does not backdate availability.

Provider corrections append a later revision. Existing evidence is never overwritten.

## Journal and raw evidence

Runtime evidence lives outside the Git checkout. Each successful response is preserved as deterministic gzip bytes in a content-addressed object store and linked to an append-only receipt in the acquisition journal. Checkpoints advance only after the batch evidence is committed.

Failed batches remain visible as failures and cannot become authoritative revision parents. Crash-created orphan objects are preserved for inspection rather than deleted automatically.

The normal capture path uses the SQLite raw-object registry for bounded accounting. A full physical object rehash is available through the explicit journal-verification command instead of rescanning the entire store before every hourly capture.

## Clock health

Each capture checks both Spot and USDⓈ-M server time. DeltaGrid compares provider time with the local request midpoint and compares wall-clock elapsed time with monotonic elapsed time. Unhealthy clock evidence cannot produce `OBSERVED_LIVE` observations.

## Backup

Mission 100 can export and verify a local evidence backup. No cloud backup provider or backup credential is authorized. Capture does not stop merely because a backup target is unavailable; later research admission may require a verified backup.

## Research boundary

Mission 100 evidence is not a Mission 99 certified real-data release and cannot be resolved for strategy research. A later reviewed custody bridge is required before forward evidence can become an admissible research dataset.

Mission 100 performs no return calculation, strategy evaluation, model work, signals, portfolio allocation, paper trading, live trading, exchange-account access, credential access, orders, or capital deployment.

## Operator commands

The foreground CLI is:

```text
python -m offchain.market_data_acquisition show-contract
python -m offchain.market_data_acquisition init-runtime ...
python -m offchain.market_data_acquisition verify-journal ...
python -m offchain.market_data_acquisition capture-once ...
python -m offchain.market_data_acquisition export-backup ...
python -m offchain.market_data_acquisition verify-backup ...
```

Write-producing commands require explicit acknowledgement strings. Mission 100 does not install a scheduler during implementation or acceptance. Scheduler activation is a separate post-merge operator decision.

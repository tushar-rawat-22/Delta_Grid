# Founder Pine strategy hypothesis intake — 2026-09-02

Status: **UNVERIFIED RESEARCH INPUT — NOT AN AUTHORIZATION OR ALPHA CLAIM**

This note records strategy ideas supplied by the founder for later governed falsification. It does not open development research, validation, holdout, paper trading, live trading, credentials, orders, permits, or capital. Any executable work must pass the existing Mission/Research Director authority chain.

## Hypothesis families

1. **GainzAlgo engulfing / ATR / RSI family**
   - Bullish/bearish engulfing pattern.
   - Candle-body/ATR stability threshold.
   - RSI filters.
   - Momentum lookback variants.
   - ATR stop and fixed risk/reward target.

2. **GainzAlgo trend-filtered variants**
   - 50/200 EMA regime filters.
   - Lower/higher RSI thresholds.
   - Wider ATR stops and lower R:R variants.

3. **Fast multi-target GainzAlgo variants**
   - Shorter RSI/momentum lookbacks.
   - Three profit targets with partial exits.
   - Optional break-even stop after TP1.

4. **One-minute SMC/FVG + stochastic + RSI family**
   - 200 EMA regime filter.
   - RSI and stochastic confirmation.
   - Fair-value-gap condition.
   - ATR-buffered stop with nominal 3:1 target.

5. **One-minute fixed-percentage scalp family**
   - 9 EMA crossover plus rising-volume condition.
   - Fixed 0.23% target and 0.15% stop.
   - Supplied variant uses 100% equity sizing and therefore requires rejection or normalized risk sizing before any serious test.

6. **SPECTRA DSP family**
   - Two-pole SuperSmoother trend estimate.
   - Derivative/spectral momentum versus rolling standard-deviation band.
   - ATR-based stop/target.

7. **SPECTRA × GainzAlgo combined family**
   - SuperSmoother momentum signal plus trailing-volatility trend state.
   - RSI filter and ATR risk model.
   - Several supplied revisions differ in entry gating and target display semantics.

## Intake defects and contradictions to resolve before research

- The supplied GainzAlgo variants contain opposite momentum definitions in different revisions (`close < close[n]` versus `close > close[n]` for bullish momentum). These are distinct hypotheses, not interchangeable implementations.
- Comments claiming “both components align” conflict with combined conditions using `(spectraBull OR gainzBull)` in supplied revisions. The intended causal hypothesis must be chosen explicitly.
- “Wider stop = lower risk” is not valid unless position size is reduced so cash risk stays fixed.
- “Lower R:R = higher win rate” is not a guaranteed property; it is an empirical hypothesis.
- The 1-minute 0.23% strategy is especially sensitive to fees, spread, slippage, latency and fill assumptions; gross bar-based results are not decision evidence.
- Same-bar Pine fills and intrabar TP/SL touches cannot be assumed equivalent to DeltaGrid's strict event-driven execution model.
- Partial-exit quantities and break-even transitions need deterministic semantics independent of TradingView's remaining-position percentage behavior.
- No supplied strategy contains evidence of robustness, cross-market stability, protected-split performance or profitable out-of-sample behavior.

## Required governed treatment

Before any candidate can be tested:

1. Normalize each family into a falsifiable economic/market-mechanism claim rather than importing Pine code literally.
2. Deduplicate materially overlapping families against DeltaGrid's rejected directional research.
3. Freeze parameter grids before looking at protected outcomes.
4. Use DeltaGrid's certified market-data path and event-driven next-bar execution semantics.
5. Model realistic commissions, spread/slippage, latency/fill uncertainty and position sizing.
6. Separate development, validation and holdout authority exactly as existing contracts require.
7. Report rejected results as first-class evidence; no cherry-picking and no “best settings” promotion without preregistered gates.
8. Preserve current authority: research software capability is not permission to paper trade, live trade or deploy capital.

## Commercial product implication

The strongest product opportunity is not to sell these signals. They are useful test inputs for a **strategy falsification / audit workflow**: ingest a strategy idea, normalize assumptions, run reproducible cost-aware tests, compare variants, produce an evidence bundle, and explain why a hypothesis survives or fails. That aligns with DeltaGrid's existing provenance/governance strengths while avoiding unsupported profitability claims.

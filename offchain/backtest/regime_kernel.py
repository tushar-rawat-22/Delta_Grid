from decimal import Decimal, getcontext

from backtest.indicator_engine import (
    adx,
    atr,
    bollinger_bandwidth,
    ema,
    rolling_percentile_rank,
    rolling_realized_volatility,
    sma,
    to_decimal,
)


getcontext().prec = 40


def extract_ohlcv(candles):
    return {
        "open": [to_decimal(candle["open"]) for candle in candles],
        "high": [to_decimal(candle["high"]) for candle in candles],
        "low": [to_decimal(candle["low"]) for candle in candles],
        "close": [to_decimal(candle["close"]) for candle in candles],
        "volume": [to_decimal(candle["volume"]) for candle in candles],
    }


def value_at(series, index):
    if index < 0 or index >= len(series):
        return None

    return series[index]


def missing_any(*values):
    return any(value is None for value in values)


def build_regime_features(candles):
    ohlcv = extract_ohlcv(candles)

    closes = ohlcv["close"]
    highs = ohlcv["high"]
    lows = ohlcv["low"]
    volumes = ohlcv["volume"]

    atr_14 = atr(highs, lows, closes, 14)
    adx_14 = adx(highs, lows, closes, 14)

    bb_width_20 = bollinger_bandwidth(closes, 20, Decimal("2"))
    bb_width_pct_120 = rolling_percentile_rank(
        [
            value if value is not None else Decimal("0")
            for value in bb_width_20
        ],
        120,
    )

    atr_pct_120 = rolling_percentile_rank(
        [
            value if value is not None else Decimal("0")
            for value in atr_14
        ],
        120,
    )

    realized_vol_20 = rolling_realized_volatility(closes, 20)
    realized_vol_pct_120 = rolling_percentile_rank(
        [
            value if value is not None else Decimal("0")
            for value in realized_vol_20
        ],
        120,
    )

    features = {
        "close": closes,
        "high": highs,
        "low": lows,
        "volume": volumes,
        "volume_sma_20": sma(volumes, 20),
        "ema_20": ema(closes, 20),
        "ema_50": ema(closes, 50),
        "ema_100": ema(closes, 100),
        "ema_200": ema(closes, 200),
        "atr_14": atr_14,
        "atr_pct_120": atr_pct_120,
        "adx_14": adx_14,
        "bb_width_20": bb_width_20,
        "bb_width_pct_120": bb_width_pct_120,
        "realized_vol_20": realized_vol_20,
        "realized_vol_pct_120": realized_vol_pct_120,
    }

    return features


def classify_regime_at(features, index):
    close = value_at(features["close"], index)
    ema_50 = value_at(features["ema_50"], index)
    ema_200 = value_at(features["ema_200"], index)
    adx_14 = value_at(features["adx_14"], index)
    atr_pct = value_at(features["atr_pct_120"], index)
    bb_width_pct = value_at(features["bb_width_pct_120"], index)
    realized_vol_pct = value_at(features["realized_vol_pct_120"], index)

    if missing_any(close, ema_50, ema_200, adx_14, atr_pct, bb_width_pct):
        return {
            "index": index,
            "primary_regime": "INSUFFICIENT_DATA",
            "labels": ["INSUFFICIENT_DATA"],
        }

    ema_spread = abs(ema_50 / ema_200 - Decimal("1"))

    labels = []

    bull_trend = (
        close > ema_200
        and ema_50 > ema_200
        and adx_14 >= Decimal("18")
    )

    bear_trend = (
        close < ema_200
        and ema_50 < ema_200
        and adx_14 >= Decimal("18")
    )

    sideways = (
        adx_14 < Decimal("18")
        and ema_spread <= Decimal("0.08")
    )

    compression = (
        bb_width_pct <= Decimal("0.25")
        and atr_pct <= Decimal("0.60")
    )

    expansion = (
        bb_width_pct >= Decimal("0.75")
        or atr_pct >= Decimal("0.75")
    )

    low_volatility = atr_pct <= Decimal("0.30")
    high_volatility = atr_pct >= Decimal("0.80")
    panic_volatility = atr_pct >= Decimal("0.90")

    if bull_trend:
        labels.append("BULL_TREND")

    if bear_trend:
        labels.append("BEAR_TREND")

    if sideways:
        labels.append("SIDEWAYS")

    if compression:
        labels.append("COMPRESSION")

    if expansion:
        labels.append("EXPANSION")

    if low_volatility:
        labels.append("LOW_VOLATILITY")

    if high_volatility:
        labels.append("HIGH_VOLATILITY")

    if panic_volatility:
        labels.append("PANIC_VOLATILITY")

    if not labels:
        labels.append("MIXED_REGIME")

    if panic_volatility:
        primary = "PANIC_VOLATILITY"
    elif bull_trend:
        primary = "BULL_TREND"
    elif bear_trend:
        primary = "BEAR_TREND"
    elif compression:
        primary = "COMPRESSION"
    elif sideways:
        primary = "SIDEWAYS"
    elif high_volatility:
        primary = "HIGH_VOLATILITY"
    elif low_volatility:
        primary = "LOW_VOLATILITY"
    elif expansion:
        primary = "EXPANSION"
    else:
        primary = "MIXED_REGIME"

    return {
        "index": index,
        "primary_regime": primary,
        "labels": labels,
        "close": format(close, "f"),
        "ema_spread": format(ema_spread, "f"),
        "adx_14": format(adx_14, "f"),
        "atr_pct_120": format(atr_pct, "f"),
        "bb_width_pct_120": format(bb_width_pct, "f"),
        "realized_vol_pct_120": None if realized_vol_pct is None else format(realized_vol_pct, "f"),
    }


def classify_regimes(candles):
    features = build_regime_features(candles)

    return [
        classify_regime_at(features, index)
        for index in range(len(candles))
    ]

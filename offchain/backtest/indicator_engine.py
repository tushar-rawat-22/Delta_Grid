from decimal import Decimal, getcontext


getcontext().prec = 40


def to_decimal(value):
    if value is None:
        return None

    return Decimal(str(value))


def to_decimal_list(values):
    return [to_decimal(value) for value in values]


def safe_div(numerator, denominator):
    numerator = to_decimal(numerator)
    denominator = to_decimal(denominator)

    if denominator == 0:
        return Decimal("0")

    return numerator / denominator


def empty_series(length):
    return [None for _ in range(length)]


def require_period(period):
    if period <= 0:
        raise ValueError("period must be positive")


def sma(values, period):
    require_period(period)

    values = to_decimal_list(values)
    result = empty_series(len(values))

    if len(values) < period:
        return result

    rolling_sum = Decimal("0")

    for index, value in enumerate(values):
        rolling_sum += value

        if index >= period:
            rolling_sum -= values[index - period]

        if index >= period - 1:
            result[index] = rolling_sum / Decimal(period)

    return result


def ema(values, period):
    require_period(period)

    values = to_decimal_list(values)
    result = empty_series(len(values))

    if len(values) < period:
        return result

    seed = sum(values[:period], Decimal("0")) / Decimal(period)
    result[period - 1] = seed

    alpha = Decimal("2") / Decimal(period + 1)

    for index in range(period, len(values)):
        result[index] = values[index] * alpha + result[index - 1] * (Decimal("1") - alpha)

    return result


def rolling_std(values, period):
    require_period(period)

    values = to_decimal_list(values)
    result = empty_series(len(values))

    if len(values) < period:
        return result

    for index in range(period - 1, len(values)):
        window = values[index - period + 1:index + 1]
        mean = sum(window, Decimal("0")) / Decimal(period)

        variance = sum(
            (value - mean) * (value - mean)
            for value in window
        ) / Decimal(period)

        result[index] = variance.sqrt()

    return result


def rolling_percentile_rank(values, period):
    require_period(period)

    values = to_decimal_list(values)
    result = empty_series(len(values))

    if len(values) < period:
        return result

    for index in range(period - 1, len(values)):
        current = values[index]
        window = values[index - period + 1:index + 1]

        less_or_equal = sum(
            1
            for value in window
            if value <= current
        )

        result[index] = Decimal(less_or_equal) / Decimal(period)

    return result


def true_range(high, low, previous_close):
    high = to_decimal(high)
    low = to_decimal(low)

    if previous_close is None:
        return high - low

    previous_close = to_decimal(previous_close)

    return max(
        high - low,
        abs(high - previous_close),
        abs(low - previous_close),
    )


def true_ranges(highs, lows, closes):
    highs = to_decimal_list(highs)
    lows = to_decimal_list(lows)
    closes = to_decimal_list(closes)

    result = []

    for index in range(len(closes)):
        previous_close = None if index == 0 else closes[index - 1]
        result.append(true_range(highs[index], lows[index], previous_close))

    return result


def atr(highs, lows, closes, period):
    require_period(period)

    ranges = true_ranges(highs, lows, closes)
    result = empty_series(len(ranges))

    if len(ranges) < period:
        return result

    seed = sum(ranges[:period], Decimal("0")) / Decimal(period)
    result[period - 1] = seed

    for index in range(period, len(ranges)):
        result[index] = (
            result[index - 1] * Decimal(period - 1) + ranges[index]
        ) / Decimal(period)

    return result


def rsi(closes, period):
    require_period(period)

    closes = to_decimal_list(closes)
    result = empty_series(len(closes))

    if len(closes) <= period:
        return result

    gains = []
    losses = []

    for index in range(1, len(closes)):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, Decimal("0")))
        losses.append(abs(min(change, Decimal("0"))))

    avg_gain = sum(gains[:period], Decimal("0")) / Decimal(period)
    avg_loss = sum(losses[:period], Decimal("0")) / Decimal(period)

    first_index = period

    if avg_loss == 0:
        result[first_index] = Decimal("100")
    else:
        rs = avg_gain / avg_loss
        result[first_index] = Decimal("100") - Decimal("100") / (Decimal("1") + rs)

    for index in range(period + 1, len(closes)):
        gain = gains[index - 1]
        loss = losses[index - 1]

        avg_gain = (
            avg_gain * Decimal(period - 1) + gain
        ) / Decimal(period)

        avg_loss = (
            avg_loss * Decimal(period - 1) + loss
        ) / Decimal(period)

        if avg_loss == 0:
            result[index] = Decimal("100")
        else:
            rs = avg_gain / avg_loss
            result[index] = Decimal("100") - Decimal("100") / (Decimal("1") + rs)

    return result


def bollinger_bands(values, period, std_mult):
    require_period(period)

    values = to_decimal_list(values)
    std_mult = to_decimal(std_mult)

    middle = sma(values, period)
    std = rolling_std(values, period)

    upper = empty_series(len(values))
    lower = empty_series(len(values))

    for index in range(len(values)):
        if middle[index] is None or std[index] is None:
            continue

        upper[index] = middle[index] + std[index] * std_mult
        lower[index] = middle[index] - std[index] * std_mult

    return {
        "middle": middle,
        "upper": upper,
        "lower": lower,
    }


def bollinger_bandwidth(values, period, std_mult):
    bands = bollinger_bands(values, period, std_mult)

    result = empty_series(len(values))

    for index in range(len(values)):
        middle = bands["middle"][index]
        upper = bands["upper"][index]
        lower = bands["lower"][index]

        if middle is None or upper is None or lower is None:
            continue

        result[index] = safe_div(upper - lower, middle)

    return result


def donchian_high(highs, period):
    require_period(period)

    highs = to_decimal_list(highs)
    result = empty_series(len(highs))

    if len(highs) <= period:
        return result

    for index in range(period, len(highs)):
        result[index] = max(highs[index - period:index])

    return result


def donchian_low(lows, period):
    require_period(period)

    lows = to_decimal_list(lows)
    result = empty_series(len(lows))

    if len(lows) <= period:
        return result

    for index in range(period, len(lows)):
        result[index] = min(lows[index - period:index])

    return result


def donchian_channel(highs, lows, period):
    return {
        "high": donchian_high(highs, period),
        "low": donchian_low(lows, period),
    }


def simple_returns(values):
    values = to_decimal_list(values)
    result = empty_series(len(values))

    for index in range(1, len(values)):
        result[index] = safe_div(values[index], values[index - 1]) - Decimal("1")

    return result


def rolling_realized_volatility(values, period, annualization_factor=365):
    require_period(period)

    returns = simple_returns(values)
    result = empty_series(len(values))

    if len(values) < period + 1:
        return result

    annualizer = Decimal(str(annualization_factor)).sqrt()

    for index in range(period, len(values)):
        window = [
            value
            for value in returns[index - period + 1:index + 1]
            if value is not None
        ]

        if len(window) < period:
            continue

        mean = sum(window, Decimal("0")) / Decimal(period)

        variance = sum(
            (value - mean) * (value - mean)
            for value in window
        ) / Decimal(period)

        result[index] = variance.sqrt() * annualizer

    return result


def adx(highs, lows, closes, period):
    require_period(period)

    highs = to_decimal_list(highs)
    lows = to_decimal_list(lows)
    closes = to_decimal_list(closes)

    length = len(closes)
    result = empty_series(length)

    if length < period * 2 + 1:
        return result

    plus_dm = [Decimal("0") for _ in range(length)]
    minus_dm = [Decimal("0") for _ in range(length)]
    tr = true_ranges(highs, lows, closes)

    for index in range(1, length):
        up_move = highs[index] - highs[index - 1]
        down_move = lows[index - 1] - lows[index]

        if up_move > down_move and up_move > 0:
            plus_dm[index] = up_move

        if down_move > up_move and down_move > 0:
            minus_dm[index] = down_move

    atr_values = empty_series(length)
    plus_smooth = empty_series(length)
    minus_smooth = empty_series(length)

    atr_values[period] = sum(tr[1:period + 1], Decimal("0"))
    plus_smooth[period] = sum(plus_dm[1:period + 1], Decimal("0"))
    minus_smooth[period] = sum(minus_dm[1:period + 1], Decimal("0"))

    dx = empty_series(length)

    for index in range(period, length):
        if index > period:
            atr_values[index] = (
                atr_values[index - 1]
                - atr_values[index - 1] / Decimal(period)
                + tr[index]
            )

            plus_smooth[index] = (
                plus_smooth[index - 1]
                - plus_smooth[index - 1] / Decimal(period)
                + plus_dm[index]
            )

            minus_smooth[index] = (
                minus_smooth[index - 1]
                - minus_smooth[index - 1] / Decimal(period)
                + minus_dm[index]
            )

        if atr_values[index] == 0:
            continue

        plus_di = Decimal("100") * plus_smooth[index] / atr_values[index]
        minus_di = Decimal("100") * minus_smooth[index] / atr_values[index]

        denominator = plus_di + minus_di

        if denominator == 0:
            dx[index] = Decimal("0")
        else:
            dx[index] = Decimal("100") * abs(plus_di - minus_di) / denominator

    first_adx_index = period * 2

    initial_dx = [
        value
        for value in dx[period + 1:first_adx_index + 1]
        if value is not None
    ]

    if len(initial_dx) < period:
        return result

    result[first_adx_index] = sum(initial_dx, Decimal("0")) / Decimal(period)

    for index in range(first_adx_index + 1, length):
        if dx[index] is None:
            continue

        result[index] = (
            result[index - 1] * Decimal(period - 1) + dx[index]
        ) / Decimal(period)

    return result

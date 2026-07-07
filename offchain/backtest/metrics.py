import math


def max_drawdown_pct(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0

    peak = equity_curve[0]
    max_dd = 0.0

    for equity in equity_curve:
        peak = max(peak, equity)

        if peak <= 0:
            continue

        drawdown = (peak - equity) / peak
        max_dd = max(max_dd, drawdown)

    return max_dd * 100


def sharpe_ratio(equity_curve: list[float], periods_per_year: int = 365) -> float:
    if len(equity_curve) < 3:
        return 0.0

    returns = []

    for prev, current in zip(equity_curve, equity_curve[1:]):
        if prev <= 0:
            continue

        returns.append((current - prev) / prev)

    if len(returns) < 2:
        return 0.0

    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
    std_dev = math.sqrt(variance)

    if std_dev == 0:
        return 0.0

    return (mean_return / std_dev) * math.sqrt(periods_per_year)


def profit_factor(trade_pnls: list[float]) -> float:
    wins = sum(pnl for pnl in trade_pnls if pnl > 0)
    losses = abs(sum(pnl for pnl in trade_pnls if pnl < 0))

    if losses == 0:
        return 999.0 if wins > 0 else 0.0

    return wins / losses


def win_rate_pct(trade_pnls: list[float]) -> float:
    if not trade_pnls:
        return 0.0

    wins = sum(1 for pnl in trade_pnls if pnl > 0)

    return (wins / len(trade_pnls)) * 100

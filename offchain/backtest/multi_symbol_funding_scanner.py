import argparse
import json
import os
import sqlite3
import sys
from decimal import Decimal, getcontext
from pathlib import Path

from dotenv import load_dotenv


getcontext().prec = 40

OFFCHAIN_ROOT = Path(__file__).resolve().parents[1]

if str(OFFCHAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(OFFCHAIN_ROOT))

from db.schema import init_market_database, utc_now

from backtest.funding_basis_model import (
    ensure_schema as ensure_funding_basis_schema,
    resolve_db_path,
    to_decimal,
)

from backtest.funding_basis_ingestion import (
    binance_public_get,
)


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


DEFAULT_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "TRXUSDT",
    "NEARUSDT",
    "APTUSDT",
    "ARBUSDT",
    "OPUSDT",
    "SUIUSDT",
    "SEIUSDT",
    "INJUSDT",
]


def avg(values):
    if not values:
        return Decimal("0")

    return sum(values, Decimal("0")) / Decimal(len(values))


def safe_div(numerator, denominator):
    numerator = to_decimal(numerator)
    denominator = to_decimal(denominator)

    if denominator == 0:
        return Decimal("0")

    return numerator / denominator


def clamp(value, low, high):
    value = to_decimal(value)
    low = to_decimal(low)
    high = to_decimal(high)

    if value < low:
        return low

    if value > high:
        return high

    return value


def ensure_schema(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS multi_symbol_funding_scan_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        exchange TEXT NOT NULL,
        symbol TEXT NOT NULL,
        current_funding_rate TEXT NOT NULL,
        annualized_funding_rate_pct TEXT NOT NULL,
        mark_price TEXT NOT NULL,
        index_price TEXT NOT NULL,
        basis_pct TEXT NOT NULL,
        price_change_pct_24h TEXT NOT NULL,
        quote_volume_24h TEXT NOT NULL,
        open_interest TEXT NOT NULL,
        open_interest_value_usd TEXT NOT NULL,
        expected_funding_edge_pct TEXT NOT NULL,
        combined_cost_proxy_pct TEXT NOT NULL,
        net_expected_edge_pct TEXT NOT NULL,
        edge_to_cost_ratio TEXT NOT NULL,
        liquidity_score TEXT NOT NULL,
        funding_score TEXT NOT NULL,
        basis_risk_penalty TEXT NOT NULL,
        scanner_score TEXT NOT NULL,
        final_verdict TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS multi_symbol_funding_scan_summary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        exchange TEXT NOT NULL,
        symbols_requested INTEGER NOT NULL,
        symbols_scanned INTEGER NOT NULL,
        results_created INTEGER NOT NULL,
        go_count INTEGER NOT NULL,
        no_go_count INTEGER NOT NULL,
        best_result_id INTEGER,
        best_symbol TEXT,
        best_scanner_score TEXT NOT NULL,
        global_verdict TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def prepare_database(db_path):
    db_path = resolve_db_path(db_path)

    init_market_database(db_path)
    ensure_funding_basis_schema(db_path)
    ensure_schema(db_path)

    return db_path


def parse_symbols(symbols_text):
    if not symbols_text:
        return list(DEFAULT_SYMBOLS)

    values = [
        item.strip().upper()
        for item in symbols_text.split(",")
        if item.strip()
    ]

    if not values:
        return list(DEFAULT_SYMBOLS)

    seen = set()
    unique = []

    for symbol in values:
        if symbol not in seen:
            unique.append(symbol)
            seen.add(symbol)

    return unique


def annualize_funding_rate_pct(funding_rate, interval_hours):
    funding_rate = to_decimal(funding_rate)
    interval_hours = to_decimal(interval_hours)

    if interval_hours <= 0:
        raise ValueError("interval_hours must be positive")

    payments_per_year = Decimal("24") / interval_hours * Decimal("365")

    return funding_rate * payments_per_year * Decimal("100")


def basis_pct(mark_price, index_price):
    mark_price = to_decimal(mark_price)
    index_price = to_decimal(index_price)

    if index_price <= 0:
        return Decimal("0")

    return (mark_price - index_price) / index_price * Decimal("100")


def expected_funding_edge_pct(annualized_funding_rate_pct, holding_days, perp_weight):
    annualized_funding_rate_pct = to_decimal(annualized_funding_rate_pct)
    holding_days = int(holding_days)
    perp_weight = to_decimal(perp_weight)

    return annualized_funding_rate_pct * Decimal(holding_days) / Decimal("365") * perp_weight


def build_lookup(rows, symbol_key="symbol"):
    lookup = {}

    for row in rows:
        symbol = str(row.get(symbol_key, "")).upper()

        if symbol:
            lookup[symbol] = row

    return lookup


def fetch_24h_tickers(client=binance_public_get, timeout=10):
    payload = client(
        "/fapi/v1/ticker/24hr",
        params=None,
        timeout=timeout,
    )

    if isinstance(payload, dict):
        return [payload]

    return payload


def fetch_premium_index(client=binance_public_get, timeout=10):
    payload = client(
        "/fapi/v1/premiumIndex",
        params=None,
        timeout=timeout,
    )

    if isinstance(payload, dict):
        return [payload]

    return payload


def fetch_open_interest(symbol, client=binance_public_get, timeout=10):
    return client(
        "/fapi/v1/openInterest",
        params={
            "symbol": symbol.upper(),
        },
        timeout=timeout,
    )


def liquidity_score(quote_volume_24h, open_interest_value_usd):
    quote_volume_24h = to_decimal(quote_volume_24h)
    open_interest_value_usd = to_decimal(open_interest_value_usd)

    volume_component = clamp(
        safe_div(quote_volume_24h, Decimal("1000000000")) * Decimal("40"),
        Decimal("0"),
        Decimal("40"),
    )

    oi_component = clamp(
        safe_div(open_interest_value_usd, Decimal("500000000")) * Decimal("40"),
        Decimal("0"),
        Decimal("40"),
    )

    return volume_component + oi_component


def funding_score(annualized_funding_rate_pct):
    annualized_funding_rate_pct = abs(to_decimal(annualized_funding_rate_pct))

    return clamp(
        annualized_funding_rate_pct * Decimal("2"),
        Decimal("0"),
        Decimal("50"),
    )


def basis_risk_penalty(basis_value_pct):
    basis_value_pct = abs(to_decimal(basis_value_pct))

    if basis_value_pct <= Decimal("0.25"):
        return Decimal("0")

    if basis_value_pct <= Decimal("0.75"):
        return Decimal("10")

    if basis_value_pct <= Decimal("1.50"):
        return Decimal("25")

    return Decimal("50")


def scanner_score(
    annualized_funding_rate_pct,
    quote_volume_24h,
    open_interest_value_usd,
    basis_value_pct,
    net_expected_edge_pct,
    edge_to_cost_ratio,
):
    liq = liquidity_score(
        quote_volume_24h=quote_volume_24h,
        open_interest_value_usd=open_interest_value_usd,
    )

    fund = funding_score(annualized_funding_rate_pct)

    basis_penalty = basis_risk_penalty(basis_value_pct)

    net_edge_component = clamp(
        to_decimal(net_expected_edge_pct) * Decimal("20"),
        Decimal("-50"),
        Decimal("50"),
    )

    edge_cost_component = clamp(
        to_decimal(edge_to_cost_ratio) * Decimal("10"),
        Decimal("0"),
        Decimal("40"),
    )

    return (
        liq
        + fund
        + net_edge_component
        + edge_cost_component
        - basis_penalty
    )


def candidate_verdict(
    annualized_funding_rate_pct,
    quote_volume_24h,
    open_interest_value_usd,
    basis_value_pct,
    expected_edge_pct,
    net_expected_edge_pct,
    edge_to_cost_ratio,
    scanner_score_value,
    min_abs_annualized_funding_pct,
    min_quote_volume_24h,
    min_open_interest_value_usd,
    min_basis_pct,
    max_basis_pct,
    min_net_expected_edge_pct,
    min_edge_to_cost_ratio,
    min_scanner_score,
):
    annualized_funding_rate_pct = abs(to_decimal(annualized_funding_rate_pct))

    if annualized_funding_rate_pct < min_abs_annualized_funding_pct:
        return "NO_GO_LOW_FUNDING"

    if quote_volume_24h < min_quote_volume_24h:
        return "NO_GO_LOW_VOLUME"

    if open_interest_value_usd < min_open_interest_value_usd:
        return "NO_GO_LOW_OPEN_INTEREST"

    if basis_value_pct < min_basis_pct or basis_value_pct > max_basis_pct:
        return "NO_GO_BASIS_OUT_OF_RANGE"

    if expected_edge_pct <= 0:
        return "NO_GO_NO_POSITIVE_EDGE"

    if net_expected_edge_pct < min_net_expected_edge_pct:
        return "NO_GO_NET_EDGE_TOO_SMALL"

    if edge_to_cost_ratio < min_edge_to_cost_ratio:
        return "NO_GO_EDGE_BELOW_COST"

    if scanner_score_value < min_scanner_score:
        return "NO_GO_LOW_SCANNER_SCORE"

    return "GO_FOR_RESEARCH"


def recommended_action(verdict):
    if verdict == "GO_FOR_RESEARCH":
        return "PROMOTE_TO_CANDIDATE_RANKING_ENGINE"

    if verdict == "NO_GO_LOW_FUNDING":
        return "IGNORE_UNTIL_FUNDING_EXPANDS"

    if verdict == "NO_GO_LOW_VOLUME":
        return "REJECT_ILLIQUID_SYMBOL"

    if verdict == "NO_GO_LOW_OPEN_INTEREST":
        return "REJECT_LOW_OPEN_INTEREST"

    if verdict == "NO_GO_BASIS_OUT_OF_RANGE":
        return "WAIT_FOR_BASIS_NORMALIZATION"

    if verdict == "NO_GO_NO_POSITIVE_EDGE":
        return "IGNORE_UNTIL_EDGE_TURNS_POSITIVE"

    if verdict == "NO_GO_NET_EDGE_TOO_SMALL":
        return "REJECT_WEAK_AFTER_COST_EDGE"

    if verdict == "NO_GO_EDGE_BELOW_COST":
        return "WAIT_FOR_BETTER_EDGE_TO_COST_RATIO"

    if verdict == "NO_GO_LOW_SCANNER_SCORE":
        return "REJECT_LOW_RANKING_SCORE"

    return "OBSERVE_ONLY"


def evaluate_symbol(
    symbol,
    ticker_row,
    premium_row,
    open_interest_row,
    holding_days,
    interval_hours,
    perp_weight,
    combined_cost_proxy_pct,
    min_abs_annualized_funding_pct,
    min_quote_volume_24h,
    min_open_interest_value_usd,
    min_basis_pct,
    max_basis_pct,
    min_net_expected_edge_pct,
    min_edge_to_cost_ratio,
    min_scanner_score,
):
    mark_price = to_decimal(premium_row.get("markPrice", "0"))
    index_price = to_decimal(premium_row.get("indexPrice", "0"))
    funding_rate = to_decimal(premium_row.get("lastFundingRate", "0"))

    annualized = annualize_funding_rate_pct(
        funding_rate=funding_rate,
        interval_hours=interval_hours,
    )

    basis_value = basis_pct(
        mark_price=mark_price,
        index_price=index_price,
    )

    price_change_pct = to_decimal(ticker_row.get("priceChangePercent", "0"))
    quote_volume = to_decimal(ticker_row.get("quoteVolume", "0"))

    open_interest = to_decimal(open_interest_row.get("openInterest", "0"))
    open_interest_value = open_interest * mark_price

    expected_edge = expected_funding_edge_pct(
        annualized_funding_rate_pct=annualized,
        holding_days=holding_days,
        perp_weight=perp_weight,
    )

    net_edge = expected_edge - to_decimal(combined_cost_proxy_pct)

    edge_cost_ratio = safe_div(
        expected_edge,
        combined_cost_proxy_pct,
    )

    liq_score = liquidity_score(
        quote_volume_24h=quote_volume,
        open_interest_value_usd=open_interest_value,
    )

    fund_score = funding_score(annualized)

    basis_penalty = basis_risk_penalty(basis_value)

    score = scanner_score(
        annualized_funding_rate_pct=annualized,
        quote_volume_24h=quote_volume,
        open_interest_value_usd=open_interest_value,
        basis_value_pct=basis_value,
        net_expected_edge_pct=net_edge,
        edge_to_cost_ratio=edge_cost_ratio,
    )

    verdict = candidate_verdict(
        annualized_funding_rate_pct=annualized,
        quote_volume_24h=quote_volume,
        open_interest_value_usd=open_interest_value,
        basis_value_pct=basis_value,
        expected_edge_pct=expected_edge,
        net_expected_edge_pct=net_edge,
        edge_to_cost_ratio=edge_cost_ratio,
        scanner_score_value=score,
        min_abs_annualized_funding_pct=to_decimal(min_abs_annualized_funding_pct),
        min_quote_volume_24h=to_decimal(min_quote_volume_24h),
        min_open_interest_value_usd=to_decimal(min_open_interest_value_usd),
        min_basis_pct=to_decimal(min_basis_pct),
        max_basis_pct=to_decimal(max_basis_pct),
        min_net_expected_edge_pct=to_decimal(min_net_expected_edge_pct),
        min_edge_to_cost_ratio=to_decimal(min_edge_to_cost_ratio),
        min_scanner_score=to_decimal(min_scanner_score),
    )

    return {
        "symbol": symbol.upper(),
        "current_funding_rate": funding_rate,
        "annualized_funding_rate_pct": annualized,
        "mark_price": mark_price,
        "index_price": index_price,
        "basis_pct": basis_value,
        "price_change_pct_24h": price_change_pct,
        "quote_volume_24h": quote_volume,
        "open_interest": open_interest,
        "open_interest_value_usd": open_interest_value,
        "expected_funding_edge_pct": expected_edge,
        "combined_cost_proxy_pct": to_decimal(combined_cost_proxy_pct),
        "net_expected_edge_pct": net_edge,
        "edge_to_cost_ratio": edge_cost_ratio,
        "liquidity_score": liq_score,
        "funding_score": fund_score,
        "basis_risk_penalty": basis_penalty,
        "scanner_score": score,
        "final_verdict": verdict,
        "recommended_action": recommended_action(verdict),
    }


def insert_scan_result(
    db_path,
    run_label,
    exchange,
    result,
    assumptions,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO multi_symbol_funding_scan_results (
        run_label,
        exchange,
        symbol,
        current_funding_rate,
        annualized_funding_rate_pct,
        mark_price,
        index_price,
        basis_pct,
        price_change_pct_24h,
        quote_volume_24h,
        open_interest,
        open_interest_value_usd,
        expected_funding_edge_pct,
        combined_cost_proxy_pct,
        net_expected_edge_pct,
        edge_to_cost_ratio,
        liquidity_score,
        funding_score,
        basis_risk_penalty,
        scanner_score,
        final_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        exchange,
        result["symbol"],
        format(result["current_funding_rate"], "f"),
        format(result["annualized_funding_rate_pct"], "f"),
        format(result["mark_price"], "f"),
        format(result["index_price"], "f"),
        format(result["basis_pct"], "f"),
        format(result["price_change_pct_24h"], "f"),
        format(result["quote_volume_24h"], "f"),
        format(result["open_interest"], "f"),
        format(result["open_interest_value_usd"], "f"),
        format(result["expected_funding_edge_pct"], "f"),
        format(result["combined_cost_proxy_pct"], "f"),
        format(result["net_expected_edge_pct"], "f"),
        format(result["edge_to_cost_ratio"], "f"),
        format(result["liquidity_score"], "f"),
        format(result["funding_score"], "f"),
        format(result["basis_risk_penalty"], "f"),
        format(result["scanner_score"], "f"),
        result["final_verdict"],
        result["recommended_action"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def insert_scan_summary(
    db_path,
    run_label,
    exchange,
    summary,
    assumptions,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO multi_symbol_funding_scan_summary (
        run_label,
        exchange,
        symbols_requested,
        symbols_scanned,
        results_created,
        go_count,
        no_go_count,
        best_result_id,
        best_symbol,
        best_scanner_score,
        global_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        exchange,
        summary["symbols_requested"],
        summary["symbols_scanned"],
        summary["results_created"],
        summary["go_count"],
        summary["no_go_count"],
        summary["best_result_id"],
        summary["best_symbol"],
        format(summary["best_scanner_score"], "f"),
        summary["global_verdict"],
        summary["recommended_action"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def summarize_scan(symbols_requested, ranked_results):
    go_results = [
        item
        for item in ranked_results
        if item["final_verdict"] == "GO_FOR_RESEARCH"
    ]

    best = ranked_results[0] if ranked_results else None

    if go_results:
        global_verdict = "MULTI_SYMBOL_FUNDING_CANDIDATES_FOUND_NO_LIVE_TRADING"
        action = "PROMOTE_TO_CANDIDATE_RANKING_ENGINE"
    else:
        global_verdict = "NO_MULTI_SYMBOL_FUNDING_CANDIDATES_NO_LIVE_TRADING"
        action = "KEEP_SCANNING_AND_WAIT_FOR_EDGE"

    return {
        "symbols_requested": int(symbols_requested),
        "symbols_scanned": len(ranked_results),
        "results_created": len(ranked_results),
        "go_count": len(go_results),
        "no_go_count": len(ranked_results) - len(go_results),
        "best_result_id": None if best is None else best["id"],
        "best_symbol": None if best is None else best["symbol"],
        "best_scanner_score": Decimal("0") if best is None else best["scanner_score"],
        "global_verdict": global_verdict,
        "recommended_action": action,
    }


def clean_decimal_dict(item):
    cleaned = {}

    for key, value in item.items():
        if isinstance(value, Decimal):
            cleaned[key] = format(value, "f")
        else:
            cleaned[key] = value

    return cleaned


def run_multi_symbol_funding_scanner(
    db_path,
    symbols,
    run_label,
    holding_days,
    interval_hours,
    perp_weight,
    combined_cost_proxy_pct,
    min_abs_annualized_funding_pct,
    min_quote_volume_24h,
    min_open_interest_value_usd,
    min_basis_pct,
    max_basis_pct,
    min_net_expected_edge_pct,
    min_edge_to_cost_ratio,
    min_scanner_score,
    timeout,
    client=binance_public_get,
):
    db_path = prepare_database(db_path)

    exchange = "Binance Futures"

    requested_symbols = [
        symbol.upper()
        for symbol in symbols
    ]

    assumptions = {
        "research_only": True,
        "no_private_keys": True,
        "no_signing": True,
        "no_real_trades": True,
        "no_order_execution": True,
        "exchange": exchange,
        "run_label": run_label,
        "symbols": requested_symbols,
        "holding_days": int(holding_days),
        "interval_hours": format(to_decimal(interval_hours), "f"),
        "perp_weight": format(to_decimal(perp_weight), "f"),
        "combined_cost_proxy_pct": format(to_decimal(combined_cost_proxy_pct), "f"),
        "min_abs_annualized_funding_pct": format(to_decimal(min_abs_annualized_funding_pct), "f"),
        "min_quote_volume_24h": format(to_decimal(min_quote_volume_24h), "f"),
        "min_open_interest_value_usd": format(to_decimal(min_open_interest_value_usd), "f"),
        "min_basis_pct": format(to_decimal(min_basis_pct), "f"),
        "max_basis_pct": format(to_decimal(max_basis_pct), "f"),
        "min_net_expected_edge_pct": format(to_decimal(min_net_expected_edge_pct), "f"),
        "min_edge_to_cost_ratio": format(to_decimal(min_edge_to_cost_ratio), "f"),
        "min_scanner_score": format(to_decimal(min_scanner_score), "f"),
    }

    ticker_lookup = build_lookup(
        fetch_24h_tickers(
            client=client,
            timeout=timeout,
        )
    )

    premium_lookup = build_lookup(
        fetch_premium_index(
            client=client,
            timeout=timeout,
        )
    )

    results = []

    for symbol in requested_symbols:
        ticker_row = ticker_lookup.get(symbol)
        premium_row = premium_lookup.get(symbol)

        if ticker_row is None or premium_row is None:
            continue

        try:
            open_interest_row = fetch_open_interest(
                symbol=symbol,
                client=client,
                timeout=timeout,
            )
        except Exception:
            open_interest_row = {
                "symbol": symbol,
                "openInterest": "0",
            }

        result = evaluate_symbol(
            symbol=symbol,
            ticker_row=ticker_row,
            premium_row=premium_row,
            open_interest_row=open_interest_row,
            holding_days=int(holding_days),
            interval_hours=to_decimal(interval_hours),
            perp_weight=to_decimal(perp_weight),
            combined_cost_proxy_pct=to_decimal(combined_cost_proxy_pct),
            min_abs_annualized_funding_pct=to_decimal(min_abs_annualized_funding_pct),
            min_quote_volume_24h=to_decimal(min_quote_volume_24h),
            min_open_interest_value_usd=to_decimal(min_open_interest_value_usd),
            min_basis_pct=to_decimal(min_basis_pct),
            max_basis_pct=to_decimal(max_basis_pct),
            min_net_expected_edge_pct=to_decimal(min_net_expected_edge_pct),
            min_edge_to_cost_ratio=to_decimal(min_edge_to_cost_ratio),
            min_scanner_score=to_decimal(min_scanner_score),
        )

        row_id = insert_scan_result(
            db_path=db_path,
            run_label=run_label,
            exchange=exchange,
            result=result,
            assumptions=assumptions,
        )

        results.append({
            "id": row_id,
            **result,
        })

    ranked = sorted(
        results,
        key=lambda item: (
            item["final_verdict"] == "GO_FOR_RESEARCH",
            item["scanner_score"],
            item["net_expected_edge_pct"],
            item["edge_to_cost_ratio"],
        ),
        reverse=True,
    )

    summary = summarize_scan(
        symbols_requested=len(requested_symbols),
        ranked_results=ranked,
    )

    summary_id = insert_scan_summary(
        db_path=db_path,
        run_label=run_label,
        exchange=exchange,
        summary=summary,
        assumptions=assumptions,
    )

    top_candidates = ranked[:10]

    return {
        "run_label": run_label,
        "exchange": exchange,
        "summary_id": summary_id,
        "symbols_requested": len(requested_symbols),
        "symbols_scanned": len(ranked),
        "results_created": len(ranked),
        "go_count": summary["go_count"],
        "no_go_count": summary["no_go_count"],
        "best_symbol": summary["best_symbol"],
        "best_scanner_score": format(summary["best_scanner_score"], "f"),
        "top_candidates": [
            clean_decimal_dict(item)
            for item in top_candidates
        ],
        "global_verdict": summary["global_verdict"],
        "recommended_action": summary["recommended_action"],
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--run-label", default="mission_29_multi_symbol_funding_scanner")
    parser.add_argument("--holding-days", type=int, default=7)
    parser.add_argument("--interval-hours", default="8")
    parser.add_argument("--perp-weight", default="0.5")
    parser.add_argument("--combined-cost-proxy-pct", default="0.0755")
    parser.add_argument("--min-abs-annualized-funding-pct", default="10")
    parser.add_argument("--min-quote-volume-24h", default="100000000")
    parser.add_argument("--min-open-interest-value-usd", default="25000000")
    parser.add_argument("--min-basis-pct", default="-1.00")
    parser.add_argument("--max-basis-pct", default="1.50")
    parser.add_argument("--min-net-expected-edge-pct", default="0.02")
    parser.add_argument("--min-edge-to-cost-ratio", default="1.50")
    parser.add_argument("--min-scanner-score", default="50")
    parser.add_argument("--timeout", type=int, default=15)

    args = parser.parse_args()

    print("DeltaGrid Multi-Symbol Funding Scanner")
    print("Mode: research-only")
    print("Public market data only.")
    print("No private keys. No signing. No real trades.")

    result = run_multi_symbol_funding_scanner(
        db_path=args.db_path,
        symbols=parse_symbols(args.symbols),
        run_label=args.run_label,
        holding_days=args.holding_days,
        interval_hours=Decimal(args.interval_hours),
        perp_weight=Decimal(args.perp_weight),
        combined_cost_proxy_pct=Decimal(args.combined_cost_proxy_pct),
        min_abs_annualized_funding_pct=Decimal(args.min_abs_annualized_funding_pct),
        min_quote_volume_24h=Decimal(args.min_quote_volume_24h),
        min_open_interest_value_usd=Decimal(args.min_open_interest_value_usd),
        min_basis_pct=Decimal(args.min_basis_pct),
        max_basis_pct=Decimal(args.max_basis_pct),
        min_net_expected_edge_pct=Decimal(args.min_net_expected_edge_pct),
        min_edge_to_cost_ratio=Decimal(args.min_edge_to_cost_ratio),
        min_scanner_score=Decimal(args.min_scanner_score),
        timeout=args.timeout,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

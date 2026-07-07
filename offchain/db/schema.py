import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: str = "deltagrid.db") -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True) if "/" in db_path else None

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_market_database(db_path: str = "deltagrid.db") -> None:
    conn = connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS chains (
        chain_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        rpc_url TEXT,
        created_at_utc TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS blocks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chain_id INTEGER NOT NULL,
        block_number INTEGER NOT NULL,
        block_hash TEXT,
        timestamp_utc TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        UNIQUE(chain_id, block_number),
        FOREIGN KEY(chain_id) REFERENCES chains(chain_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS gas_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chain_id INTEGER NOT NULL,
        block_number INTEGER NOT NULL,
        gas_price_wei TEXT NOT NULL,
        timestamp_utc TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY(chain_id) REFERENCES chains(chain_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chain_id INTEGER NOT NULL,
        address TEXT NOT NULL,
        symbol TEXT NOT NULL,
        decimals INTEGER NOT NULL,
        created_at_utc TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL,
        UNIQUE(chain_id, address),
        FOREIGN KEY(chain_id) REFERENCES chains(chain_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS pools (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chain_id INTEGER NOT NULL,
        protocol TEXT NOT NULL,
        pool_address TEXT NOT NULL,
        token0_address TEXT NOT NULL,
        token1_address TEXT NOT NULL,
        fee_bps INTEGER NOT NULL,
        created_at_utc TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL,
        UNIQUE(chain_id, protocol, pool_address),
        FOREIGN KEY(chain_id) REFERENCES chains(chain_id)
    )
    """)


    cur.execute("""
    CREATE TABLE IF NOT EXISTS pool_price_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pool_id INTEGER NOT NULL,
        chain_id INTEGER NOT NULL,
        protocol TEXT NOT NULL,
        pool_address TEXT NOT NULL,
        token0_address TEXT NOT NULL,
        token1_address TEXT NOT NULL,
        price_token1_per_token0 TEXT NOT NULL,
        price_token0_per_token1 TEXT NOT NULL,
        liquidity_score INTEGER NOT NULL,
        source TEXT NOT NULL,
        block_number INTEGER,
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY(pool_id) REFERENCES pools(id),
        FOREIGN KEY(chain_id) REFERENCES chains(chain_id)
    )
    """)


    cur.execute("""
    CREATE TABLE IF NOT EXISTS route_candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chain_id INTEGER NOT NULL,
        start_token_address TEXT NOT NULL,
        end_token_address TEXT NOT NULL,
        hops INTEGER NOT NULL,
        route_json TEXT NOT NULL,
        estimated_output_per_input TEXT NOT NULL,
        min_liquidity_score INTEGER NOT NULL,
        source TEXT NOT NULL,
        block_number INTEGER,
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY(chain_id) REFERENCES chains(chain_id)
    )
    """)


    cur.execute("""
    CREATE TABLE IF NOT EXISTS historical_candles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chain_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        timestamp_utc TEXT NOT NULL,
        open TEXT NOT NULL,
        high TEXT NOT NULL,
        low TEXT NOT NULL,
        close TEXT NOT NULL,
        volume TEXT NOT NULL,
        source TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL,
        UNIQUE(chain_id, symbol, timeframe, timestamp_utc, source),
        FOREIGN KEY(chain_id) REFERENCES chains(chain_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS backtest_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        strategy_name TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
        chain_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        start_timestamp_utc TEXT NOT NULL,
        end_timestamp_utc TEXT NOT NULL,
        initial_capital TEXT NOT NULL,
        final_equity TEXT NOT NULL,
        net_return_pct TEXT NOT NULL,
        max_drawdown_pct TEXT NOT NULL,
        sharpe_ratio TEXT NOT NULL,
        profit_factor TEXT NOT NULL,
        win_rate_pct TEXT NOT NULL,
        trades_count INTEGER NOT NULL,
        total_costs TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY(chain_id) REFERENCES chains(chain_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS backtest_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        chain_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        entry_timestamp_utc TEXT NOT NULL,
        exit_timestamp_utc TEXT NOT NULL,
        side TEXT NOT NULL,
        entry_price TEXT NOT NULL,
        exit_price TEXT NOT NULL,
        quantity TEXT NOT NULL,
        gross_pnl TEXT NOT NULL,
        costs TEXT NOT NULL,
        net_pnl TEXT NOT NULL,
        return_pct TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES backtest_runs(id),
        FOREIGN KEY(chain_id) REFERENCES chains(chain_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS simulated_opportunities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chain_id INTEGER NOT NULL,
        block_number INTEGER,
        opportunity_type TEXT NOT NULL,
        route_json TEXT NOT NULL,
        gross_profit_wei TEXT NOT NULL,
        gas_cost_wei TEXT NOT NULL,
        flash_fee_wei TEXT NOT NULL,
        slippage_cost_wei TEXT NOT NULL,
        total_cost_wei TEXT NOT NULL,
        net_profit_wei TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY(chain_id) REFERENCES chains(chain_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS risk_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        opportunity_id INTEGER NOT NULL,
        risk_score INTEGER NOT NULL,
        approved INTEGER NOT NULL,
        reasons_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        FOREIGN KEY(opportunity_id) REFERENCES simulated_opportunities(id)
    )
    """)

    cur.execute("""
    INSERT OR IGNORE INTO schema_migrations (version, applied_at_utc)
    VALUES (?, ?)
    """, (SCHEMA_VERSION, utc_now()))

    conn.commit()
    conn.close()


def upsert_chain(
    db_path: str,
    chain_id: int,
    name: str,
    rpc_url: Optional[str] = None,
) -> None:
    conn = connect(db_path)
    cur = conn.cursor()
    now = utc_now()

    cur.execute("""
    INSERT INTO chains (
        chain_id,
        name,
        rpc_url,
        created_at_utc,
        updated_at_utc
    )
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(chain_id) DO UPDATE SET
        name = excluded.name,
        rpc_url = excluded.rpc_url,
        updated_at_utc = excluded.updated_at_utc
    """, (chain_id, name, rpc_url, now, now))

    conn.commit()
    conn.close()


def insert_block(
    db_path: str,
    chain_id: int,
    block_number: int,
    block_hash: str = "",
    timestamp_utc: Optional[str] = None,
) -> None:
    conn = connect(db_path)
    cur = conn.cursor()
    now = utc_now()

    cur.execute("""
    INSERT OR IGNORE INTO blocks (
        chain_id,
        block_number,
        block_hash,
        timestamp_utc,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?)
    """, (
        chain_id,
        block_number,
        block_hash,
        timestamp_utc or now,
        now,
    ))

    conn.commit()
    conn.close()


def insert_gas_snapshot(
    db_path: str,
    chain_id: int,
    block_number: int,
    gas_price_wei: int,
) -> None:
    conn = connect(db_path)
    cur = conn.cursor()
    now = utc_now()

    cur.execute("""
    INSERT INTO gas_snapshots (
        chain_id,
        block_number,
        gas_price_wei,
        timestamp_utc,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?)
    """, (
        chain_id,
        block_number,
        str(gas_price_wei),
        now,
        now,
    ))

    conn.commit()
    conn.close()


def upsert_token(
    db_path: str,
    chain_id: int,
    address: str,
    symbol: str,
    decimals: int,
) -> None:
    conn = connect(db_path)
    cur = conn.cursor()
    now = utc_now()

    cur.execute("""
    INSERT INTO tokens (
        chain_id,
        address,
        symbol,
        decimals,
        created_at_utc,
        updated_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(chain_id, address) DO UPDATE SET
        symbol = excluded.symbol,
        decimals = excluded.decimals,
        updated_at_utc = excluded.updated_at_utc
    """, (
        chain_id,
        address.lower(),
        symbol,
        decimals,
        now,
        now,
    ))

    conn.commit()
    conn.close()


def upsert_pool(
    db_path: str,
    chain_id: int,
    protocol: str,
    pool_address: str,
    token0_address: str,
    token1_address: str,
    fee_bps: int,
) -> None:
    conn = connect(db_path)
    cur = conn.cursor()
    now = utc_now()

    cur.execute("""
    INSERT INTO pools (
        chain_id,
        protocol,
        pool_address,
        token0_address,
        token1_address,
        fee_bps,
        created_at_utc,
        updated_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(chain_id, protocol, pool_address) DO UPDATE SET
        token0_address = excluded.token0_address,
        token1_address = excluded.token1_address,
        fee_bps = excluded.fee_bps,
        updated_at_utc = excluded.updated_at_utc
    """, (
        chain_id,
        protocol,
        pool_address.lower(),
        token0_address.lower(),
        token1_address.lower(),
        fee_bps,
        now,
        now,
    ))

    conn.commit()
    conn.close()


def insert_simulated_opportunity(
    db_path: str,
    chain_id: int,
    block_number: int,
    opportunity_type: str,
    route: list[dict],
    gross_profit_wei: int,
    gas_cost_wei: int,
    flash_fee_wei: int,
    slippage_cost_wei: int,
) -> int:
    total_cost_wei = gas_cost_wei + flash_fee_wei + slippage_cost_wei
    net_profit_wei = gross_profit_wei - total_cost_wei

    conn = connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO simulated_opportunities (
        chain_id,
        block_number,
        opportunity_type,
        route_json,
        gross_profit_wei,
        gas_cost_wei,
        flash_fee_wei,
        slippage_cost_wei,
        total_cost_wei,
        net_profit_wei,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        chain_id,
        block_number,
        opportunity_type,
        json.dumps(route),
        str(gross_profit_wei),
        str(gas_cost_wei),
        str(flash_fee_wei),
        str(slippage_cost_wei),
        str(total_cost_wei),
        str(net_profit_wei),
        utc_now(),
    ))

    opportunity_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(opportunity_id)


def insert_risk_decision(
    db_path: str,
    opportunity_id: int,
    risk_score: int,
    approved: bool,
    reasons: list[str],
) -> int:
    conn = connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO risk_decisions (
        opportunity_id,
        risk_score,
        approved,
        reasons_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?)
    """, (
        opportunity_id,
        risk_score,
        1 if approved else 0,
        json.dumps(reasons),
        utc_now(),
    ))

    decision_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(decision_id)


def list_pools(db_path: str) -> list[dict]:
    conn = connect(db_path)
    cur = conn.cursor()

    rows = cur.execute("""
    SELECT
        id,
        chain_id,
        protocol,
        pool_address,
        token0_address,
        token1_address,
        fee_bps
    FROM pools
    ORDER BY id
    """).fetchall()

    conn.close()

    return [
        {
            "id": row[0],
            "chain_id": row[1],
            "protocol": row[2],
            "pool_address": row[3],
            "token0_address": row[4],
            "token1_address": row[5],
            "fee_bps": row[6],
        }
        for row in rows
    ]


def insert_pool_price_snapshot(
    db_path: str,
    pool_id: int,
    chain_id: int,
    protocol: str,
    pool_address: str,
    token0_address: str,
    token1_address: str,
    price_token1_per_token0: str,
    price_token0_per_token1: str,
    liquidity_score: int,
    source: str,
    block_number: int | None = None,
) -> int:
    conn = connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO pool_price_snapshots (
        pool_id,
        chain_id,
        protocol,
        pool_address,
        token0_address,
        token1_address,
        price_token1_per_token0,
        price_token0_per_token1,
        liquidity_score,
        source,
        block_number,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        pool_id,
        chain_id,
        protocol,
        pool_address.lower(),
        token0_address.lower(),
        token1_address.lower(),
        price_token1_per_token0,
        price_token0_per_token1,
        liquidity_score,
        source,
        block_number,
        utc_now(),
    ))

    snapshot_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(snapshot_id)


def list_latest_pool_price_snapshots(db_path: str) -> list[dict]:
    conn = connect(db_path)
    cur = conn.cursor()

    rows = cur.execute("""
    SELECT
        s.id,
        s.pool_id,
        s.chain_id,
        s.protocol,
        s.pool_address,
        s.token0_address,
        s.token1_address,
        s.price_token1_per_token0,
        s.price_token0_per_token1,
        s.liquidity_score,
        s.source,
        s.block_number
    FROM pool_price_snapshots s
    INNER JOIN (
        SELECT pool_id, MAX(id) AS max_id
        FROM pool_price_snapshots
        GROUP BY pool_id
    ) latest
    ON s.pool_id = latest.pool_id
    AND s.id = latest.max_id
    ORDER BY s.id
    """).fetchall()

    conn.close()

    return [
        {
            "id": row[0],
            "pool_id": row[1],
            "chain_id": row[2],
            "protocol": row[3],
            "pool_address": row[4],
            "token0_address": row[5],
            "token1_address": row[6],
            "price_token1_per_token0": row[7],
            "price_token0_per_token1": row[8],
            "liquidity_score": row[9],
            "source": row[10],
            "block_number": row[11],
        }
        for row in rows
    ]


def insert_route_candidate(
    db_path: str,
    chain_id: int,
    start_token_address: str,
    end_token_address: str,
    hops: int,
    route_json: str,
    estimated_output_per_input: str,
    min_liquidity_score: int,
    source: str,
    block_number: int | None = None,
) -> int:
    conn = connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO route_candidates (
        chain_id,
        start_token_address,
        end_token_address,
        hops,
        route_json,
        estimated_output_per_input,
        min_liquidity_score,
        source,
        block_number,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        chain_id,
        start_token_address.lower(),
        end_token_address.lower(),
        hops,
        route_json,
        estimated_output_per_input,
        min_liquidity_score,
        source,
        block_number,
        utc_now(),
    ))

    route_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(route_id)


def insert_historical_candle(
    db_path: str,
    chain_id: int,
    symbol: str,
    timeframe: str,
    timestamp_utc: str,
    open_price: str,
    high_price: str,
    low_price: str,
    close_price: str,
    volume: str,
    source: str,
) -> None:
    conn = connect(db_path)
    cur = conn.cursor()
    now = utc_now()

    cur.execute("""
    INSERT INTO historical_candles (
        chain_id,
        symbol,
        timeframe,
        timestamp_utc,
        open,
        high,
        low,
        close,
        volume,
        source,
        created_at_utc,
        updated_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(chain_id, symbol, timeframe, timestamp_utc, source)
    DO UPDATE SET
        open = excluded.open,
        high = excluded.high,
        low = excluded.low,
        close = excluded.close,
        volume = excluded.volume,
        updated_at_utc = excluded.updated_at_utc
    """, (
        chain_id,
        symbol,
        timeframe,
        timestamp_utc,
        open_price,
        high_price,
        low_price,
        close_price,
        volume,
        source,
        now,
        now,
    ))

    conn.commit()
    conn.close()


def list_historical_candles(
    db_path: str,
    chain_id: int,
    symbol: str,
    timeframe: str,
    source: str | None = None,
) -> list[dict]:
    conn = connect(db_path)
    cur = conn.cursor()

    if source:
        rows = cur.execute("""
        SELECT timestamp_utc, open, high, low, close, volume, source
        FROM historical_candles
        WHERE chain_id = ?
        AND symbol = ?
        AND timeframe = ?
        AND source = ?
        ORDER BY timestamp_utc
        """, (chain_id, symbol, timeframe, source)).fetchall()
    else:
        rows = cur.execute("""
        SELECT timestamp_utc, open, high, low, close, volume, source
        FROM historical_candles
        WHERE chain_id = ?
        AND symbol = ?
        AND timeframe = ?
        ORDER BY timestamp_utc
        """, (chain_id, symbol, timeframe)).fetchall()

    conn.close()

    return [
        {
            "timestamp_utc": row[0],
            "open": row[1],
            "high": row[2],
            "low": row[3],
            "close": row[4],
            "volume": row[5],
            "source": row[6],
        }
        for row in rows
    ]


def insert_backtest_run(
    db_path: str,
    strategy_name: str,
    strategy_version: str,
    chain_id: int,
    symbol: str,
    timeframe: str,
    start_timestamp_utc: str,
    end_timestamp_utc: str,
    initial_capital: str,
    final_equity: str,
    net_return_pct: str,
    max_drawdown_pct: str,
    sharpe_ratio: str,
    profit_factor: str,
    win_rate_pct: str,
    trades_count: int,
    total_costs: str,
    assumptions_json: str,
    status: str,
) -> int:
    conn = connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO backtest_runs (
        strategy_name,
        strategy_version,
        chain_id,
        symbol,
        timeframe,
        start_timestamp_utc,
        end_timestamp_utc,
        initial_capital,
        final_equity,
        net_return_pct,
        max_drawdown_pct,
        sharpe_ratio,
        profit_factor,
        win_rate_pct,
        trades_count,
        total_costs,
        assumptions_json,
        status,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        strategy_name,
        strategy_version,
        chain_id,
        symbol,
        timeframe,
        start_timestamp_utc,
        end_timestamp_utc,
        initial_capital,
        final_equity,
        net_return_pct,
        max_drawdown_pct,
        sharpe_ratio,
        profit_factor,
        win_rate_pct,
        trades_count,
        total_costs,
        assumptions_json,
        status,
        utc_now(),
    ))

    run_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(run_id)


def insert_backtest_trade(
    db_path: str,
    run_id: int,
    chain_id: int,
    symbol: str,
    entry_timestamp_utc: str,
    exit_timestamp_utc: str,
    side: str,
    entry_price: str,
    exit_price: str,
    quantity: str,
    gross_pnl: str,
    costs: str,
    net_pnl: str,
    return_pct: str,
) -> int:
    conn = connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO backtest_trades (
        run_id,
        chain_id,
        symbol,
        entry_timestamp_utc,
        exit_timestamp_utc,
        side,
        entry_price,
        exit_price,
        quantity,
        gross_pnl,
        costs,
        net_pnl,
        return_pct,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id,
        chain_id,
        symbol,
        entry_timestamp_utc,
        exit_timestamp_utc,
        side,
        entry_price,
        exit_price,
        quantity,
        gross_pnl,
        costs,
        net_pnl,
        return_pct,
        utc_now(),
    ))

    trade_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(trade_id)

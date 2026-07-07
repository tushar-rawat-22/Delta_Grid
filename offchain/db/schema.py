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

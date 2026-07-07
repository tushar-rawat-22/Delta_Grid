import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from web3 import Web3


OFFCHAIN_ROOT = Path(__file__).resolve().parents[1]

if str(OFFCHAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(OFFCHAIN_ROOT))

from db.schema import (
    init_market_database,
    insert_block,
    insert_gas_snapshot,
    upsert_chain,
)


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

RPC_URL = os.getenv("RPC_URL", "https://sepolia.base.org")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "5"))
DB_PATH_RAW = os.getenv("DB_PATH", "deltagrid.db")
CHAIN_NAME = os.getenv("CHAIN_NAME", "Base Sepolia")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_db_path(db_path: str = DB_PATH_RAW) -> str:
    candidate = Path(db_path)

    if candidate.is_absolute():
        return str(candidate)

    return str(OFFCHAIN_ROOT / candidate)


DB_PATH = resolve_db_path(DB_PATH_RAW)


def init_legacy_block_logs(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS block_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp_utc TEXT NOT NULL,
        chain_id INTEGER NOT NULL,
        block_number INTEGER NOT NULL,
        gas_price_wei TEXT NOT NULL,
        rpc_url TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def insert_legacy_block_log(
    db_path: str,
    timestamp_utc: str,
    chain_id: int,
    block_number: int,
    gas_price_wei: int,
    rpc_url: str,
) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO block_logs (
        timestamp_utc,
        chain_id,
        block_number,
        gas_price_wei,
        rpc_url
    )
    VALUES (?, ?, ?, ?, ?)
    """, (
        timestamp_utc,
        chain_id,
        block_number,
        str(gas_price_wei),
        rpc_url,
    ))

    conn.commit()
    conn.close()


def normalize_block_hash(value: Any) -> str:
    if value is None:
        return ""

    if hasattr(value, "hex"):
        return value.hex()

    return str(value)


def fetch_block_hash(w3: Web3, block_number: int) -> str:
    try:
        block = w3.eth.get_block(block_number)
        return normalize_block_hash(block.get("hash"))
    except Exception:
        return ""


def persist_block_snapshot(
    db_path: str,
    chain_id: int,
    chain_name: str,
    rpc_url: str,
    block_number: int,
    gas_price_wei: int,
    block_hash: str = "",
) -> dict:
    timestamp = now_utc()

    init_market_database(db_path)

    upsert_chain(
        db_path=db_path,
        chain_id=chain_id,
        name=chain_name,
        rpc_url=rpc_url,
    )

    insert_block(
        db_path=db_path,
        chain_id=chain_id,
        block_number=block_number,
        block_hash=block_hash,
        timestamp_utc=timestamp,
    )

    insert_gas_snapshot(
        db_path=db_path,
        chain_id=chain_id,
        block_number=block_number,
        gas_price_wei=gas_price_wei,
    )

    init_legacy_block_logs(db_path)

    insert_legacy_block_log(
        db_path=db_path,
        timestamp_utc=timestamp,
        chain_id=chain_id,
        block_number=block_number,
        gas_price_wei=gas_price_wei,
        rpc_url=rpc_url,
    )

    return {
        "timestamp_utc": timestamp,
        "chain_id": chain_id,
        "chain_name": chain_name,
        "block_number": block_number,
        "gas_price_wei": gas_price_wei,
        "block_hash": block_hash,
        "db_path": db_path,
    }


def build_web3(rpc_url: str) -> Web3:
    return Web3(Web3.HTTPProvider(rpc_url))


def run_once(w3: Web3) -> dict:
    chain_id = int(w3.eth.chain_id)
    block_number = int(w3.eth.block_number)
    gas_price_wei = int(w3.eth.gas_price)
    block_hash = fetch_block_hash(w3, block_number)

    return persist_block_snapshot(
        db_path=DB_PATH,
        chain_id=chain_id,
        chain_name=CHAIN_NAME,
        rpc_url=RPC_URL,
        block_number=block_number,
        gas_price_wei=gas_price_wei,
        block_hash=block_hash,
    )


def print_snapshot(snapshot: dict) -> None:
    print(
        f"[{snapshot['timestamp_utc']}] "
        f"chain_id={snapshot['chain_id']} "
        f"block={snapshot['block_number']} "
        f"gas={snapshot['gas_price_wei']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="DeltaGrid safe chain monitor")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one safe read-only snapshot and exit",
    )

    args = parser.parse_args()

    print("DeltaGrid Chain Monitor")
    print("Mode: safe monitoring only")
    print("No private keys. No signing. No real trades.")
    print(f"RPC: {RPC_URL}")
    print(f"DB_PATH: {DB_PATH}")

    w3 = build_web3(RPC_URL)

    if not w3.is_connected():
        raise RuntimeError("Could not connect to RPC")

    print(f"Connected to chain_id={w3.eth.chain_id}")

    if args.once:
        snapshot = run_once(w3)
        print_snapshot(snapshot)
        return

    try:
        while True:
            snapshot = run_once(w3)
            print_snapshot(snapshot)
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()

import os
import time
import sqlite3
from datetime import datetime, timezone

from dotenv import load_dotenv
from web3 import Web3


load_dotenv("config/.env")

RPC_URL = os.getenv("RPC_URL", "https://sepolia.base.org")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "5"))
DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS block_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp_utc TEXT NOT NULL,
        chain_id INTEGER NOT NULL,
        block_number INTEGER NOT NULL,
        gas_price_wei TEXT,
        rpc_url TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def insert_block(chain_id, block_number, gas_price):
    conn = sqlite3.connect(DB_PATH)
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
        now_utc(),
        chain_id,
        block_number,
        str(gas_price),
        RPC_URL
    ))

    conn.commit()
    conn.close()


def main():
    print("DeltaGrid Chain Monitor")
    print("Mode: safe monitoring only")
    print("No private keys. No signing. No real trades.")
    print(f"RPC: {RPC_URL}")

    init_db()

    web3 = Web3(Web3.HTTPProvider(RPC_URL))

    if not web3.is_connected():
        raise RuntimeError("RPC connection failed")

    chain_id = web3.eth.chain_id
    print(f"Connected to chain_id={chain_id}")

    last_block = None

    while True:
        try:
            block_number = web3.eth.block_number

            if block_number != last_block:
                gas_price = web3.eth.gas_price
                insert_block(chain_id, block_number, gas_price)
                print(f"[{now_utc()}] block={block_number} gas={gas_price}")
                last_block = block_number
            else:
                print(f"[{now_utc()}] no new block")

            time.sleep(POLL_SECONDS)

        except KeyboardInterrupt:
            print("Stopped.")
            break

        except Exception as exc:
            print(f"[{now_utc()}] error={exc}")
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()

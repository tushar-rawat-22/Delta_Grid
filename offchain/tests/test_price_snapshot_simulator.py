import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from db.seed_registry import seed_registry
from simulator.price_snapshot_simulator import generate_pool_price_snapshots


class PriceSnapshotSimulatorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = str(self.root / "price_test.db")
        self.tokens_path = self.root / "seed_tokens.json"
        self.pools_path = self.root / "seed_pools.json"

        self.tokens_path.write_text(json.dumps([
            {
                "chain_id": 84532,
                "chain_name": "Base Sepolia",
                "rpc_url": "https://sepolia.base.org",
                "address": "0x4200000000000000000000000000000000000006",
                "symbol": "WETH",
                "decimals": 18
            },
            {
                "chain_id": 84532,
                "chain_name": "Base Sepolia",
                "rpc_url": "https://sepolia.base.org",
                "address": "0x0000000000000000000000000000000000000001",
                "symbol": "USDC_DEMO",
                "decimals": 6
            },
            {
                "chain_id": 84532,
                "chain_name": "Base Sepolia",
                "rpc_url": "https://sepolia.base.org",
                "address": "0x0000000000000000000000000000000000000002",
                "symbol": "DAI_DEMO",
                "decimals": 18
            }
        ]), encoding="utf-8")

        self.pools_path.write_text(json.dumps([
            {
                "chain_id": 84532,
                "chain_name": "Base Sepolia",
                "rpc_url": "https://sepolia.base.org",
                "protocol": "demo-uniswap-v3",
                "pool_address": "0x0000000000000000000000000000000000001000",
                "token0_address": "0x4200000000000000000000000000000000000006",
                "token1_address": "0x0000000000000000000000000000000000000001",
                "fee_bps": 30
            },
            {
                "chain_id": 84532,
                "chain_name": "Base Sepolia",
                "rpc_url": "https://sepolia.base.org",
                "protocol": "demo-uniswap-v3",
                "pool_address": "0x0000000000000000000000000000000000002000",
                "token0_address": "0x0000000000000000000000000000000000000001",
                "token1_address": "0x0000000000000000000000000000000000000002",
                "fee_bps": 30
            }
        ]), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_generate_pool_price_snapshots(self):
        seed_registry(
            db_path=self.db_path,
            tokens_path=self.tokens_path,
            pools_path=self.pools_path,
        )

        result = generate_pool_price_snapshots(
            db_path=self.db_path,
            block_number=12345,
        )

        self.assertEqual(result["pools_seen"], 2)
        self.assertEqual(result["snapshots_created"], 2)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        snapshot_count = cur.execute("""
        SELECT COUNT(*)
        FROM pool_price_snapshots
        """).fetchone()[0]

        prices = cur.execute("""
        SELECT price_token1_per_token0, liquidity_score, source, block_number
        FROM pool_price_snapshots
        ORDER BY id
        """).fetchall()

        conn.close()

        self.assertEqual(snapshot_count, 2)
        self.assertEqual(prices[0][0], "3000")
        self.assertEqual(prices[0][1], 90)
        self.assertEqual(prices[0][2], "local_simulator")
        self.assertEqual(prices[0][3], 12345)

        self.assertEqual(prices[1][0], "1")
        self.assertEqual(prices[1][1], 80)


if __name__ == "__main__":
    unittest.main()

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from db.seed_registry import seed_registry


class SeedRegistryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = str(self.root / "seed_test.db")
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
            }
        ]), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_seed_registry_inserts_tokens_and_pools(self):
        result = seed_registry(
            db_path=self.db_path,
            tokens_path=self.tokens_path,
            pools_path=self.pools_path,
        )

        self.assertEqual(result["tokens"], 2)
        self.assertEqual(result["pools"], 1)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        chain_count = cur.execute("SELECT COUNT(*) FROM chains").fetchone()[0]
        token_count = cur.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]
        pool_count = cur.execute("SELECT COUNT(*) FROM pools").fetchone()[0]

        symbols = {
            row[0]
            for row in cur.execute("SELECT symbol FROM tokens").fetchall()
        }

        conn.close()

        self.assertEqual(chain_count, 1)
        self.assertEqual(token_count, 2)
        self.assertEqual(pool_count, 1)
        self.assertIn("WETH", symbols)
        self.assertIn("USDC_DEMO", symbols)

    def test_seed_registry_is_idempotent(self):
        seed_registry(
            db_path=self.db_path,
            tokens_path=self.tokens_path,
            pools_path=self.pools_path,
        )

        seed_registry(
            db_path=self.db_path,
            tokens_path=self.tokens_path,
            pools_path=self.pools_path,
        )

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        token_count = cur.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]
        pool_count = cur.execute("SELECT COUNT(*) FROM pools").fetchone()[0]

        conn.close()

        self.assertEqual(token_count, 2)
        self.assertEqual(pool_count, 1)


if __name__ == "__main__":
    unittest.main()

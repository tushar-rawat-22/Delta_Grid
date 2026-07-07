import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from db.seed_registry import seed_registry
from simulator.price_snapshot_simulator import generate_pool_price_snapshots
from simulator.route_builder import generate_route_candidates


class RouteBuilderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = str(self.root / "route_test.db")
        self.tokens_path = self.root / "seed_tokens.json"
        self.pools_path = self.root / "seed_pools.json"

        self.weth = "0x4200000000000000000000000000000000000006"
        self.usdc = "0x0000000000000000000000000000000000000001"
        self.dai = "0x0000000000000000000000000000000000000002"

        self.tokens_path.write_text(json.dumps([
            {
                "chain_id": 84532,
                "chain_name": "Base Sepolia",
                "rpc_url": "https://sepolia.base.org",
                "address": self.weth,
                "symbol": "WETH",
                "decimals": 18
            },
            {
                "chain_id": 84532,
                "chain_name": "Base Sepolia",
                "rpc_url": "https://sepolia.base.org",
                "address": self.usdc,
                "symbol": "USDC_DEMO",
                "decimals": 6
            },
            {
                "chain_id": 84532,
                "chain_name": "Base Sepolia",
                "rpc_url": "https://sepolia.base.org",
                "address": self.dai,
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
                "token0_address": self.weth,
                "token1_address": self.usdc,
                "fee_bps": 30
            },
            {
                "chain_id": 84532,
                "chain_name": "Base Sepolia",
                "rpc_url": "https://sepolia.base.org",
                "protocol": "demo-uniswap-v3",
                "pool_address": "0x0000000000000000000000000000000000002000",
                "token0_address": self.usdc,
                "token1_address": self.dai,
                "fee_bps": 30
            }
        ]), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_generate_route_candidates(self):
        seed_registry(
            db_path=self.db_path,
            tokens_path=self.tokens_path,
            pools_path=self.pools_path,
        )

        generate_pool_price_snapshots(
            db_path=self.db_path,
            block_number=12345,
        )

        result = generate_route_candidates(db_path=self.db_path)

        self.assertEqual(result["snapshots_seen"], 2)
        self.assertEqual(result["routes_created"], 2)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        rows = cur.execute("""
        SELECT
            start_token_address,
            end_token_address,
            hops,
            estimated_output_per_input,
            min_liquidity_score,
            source,
            block_number
        FROM route_candidates
        ORDER BY id
        """).fetchall()

        conn.close()

        self.assertEqual(len(rows), 2)

        route_pairs = {
            (row[0], row[1]): row
            for row in rows
        }

        weth_to_dai = route_pairs[(self.weth.lower(), self.dai.lower())]
        dai_to_weth = route_pairs[(self.dai.lower(), self.weth.lower())]

        self.assertEqual(weth_to_dai[2], 2)
        self.assertEqual(weth_to_dai[3], "3000")
        self.assertEqual(weth_to_dai[4], 80)
        self.assertEqual(weth_to_dai[5], "local_route_builder")
        self.assertEqual(weth_to_dai[6], 12345)

        self.assertEqual(dai_to_weth[2], 2)
        self.assertEqual(dai_to_weth[4], 80)

    def test_no_routes_without_price_snapshots(self):
        seed_registry(
            db_path=self.db_path,
            tokens_path=self.tokens_path,
            pools_path=self.pools_path,
        )

        result = generate_route_candidates(db_path=self.db_path)

        self.assertEqual(result["snapshots_seen"], 0)
        self.assertEqual(result["routes_created"], 0)


if __name__ == "__main__":
    unittest.main()

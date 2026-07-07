import json
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from db.seed_registry import seed_registry
from detector.opportunity_detector import detect_opportunities
from simulator.closed_loop_route_builder import create_closed_loop_route_candidates
from simulator.price_snapshot_simulator import generate_pool_price_snapshots


class ClosedLoopRouteBuilderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = str(self.root / "closed_loop_test.db")

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

    def tearDown(self):
        self.tmp.cleanup()

    def write_pools(self, include_third_pool: bool) -> None:
        pools = [
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
        ]

        if include_third_pool:
            pools.append({
                "chain_id": 84532,
                "chain_name": "Base Sepolia",
                "rpc_url": "https://sepolia.base.org",
                "protocol": "demo-uniswap-v3",
                "pool_address": "0x0000000000000000000000000000000000003000",
                "token0_address": self.dai,
                "token1_address": self.weth,
                "fee_bps": 30
            })

        self.pools_path.write_text(json.dumps(pools), encoding="utf-8")

    def seed_and_snapshot(self, include_third_pool: bool) -> None:
        self.write_pools(include_third_pool=include_third_pool)

        seed_registry(
            db_path=self.db_path,
            tokens_path=self.tokens_path,
            pools_path=self.pools_path,
        )

        generate_pool_price_snapshots(
            db_path=self.db_path,
            block_number=12345,
        )

    def test_closed_loop_routes_created_with_three_pools(self):
        self.seed_and_snapshot(include_third_pool=True)

        result = create_closed_loop_route_candidates(
            db_path=self.db_path,
            start_token_address=self.weth,
        )

        self.assertEqual(result["snapshots_seen"], 3)
        self.assertEqual(result["closed_loop_routes_created"], 2)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        rows = cur.execute("""
        SELECT
            start_token_address,
            end_token_address,
            hops,
            estimated_output_per_input,
            min_liquidity_score,
            source
        FROM route_candidates
        WHERE source = 'closed_loop_route_builder_v1'
        ORDER BY id
        """).fetchall()

        conn.close()

        self.assertEqual(len(rows), 2)

        multipliers = {
            Decimal(row[3])
            for row in rows
        }

        self.assertIn(Decimal("1.02000"), multipliers)

        for row in rows:
            self.assertEqual(row[0], self.weth.lower())
            self.assertEqual(row[1], self.weth.lower())
            self.assertEqual(row[2], 3)
            self.assertEqual(row[4], 80)
            self.assertEqual(row[5], "closed_loop_route_builder_v1")

    def test_detector_approves_only_profitable_closed_loop(self):
        self.seed_and_snapshot(include_third_pool=True)

        create_closed_loop_route_candidates(
            db_path=self.db_path,
            start_token_address=self.weth,
        )

        result = detect_opportunities(
            db_path=self.db_path,
            fee_bps=10,
            slippage_bps=10,
            gas_cost_bps=10,
            safety_buffer_bps=20,
            min_net_edge_bps=50,
            min_liquidity_score=70,
        )

        self.assertEqual(result["routes_seen"], 2)
        self.assertEqual(result["approved"], 1)
        self.assertEqual(result["rejected"], 1)

    def test_no_closed_loop_without_third_pool(self):
        self.seed_and_snapshot(include_third_pool=False)

        result = create_closed_loop_route_candidates(
            db_path=self.db_path,
            start_token_address=self.weth,
        )

        self.assertEqual(result["snapshots_seen"], 2)
        self.assertEqual(result["closed_loop_routes_created"], 0)


if __name__ == "__main__":
    unittest.main()

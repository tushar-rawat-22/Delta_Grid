import sqlite3
import tempfile
import unittest
from pathlib import Path

from db.schema import (
    init_market_database,
    insert_block,
    insert_gas_snapshot,
    insert_risk_decision,
    insert_simulated_opportunity,
    upsert_chain,
    upsert_pool,
    upsert_token,
)


class MarketSchemaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "test_deltagrid.db")
        self.chain_id = 84532

    def tearDown(self):
        self.tmp.cleanup()

    def test_schema_initializes_required_tables(self):
        init_market_database(self.db_path)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        tables = {
            row[0]
            for row in cur.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            """).fetchall()
        }

        conn.close()

        self.assertIn("chains", tables)
        self.assertIn("blocks", tables)
        self.assertIn("gas_snapshots", tables)
        self.assertIn("tokens", tables)
        self.assertIn("pools", tables)
        self.assertIn("simulated_opportunities", tables)
        self.assertIn("risk_decisions", tables)
        self.assertIn("schema_migrations", tables)

    def test_insert_market_data_and_risk_decision(self):
        init_market_database(self.db_path)

        upsert_chain(
            db_path=self.db_path,
            chain_id=self.chain_id,
            name="Base Sepolia",
            rpc_url="https://sepolia.base.org",
        )

        insert_block(
            db_path=self.db_path,
            chain_id=self.chain_id,
            block_number=43829863,
            block_hash="demo-block-hash",
        )

        insert_gas_snapshot(
            db_path=self.db_path,
            chain_id=self.chain_id,
            block_number=43829863,
            gas_price_wei=6_000_000,
        )

        weth = "0x4200000000000000000000000000000000000006"
        usdc = "0x0000000000000000000000000000000000000001"

        upsert_token(self.db_path, self.chain_id, weth, "WETH", 18)
        upsert_token(self.db_path, self.chain_id, usdc, "USDC", 6)

        upsert_pool(
            db_path=self.db_path,
            chain_id=self.chain_id,
            protocol="demo-uniswap-v3",
            pool_address="0x0000000000000000000000000000000000001000",
            token0_address=weth,
            token1_address=usdc,
            fee_bps=30,
        )

        opportunity_id = insert_simulated_opportunity(
            db_path=self.db_path,
            chain_id=self.chain_id,
            block_number=43829863,
            opportunity_type="demo_arbitrage",
            route=[{"step": 1, "token_in": "WETH", "token_out": "USDC"}],
            gross_profit_wei=5_000_000_000_000_000,
            gas_cost_wei=1_000_000_000_000_000,
            flash_fee_wei=500_000_000_000_000,
            slippage_cost_wei=500_000_000_000_000,
        )

        decision_id = insert_risk_decision(
            db_path=self.db_path,
            opportunity_id=opportunity_id,
            risk_score=100,
            approved=True,
            reasons=[],
        )

        self.assertGreater(opportunity_id, 0)
        self.assertGreater(decision_id, 0)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        opportunity_count = cur.execute("""
        SELECT COUNT(*)
        FROM simulated_opportunities
        """).fetchone()[0]

        decision_count = cur.execute("""
        SELECT COUNT(*)
        FROM risk_decisions
        """).fetchone()[0]

        approved = cur.execute("""
        SELECT approved
        FROM risk_decisions
        WHERE id = ?
        """, (decision_id,)).fetchone()[0]

        conn.close()

        self.assertEqual(opportunity_count, 1)
        self.assertEqual(decision_count, 1)
        self.assertEqual(approved, 1)


if __name__ == "__main__":
    unittest.main()

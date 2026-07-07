import sqlite3
import tempfile
import unittest
from pathlib import Path

from indexer.chain_monitor import persist_block_snapshot


class ChainMonitorSchemaIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "monitor_test.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_monitor_snapshot_writes_legacy_and_market_tables(self):
        persist_block_snapshot(
            db_path=self.db_path,
            chain_id=84532,
            chain_name="Base Sepolia",
            rpc_url="mock://base-sepolia",
            block_number=100,
            gas_price_wei=6_000_000,
            block_hash="0xabc",
        )

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        chain_count = cur.execute("SELECT COUNT(*) FROM chains").fetchone()[0]
        block_count = cur.execute("SELECT COUNT(*) FROM blocks").fetchone()[0]
        gas_count = cur.execute("SELECT COUNT(*) FROM gas_snapshots").fetchone()[0]
        legacy_count = cur.execute("SELECT COUNT(*) FROM block_logs").fetchone()[0]

        chain_name = cur.execute(
            "SELECT name FROM chains WHERE chain_id = 84532"
        ).fetchone()[0]

        conn.close()

        self.assertEqual(chain_count, 1)
        self.assertEqual(block_count, 1)
        self.assertEqual(gas_count, 1)
        self.assertEqual(legacy_count, 1)
        self.assertEqual(chain_name, "Base Sepolia")

    def test_duplicate_block_is_not_duplicated_but_gas_snapshot_is_logged(self):
        for _ in range(2):
            persist_block_snapshot(
                db_path=self.db_path,
                chain_id=84532,
                chain_name="Base Sepolia",
                rpc_url="mock://base-sepolia",
                block_number=100,
                gas_price_wei=6_000_000,
                block_hash="0xabc",
            )

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        block_count = cur.execute("SELECT COUNT(*) FROM blocks").fetchone()[0]
        gas_count = cur.execute("SELECT COUNT(*) FROM gas_snapshots").fetchone()[0]
        legacy_count = cur.execute("SELECT COUNT(*) FROM block_logs").fetchone()[0]

        conn.close()

        self.assertEqual(block_count, 1)
        self.assertEqual(gas_count, 2)
        self.assertEqual(legacy_count, 2)


if __name__ == "__main__":
    unittest.main()

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from db.schema import init_market_database, upsert_chain
from detector.opportunity_detector import (
    detect_opportunities,
    evaluate_route_candidate,
)


class OpportunityDetectorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "opportunity_test.db")

        init_market_database(self.db_path)

        upsert_chain(
            db_path=self.db_path,
            chain_id=84532,
            name="Base Sepolia",
            rpc_url="https://sepolia.base.org",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def insert_route(
        self,
        start_token: str,
        end_token: str,
        multiplier: str,
        liquidity_score: int = 90,
    ) -> int:
        conn = sqlite3.connect(self.db_path)
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
            84532,
            start_token.lower(),
            end_token.lower(),
            2,
            json.dumps([
                {
                    "step": 1,
                    "token_in": start_token.lower(),
                    "token_out": end_token.lower(),
                }
            ]),
            multiplier,
            liquidity_score,
            "test_route_builder",
            12345,
            "2026-07-07T00:00:00+00:00",
        ))

        route_id = cur.lastrowid

        conn.commit()
        conn.close()

        return int(route_id)

    def test_closed_loop_route_can_be_approved(self):
        token = "0x0000000000000000000000000000000000000001"

        route = {
            "id": 1,
            "chain_id": 84532,
            "start_token_address": token,
            "end_token_address": token,
            "estimated_output_per_input": "1.02",
            "min_liquidity_score": 90,
            "block_number": 12345,
        }

        result = evaluate_route_candidate(
            route=route,
            fee_bps=10,
            slippage_bps=10,
            gas_cost_bps=10,
            safety_buffer_bps=20,
            min_net_edge_bps=50,
            min_liquidity_score=70,
        )

        self.assertEqual(result["status"], "APPROVED")
        self.assertEqual(result["opportunity_type"], "closed_loop_arbitrage")
        self.assertEqual(result["gross_edge_bps"], "200.00")
        self.assertEqual(result["total_cost_bps"], "50")
        self.assertEqual(result["net_edge_bps"], "150.00")
        self.assertGreater(result["risk_score"], 0)
        self.assertEqual(result["rejection_reasons"], [])

    def test_non_closed_loop_route_is_rejected(self):
        token_a = "0x0000000000000000000000000000000000000001"
        token_b = "0x0000000000000000000000000000000000000002"

        route = {
            "id": 1,
            "chain_id": 84532,
            "start_token_address": token_a,
            "end_token_address": token_b,
            "estimated_output_per_input": "3000",
            "min_liquidity_score": 90,
            "block_number": 12345,
        }

        result = evaluate_route_candidate(
            route=route,
            fee_bps=10,
            slippage_bps=10,
            gas_cost_bps=10,
            safety_buffer_bps=20,
            min_net_edge_bps=50,
            min_liquidity_score=70,
        )

        self.assertEqual(result["status"], "REJECTED")
        self.assertEqual(result["opportunity_type"], "conversion_route_not_profit_valid")
        self.assertEqual(result["risk_score"], 0)
        self.assertIn("not_closed_loop_route", result["rejection_reasons"])

    def test_detect_opportunities_approves_and_rejects_correctly(self):
        token_a = "0x0000000000000000000000000000000000000001"
        token_b = "0x0000000000000000000000000000000000000002"

        self.insert_route(
            start_token=token_a,
            end_token=token_a,
            multiplier="1.02",
            liquidity_score=90,
        )

        self.insert_route(
            start_token=token_a,
            end_token=token_b,
            multiplier="3000",
            liquidity_score=90,
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
        self.assertEqual(result["detections_created"], 2)
        self.assertEqual(result["approved"], 1)
        self.assertEqual(result["rejected"], 1)
        self.assertEqual(result["global_verdict"], "RESEARCH_ONLY_NO_LIVE_TRADING")

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        rows = cur.execute("""
        SELECT
            opportunity_type,
            status,
            rejection_reasons_json
        FROM opportunity_detections
        ORDER BY id
        """).fetchall()

        conn.close()

        self.assertEqual(rows[0][0], "closed_loop_arbitrage")
        self.assertEqual(rows[0][1], "APPROVED")
        self.assertEqual(json.loads(rows[0][2]), [])

        self.assertEqual(rows[1][0], "conversion_route_not_profit_valid")
        self.assertEqual(rows[1][1], "REJECTED")
        self.assertIn("not_closed_loop_route", json.loads(rows[1][2]))


if __name__ == "__main__":
    unittest.main()

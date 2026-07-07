import os
import sys
from pathlib import Path

from dotenv import load_dotenv

OFFCHAIN_ROOT = Path(__file__).resolve().parents[1]
if str(OFFCHAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(OFFCHAIN_ROOT))

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


load_dotenv("config/.env")

DB_PATH = os.getenv("DB_PATH", "deltagrid.db")
CHAIN_ID = 84532


def main() -> None:
    print("DeltaGrid Opportunity Store Demo")
    print("Mode: local database only")
    print("No private keys. No signing. No real trades.")
    print(f"DB_PATH: {DB_PATH}")

    init_market_database(DB_PATH)

    upsert_chain(
        db_path=DB_PATH,
        chain_id=CHAIN_ID,
        name="Base Sepolia",
        rpc_url="https://sepolia.base.org",
    )

    insert_block(
        db_path=DB_PATH,
        chain_id=CHAIN_ID,
        block_number=43829863,
        block_hash="demo-block-hash",
    )

    insert_gas_snapshot(
        db_path=DB_PATH,
        chain_id=CHAIN_ID,
        block_number=43829863,
        gas_price_wei=6_000_000,
    )

    weth = "0x4200000000000000000000000000000000000006"
    usdc = "0x0000000000000000000000000000000000000001"

    upsert_token(DB_PATH, CHAIN_ID, weth, "WETH", 18)
    upsert_token(DB_PATH, CHAIN_ID, usdc, "USDC", 6)

    upsert_pool(
        db_path=DB_PATH,
        chain_id=CHAIN_ID,
        protocol="demo-uniswap-v3",
        pool_address="0x0000000000000000000000000000000000001000",
        token0_address=weth,
        token1_address=usdc,
        fee_bps=30,
    )

    opportunity_id = insert_simulated_opportunity(
        db_path=DB_PATH,
        chain_id=CHAIN_ID,
        block_number=43829863,
        opportunity_type="demo_arbitrage",
        route=[
            {
                "step": 1,
                "protocol": "demo-uniswap-v3",
                "token_in": "WETH",
                "token_out": "USDC",
            },
            {
                "step": 2,
                "protocol": "demo-uniswap-v3",
                "token_in": "USDC",
                "token_out": "WETH",
            },
        ],
        gross_profit_wei=5_000_000_000_000_000,
        gas_cost_wei=1_000_000_000_000_000,
        flash_fee_wei=500_000_000_000_000,
        slippage_cost_wei=500_000_000_000_000,
    )

    decision_id = insert_risk_decision(
        db_path=DB_PATH,
        opportunity_id=opportunity_id,
        risk_score=100,
        approved=True,
        reasons=[],
    )

    print(f"Inserted opportunity_id={opportunity_id}")
    print(f"Inserted decision_id={decision_id}")
    print("Opportunity store demo complete.")


if __name__ == "__main__":
    main()

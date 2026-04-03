import os

from dotenv import load_dotenv
from loguru import logger

# Load .env explicitly for tests
load_dotenv()

def verify_system():
    logger.info("Verifying system configurations...")

    # Check DB
    try:
        from core.database import create_db_and_tables, get_session
        create_db_and_tables()
        with get_session():
            pass
        logger.success("Database Connection: OK")
    except Exception as e:
        logger.error(f"Database Initialization Failed: {e}")

    # Check Gamma API
    try:
        from core.data import MarketData
        md = MarketData()
        markets = md.get_markets(limit=1)
        if markets:
            logger.success("Gamma API Connection: OK")
        else:
            logger.error("Gamma API Connection: FAILED")
    except Exception as e:
        logger.error(f"Gamma API Connection Failed: {e}")

    # Check Falcon API
    try:
        api_key = os.getenv("FALCON_API_KEY")
        if api_key:
            res = md.get_falcon_trade_history("0x56687bf447db6ffa42ffe2204a05edaa20f55839", window_days=1)
            if res is not None:
                logger.success("Falcon Analytics API: OK")
            else:
                logger.error("Falcon Analytics API: KEY INVALID OR LIMIT EXCEEDED")
        else:
            logger.warning("Falcon Analytics API: MISSING FALCON_API_KEY in .env")
    except Exception as e:
        logger.error(f"Falcon API Verification Failed: {e}")

    # Check Web3
    try:
        rpc = os.getenv("POLYGON_RPC_URL")
        if rpc:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(rpc))
            if w3.is_connected():
                logger.success("Web3/Polygon RPC: OK")
            else:
                logger.error("Web3/Polygon RPC: CONNECTION REJECTED")
        else:
            logger.warning("Web3/Polygon RPC: MISSING POLYGON_RPC_URL in .env")
    except Exception as e:
        logger.error(f"Web3 Verification Failed: {e}")

if __name__ == "__main__":
    verify_system()

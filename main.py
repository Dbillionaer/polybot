import sys
import os
from dotenv import load_dotenv
from loguru import logger
from core.auth import initialize_clob_client
from core.client import PolyClient
from core.database import create_db_and_tables
from core.ws import PolyWebSocket
from engine.risk import RiskManager
from engine.execution import ExecutionEngine
import time


load_dotenv()

def main():
    logger.info("Starting PolyBot 2026 Core Loop...")
    
    # 1. Initialize Database
    create_db_and_tables()
    
    # 2. Initialize Polymarket Client
    try:
        clob_client = initialize_clob_client()
        poly_client = PolyClient(clob_client)
    except Exception as e:
        logger.critical(f"Failed to initialize CLOB client: {e}")
        sys.exit(1)
        
    # 3. Initialize Risk & Execution
    risk_manager = RiskManager(
        max_pos_size_pct=float(os.getenv("MAX_POSITION_SIZE_PCT", 0.05)),
        daily_loss_limit_pct=float(os.getenv("DAILY_LOSS_LIMIT_PCT", 0.05))
    )
    _execution_engine = ExecutionEngine(poly_client, risk_manager)

    
    # 4. Initialize WebSocket
    ws = PolyWebSocket()
    ws.start()
    
    # 5. Load Strategies
    strategies = []
    
    # Example: Start AMM on a specific token
    from strategies.amm import AMMStrategy
    amm = AMMStrategy(_execution_engine, ws, token_id="0x1234...")
    strategies.append(amm)

    # Example: Start AI Arb on a market
    # from strategies.ai_arb import AIArbStrategy
    # ai_arb = AIArbStrategy(
    #     _execution_engine, ws,
    #     "Will BTC reach $100k by tomorrow?", "0xABCD..."
    # )
    # strategies.append(ai_arb)

    for strategy in strategies:
        strategy.run()
        
    logger.success("All systems operational. Bot is running.")
    
    # 6. Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutdown signal received.")
        ws.stop()

if __name__ == "__main__":
    main()

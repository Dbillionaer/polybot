"""Smart Copy-Trading Strategy."""

from loguru import logger
import threading
import time
from strategies.base import BaseStrategy

class CopyTradingStrategy(BaseStrategy):
    """
    Monitors a specific highly profitable wallet via Gamma/Web3
    and mimics their trades proportionally.
    """
    def __init__(self, engine, ws, target_wallet: str, size_multiplier: float = 0.1):
        super().__init__(engine, ws, "CopyTrading")
        self.target_wallet = target_wallet
        self.size_multiplier = size_multiplier

    def on_market_update(self, data: dict):
        pass

    def on_trade_update(self, data: dict):
        # We could potentially listen to trades WS for maker_address, but generally 
        # on-chain monitoring is better for copy trading as maker won't always trigger.
        pass

    def run(self):
        logger.info(f"Starting Copy-Trading monitoring wallet: {self.target_wallet}...")
        
        def _loop():
            while True:
                # 1. Fetch target wallet's latest trades via Gamma API / Etherscan
                # 2. Check if we already mimicked this trade locally
                # 3. Calculate proportional size: their_size * self.size_multiplier
                # 4. Execute limit order to match
                # self.engine.execute_limit_order(...)
                time.sleep(60) # Poll every 60 seconds

        threading.Thread(target=_loop, daemon=True).start()

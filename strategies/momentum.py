import time
from collections import deque

from loguru import logger

from engine.execution import ExecutionEngine
from core.ws import PolyWebSocket
from strategies.base import BaseStrategy


class MomentumStrategy(BaseStrategy):
    """
    High-Frequency Momentum + Behavioral Strategy.
    Detects volume surges or orderbook imbalances for quick scalp trades.
    """
    def __init__(
        self,
        engine: ExecutionEngine,
        ws: PolyWebSocket,
        token_id: str
    ):
        super().__init__(engine, ws, "HFM")

        self.token_id = token_id
        self.volume_history = deque(maxlen=60) # Last 60 updates
        self.price_history = deque(maxlen=60)
        self.trade_window_sec = 60 # 1 min tracking

    def on_market_update(self, data: dict):
        if data.get("event_type") == "book":
            # Book imbalance detection
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            
            # Simple volume/bid-ask depth ratio
            bid_depth = sum(float(b[1]) for b in bids[:5])
            ask_depth = sum(float(a[1]) for a in asks[:5])
            
            if ask_depth > 0 and bid_depth / ask_depth > 5:
                # Heavy buy pressure relative to sell
                logger.warning(
                    f"BUY IMBALANCE detected on {self.token_id}: "
                    f"Ratio {bid_depth/ask_depth:.2f}"
                )
                # self.engine.execute(...)


    def on_trade_update(self, data: dict):
        if data.get("event_type") == "trade":
            # Tracking volume surge logic
            size = float(data.get("size", 0))
            self.volume_history.append((time.time(), size))
            
            # Check for sudden 300% average volume burst
            # ...
            pass

    def run(self):
        logger.info(f"Starting Momentum HFM on {self.token_id}...")
        self.ws.subscribe(self.token_id, "book")
        self.ws.subscribe(self.token_id, "trades")

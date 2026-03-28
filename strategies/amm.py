"""Automated Market Making strategy implementation."""

from loguru import logger

from core.ws import PolyWebSocket
from engine.execution import ExecutionEngine
from strategies.base import BaseStrategy


class AMMStrategy(BaseStrategy):

    """
    Automated Market Making Strategy.
    Places buy/sell limit orders around the mid-price to capture spread.
    """
    def __init__(
        self,
        engine: ExecutionEngine,
        ws: PolyWebSocket,
        token_id: str,
        spread: float = 0.02,
        size: int = 100
    ):
        super().__init__(engine, ws, "AMM")
        self.token_id = token_id

        self.spread = spread
        self.size = size
        self.last_mid_price: float = 0.0
        self.inventory: float = 0.0  # Track net shares
        self.max_inventory: float = 1000.0


    def on_market_update(self, data: dict):
        if data.get("event_type") == "book":
            # Extract bid/ask from orderbook update
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            
            if bids and asks:
                best_bid = float(bids[0][0])
                best_ask = float(asks[0][0])
                mid_price = (best_bid + best_ask) / 2
                self.last_mid_price = mid_price
                
                # Logic: Maintain orders at mid_price +/- (spread/2)
                # This would typically involve cancelling old 
                # and placing new or using 'replace' if supported.


    def on_trade_update(self, data: dict):
        is_trade = data.get("event_type") == "trade"
        is_maker = data.get("maker_address") == self.engine.client.address
        if is_trade and is_maker:
            # We were filled! Update inventory
            side = data.get("side")

            size_str = data.get("size")
            if size_str:
                size = float(size_str)
                if side == "BUY":
                    self.inventory += size
                else:
                    self.inventory -= size
                logger.info(
                    f"AMM Filled: {side} {size}. "
                    f"Current Inventory: {self.inventory}"
                )

    def run(self):

        logger.info(f"Starting AMM on {self.token_id}...")
        self.ws.subscribe(self.token_id, "book")
        self.ws.subscribe(self.token_id, "trades")
        # In actual implementation, we might poll at intervals to manage orders

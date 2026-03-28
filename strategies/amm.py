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
                
                # Volatility widening logic
                spread = best_ask - best_bid
                if hasattr(self, 'volatility_multiplier'):
                    pass
                else:
                    self.volatility_multiplier = 1.0

                if spread > 0.03:
                    self.volatility_multiplier = 1.5
                else:
                    self.volatility_multiplier = 1.0
                    
                actual_spread = self.spread * self.volatility_multiplier
                
                # Rebalancing / Inventory dampening
                bid_adj = 0.0
                ask_adj = 0.0
                if self.inventory > self.max_inventory * 0.5: # Too long
                    bid_adj -= 0.01  
                    ask_adj -= 0.01
                elif self.inventory < -self.max_inventory * 0.5: # Too short
                    bid_adj += 0.01  
                    ask_adj += 0.01
                    
                target_bid = mid_price - (actual_spread / 2) + bid_adj
                target_ask = mid_price + (actual_spread / 2) + ask_adj
                
                logger.debug(
                    f"[{self.name}] Target Quotes: BID {target_bid:.3f} | "
                    f"ASK {target_ask:.3f} (Inv: {self.inventory})"
                )

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

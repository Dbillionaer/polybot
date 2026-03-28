from typing import List, Dict

from loguru import logger

from engine.execution import ExecutionEngine
from core.ws import PolyWebSocket
from strategies.base import BaseStrategy

class LogicalArbStrategy(BaseStrategy):
    """
    Logical Arbitrage Strategy.
    Detects impossible pricing (e.g., sum of outcome probabilities > 105%)
    across related markets.
    """
    def __init__(
        self,
        engine: ExecutionEngine,
        ws: PolyWebSocket,
        markets: List[Dict]
    ):
        super().__init__(engine, ws, "Logical-Arb")

        # markets: list of token_ids or pairs to monitor
        self.markets = markets 
        self.prices: Dict[str, float] = {}

    def on_market_update(self, data: dict):
        if data.get("event_type") == "price":
            token_id = data.get("market")
            price_str = data.get("price")
            if token_id is not None and price_str is not None:
                self.prices[str(token_id)] = float(price_str)

                # Re-check sum across related tokens
                self.check_sum_violations()


    def check_sum_violations(self):
        # Example: if tokens are mutually exclusive (e.g., A wins, B wins, C wins)
        total_prob = sum(self.prices.values())
        if total_prob > 1.05 and len(self.prices) == len(self.markets):
            # Opportunity! Short the outcomes (sell YES or buy NO)
            logger.warning(
                f"Logical ARB detected: Total sum {total_prob:.2f} "
                f"across {len(self.markets)} markets."
            )
            # self.execute_arb(...)

    def on_trade_update(self, _data: dict):

        pass

    def run(self):
        logger.info(f"Starting Arb on {len(self.markets)} markets...")
        for m in self.markets:
            token_id = m.get("token_id")
            if token_id:
                # Use price channel if available
                self.ws.subscribe(str(token_id), "price")

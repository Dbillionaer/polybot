from strategies.base import BaseStrategy
from loguru import logger
from engine.execution import ExecutionEngine
from core.ws import PolyWebSocket
from openai import OpenAI
import os
import json

class AIArbStrategy(BaseStrategy):
    """
    AI-Powered Probability Arbitrage.
    Uses Grok (xAI) to quantify real-world edge against market price.
    """
    def __init__(
        self,
        engine: ExecutionEngine,
        ws: PolyWebSocket,
        market_name: str,
        token_id: str
    ):
        super().__init__(engine, ws, "AI-Arb")

        self.market_name = market_name
        self.token_id = token_id
        self.client = OpenAI(
            api_key=os.getenv("XAI_API_KEY"),
            base_url="https://api.x.ai/v1"
        )
        self.edge_threshold = 0.12 # 12% edge required

    def get_ai_probability(self):
        """
        Ask Grok for the true probability of the event.
        """
        prompt = (
            f"Given recent news and historical trends, what is the "
            f"estimated percentage probability for the outcome: "
            f"{self.market_name}? Provide a structured JSON response "
            f"with 'probability' (0.0 to 1.0) and 'reasoning'."
        )

        try:
            completion = self.client.chat.completions.create(
                model="grok-3",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a world-class political and "
                                   "sports analyst specializing in prediction "
                                   "markets. You provide precise, neutral "
                                   "probabilities."
                    },
                    {"role": "user", "content": prompt}
                ],

                response_format={"type": "json_object"}
            )
            data = json.loads(completion.choices[0].message.content)
            return data.get("probability", 0.5), data.get("reasoning", "")
        except Exception as e:
            logger.error(f"Error querying Grok: {e}")
            return None, ""

    def evaluate_edge(self, current_price: float):
        """
        Compares AI probability with market price to find edge.
        """
        true_prob, reasoning = self.get_ai_probability()
        if true_prob is None:
            return
            
        edge = true_prob - current_price
        logger.info(
            f"AI Eval for {self.market_name}: True Prob {true_prob:.2f} "
            f"vs Price {current_price:.2f} (Edge: {edge:.2%})"
        )

        
        if edge >= self.edge_threshold:
            # Use Kelly Criterion for sizing
            bankroll = 1000 # Example current USDC balance
            size = self.engine.risk_manager.calculate_kelly_size(current_price, true_prob, bankroll)
            if size > 0:
                logger.success(
                    f"BULLISH EDGE: {edge:.2%}. Placing BUY order."
                )
                self.engine.execute_limit_order(
                    self.token_id, current_price + 0.01,
                    int(size), "BUY", self.name
                )

        elif edge <= -self.edge_threshold:
            # Bearish edge logic (consider selling or ignoring if no position)
            logger.warning(
                f"BEARISH EDGE: {edge:.2%}. Consider SELL logic."
            )

    def on_market_update(self, _data: dict):
        pass

    def on_trade_update(self, _data: dict):
        pass

    def run(self):
        import time
        import threading
        logger.info(f"Starting AI Arb strategy on {self.market_name}...")
        
        def _loop():
            # Periodically re-evaluate every 30 mins
            while True:
                # Default to 0.50 if can't load current price via engine
                price = 0.50 
                self.evaluate_edge(price)
                time.sleep(1800)

        threading.Thread(target=_loop, daemon=True).start()

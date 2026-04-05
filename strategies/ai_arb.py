"""AI-powered probability arbitrage using Grok (xAI API)."""

import json
import os
import threading
import time

from loguru import logger
from openai import OpenAI

from core.ws import PolyWebSocket
from engine.execution import ExecutionEngine
from strategies.base import BaseStrategy


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
        token_id: str,
        edge_threshold: float = 0.12,
        poll_interval_sec: int = 1800,
    ):
        super().__init__(engine, ws, "AI-Arb", token_ids=token_id)
        self.token_id = token_id
        self.market_name = market_name
        self.edge_threshold = edge_threshold
        self.poll_interval_sec = poll_interval_sec

        # Live price updated by WS callback
        self._current_price: float = 0.5

        self._ai_client = OpenAI(
            api_key=os.getenv("XAI_API_KEY"),
            base_url="https://api.x.ai/v1",
        )

    # ------------------------------------------------------------------
    # WS callbacks
    # ------------------------------------------------------------------

    def on_market_update(self, data: dict):
        if data.get("event_type") != "book":
            return
        market_id = data.get("market") or self.token_id
        if market_id != self.token_id:
            return
        bids = data.get("bids", [])
        asks = data.get("asks", [])
        if bids and asks:
            self._current_price = (float(bids[0][0]) + float(asks[0][0])) / 2

    def on_trade_update(self, data: dict):
        del data
        pass

    # ------------------------------------------------------------------
    # AI probability query
    # ------------------------------------------------------------------

    def get_ai_probability(self):
        prompt = (
            f"Given recent news and historical trends, what is the "
            f"estimated percentage probability for the outcome: "
            f"{self.market_name}? Provide a structured JSON response "
            f"with 'probability' (0.0 to 1.0) and 'reasoning'."
        )
        try:
            completion = self._ai_client.chat.completions.create(
                model="grok-3",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a world-class political and sports analyst "
                            "specialising in prediction markets. Provide precise, "
                            "neutral probabilities."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
            content = completion.choices[0].message.content
            if not isinstance(content, (str, bytes, bytearray)):
                logger.error("[AI-Arb] Grok returned no JSON content.")
                return None, ""
            data = json.loads(content)
            return data.get("probability", 0.5), data.get("reasoning", "")
        except Exception as e:
            logger.error(f"[AI-Arb] Error querying Grok: {e}")
            return None, ""

    # ------------------------------------------------------------------
    # Edge evaluation
    # ------------------------------------------------------------------

    def evaluate_edge(self):
        current_price = self._current_price
        if current_price <= 0:
            logger.warning("[AI-Arb] No live price yet, skipping cycle.")
            return

        true_prob, reasoning = self.get_ai_probability()
        if true_prob is None:
            return

        edge = true_prob - current_price
        logger.info(
            f"[AI-Arb] {self.market_name}: AI={true_prob:.3f} | "
            f"Mkt={current_price:.3f} | Edge={edge:.2%}"
        )

        bankroll = float(os.getenv("BANKROLL_USDC", "1000"))

        if edge >= self.edge_threshold:
            size = self.engine.risk_manager.calculate_kelly_size(
                current_price, true_prob, bankroll
            )
            if size > 0:
                logger.success(
                    f"[AI-Arb] BULLISH EDGE {edge:.2%}. "
                    f"Placing BUY {int(size)} @ {current_price + 0.01:.3f}"
                )
                if self.engine.risk_manager.check_trade_allowed(
                    self.name, current_price + 0.01, int(size), "BUY"
                ):
                    self.engine.execute_limit_order(
                        self.token_id, current_price + 0.01,
                        int(size), "BUY", self.name,
                        dry_run=self.engine.dry_run
                    )

        elif edge <= -self.edge_threshold:
            logger.warning(
                f"[AI-Arb] BEARISH EDGE {edge:.2%}. "
                f"Market overpriced — consider shorting or skipping."
            )
            # Optionally place a SELL here if you hold YES shares

    # ------------------------------------------------------------------

    def run(self):
        logger.info(f"[AI-Arb] Starting on '{self.market_name}' (poll={self.poll_interval_sec}s)…")
        self.subscribe_all()

        def _loop():
            while True:
                self.evaluate_edge()
                time.sleep(self.poll_interval_sec)

        threading.Thread(target=_loop, daemon=True, name="AI-Arb-loop").start()

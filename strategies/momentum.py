"""Momentum / High-Frequency scalp strategy."""

import time
from collections import deque

from loguru import logger

from core.ws import PolyWebSocket
from engine.execution import ExecutionEngine
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
        token_ids: str | list[str],
        imbalance_ratio: float = 5.0,
        volume_surge_mult: float = 3.0,
        scalp_size: int = 50,
    ):
        super().__init__(engine, ws, "HFM", token_ids=token_ids)
        self.token_id = self.token_ids[0] if self.token_ids else ""

        self.imbalance_ratio = imbalance_ratio
        self.volume_surge_mult = volume_surge_mult
        self.scalp_size = scalp_size

        self.volume_history: dict = {t: deque(maxlen=60) for t in self.token_ids}

    # ------------------------------------------------------------------

    def on_market_update(self, data: dict):
        if data.get("event_type") != "book":
            return

        market_id = data.get("market") or self.token_id
        if market_id not in self.token_ids:
            return

        bids = data.get("bids", [])
        asks = data.get("asks", [])
        if not bids or not asks:
            return

        bid_depth = sum(float(b[1]) for b in bids[:5])
        ask_depth = sum(float(a[1]) for a in asks[:5])
        if ask_depth <= 0:
            return

        ratio = bid_depth / ask_depth
        if ratio > self.imbalance_ratio:
            best_ask = float(asks[0][0])
            logger.warning(
                f"[HFM] BUY IMBALANCE on {market_id[:10]}… "
                f"Ratio {ratio:.2f} → buying at {best_ask:.3f}"
            )
            if self.engine.risk_manager.check_trade_allowed(
                self.name, best_ask, self.scalp_size, "BUY"
            ):
                self.engine.execute_limit_order(
                    market_id, best_ask, self.scalp_size, "BUY",
                    self.name, dry_run=self.engine.dry_run
                )
        elif ratio < (1 / self.imbalance_ratio):
            best_bid = float(bids[0][0])
            logger.warning(
                f"[HFM] SELL IMBALANCE on {market_id[:10]}… "
                f"Ratio {ratio:.2f} → selling at {best_bid:.3f}"
            )
            if self.engine.risk_manager.check_trade_allowed(
                self.name, best_bid, self.scalp_size, "SELL"
            ):
                self.engine.execute_limit_order(
                    market_id, best_bid, self.scalp_size, "SELL",
                    self.name, dry_run=self.engine.dry_run
                )

    def on_trade_update(self, data: dict):
        if data.get("event_type") != "trade":
            return

        market_id = data.get("market") or self.token_id
        if market_id not in self.token_ids:
            return

        size = float(data.get("size", 0))
        hist = self.volume_history.get(market_id)
        if hist is None:
            return

        hist.append((time.time(), size))

        # Detect volume surge
        recent_sizes = [v for _, v in hist]
        if len(recent_sizes) >= 10:
            avg = sum(recent_sizes[:-1]) / max(len(recent_sizes) - 1, 1)
            if avg > 0 and recent_sizes[-1] > avg * self.volume_surge_mult:
                logger.info(
                    f"[HFM] Volume surge on {market_id[:10]}… "
                    f"{recent_sizes[-1]:.1f} vs avg {avg:.1f}"
                )

    def run(self):
        logger.info(f"[HFM] Starting on {len(self.token_ids)} market(s)…")
        self.subscribe_all()

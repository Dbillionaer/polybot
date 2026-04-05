"""Logical arbitrage across mutually-exclusive market outcomes."""


from loguru import logger

from core.orderbook import extract_best_bid_ask
from core.ws import PolyWebSocket
from engine.execution import ExecutionEngine
from strategies.base import BaseStrategy


class LogicalArbStrategy(BaseStrategy):
    """
    Logical Arbitrage Strategy.
    Detects impossible pricing (e.g., sum of outcome probabilities > 105%)
    across related markets and fires counter-trades on the over-priced tokens.
    """

    def __init__(
        self,
        engine: ExecutionEngine,
        ws: PolyWebSocket,
        markets: list[dict],
        threshold: float = 1.05,
        arb_size: int = 80,
    ):
        # Extract token_ids for base class subscription management
        token_ids = [m.get("token_id", "") for m in markets if m.get("token_id")]
        super().__init__(engine, ws, "Logical-Arb", token_ids=token_ids)

        self.markets = markets
        self.threshold = threshold
        self.arb_size = arb_size
        self.prices: dict[str, float] = {}
        self.condition_families: dict[str, list[str]] = {}

        for market in markets:
            token_id = market.get("token_id")
            condition_id = market.get("condition_id") or token_id
            if token_id and condition_id:
                self.condition_families.setdefault(str(condition_id), []).append(str(token_id))

    # ------------------------------------------------------------------

    def on_market_update(self, data: dict):
        event = data.get("event_type")

        # Accept both "price" and "book" events
        if event == "price":
            token_id = data.get("market")
            price_str = data.get("price")
            if token_id and price_str:
                self.prices[str(token_id)] = float(price_str)
                self.check_sum_violations()

        elif event == "book":
            token_id = data.get("market")
            if token_id not in self.token_ids:
                return
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            if bids and asks:
                best_bid, best_ask = extract_best_bid_ask({"bids": bids, "asks": asks})
                if best_bid is None or best_ask is None:
                    logger.debug(f"[Logical-Arb] Skipping malformed book for {str(token_id)[:12]}…")
                    return
                mid = (best_bid + best_ask) / 2
                self.prices[str(token_id)] = mid
                self.check_sum_violations()

    def check_sum_violations(self):
        for condition_id, token_ids in self.condition_families.items():
            if len(token_ids) < 2:
                continue
            if any(token_id not in self.prices for token_id in token_ids):
                continue

            family_prices = {token_id: self.prices[token_id] for token_id in token_ids}
            total_prob = sum(family_prices.values())
            if total_prob <= self.threshold:
                continue

            logger.warning(
                f"[Logical-Arb] Sum violation: {total_prob:.4f} in condition {condition_id[:12]}… "
                f"across {len(token_ids)} outcomes → arbing over-priced leg(s)"
            )
            most_overpriced_id = max(family_prices, key=lambda k: family_prices[k])
            overpriced_price = family_prices[most_overpriced_id]
            if self.engine.risk_manager.check_trade_allowed(self.name, overpriced_price, self.arb_size, "SELL"):
                self.engine.execute_limit_order(
                    most_overpriced_id,
                    overpriced_price,
                    self.arb_size,
                    "SELL",
                    self.name,
                    dry_run=self.engine.dry_run,
                )

    def on_trade_update(self, data: dict):
        del data
        pass

    def run(self):
        logger.info(f"[Logical-Arb] Monitoring {len(self.markets)} markets…")
        for m in self.markets:
            token_id = m.get("token_id")
            if token_id:
                self.ws.subscribe(str(token_id), "book")
                self.ws.subscribe(str(token_id), "price")

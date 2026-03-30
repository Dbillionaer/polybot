"""Automated Market Making strategy implementation."""

from typing import List, Union

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from core.ws import PolyWebSocket
from engine.execution import ExecutionEngine
from strategies.base import BaseStrategy


class AMMStrategy(BaseStrategy):
    """
    Automated Market Making Strategy.
    Places buy/sell limit orders around the mid-price to capture spread.
    Supports multiple token_ids (one AMM book per market).
    """

    def __init__(
        self,
        engine: ExecutionEngine,
        ws: PolyWebSocket,
        token_ids: Union[str, List[str]],
        spread: float = 0.02,
        size: int = 100,
        max_inventory: float = 1000.0,
    ):
        super().__init__(engine, ws, "AMM", token_ids=token_ids)

        # Keep single token_id alias for backwards compatibility
        self.token_id = self.token_ids[0] if self.token_ids else ""

        self.spread = spread
        self.size = size
        self.max_inventory = max_inventory

        # Per-market state keyed by token_id
        self.last_mid_price: dict = {t: 0.0 for t in self.token_ids}
        self.inventory: dict = {t: 0.0 for t in self.token_ids}
        self.volatility_multiplier: dict = {t: 1.0 for t in self.token_ids}
        self.quote_reprice_threshold = 0.005
        self.active_quotes: dict = {
            t: {
                "BUY": {"order_id": None, "price": None},
                "SELL": {"order_id": None, "price": None},
            }
            for t in self.token_ids
        }

        # Sync inventory from on-chain / db at startup
        for t in self.token_ids:
            self.inventory[t] = self._sync_inventory(t)

    # ------------------------------------------------------------------
    # Inventory / state helpers
    # ------------------------------------------------------------------

    def _sync_inventory(self, token_id: str) -> float:
        """Pull current on-chain balance for a token at startup."""
        try:
            balance = self.engine.client.get_user_balance(token_id)
            inv = float(balance or 0.0)
            logger.info(f"[AMM] Synced inventory for {token_id[:10]}…: {inv:.2f}")
            return inv
        except Exception as e:
            logger.warning(f"[AMM] Inventory sync failed for {token_id[:10]}…: {e}")
            return 0.0

    def _requote(self):
        """Re-run quoting logic for all active markets (called by scheduler)."""
        for tid in self.token_ids:
            if self.last_mid_price.get(tid, 0) > 0:
                try:
                    book = self.engine.client.get_order_book(tid)
                except Exception as e:
                    logger.warning(f"[AMM] Requote book fetch failed for {tid[:10]}…: {e}")
                    continue
                self.on_market_update({
                    "event_type": "book",
                    "market": tid,
                    "bids": book.get("bids", []),
                    "asks": book.get("asks", []),
                })

    def _quote_slot(self, market_id: str, side: str) -> dict:
        return self.active_quotes.setdefault(market_id, {}).setdefault(
            side,
            {"order_id": None, "price": None},
        )

    def _clear_stale_quote(self, market_id: str, side: str) -> None:
        quote = self._quote_slot(market_id, side)
        order_id = quote.get("order_id")
        if order_id and not self.engine.is_order_pending(order_id):
            quote["order_id"] = None
            quote["price"] = None

    def _place_or_replace_quote(self, market_id: str, side: str, target_price: float) -> None:
        quote = self._quote_slot(market_id, side)
        self._clear_stale_quote(market_id, side)

        existing_order_id = quote.get("order_id")
        existing_price = quote.get("price")
        if existing_order_id and existing_price is not None:
            if abs(float(existing_price) - target_price) < self.quote_reprice_threshold:
                return
            if not self.engine.cancel_order(existing_order_id, reason=f"{self.name} requote {side}"):
                logger.warning(f"[AMM] Failed to cancel stale {side} quote {existing_order_id} for {market_id[:10]}…")
                return
            quote["order_id"] = None
            quote["price"] = None

        response = self.engine.execute_limit_order(
            market_id,
            target_price,
            self.size,
            side,
            self.name,
            dry_run=self.engine.dry_run,
        )
        if response and response.get("execution_status") == "ACCEPTED":
            quote["order_id"] = response.get("orderID")
            quote["price"] = target_price

    # ------------------------------------------------------------------
    # WebSocket callbacks
    # ------------------------------------------------------------------

    def on_market_update(self, data: dict):
        if data.get("event_type") != "book":
            return

        # Identify which market this update belongs to
        market_id = data.get("market") or data.get("_requote_market") or self.token_id
        if market_id not in self.token_ids:
            return

        bids = data.get("bids", [])
        asks = data.get("asks", [])

        if bids and asks:
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
            mid_price = (best_bid + best_ask) / 2
            self.last_mid_price[market_id] = mid_price

            # Volatility widening
            raw_spread = best_ask - best_bid
            self.volatility_multiplier[market_id] = 1.5 if raw_spread > 0.03 else 1.0
            actual_spread = self.spread * self.volatility_multiplier[market_id]

            # Inventory dampening
            inv = self.inventory[market_id]
            bid_adj = ask_adj = 0.0
            if inv > self.max_inventory * 0.5:        # Too long → push quotes down
                bid_adj -= 0.01
                ask_adj -= 0.01
            elif inv < -self.max_inventory * 0.5:     # Too short → push quotes up
                bid_adj += 0.01
                ask_adj += 0.01

            target_bid = mid_price - (actual_spread / 2) + bid_adj
            target_ask = mid_price + (actual_spread / 2) + ask_adj

            logger.debug(
                f"[AMM] {market_id[:10]}… BID {target_bid:.3f} | "
                f"ASK {target_ask:.3f} | Inv: {inv:.1f} | VM: {self.volatility_multiplier[market_id]}"
            )

            # Execute both sides with quote ownership / cancel-replace
            if self.engine.risk_manager.check_trade_allowed(self.name, target_bid, self.size, "BUY"):
                self._place_or_replace_quote(market_id, "BUY", target_bid)
            if self.engine.risk_manager.check_trade_allowed(self.name, target_ask, self.size, "SELL"):
                self._place_or_replace_quote(market_id, "SELL", target_ask)

    def on_trade_update(self, data: dict):
        if data.get("event_type") != "trade":
            return

        market_id = data.get("market") or self.token_id
        if market_id not in self.token_ids:
            return

        is_maker = data.get("maker_address") == self.engine.client.address
        if not is_maker:
            return

        side = data.get("side")
        size_str = data.get("size")
        if size_str:
            size = float(size_str)
            if side == "BUY":
                self.inventory[market_id] = self.inventory.get(market_id, 0) + size
            else:
                self.inventory[market_id] = self.inventory.get(market_id, 0) - size
            if side in ("BUY", "SELL"):
                self.active_quotes.get(market_id, {}).get(side, {}).update({"order_id": None, "price": None})
            logger.info(
                f"[AMM] {market_id[:10]}… Fill: {side} {size}  "
                f"→ Inventory: {self.inventory[market_id]:.2f}"
            )

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self):
        logger.info(f"[AMM] Starting on {len(self.token_ids)} market(s)…")

        # Subscribe to all markets (base class already registered callbacks)
        self.subscribe_all()

        # 15-second re-quoting timer
        scheduler = BackgroundScheduler()
        scheduler.add_job(self._requote, "interval", seconds=15)
        scheduler.start()
        logger.info("[AMM] Re-quoting scheduler started (15s interval)")

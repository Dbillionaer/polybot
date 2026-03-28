"""Execution engine for managing PolyBot orders."""

import os

from loguru import logger

from core.client import PolyClient
from core.database import record_trade, update_position
from engine.risk import RiskManager


class ExecutionEngine:
    """Handles the execution of trades and order tracking."""

    def __init__(
        self,
        client: PolyClient,
        risk_manager: RiskManager,
        dry_run: bool = True,
    ):
        self.client = client
        self.risk_manager = risk_manager
        # Master dry_run flag — overrides per-call flag when True
        self.dry_run = dry_run

    def execute_limit_order(
        self,
        token_id: str,
        price: float,
        size: int,
        side: str,
        strategy_name: str,
        dry_run: bool = None,   # None → use self.dry_run
    ):
        """
        Submits a limit order if risk management allows.
        dry_run=True: log only, never touch the CLOB.
        """
        effective_dry_run = self.dry_run if dry_run is None else dry_run

        if effective_dry_run:
            logger.info(
                f"[DRY-RUN] Would post: {side} {size} shares of "
                f"{token_id[:12]}… @ {price:.3f} via {strategy_name}"
            )
            return {"status": "OK", "orderID": "DRY-RUN-ID"}

        # ── Live path ────────────────────────────────────────────────────

        # 1. Liquidity / spread check
        book = self.client.get_order_book(token_id)
        if not book:
            logger.error(f"[Execution] Cannot fetch order book for {token_id[:12]}…")
            return None

        bids = book.get("bids", [])
        asks = book.get("asks", [])
        if not bids or not asks:
            logger.warning(f"[Execution] Empty order book for {token_id[:12]}…")
            return None

        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        spread = best_ask - best_bid

        if spread > float(os.getenv("MAX_SPREAD", "0.05")):
            logger.warning(
                f"[Execution] Spread {spread:.3f} too wide for {token_id[:12]}…. Skipping."
            )
            return None

        fee_rate = float(os.getenv("TAKER_FEE_RATE", "0.002"))
        fee_estimate = price * size * fee_rate
        logger.info(f"[Execution] Fee estimate: ${fee_estimate:.4f} ({fee_rate:.2%})")

        # 2. Submit order
        response = self.client.post_limit_order(token_id, price, size, side)

        if response and response.get("status") == "OK":
            order_id = response.get("orderID", "UNKNOWN")
            record_trade(order_id, token_id, side, price, size, strategy_name)
            # Update position state
            update_position(
                condition_id=token_id,        # simplified: token_id used as condition
                _token_id=token_id,
                outcome="YES" if side == "BUY" else "NO",
                _size_delta=float(size),
                _price=price,
            )
            logger.success(
                f"[Execution] {side} {size} shares @ {price:.3f} — "
                f"Order {order_id} accepted by {strategy_name}"
            )
            return response
        else:
            logger.error(
                f"[Execution] Order FAILED for {strategy_name} on {token_id[:12]}… — "
                f"Response: {response}"
            )
            return response

    def cancel_all_open_orders(self):
        """Cancels all open orders for the account."""
        try:
            self.client.clob.cancel_all()
            logger.info("[Execution] All open orders cancelled.")
            return True
        except Exception as e:
            logger.error(f"[Execution] Error cancelling orders: {e}")
            return False

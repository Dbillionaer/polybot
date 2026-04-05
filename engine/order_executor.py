"""Order execution helpers extracted from the main execution engine."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from loguru import logger

from core.orderbook import extract_best_bid_ask


class OrderExecutor:
    """Handle live order submission, cancellation, and spread checks."""

    def __init__(
        self,
        *,
        client,
        circuit_breaker,
        refresh_mark_to_market: Callable[[], dict[str, Any]],
        record_strategy_attempt: Callable[[str], None],
        record_strategy_error: Callable[[str, str, Exception | str], None],
    ) -> None:
        self.client = client
        self.circuit_breaker = circuit_breaker
        self.refresh_mark_to_market = refresh_mark_to_market
        self.record_strategy_attempt = record_strategy_attempt
        self.record_strategy_error = record_strategy_error

    def submit_limit_order(
        self,
        *,
        token_id: str,
        price: float,
        size: int,
        side: str,
        strategy_name: str,
        effective_dry_run: bool,
        risk_manager,
    ) -> dict[str, Any] | None:
        """Run order submission safety checks and submit through the client."""
        if effective_dry_run:
            neg_risk_flag = self.client.check_neg_risk(token_id)
            logger.info(
                f"[DRY-RUN] Would post: {side} {size} shares of "
                f"{token_id[:12]}… @ {price:.3f} via {strategy_name}"
                + (" [NegRisk]" if neg_risk_flag else "")
            )
            self.circuit_breaker.record_success()
            return {
                "status": "OK",
                "orderID": "DRY-RUN-ID",
                "execution_status": "SIMULATED",
            }

        self.refresh_mark_to_market()
        self.record_strategy_attempt(strategy_name)

        if not risk_manager.check_trade_allowed(strategy_name, price, size, side):
            return None

        try:
            book = self.client.get_order_book(token_id)
        except Exception as exc:
            logger.error(f"[Execution] Cannot fetch order book for {token_id[:12]}…: {exc}")
            self.record_strategy_error(strategy_name, "get_order_book", exc)
            self.circuit_breaker.record_error(f"get_order_book failed: {exc}")
            return None

        if not book:
            logger.error(f"[Execution] Empty order book response for {token_id[:12]}…")
            self.circuit_breaker.record_error("empty order book response")
            return None

        best_bid, best_ask = extract_best_bid_ask(book)
        if best_bid is None or best_ask is None:
            logger.warning(f"[Execution] Empty bids/asks for {token_id[:12]}…")
            return None
        spread = best_ask - best_bid

        max_spread = float(os.getenv("MAX_SPREAD", "0.05"))
        if spread > max_spread:
            logger.warning(
                f"[Execution] Spread {spread:.3f} too wide (max {max_spread}) "
                f"for {token_id[:12]}…. Skipping."
            )
            return None

        fee_rate = float(os.getenv("TAKER_FEE_RATE", "0.002"))
        fee_estimate = price * size * fee_rate
        logger.info(f"[Execution] Fee estimate: ${fee_estimate:.4f} ({fee_rate:.2%})")

        try:
            response = self.client.post_limit_order(token_id, price, size, side)
        except Exception as exc:
            logger.error(f"[Execution] post_limit_order raised: {exc}")
            self.record_strategy_error(strategy_name, "post_limit_order", exc)
            self.circuit_breaker.record_error(f"post_limit_order: {exc}")
            return None

        if not isinstance(response, dict):
            logger.error(
                f"[Execution] post_limit_order returned unexpected payload type: {type(response).__name__}"
            )
            self.record_strategy_error(
                strategy_name,
                "post_limit_order",
                f"unexpected payload type: {type(response).__name__}",
            )
            self.circuit_breaker.record_error("post_limit_order returned non-dict payload")
            return None

        return response

    def cancel_live_order(self, order_id: str) -> bool:
        """Cancel a live order through the client."""
        self.client.cancel_order(order_id)
        return True

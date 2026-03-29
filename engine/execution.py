"""Execution engine for managing PolyBot orders — with circuit breaker + NegRisk awareness."""

from __future__ import annotations

import os

from loguru import logger

from core.client import PolyClient
from core.database import record_trade, update_position
from engine.risk import RiskManager
from engine.circuit_breaker import CircuitBreaker


class ExecutionEngine:
    """
    Handles the execution of trades and order tracking.

    Safety layers (in order):
      1. Master dry_run flag — never reaches CLOB if True.
      2. Circuit breaker — pauses all trading after error/drawdown surge.
      3. Risk manager  — checks size/drawdown/daily-loss limits.
      4. Spread check  — skips execution if book spread is too wide.
      5. NegRisk       — auto-detected via PolyClient; neg_risk=True flagged on order.
    """

    def __init__(
        self,
        client: PolyClient,
        risk_manager: RiskManager,
        dry_run: bool = True,
        circuit_breaker: CircuitBreaker | None = None,
    ):
        self.client = client
        self.risk_manager = risk_manager
        # Master dry_run flag — overrides per-call flag when True
        self.dry_run = dry_run
        # Circuit breaker — created here if not injected (so it can be shared across strategies)
        self.circuit_breaker = circuit_breaker or CircuitBreaker()

    # ──────────────────────────────────────────────────────────────────────
    # Order execution
    # ──────────────────────────────────────────────────────────────────────

    def execute_limit_order(
        self,
        token_id: str,
        price: float,
        size: int,
        side: str,
        strategy_name: str,
        dry_run: bool | None = None,  # None → use self.dry_run
    ):
        """
        Submits a limit order if all safety checks pass.

        dry_run=True  → log only, never touch the CLOB.
        dry_run=False → live order; still guarded by circuit breaker + risk manager.
        """
        effective_dry_run = self.dry_run if dry_run is None else dry_run

        # ── 0. Circuit breaker check ──────────────────────────────────────
        if not self.circuit_breaker.is_open():
            logger.warning(
                f"[Execution] 🔴 Circuit breaker OPEN — skipping {side} {size}×{token_id[:12]}… "
                f"from {strategy_name}"
            )
            return None

        # ── 1. DRY-RUN fast path ──────────────────────────────────────────
        if effective_dry_run:
            neg_risk_flag = self.client.check_neg_risk(token_id)
            logger.info(
                f"[DRY-RUN] Would post: {side} {size} shares of "
                f"{token_id[:12]}… @ {price:.3f} via {strategy_name}"
                + (" [NegRisk]" if neg_risk_flag else "")
            )
            self.circuit_breaker.record_success()
            return {"status": "OK", "orderID": "DRY-RUN-ID"}

        # ── 2. Risk manager gate ──────────────────────────────────────────
        if not self.risk_manager.check_trade_allowed(strategy_name, price, size, side):
            return None

        # ── 3. Live path: spread + book check ────────────────────────────
        try:
            book = self.client.get_order_book(token_id)
        except Exception as e:
            logger.error(f"[Execution] Cannot fetch order book for {token_id[:12]}…: {e}")
            self.circuit_breaker.record_error(f"get_order_book failed: {e}")
            return None

        if not book:
            logger.error(f"[Execution] Empty order book response for {token_id[:12]}…")
            self.circuit_breaker.record_error("empty order book response")
            return None

        bids = book.get("bids", [])
        asks = book.get("asks", [])
        if not bids or not asks:
            logger.warning(f"[Execution] Empty bids/asks for {token_id[:12]}…")
            return None

        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
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

        # ── 4. Submit order ───────────────────────────────────────────────
        try:
            response = self.client.post_limit_order(token_id, price, size, side)
        except Exception as e:
            logger.error(f"[Execution] post_limit_order raised: {e}")
            self.circuit_breaker.record_error(f"post_limit_order: {e}")
            return None

        if response and response.get("status") == "OK":
            order_id = response.get("orderID", "UNKNOWN")
            record_trade(order_id, token_id, side, price, size, strategy_name)
            update_position(
                condition_id=token_id,
                _token_id=token_id,
                outcome="YES" if side == "BUY" else "NO",
                _size_delta=float(size),
                _price=price,
            )
            logger.success(
                f"[Execution] {side} {size} shares @ {price:.3f} — "
                f"Order {order_id} accepted by {strategy_name}"
            )
            self.circuit_breaker.record_success()
            # Feed realized PnL delta to circuit breaker (cost basis as negative)
            self.circuit_breaker.record_pnl_delta(-(price * size * fee_rate))
            return response
        else:
            logger.error(
                f"[Execution] Order FAILED for {strategy_name} on {token_id[:12]}… — "
                f"Response: {response}"
            )
            self.circuit_breaker.record_error(f"order rejected: {response}")
            return response

    # ──────────────────────────────────────────────────────────────────────
    # Bulk operations
    # ──────────────────────────────────────────────────────────────────────

    def cancel_all_open_orders(self):
        """Cancels all open orders for the account."""
        try:
            self.client.clob.cancel_all()
            logger.info("[Execution] All open orders cancelled.")
            return True
        except Exception as e:
            logger.error(f"[Execution] Error cancelling orders: {e}")
            self.circuit_breaker.record_error(f"cancel_all: {e}")
            return False

"""Execution engine orchestration layer for managing PolyBot orders."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Event, Lock, Thread
from typing import Any
from uuid import uuid4

from loguru import logger

from core.client import PolyClient
from core.database import get_open_positions, record_trade, update_position
from engine.circuit_breaker import CircuitBreaker
from engine.fill_reconciler import FillReconciler
from engine.order_executor import OrderExecutor
from engine.risk import RiskManager
from engine.telemetry_collector import TelemetryCollector


@dataclass(slots=True)
class MarketMetadata:
    """Execution-time market identity used for correct position accounting."""

    token_id: str
    condition_id: str
    outcome: str | None = None


@dataclass(slots=True)
class AcceptedOrder:
    """Represents an order accepted by the CLOB but not yet confirmed filled."""

    order_id: str
    token_id: str
    condition_id: str
    outcome: str | None
    side: str
    price: float
    size: float
    strategy_name: str
    filled_size: float = 0.0
    last_status: str | None = None
    accepted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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
        self.market_metadata_by_token: dict[str, MarketMetadata] = {}
        self.pending_orders: dict[str, AcceptedOrder] = {}
        self._mark_price_cache: dict[str, float] = {}
        self._pending_orders_lock = Lock()
        self._operator_pause_lock = Lock()
        self._reconciliation_stop = Event()
        self._reconciliation_thread: Thread | None = None
        self._operator_trading_paused = False
        self._operator_pause_reason = ""
        self._operator_pause_at: datetime | None = None
        self.telemetry = TelemetryCollector()
        self.order_executor = OrderExecutor(
            client=self.client,
            circuit_breaker=self.circuit_breaker,
            refresh_mark_to_market=self.refresh_mark_to_market,
            record_strategy_attempt=self.telemetry.record_strategy_attempt,
            record_strategy_error=self.record_strategy_error,
        )
        self.fill_reconciler = FillReconciler(
            client=self.client,
            risk_manager=self.risk_manager,
            circuit_breaker=self.circuit_breaker,
            get_open_positions=get_open_positions,
            telemetry_collector=self.telemetry,
            mark_price_cache=self._mark_price_cache,
            pop_pending_order=self._pop_pending_order,
            record_fill=self._record_fill,
        )

    def _record_fill_telemetry(self, accepted_order: AcceptedOrder, *, fill_price: float) -> None:
        self.telemetry.record_fill(accepted_order, fill_price=fill_price)

    def record_strategy_error(self, strategy_name: str, context: str, error: Exception | str) -> None:
        """Track a strategy-attributed runtime error for telemetry surfaces."""
        self.telemetry.record_strategy_error(strategy_name, context, error)

    def get_telemetry_snapshot(self) -> dict[str, Any]:
        """Return execution telemetry for UI/operator use."""
        return dict(self.telemetry.snapshot())

    def pause_operator_trading(self, reason: str = "") -> bool:
        """Persistently block new order submissions until explicitly resumed."""
        with self._operator_pause_lock:
            self._operator_trading_paused = True
            self._operator_pause_reason = reason.strip()
            self._operator_pause_at = datetime.now(timezone.utc)
        logger.warning(
            "[Execution] Operator pause enabled. New orders blocked."
            + (f" Reason: {self._operator_pause_reason}" if self._operator_pause_reason else "")
        )
        return True

    def resume_operator_trading(self) -> bool:
        """Release the persistent operator trading pause."""
        with self._operator_pause_lock:
            was_paused = self._operator_trading_paused
            self._operator_trading_paused = False
            self._operator_pause_reason = ""
            self._operator_pause_at = None
        if was_paused:
            logger.info("[Execution] Operator pause cleared. New orders allowed.")
        return True

    def get_operator_trading_status(self) -> dict[str, Any]:
        """Return the persistent operator pause state for admin surfaces."""
        with self._operator_pause_lock:
            return {
                "paused": self._operator_trading_paused,
                "reason": self._operator_pause_reason,
                "paused_at": self._operator_pause_at.isoformat() if self._operator_pause_at else None,
            }

    def _pop_pending_order(self, order_id: str) -> AcceptedOrder | None:
        """Remove and return a pending order under lock."""
        with self._pending_orders_lock:
            return self.pending_orders.pop(order_id, None)

    def _record_fill(
        self,
        accepted_order: AcceptedOrder,
        *,
        fill_price: float,
        fill_size: float,
    ) -> bool:
        """Persist an incremental confirmed fill without altering pending-order membership."""
        if fill_size <= 0:
            logger.warning(f"[Execution] Ignoring non-positive confirmed fill for {accepted_order.order_id}.")
            return False

        record_trade(
            accepted_order.order_id,
            accepted_order.token_id,
            accepted_order.side,
            fill_price,
            fill_size,
            accepted_order.strategy_name,
        )
        position_updated = update_position(
            condition_id=accepted_order.condition_id,
            token_id=accepted_order.token_id,
            outcome=accepted_order.outcome,
            side=accepted_order.side,
            size_delta=fill_size,
            price=fill_price,
        )
        if not position_updated:
            logger.warning(
                f"[Execution] Confirmed fill recorded, but position sync failed for "
                f"{accepted_order.token_id[:12]}…."
            )

        if position_updated.realized_pnl:
            record_realized_fn = getattr(self.risk_manager, "record_realized_pnl", None)
            if callable(record_realized_fn):
                record_realized_fn(position_updated.realized_pnl)
            else:
                record_pnl_fn = getattr(self.risk_manager, "record_pnl", None)
                if callable(record_pnl_fn):
                    record_pnl_fn(position_updated.realized_pnl)
            self.fill_reconciler.observe_total_pnl()

        self._record_fill_telemetry(accepted_order, fill_price=fill_price)
        self.refresh_mark_to_market()
        return bool(position_updated)

    def refresh_mark_to_market(self) -> dict[str, Any]:
        """Refresh unrealized PnL from open positions using current mid prices."""
        return dict(self.fill_reconciler.refresh_mark_to_market())

    def register_markets(self, markets: list[dict[str, Any]]) -> None:
        """Register discovered market metadata for later fill accounting."""
        for market in markets:
            token_id = market.get("token_id")
            if not token_id:
                continue
            token_key = str(token_id)
            condition_id = str(market.get("condition_id") or market.get("conditionId") or token_key)
            outcome = market.get("outcome")
            self.market_metadata_by_token[token_key] = MarketMetadata(
                token_id=token_key,
                condition_id=condition_id,
                outcome=str(outcome) if outcome else None,
            )

    def _resolve_market_metadata(
        self,
        token_id: str,
        condition_id: str | None = None,
        outcome: str | None = None,
    ) -> MarketMetadata:
        """Resolve the best-known market identity for a token."""
        registered = self.market_metadata_by_token.get(token_id)
        resolved_condition = condition_id or (registered.condition_id if registered else token_id)
        resolved_outcome = outcome or (registered.outcome if registered else None)
        return MarketMetadata(
            token_id=token_id,
            condition_id=resolved_condition,
            outcome=resolved_outcome,
        )

    def get_pending_orders(self) -> list[AcceptedOrder]:
        """Return the currently accepted-but-unfilled orders."""
        with self._pending_orders_lock:
            return list(self.pending_orders.values())

    def is_order_pending(self, order_id: str) -> bool:
        """Return whether an order is still awaiting fill/cancel confirmation."""
        with self._pending_orders_lock:
            return order_id in self.pending_orders

    def mark_order_filled(
        self,
        order_id: str,
        *,
        fill_price: float | None = None,
        fill_size: float | None = None,
    ) -> dict[str, Any] | None:
        """Persist a confirmed fill and update the position ledger."""
        accepted_order = self._pop_pending_order(order_id)
        if accepted_order is None:
            logger.warning(f"[Execution] Fill confirmation for unknown order {order_id}.")
            return None

        trade_price = float(fill_price if fill_price is not None else accepted_order.price)
        remaining_size = max(accepted_order.size - accepted_order.filled_size, 0.0)
        trade_size = float(fill_size if fill_size is not None else remaining_size or accepted_order.size)

        self._record_fill(
            accepted_order,
            fill_price=trade_price,
            fill_size=trade_size,
        )
        accepted_order.filled_size += trade_size

        logger.success(
            f"[Execution] Fill confirmed: {accepted_order.side} {trade_size:g} shares @ "
            f"{trade_price:.3f} — Order {order_id} ({accepted_order.strategy_name})"
        )
        return {
            "orderID": order_id,
            "status": "FILLED",
            "execution_status": "FILLED",
            "token_id": accepted_order.token_id,
            "condition_id": accepted_order.condition_id,
            "side": accepted_order.side,
            "price": trade_price,
            "size": trade_size,
        }

    def mark_order_cancelled(self, order_id: str, reason: str = "") -> bool:
        """Clear an accepted order that never filled."""
        cancelled = self._pop_pending_order(order_id)
        if cancelled is None:
            logger.warning(f"[Execution] Cancel confirmation for unknown order {order_id}.")
            return False
        logger.info(f"[Execution] Order {order_id} cancelled before fill. {reason}".strip())
        return True

    def cancel_order(self, order_id: str, reason: str = "") -> bool:
        """Cancel a live order through the client and clear pending state if successful."""
        with self._pending_orders_lock:
            pending_order = self.pending_orders.get(order_id)
        try:
            self.order_executor.cancel_live_order(order_id)
        except Exception as exc:
            logger.error(f"[Execution] Error cancelling order {order_id}: {exc}")
            if pending_order is not None:
                self.record_strategy_error(pending_order.strategy_name, "cancel_order", exc)
            self.circuit_breaker.record_error(f"cancel_order {order_id}: {exc}")
            return False
        return self.mark_order_cancelled(order_id, reason=reason or "cancelled by strategy")

    def reconcile_pending_orders(self, order_ids: list[str] | None = None) -> list[dict[str, Any]]:
        """Poll live order status and record newly confirmed fills/cancels."""
        with self._pending_orders_lock:
            if order_ids is None:
                pending_snapshot = list(self.pending_orders.items())
            else:
                pending_snapshot = [
                    (order_id, self.pending_orders[order_id])
                    for order_id in order_ids
                    if order_id in self.pending_orders
                ]

        reconciled_events = self.fill_reconciler.reconcile_pending_orders(
            pending_snapshot=pending_snapshot,
            mark_order_cancelled=self.mark_order_cancelled,
            record_strategy_error=self.record_strategy_error,
        )
        return list(reconciled_events)

    def start_fill_reconciliation(self, poll_interval_seconds: float = 2.0) -> bool:
        """Start a background poller that reconciles pending orders against live CLOB status."""
        if self.dry_run:
            logger.info("[Execution] Fill reconciliation not started because DRY_RUN=true.")
            return False
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if self._reconciliation_thread and self._reconciliation_thread.is_alive():
            logger.info("[Execution] Fill reconciliation thread already running.")
            return False

        self._reconciliation_stop.clear()

        def _poll_loop() -> None:
            logger.info(
                f"[Execution] Fill reconciliation poller started (interval={poll_interval_seconds:.1f}s)."
            )
            while not self._reconciliation_stop.wait(poll_interval_seconds):
                try:
                    self.reconcile_pending_orders()
                    self.refresh_mark_to_market()
                except Exception as exc:
                    logger.error(f"[Execution] Fill reconciliation loop error: {exc}")
                    self.circuit_breaker.record_error(f"fill_reconciliation_loop: {exc}")

        self._reconciliation_thread = Thread(
            target=_poll_loop,
            name="polybot-fill-reconciler",
            daemon=True,
        )
        self._reconciliation_thread.start()
        return True

    def stop_fill_reconciliation(self, join_timeout: float = 5.0) -> None:
        """Stop the background fill reconciler if it is running."""
        thread = self._reconciliation_thread
        if thread is None:
            return

        self._reconciliation_stop.set()
        if thread.is_alive():
            thread.join(timeout=join_timeout)
        self._reconciliation_thread = None
        logger.info("[Execution] Fill reconciliation poller stopped.")

    def is_fill_reconciliation_running(self) -> bool:
        """Return whether the background reconciliation poller is currently active."""
        thread = self._reconciliation_thread
        return bool(thread is not None and thread.is_alive())

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
        condition_id: str | None = None,
        outcome: str | None = None,
    ):
        """
        Submits a limit order if all safety checks pass.

        dry_run=True  → log only, never touch the CLOB.
        dry_run=False → live order; still guarded by circuit breaker + risk manager.
        """
        effective_dry_run = self.dry_run if dry_run is None else dry_run
        market_meta = self._resolve_market_metadata(
            token_id,
            condition_id=condition_id,
            outcome=outcome,
        )

        # ── 0. Circuit breaker check ──────────────────────────────────────
        operator_pause = self.get_operator_trading_status()
        if operator_pause["paused"]:
            logger.warning(
                f"[Execution] Operator pause active — skipping {side} {size}x{token_id[:12]}… "
                f"from {strategy_name}."
            )
            return None

        trading_allowed_fn = getattr(self.circuit_breaker, "allows_trading", None)
        trading_allowed = (
            trading_allowed_fn()
            if callable(trading_allowed_fn)
            else self.circuit_breaker.is_open()
        )
        if not trading_allowed:
            logger.warning(
                f"[Execution] 🔴 Circuit breaker OPEN — skipping {side} {size}×{token_id[:12]}… "
                f"from {strategy_name}"
            )
            return None

        response = self.order_executor.submit_limit_order(
            token_id=token_id,
            price=price,
            size=size,
            side=side,
            strategy_name=strategy_name,
            effective_dry_run=effective_dry_run,
            risk_manager=self.risk_manager,
        )

        if response is None:
            return None

        if response and (response.get("orderID") or response.get("orderId") or response.get("id")):
            order_id = str(
                response.get("orderID")
                or response.get("orderId")
                or response.get("id")
                or f"ACCEPTED-{uuid4().hex}"
            )
            with self._pending_orders_lock:
                self.pending_orders[order_id] = AcceptedOrder(
                    order_id=order_id,
                    token_id=token_id,
                    condition_id=market_meta.condition_id,
                    outcome=market_meta.outcome,
                    side=side.upper(),
                    price=price,
                    size=float(size),
                    strategy_name=strategy_name,
                    last_status=str(response.get("status") or "").lower() or None,
                )
            logger.success(
                f"[Execution] {side} {size} shares @ {price:.3f} — "
                f"Order {order_id} accepted by {strategy_name}; awaiting fill confirmation."
            )
            self.telemetry.record_strategy_acceptance(strategy_name)
            self.circuit_breaker.record_success()
            response = dict(response)
            response["orderID"] = order_id
            response["execution_status"] = "ACCEPTED"
            return response
        else:
            logger.error(
                f"[Execution] Order FAILED for {strategy_name} on {token_id[:12]}… — "
                f"Response: {response}"
            )
            self.record_strategy_error(strategy_name, "order_rejected", str(response))
            self.circuit_breaker.record_error(f"order rejected: {response}")
            return response

    # ──────────────────────────────────────────────────────────────────────
    # Bulk operations
    # ──────────────────────────────────────────────────────────────────────

    def cancel_all_open_orders(self):
        """Cancels all open orders for the account."""
        try:
            self.client.clob.cancel_all()
            with self._pending_orders_lock:
                self.pending_orders.clear()
            logger.info("[Execution] All open orders cancelled.")
            return True
        except Exception as e:
            logger.error(f"[Execution] Error cancelling orders: {e}")
            self.circuit_breaker.record_error(f"cancel_all: {e}")
            return False

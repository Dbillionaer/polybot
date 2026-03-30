"""Execution engine for managing PolyBot orders — with circuit breaker + NegRisk awareness."""

from __future__ import annotations

from collections import defaultdict, deque
import os
from dataclasses import dataclass, field
from datetime import datetime
from threading import Event, Lock, Thread
from typing import Any
from uuid import uuid4

from loguru import logger

from core.client import PolyClient
from core.database import get_open_positions, record_trade, update_position
from engine.risk import RiskManager
from engine.circuit_breaker import CircuitBreaker


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
    accepted_at: datetime = field(default_factory=datetime.utcnow)


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
        self._telemetry_lock = Lock()
        self._reconciliation_stop = Event()
        self._reconciliation_thread: Thread | None = None
        self._recent_fill_latency_ms: deque[float] = deque(maxlen=200)
        self._recent_slippage_bps: deque[float] = deque(maxlen=200)
        self._strategy_order_attempts: dict[str, int] = defaultdict(int)
        self._strategy_accepted_orders: dict[str, int] = defaultdict(int)
        self._strategy_fill_events: dict[str, int] = defaultdict(int)
        self._strategy_error_counts: dict[str, int] = defaultdict(int)
        self._recent_strategy_errors: deque[dict[str, Any]] = deque(maxlen=50)

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        """Best-effort float parsing for CLOB payload fields."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalize_order_status(order_snapshot: dict[str, Any]) -> str:
        """Normalize order status strings from CLOB responses."""
        return str(order_snapshot.get("status") or order_snapshot.get("order_status") or "").strip().lower()

    @staticmethod
    def _extract_fill_price(order_snapshot: dict[str, Any], fallback_price: float) -> float:
        """Extract the best available fill/limit price from an order snapshot."""
        for key in ("avg_price", "average_price", "matched_price", "price"):
            value = ExecutionEngine._as_float(order_snapshot.get(key), default=0.0)
            if value > 0:
                return value
        return fallback_price

    @staticmethod
    def _extract_mid_price(order_book: Any) -> float | None:
        """Extract a midpoint from a common order-book payload shape."""
        if not isinstance(order_book, dict):
            return None
        bids = order_book.get("bids") or []
        asks = order_book.get("asks") or []
        if not bids or not asks:
            return None
        try:
            best_bid = float(bids[0][0] if isinstance(bids[0], (list, tuple)) else bids[0]["price"])
            best_ask = float(asks[0][0] if isinstance(asks[0], (list, tuple)) else asks[0]["price"])
        except (KeyError, TypeError, ValueError, IndexError):
            return None
        return (best_bid + best_ask) / 2.0

    @staticmethod
    def _calculate_adverse_slippage_bps(side: str, limit_price: float, fill_price: float) -> float:
        """Return adverse slippage in basis points; positive means worse than intended."""
        if limit_price <= 0:
            return 0.0
        if side.upper() == "SELL":
            return ((limit_price - fill_price) / limit_price) * 10_000
        return ((fill_price - limit_price) / limit_price) * 10_000

    def _record_strategy_attempt(self, strategy_name: str) -> None:
        with self._telemetry_lock:
            self._strategy_order_attempts[strategy_name] += 1

    def _record_strategy_acceptance(self, strategy_name: str) -> None:
        with self._telemetry_lock:
            self._strategy_accepted_orders[strategy_name] += 1

    def _record_fill_telemetry(self, accepted_order: AcceptedOrder, *, fill_price: float) -> None:
        latency_ms = max((datetime.utcnow() - accepted_order.accepted_at).total_seconds() * 1000.0, 0.0)
        slippage_bps = self._calculate_adverse_slippage_bps(
            accepted_order.side,
            accepted_order.price,
            fill_price,
        )
        with self._telemetry_lock:
            self._recent_fill_latency_ms.append(latency_ms)
            self._recent_slippage_bps.append(slippage_bps)
            self._strategy_fill_events[accepted_order.strategy_name] += 1

    def record_strategy_error(self, strategy_name: str, context: str, error: Exception | str) -> None:
        """Track a strategy-attributed runtime error for telemetry surfaces."""
        with self._telemetry_lock:
            self._strategy_error_counts[strategy_name] += 1
            self._recent_strategy_errors.appendleft({
                "timestamp": datetime.utcnow().isoformat(),
                "strategy": strategy_name,
                "context": context,
                "error": str(error)[:240],
            })

    def get_telemetry_snapshot(self) -> dict[str, Any]:
        """Return execution telemetry for UI/operator use."""
        with self._telemetry_lock:
            fill_count = len(self._recent_fill_latency_ms)
            all_strategies = sorted({
                *self._strategy_order_attempts.keys(),
                *self._strategy_accepted_orders.keys(),
                *self._strategy_fill_events.keys(),
                *self._strategy_error_counts.keys(),
            })
            return {
                "fills": {
                    "count": fill_count,
                    "avg_latency_ms": (
                        sum(self._recent_fill_latency_ms) / fill_count if fill_count else 0.0
                    ),
                    "max_latency_ms": max(self._recent_fill_latency_ms) if fill_count else 0.0,
                    "avg_adverse_slippage_bps": (
                        sum(self._recent_slippage_bps) / len(self._recent_slippage_bps)
                        if self._recent_slippage_bps
                        else 0.0
                    ),
                    "max_adverse_slippage_bps": (
                        max(self._recent_slippage_bps) if self._recent_slippage_bps else 0.0
                    ),
                },
                "strategies": {
                    name: {
                        "order_attempts": self._strategy_order_attempts.get(name, 0),
                        "accepted_orders": self._strategy_accepted_orders.get(name, 0),
                        "fill_events": self._strategy_fill_events.get(name, 0),
                        "error_count": self._strategy_error_counts.get(name, 0),
                        "error_rate": (
                            self._strategy_error_counts.get(name, 0) / self._strategy_order_attempts[name]
                            if self._strategy_order_attempts.get(name, 0)
                            else 0.0
                        ),
                    }
                    for name in all_strategies
                },
                "recent_errors": list(self._recent_strategy_errors),
            }

    def _observe_total_pnl(self) -> None:
        """Push the latest total PnL snapshot into the circuit breaker when supported."""
        snapshot_fn = getattr(self.risk_manager, "snapshot", None)
        observe_fn = getattr(self.circuit_breaker, "observe_total_pnl", None)
        if not callable(snapshot_fn) or not callable(observe_fn):
            return
        try:
            observe_fn(snapshot_fn()["total_pnl"])
        except Exception as exc:
            logger.debug(f"[Execution] Skipping total PnL observation update: {exc}")

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
            self._observe_total_pnl()

        self._record_fill_telemetry(accepted_order, fill_price=fill_price)
        self.refresh_mark_to_market()
        return bool(position_updated)

    def refresh_mark_to_market(self) -> dict[str, Any]:
        """Refresh unrealized PnL from open positions using current mid prices."""
        open_positions = get_open_positions()
        update_mtm_fn = getattr(self.risk_manager, "update_mark_to_market", None)
        if not callable(update_mtm_fn):
            return {"updated": False, "reason": "risk_manager_missing_mark_to_market"}

        if not open_positions:
            update_mtm_fn(0.0)
            self._observe_total_pnl()
            return {"updated": True, "open_positions": 0, "open_pnl_total": 0.0}

        unresolved_tokens: list[str] = []
        open_pnl_total = 0.0

        for position in open_positions:
            token_id = str(position.token_id)
            mid_price = None
            try:
                order_book = self.client.get_order_book(token_id)
                mid_price = self._extract_mid_price(order_book)
                if mid_price is not None:
                    self._mark_price_cache[token_id] = mid_price
            except Exception as exc:
                logger.debug(f"[Execution] MTM refresh book fetch failed for {token_id[:12]}…: {exc}")

            if mid_price is None:
                mid_price = self._mark_price_cache.get(token_id)

            if mid_price is None:
                unresolved_tokens.append(token_id)
                continue

            open_pnl_total += (mid_price - float(position.avg_price)) * float(position.size)

        if unresolved_tokens and len(unresolved_tokens) == len(open_positions):
            return {
                "updated": False,
                "open_positions": len(open_positions),
                "unresolved_tokens": unresolved_tokens,
            }

        update_mtm_fn(open_pnl_total)
        self._observe_total_pnl()
        return {
            "updated": True,
            "open_positions": len(open_positions),
            "open_pnl_total": open_pnl_total,
            "unresolved_tokens": unresolved_tokens,
        }

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
            self.client.cancel_order(order_id)
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

        if not pending_snapshot:
            return []

        reconciled_events: list[dict[str, Any]] = []
        filled_statuses = {"matched", "filled"}
        cancelled_statuses = {"cancelled", "canceled"}
        completion_tolerance = 1e-9

        for order_id, accepted_order in pending_snapshot:
            try:
                order_snapshot = self.client.get_order(order_id)
            except Exception as exc:
                logger.error(f"[Execution] Failed to reconcile order {order_id}: {exc}")
                self.record_strategy_error(accepted_order.strategy_name, "reconcile_order", exc)
                self.circuit_breaker.record_error(f"reconcile_order {order_id}: {exc}")
                continue

            normalized_status = self._normalize_order_status(order_snapshot)
            accepted_order.last_status = normalized_status or accepted_order.last_status

            matched_size = min(
                self._as_float(
                    order_snapshot.get("size_matched")
                    or order_snapshot.get("matched_size")
                    or order_snapshot.get("filled_size"),
                    default=0.0,
                ),
                accepted_order.size,
            )
            fill_price = self._extract_fill_price(order_snapshot, accepted_order.price)

            incremental_fill = max(matched_size - accepted_order.filled_size, 0.0)
            if incremental_fill > completion_tolerance:
                self._record_fill(
                    accepted_order,
                    fill_price=fill_price,
                    fill_size=incremental_fill,
                )
                accepted_order.filled_size += incremental_fill
                logger.success(
                    f"[Execution] Reconciled fill: {accepted_order.side} {incremental_fill:g} shares @ "
                    f"{fill_price:.3f} — Order {order_id} ({accepted_order.strategy_name})"
                )

            order_complete = accepted_order.filled_size >= (accepted_order.size - completion_tolerance)
            if normalized_status in filled_statuses and not order_complete:
                remaining_size = accepted_order.size - accepted_order.filled_size
                if remaining_size > completion_tolerance:
                    self._record_fill(
                        accepted_order,
                        fill_price=fill_price,
                        fill_size=remaining_size,
                    )
                    accepted_order.filled_size = accepted_order.size
                order_complete = True

            if order_complete:
                self._pop_pending_order(order_id)
                reconciled_events.append({
                    "orderID": order_id,
                    "status": normalized_status or "filled",
                    "execution_status": "FILLED",
                    "size": accepted_order.filled_size,
                    "price": fill_price,
                })
                continue

            if normalized_status in cancelled_statuses:
                partial_reason = ""
                if accepted_order.filled_size > completion_tolerance:
                    partial_reason = (
                        f" Partially filled {accepted_order.filled_size:g}/{accepted_order.size:g} before cancel."
                    )
                self.mark_order_cancelled(
                    order_id,
                    reason=f"status={normalized_status}.{partial_reason}".strip(),
                )
                reconciled_events.append({
                    "orderID": order_id,
                    "status": normalized_status,
                    "execution_status": "CANCELLED",
                    "size": accepted_order.filled_size,
                })

        return reconciled_events

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

        # ── 1. DRY-RUN fast path ──────────────────────────────────────────
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
        self._record_strategy_attempt(strategy_name)

        # ── 2. Risk manager gate ──────────────────────────────────────────
        if not self.risk_manager.check_trade_allowed(strategy_name, price, size, side):
            return None

        # ── 3. Live path: spread + book check ────────────────────────────
        try:
            book = self.client.get_order_book(token_id)
        except Exception as e:
            logger.error(f"[Execution] Cannot fetch order book for {token_id[:12]}…: {e}")
            self.record_strategy_error(strategy_name, "get_order_book", e)
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
            self.record_strategy_error(strategy_name, "post_limit_order", e)
            self.circuit_breaker.record_error(f"post_limit_order: {e}")
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
            self._record_strategy_acceptance(strategy_name)
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
            self.record_strategy_error(strategy_name, "order_rejected", response)
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

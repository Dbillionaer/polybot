"""Fill reconciliation and mark-to-market refresh extracted from the main execution engine."""

from __future__ import annotations

from typing import Any

from loguru import logger


class FillReconciler:
    """Handle pending-order reconciliation and open-position MTM refresh."""

    def __init__(
        self,
        *,
        client,
        risk_manager,
        circuit_breaker,
        get_open_positions,
        telemetry_collector,
        mark_price_cache: dict[str, float],
        pop_pending_order,
        record_fill,
    ) -> None:
        self.client = client
        self.risk_manager = risk_manager
        self.circuit_breaker = circuit_breaker
        self.get_open_positions = get_open_positions
        self.telemetry_collector = telemetry_collector
        self.mark_price_cache = mark_price_cache
        self.pop_pending_order = pop_pending_order
        self.record_fill = record_fill

    @staticmethod
    def as_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def normalize_order_status(order_snapshot: dict[str, Any]) -> str:
        return str(order_snapshot.get("status") or order_snapshot.get("order_status") or "").strip().lower()

    @staticmethod
    def extract_fill_price(order_snapshot: dict[str, Any], fallback_price: float) -> float:
        for key in ("avg_price", "average_price", "matched_price", "price"):
            value = FillReconciler.as_float(order_snapshot.get(key), default=0.0)
            if value > 0:
                return value
        return fallback_price

    @staticmethod
    def extract_mid_price(order_book: Any) -> float | None:
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

    def observe_total_pnl(self) -> None:
        snapshot_fn = getattr(self.risk_manager, "snapshot", None)
        observe_fn = getattr(self.circuit_breaker, "observe_total_pnl", None)
        if not callable(snapshot_fn) or not callable(observe_fn):
            return
        try:
            snapshot = snapshot_fn()
            total_pnl = 0.0
            if isinstance(snapshot, dict):
                total_pnl = self.as_float(snapshot.get("total_pnl"), 0.0)
            observe_fn(total_pnl)
        except Exception as exc:
            logger.debug(f"[Execution] Skipping total PnL observation update: {exc}")

    def refresh_mark_to_market(self) -> dict[str, Any]:
        open_positions = self.get_open_positions()
        update_mtm_fn = getattr(self.risk_manager, "update_mark_to_market", None)
        if not callable(update_mtm_fn):
            return {"updated": False, "reason": "risk_manager_missing_mark_to_market"}

        if not open_positions:
            update_mtm_fn(0.0)
            self.observe_total_pnl()
            return {"updated": True, "open_positions": 0, "open_pnl_total": 0.0}

        unresolved_tokens: list[str] = []
        open_pnl_total = 0.0

        for position in open_positions:
            token_id = str(position.token_id)
            mid_price = None
            try:
                order_book = self.client.get_order_book(token_id)
                mid_price = self.extract_mid_price(order_book)
                if mid_price is not None:
                    self.mark_price_cache[token_id] = mid_price
            except Exception as exc:
                logger.debug(f"[Execution] MTM refresh book fetch failed for {token_id[:12]}…: {exc}")

            if mid_price is None:
                mid_price = self.mark_price_cache.get(token_id)

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
        self.observe_total_pnl()
        return {
            "updated": True,
            "open_positions": len(open_positions),
            "open_pnl_total": open_pnl_total,
            "unresolved_tokens": unresolved_tokens,
        }

    def reconcile_pending_orders(
        self,
        *,
        pending_snapshot: list[tuple[str, Any]],
        mark_order_cancelled,
        record_strategy_error,
    ) -> list[dict[str, Any]]:
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
                record_strategy_error(accepted_order.strategy_name, "reconcile_order", exc)
                self.circuit_breaker.record_error(f"reconcile_order {order_id}: {exc}")
                continue

            normalized_status = self.normalize_order_status(order_snapshot)
            accepted_order.last_status = normalized_status or accepted_order.last_status

            matched_size = min(
                self.as_float(
                    order_snapshot.get("size_matched")
                    or order_snapshot.get("matched_size")
                    or order_snapshot.get("filled_size"),
                    default=0.0,
                ),
                accepted_order.size,
            )
            fill_price = self.extract_fill_price(order_snapshot, accepted_order.price)

            incremental_fill = max(matched_size - accepted_order.filled_size, 0.0)
            if incremental_fill > completion_tolerance:
                self.record_fill(accepted_order, fill_price=fill_price, fill_size=incremental_fill)
                accepted_order.filled_size += incremental_fill
                logger.success(
                    f"[Execution] Reconciled fill: {accepted_order.side} {incremental_fill:g} shares @ "
                    f"{fill_price:.3f} — Order {order_id} ({accepted_order.strategy_name})"
                )

            order_complete = accepted_order.filled_size >= (accepted_order.size - completion_tolerance)
            if normalized_status in filled_statuses and not order_complete:
                remaining_size = accepted_order.size - accepted_order.filled_size
                if remaining_size > completion_tolerance:
                    self.record_fill(accepted_order, fill_price=fill_price, fill_size=remaining_size)
                    accepted_order.filled_size = accepted_order.size
                order_complete = True

            if order_complete:
                self.pop_pending_order(order_id)
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
                mark_order_cancelled(
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

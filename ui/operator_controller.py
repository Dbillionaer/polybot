"""Operator-facing control and status snapshot helpers for PolyBot."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from sqlmodel import select

from core.database import Position, Trade, get_session


class OperatorController:
    """Expose runtime state and safe control actions for the admin surface."""

    def __init__(
        self,
        *,
        execution_engine=None,
        ws=None,
        circuit_breaker=None,
        strategies: list[Any] | None = None,
        markets: list[dict[str, Any]] | None = None,
        bot_name: str = "PolyBot 2026",
    ):
        self.execution_engine = execution_engine
        self.ws = ws
        self.circuit_breaker = circuit_breaker
        self.strategies = list(strategies or [])
        self.markets = list(markets or [])
        self.bot_name = bot_name
        self._market_names_by_token: dict[str, str] = {}
        self._index_markets(self.markets)

    def _index_markets(self, markets: Iterable[dict[str, Any]]) -> None:
        for market in markets:
            token_id = market.get("token_id")
            if not token_id:
                continue
            label = str(
                market.get("question")
                or market.get("market_name")
                or market.get("title")
                or f"Token {token_id}"
            )
            self._market_names_by_token[str(token_id)] = label

    def _market_name(self, token_id: str | None) -> str:
        if not token_id:
            return "Unknown Market"
        return self._market_names_by_token.get(str(token_id), f"Token {str(token_id)[:12]}...")

    def _load_open_positions(self) -> list[dict[str, Any]]:
        with get_session() as session:
            query = select(Position).where(Position.status == "OPEN")
            positions = list(session.exec(query).all())

        return [
            {
                "market_name": self._market_name(position.token_id),
                "condition_id": position.condition_id,
                "token_id": position.token_id,
                "outcome": position.outcome,
                "size": float(position.size),
                "avg_price": float(position.avg_price),
                "status": position.status,
                "entry_time": position.entry_time.isoformat() if position.entry_time else None,
            }
            for position in positions
        ]

    def _load_recent_trades(self, limit: int = 20) -> list[dict[str, Any]]:
        with get_session() as session:
            query = select(Trade).order_by(Trade.timestamp, Trade.id)
            trades = list(session.exec(query).all())
        trades.reverse()

        return [
            {
                "trade_id": trade.order_id,
                "market_name": self._market_name(trade.token_id),
                "token_id": trade.token_id,
                "side": trade.side,
                "price": float(trade.price),
                "size": float(trade.size),
                "strategy": trade.strategy,
                "timestamp": trade.timestamp.isoformat() if trade.timestamp else None,
            }
            for trade in trades
        ]

    def _pending_orders(self) -> list[dict[str, Any]]:
        if self.execution_engine is None:
            return []

        return [
            {
                "order_id": order.order_id,
                "market_name": self._market_name(order.token_id),
                "token_id": order.token_id,
                "condition_id": order.condition_id,
                "outcome": order.outcome,
                "side": order.side,
                "price": order.price,
                "size": order.size,
                "filled_size": order.filled_size,
                "strategy_name": order.strategy_name,
                "accepted_at": order.accepted_at.isoformat(),
                "last_status": order.last_status,
            }
            for order in self.execution_engine.get_pending_orders()
        ]

    def get_status_snapshot(self) -> dict[str, Any]:
        execution_engine = self.execution_engine
        mode = "DRY_RUN"
        if execution_engine is not None and not getattr(execution_engine, "dry_run", True):
            mode = "LIVE"

        return {
            "bot_name": self.bot_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "market_count": len(self.markets),
            "strategies": [
                {
                    "name": getattr(strategy, "name", strategy.__class__.__name__),
                    "token_count": len(getattr(strategy, "token_ids", []) or []),
                }
                for strategy in self.strategies
            ],
            "websocket": self.ws.status_summary() if self.ws is not None else None,
            "circuit_breaker": (
                self.circuit_breaker.status_summary() if self.circuit_breaker is not None else None
            ),
            "execution": {
                "reconciliation_running": (
                    execution_engine.is_fill_reconciliation_running()
                    if execution_engine is not None
                    else False
                ),
                "operator_pause": (
                    execution_engine.get_operator_trading_status()
                    if execution_engine is not None
                    else {"paused": False, "reason": "", "paused_at": None}
                ),
                "pending_orders": self._pending_orders(),
                "telemetry": (
                    execution_engine.get_telemetry_snapshot()
                    if execution_engine is not None
                    else {}
                ),
            },
            "positions": self._load_open_positions(),
            "recent_trades": self._load_recent_trades(),
        }

    def cancel_all_open_orders(self) -> dict[str, Any]:
        if self.execution_engine is None:
            return {"success": False, "message": "Execution engine unavailable."}

        success = bool(self.execution_engine.cancel_all_open_orders())
        message = "Canceled all open orders." if success else "Failed to cancel open orders."
        return {"success": success, "message": message}

    def start_fill_reconciliation(self, poll_interval_seconds: float = 2.0) -> dict[str, Any]:
        if self.execution_engine is None:
            return {"success": False, "message": "Execution engine unavailable."}

        started = bool(
            self.execution_engine.start_fill_reconciliation(
                poll_interval_seconds=poll_interval_seconds,
            )
        )
        if started:
            message = f"Started fill reconciliation poller ({poll_interval_seconds:.1f}s interval)."
        else:
            message = "Fill reconciliation was already running or is disabled in DRY_RUN mode."
        return {"success": started, "message": message}

    def stop_fill_reconciliation(self) -> dict[str, Any]:
        if self.execution_engine is None:
            return {"success": False, "message": "Execution engine unavailable."}

        was_running = self.execution_engine.is_fill_reconciliation_running()
        self.execution_engine.stop_fill_reconciliation()
        message = (
            "Stopped fill reconciliation poller."
            if was_running
            else "Fill reconciliation poller was not running."
        )
        return {"success": True, "message": message}

    def pause_trading(self, reason: str = "") -> dict[str, Any]:
        if self.execution_engine is None:
            return {"success": False, "message": "Execution engine unavailable."}

        self.execution_engine.pause_operator_trading(reason=reason)
        message = "Trading paused by operator."
        if reason.strip():
            message = f"{message} Reason: {reason.strip()}"
        return {"success": True, "message": message}

    def resume_trading(self) -> dict[str, Any]:
        if self.execution_engine is None:
            return {"success": False, "message": "Execution engine unavailable."}

        self.execution_engine.resume_operator_trading()
        return {"success": True, "message": "Trading resumed by operator."}

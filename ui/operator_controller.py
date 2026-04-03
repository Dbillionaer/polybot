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
        poly_client=None,
        execution_engine=None,
        ws=None,
        circuit_breaker=None,
        strategies: list[Any] | None = None,
        markets: list[dict[str, Any]] | None = None,
        bot_name: str = "PolyBot 2026",
    ) -> None:
        self.poly_client = poly_client
        self.execution_engine = execution_engine
        self.ws = ws
        self.circuit_breaker = circuit_breaker
        self.strategies = list(strategies or [])
        self.markets = list(markets or [])
        self.bot_name = bot_name
        self._market_names_by_token: dict[str, str] = {}
        self._index_markets(self.markets)

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _format_strategy_name(name: str) -> str:
        replacements = {
            "AIArb": "AI_Arb",
            "LogicalArb": "Logical_Arb",
            "CopyTrading": "Copy_Trading",
        }
        return replacements.get(name, name)

    def _risk_snapshot(self) -> dict[str, float]:
        if self.execution_engine is None:
            return {
                "initial_bankroll": 0.0,
                "current_bankroll": 0.0,
                "daily_pnl": 0.0,
                "realized_pnl": 0.0,
                "mark_to_market_pnl": 0.0,
                "total_pnl": 0.0,
            }
        risk_manager = getattr(self.execution_engine, "risk_manager", None)
        if risk_manager is None:
            return {
                "initial_bankroll": 0.0,
                "current_bankroll": 0.0,
                "daily_pnl": 0.0,
                "realized_pnl": 0.0,
                "mark_to_market_pnl": 0.0,
                "total_pnl": 0.0,
            }
        snapshot_fn = getattr(risk_manager, "snapshot", None)
        if not callable(snapshot_fn):
            return {
                "initial_bankroll": 0.0,
                "current_bankroll": 0.0,
                "daily_pnl": 0.0,
                "realized_pnl": 0.0,
                "mark_to_market_pnl": 0.0,
                "total_pnl": 0.0,
            }
        snapshot = snapshot_fn()
        if not isinstance(snapshot, dict):
            return {
                "initial_bankroll": 0.0,
                "current_bankroll": 0.0,
                "daily_pnl": 0.0,
                "realized_pnl": 0.0,
                "mark_to_market_pnl": 0.0,
                "total_pnl": 0.0,
            }
        return {
            "initial_bankroll": self._as_float(snapshot.get("initial_bankroll")),
            "current_bankroll": self._as_float(snapshot.get("current_bankroll")),
            "daily_pnl": self._as_float(snapshot.get("daily_pnl")),
            "realized_pnl": self._as_float(snapshot.get("realized_pnl")),
            "mark_to_market_pnl": self._as_float(snapshot.get("mark_to_market_pnl")),
            "total_pnl": self._as_float(snapshot.get("total_pnl")),
        }

    def _usdc_balance(self) -> float | None:
        if self.poly_client is None:
            return None
        get_balance = getattr(self.poly_client, "get_user_balance", None)
        if not callable(get_balance):
            return None
        try:
            return self._as_float(get_balance("USDC"), default=0.0)
        except Exception:
            return None

    def _strategy_statuses(self) -> list[dict[str, Any]]:
        operator_pause = (
            self.execution_engine.get_operator_trading_status()
            if self.execution_engine is not None
            else {"paused": False, "reason": "", "paused_at": None}
        )
        telemetry = (
            self.execution_engine.get_telemetry_snapshot() if self.execution_engine is not None else {}
        )
        recent_errors = telemetry.get("recent_errors", []) if isinstance(telemetry, dict) else []

        statuses: list[dict[str, Any]] = []
        for strategy in self.strategies:
            raw_name = getattr(strategy, "name", strategy.__class__.__name__)
            name = self._format_strategy_name(raw_name)
            strategy_errors = [
                err
                for err in recent_errors
                if isinstance(err, dict) and err.get("strategy") in {raw_name, name}
            ]
            if strategy_errors:
                state = "error"
                label = "Error"
            elif operator_pause.get("paused"):
                state = "paused"
                label = "Paused"
            else:
                state = "running"
                label = "Running"

            statuses.append(
                {
                    "name": name,
                    "state": state,
                    "state_label": label,
                    "token_count": len(getattr(strategy, "token_ids", []) or []),
                    "last_error": strategy_errors[0].get("error") if strategy_errors else None,
                }
            )
        return statuses

    def _health_snapshot(self) -> dict[str, Any]:
        execution_engine = self.execution_engine
        websocket_status = self.ws.status_summary() if self.ws is not None else {}
        return {
            "dry_run": bool(getattr(execution_engine, "dry_run", True)) if execution_engine else True,
            "circuit_breaker": (
                self.circuit_breaker.status_summary() if self.circuit_breaker is not None else None
            ),
            "websocket_connected": bool(websocket_status.get("is_connected")) if websocket_status else False,
            "last_websocket_message_at": websocket_status.get("last_message_at") if websocket_status else None,
            "reconciliation_running": (
                execution_engine.is_fill_reconciliation_running() if execution_engine else False
            ),
        }

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
        risk_snapshot = self._risk_snapshot()
        mtm_total = risk_snapshot["mark_to_market_pnl"]
        with get_session() as session:
            query = select(Position).where(Position.status == "OPEN")
            positions = list(session.exec(query).all())

        total_abs_size = sum(abs(float(position.size)) for position in positions) or 0.0

        return [
            {
                "market_name": self._market_name(position.token_id),
                "condition_id": position.condition_id,
                "token_id": position.token_id,
                "outcome": position.outcome,
                "side": position.side,
                "size": float(position.size),
                "entry_price": float(position.avg_price),
                "mark_price": float(position.avg_price),
                "unrealized_pnl": (
                    (abs(float(position.size)) / total_abs_size) * mtm_total if total_abs_size else 0.0
                ),
                "status": position.status,
                "entry_time": position.entry_time.isoformat() if position.entry_time else None,
            }
            for position in positions
        ]

    def _load_recent_trades(self, limit: int = 10) -> list[dict[str, Any]]:
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
            for trade in trades[:limit]
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

        risk_snapshot = self._risk_snapshot()
        operator_pause = (
            execution_engine.get_operator_trading_status()
            if execution_engine is not None
            else {"paused": False, "reason": "", "paused_at": None}
        )
        telemetry = (
            execution_engine.get_telemetry_snapshot() if execution_engine is not None else {}
        )

        return {
            "bot_name": self.bot_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "market_count": len(self.markets),
            "portfolio": {
                **risk_snapshot,
                "usdc_balance": self._usdc_balance(),
            },
            "strategies": self._strategy_statuses(),
            "websocket": self.ws.status_summary() if self.ws is not None else None,
            "circuit_breaker": (
                self.circuit_breaker.status_summary() if self.circuit_breaker is not None else None
            ),
            "health": self._health_snapshot(),
            "execution": {
                "reconciliation_running": (
                    execution_engine.is_fill_reconciliation_running()
                    if execution_engine is not None
                    else False
                ),
                "operator_pause": operator_pause,
                "pending_orders": self._pending_orders(),
                "telemetry": telemetry,
            },
            "positions": self._load_open_positions(),
            "recent_trades": self._load_recent_trades(),
            "recent_fills": self._load_recent_trades(),
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

    def manual_redeem(self) -> dict[str, Any]:
        return {
            "success": False,
            "message": "Manual redeem is not wired into the operator controller yet.",
        }

"""Execution telemetry collection extracted from the main execution engine."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any


class TelemetryCollector:
    """Collect lightweight runtime execution telemetry for operators and tests."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._recent_fill_latency_ms: deque[float] = deque(maxlen=200)
        self._recent_slippage_bps: deque[float] = deque(maxlen=200)
        self._strategy_order_attempts: dict[str, int] = defaultdict(int)
        self._strategy_accepted_orders: dict[str, int] = defaultdict(int)
        self._strategy_fill_events: dict[str, int] = defaultdict(int)
        self._strategy_error_counts: dict[str, int] = defaultdict(int)
        self._recent_strategy_errors: deque[dict[str, Any]] = deque(maxlen=50)

    @staticmethod
    def calculate_adverse_slippage_bps(side: str, limit_price: float, fill_price: float) -> float:
        """Return adverse slippage in basis points; positive means worse than intended."""
        if limit_price <= 0:
            return 0.0
        if side.upper() == "SELL":
            return ((limit_price - fill_price) / limit_price) * 10_000
        return ((fill_price - limit_price) / limit_price) * 10_000

    def record_strategy_attempt(self, strategy_name: str) -> None:
        with self._lock:
            self._strategy_order_attempts[strategy_name] += 1

    def record_strategy_acceptance(self, strategy_name: str) -> None:
        with self._lock:
            self._strategy_accepted_orders[strategy_name] += 1

    def record_fill(self, accepted_order, *, fill_price: float) -> None:
        latency_ms = max((datetime.now(timezone.utc) - accepted_order.accepted_at).total_seconds() * 1000.0, 0.0)
        slippage_bps = self.calculate_adverse_slippage_bps(
            accepted_order.side,
            accepted_order.price,
            fill_price,
        )
        with self._lock:
            self._recent_fill_latency_ms.append(latency_ms)
            self._recent_slippage_bps.append(slippage_bps)
            self._strategy_fill_events[accepted_order.strategy_name] += 1

    def record_strategy_error(self, strategy_name: str, context: str, error: Exception | str) -> None:
        with self._lock:
            self._strategy_error_counts[strategy_name] += 1
            self._recent_strategy_errors.appendleft({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "strategy": strategy_name,
                "context": context,
                "error": str(error)[:240],
            })

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
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

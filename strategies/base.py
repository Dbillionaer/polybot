from abc import ABC, abstractmethod

from loguru import logger

from core.ws import PolyWebSocket
from engine.execution import ExecutionEngine


class BaseStrategy(ABC):
    """Base class for all trading strategies."""

    def __init__(
        self,
        engine: ExecutionEngine,
        ws: PolyWebSocket,
        name: str,
        token_ids: str | list[str] | None = None,
    ) -> None:
        self.engine = engine
        self.ws = ws
        self.name = name

        # Normalise token_ids to always be a list
        if token_ids is None:
            self.token_ids: list[str] = []
        elif isinstance(token_ids, str):
            self.token_ids = [token_ids]
        else:
            self.token_ids = list(token_ids)

        # Register real-time callbacks so strategies react to market data
        self.ws.add_callback("book", self._dispatch_market_update)
        self.ws.add_callback("trades", self._dispatch_trade_update)
        logger.info(f"Strategy {self.name} registered WS callbacks for {len(self.token_ids)} market(s)")

    def _record_strategy_error(self, context: str, exc: Exception) -> None:
        """Forward strategy callback errors into execution telemetry when available."""
        record_error = getattr(self.engine, "record_strategy_error", None)
        if callable(record_error):
            record_error(self.name, context, exc)
        logger.error(f"[{self.name}] {context} failed: {exc}")

    def _dispatch_market_update(self, data: dict) -> None:
        """Execute the strategy market callback with telemetry-safe error capture."""
        try:
            self.on_market_update(data)
        except Exception as exc:
            self._record_strategy_error("book_callback", exc)

    def _dispatch_trade_update(self, data: dict) -> None:
        """Execute the strategy trade callback with telemetry-safe error capture."""
        try:
            self.on_trade_update(data)
        except Exception as exc:
            self._record_strategy_error("trade_callback", exc)

    def subscribe_all(self):
        """Subscribe this strategy to book + trades channels for all its token_ids."""
        for tid in self.token_ids:
            self.ws.subscribe(tid, "book")
            self.ws.subscribe(tid, "trades")
            logger.debug(f"[{self.name}] Subscribed to market {tid[:12]}…")

    @abstractmethod
    def on_market_update(self, data: dict):
        """Handle real-time order book / price updates."""
        pass

    @abstractmethod
    def on_trade_update(self, data: dict):
        """Handle real-time trade updates."""
        pass

    @abstractmethod
    def run(self):
        """Main loop or initialization for the strategy."""
        pass

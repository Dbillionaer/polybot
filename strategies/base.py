from abc import ABC, abstractmethod
from engine.execution import ExecutionEngine
from core.ws import PolyWebSocket

class BaseStrategy(ABC):
    """Base class for all trading strategies."""

    def __init__(self, engine: ExecutionEngine, ws: PolyWebSocket, name: str):

        self.engine = engine
        self.ws = ws
        self.name = name

    @abstractmethod
    def on_market_update(self, data: dict):
        """
        Handle real-time order book / price updates.
        """
        pass

    @abstractmethod
    def on_trade_update(self, data: dict):
        """
        Handle real-time trade updates.
        """
        pass

    @abstractmethod
    def run(self):
        """
        Main loop or initialization for the strategy.
        """
        pass

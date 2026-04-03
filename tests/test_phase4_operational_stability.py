import os
import sys
import unittest
from pathlib import Path

from sqlmodel import SQLModel

TEST_DB_PATH = Path("phase4_operational_stability.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["BANKROLL_USDC"] = "1000"
os.environ["MAX_SPREAD"] = "1.0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.database import create_db_and_tables  # noqa: E402
from core.database import engine as db_engine
from core.ws import PolyWebSocket  # noqa: E402
from engine.circuit_breaker import CircuitBreaker  # noqa: E402
from engine.execution import ExecutionEngine  # noqa: E402
from engine.risk import RiskManager  # noqa: E402
from strategies.base import BaseStrategy  # noqa: E402
from tests.mocks.execution import MockPolyClient


class ExplodingStrategy(BaseStrategy):
    def __init__(self, engine, ws):
        super().__init__(engine, ws, "Exploder", token_ids=["tok-1"])

    def on_market_update(self, data: dict):
        raise RuntimeError("boom-market")

    def on_trade_update(self, data: dict):
        raise RuntimeError("boom-trade")

    def run(self):
        return None


class Phase4OperationalStabilityTest(unittest.TestCase):
    def setUp(self):
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()
        SQLModel.metadata.drop_all(db_engine)
        create_db_and_tables()

    def tearDown(self):
        db_engine.dispose()
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

    def test_websocket_deduplicates_subscriptions_and_callbacks(self):
        ws = PolyWebSocket()

        def callback(_data):
            return None

        self.assertTrue(ws.add_callback("book", callback))
        self.assertFalse(ws.add_callback("book", callback))
        self.assertTrue(ws.subscribe("tok-1", "book"))
        self.assertFalse(ws.subscribe("tok-1", "book"))
        self.assertTrue(ws.subscribe("tok-1", "trades"))

        self.assertEqual(len(ws.callbacks["book"]), 1)
        self.assertEqual(len(ws.subscriptions), 2)
        self.assertEqual(ws.status_summary()["subscription_count"], 2)

    def test_strategy_callback_errors_feed_execution_telemetry(self):
        engine = ExecutionEngine(MockPolyClient(), RiskManager(), dry_run=False, circuit_breaker=CircuitBreaker(enabled=False))
        ws = PolyWebSocket()
        strategy = ExplodingStrategy(engine, ws)

        ws.callbacks["book"][0]({"market": "tok-1"})
        ws.callbacks["trades"][0]({"market": "tok-1"})

        telemetry = engine.get_telemetry_snapshot()
        self.assertEqual(strategy.name, "Exploder")
        self.assertEqual(telemetry["strategies"]["Exploder"]["error_count"], 2)
        self.assertEqual(len(telemetry["recent_errors"]), 2)

    def test_execution_telemetry_tracks_fill_latency_and_slippage(self):
        engine = ExecutionEngine(MockPolyClient(), RiskManager(), dry_run=False, circuit_breaker=CircuitBreaker(enabled=False))
        engine.register_markets([
            {"token_id": "tok-1", "condition_id": "cond-1", "outcome": "YES"}
        ])

        response = engine.execute_limit_order("tok-1", 0.40, 10, "BUY", "TelemetryStrategy")
        self.assertEqual(response["execution_status"], "ACCEPTED")
        engine.mark_order_filled(response["orderID"], fill_price=0.41, fill_size=10)

        telemetry = engine.get_telemetry_snapshot()
        fills = telemetry["fills"]
        strategy_stats = telemetry["strategies"]["TelemetryStrategy"]

        self.assertEqual(fills["count"], 1)
        self.assertGreaterEqual(fills["avg_latency_ms"], 0.0)
        self.assertAlmostEqual(fills["avg_adverse_slippage_bps"], 250.0, places=3)
        self.assertEqual(strategy_stats["order_attempts"], 1)
        self.assertEqual(strategy_stats["accepted_orders"], 1)
        self.assertEqual(strategy_stats["fill_events"], 1)
        self.assertEqual(strategy_stats["error_count"], 0)


if __name__ == "__main__":
    unittest.main()

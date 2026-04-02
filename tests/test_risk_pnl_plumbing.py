import os
from pathlib import Path
import sys
import unittest

from sqlmodel import SQLModel


TEST_DB_PATH = Path("phase2_risk_pnl_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["BANKROLL_USDC"] = "1000"
os.environ["MAX_SPREAD"] = "1.0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.database import create_db_and_tables, engine as db_engine  # noqa: E402
from engine.circuit_breaker import CircuitBreaker  # noqa: E402
from engine.execution import ExecutionEngine  # noqa: E402
from engine.risk import RiskManager  # noqa: E402
from tests.mocks.execution import MockPolyClient


class RiskPnlPlumbingTest(unittest.TestCase):
    def setUp(self):
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()
        SQLModel.metadata.drop_all(db_engine)
        create_db_and_tables()
        self.client = MockPolyClient(books={"tok-yes": {"bids": [[0.39, 100]], "asks": [[0.41, 100]]}})
        self.risk_manager = RiskManager()
        self.circuit_breaker = CircuitBreaker(
            max_consecutive_errors=99,
            drawdown_pct_trigger=0.5,
            drawdown_window_minutes=60,
            cool_down_minutes=1,
            enabled=True,
        )
        self.engine = ExecutionEngine(
            self.client,
            self.risk_manager,
            dry_run=False,
            circuit_breaker=self.circuit_breaker,
        )
        self.engine.register_markets([
            {"token_id": "tok-yes", "condition_id": "cond-1", "outcome": "YES"}
        ])

    def tearDown(self):
        db_engine.dispose()
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

    def test_realized_and_mark_to_market_pnl_feed_risk_and_breaker(self):
        buy_response = self.engine.execute_limit_order("tok-yes", 0.40, 10, "BUY", "phase2-buy")
        self.engine.mark_order_filled(buy_response["orderID"], fill_price=0.40, fill_size=10)

        snapshot = self.risk_manager.snapshot()
        self.assertEqual(snapshot["realized_pnl"], 0.0)
        self.assertEqual(snapshot["mark_to_market_pnl"], 0.0)
        self.assertTrue(self.circuit_breaker.status_summary()["trading_allowed"])

        self.client.books["tok-yes"] = {"bids": [[0.59, 100]], "asks": [[0.61, 100]]}
        mtm_report = self.engine.refresh_mark_to_market()
        self.assertTrue(mtm_report["updated"])

        snapshot = self.risk_manager.snapshot()
        self.assertAlmostEqual(snapshot["mark_to_market_pnl"], 2.0, places=6)
        self.assertAlmostEqual(snapshot["current_bankroll"], 1002.0, places=6)

        sell_response = self.engine.execute_limit_order("tok-yes", 0.55, 10, "SELL", "phase2-sell")
        self.engine.mark_order_filled(sell_response["orderID"], fill_price=0.55, fill_size=10)

        snapshot = self.risk_manager.snapshot()
        self.assertAlmostEqual(snapshot["realized_pnl"], 1.5, places=6)
        self.assertAlmostEqual(snapshot["mark_to_market_pnl"], 0.0, places=6)
        self.assertAlmostEqual(snapshot["total_pnl"], 1.5, places=6)
        self.assertAlmostEqual(snapshot["current_bankroll"], 1001.5, places=6)
        self.assertTrue(self.circuit_breaker.status_summary()["trading_allowed"])


if __name__ == "__main__":
    unittest.main()

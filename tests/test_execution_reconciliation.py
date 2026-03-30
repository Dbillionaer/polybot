import os
from pathlib import Path
import sys
import unittest

from sqlmodel import select


TEST_DB_PATH = Path("phase1_reconciliation_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["MAX_SPREAD"] = "1.0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.database import Position, Trade, create_db_and_tables, engine as db_engine, get_session  # noqa: E402
from engine.execution import ExecutionEngine  # noqa: E402


class FakeCircuitBreaker:
    def is_open(self):
        return True

    def record_success(self):
        return None

    def record_error(self, _message: str):
        return None


class FakeRiskManager:
    def check_trade_allowed(self, *_args, **_kwargs):
        return True


class FakePolyClient:
    def __init__(self):
        self.orders = {}
        self.post_count = 0

    def check_neg_risk(self, _token_id: str) -> bool:
        return False

    def get_order_book(self, _token_id: str):
        return {"bids": [[0.49, 100]], "asks": [[0.51, 100]]}

    def post_limit_order(self, token_id: str, price: float, size: int, side: str):
        self.post_count += 1
        order_id = f"order-{self.post_count}"
        self.orders[order_id] = {
            "orderID": order_id,
            "token_id": token_id,
            "status": "live",
            "price": str(price),
            "original_size": str(size),
            "size_matched": "0",
            "side": side,
        }
        return {"success": True, "status": "live", "orderID": order_id}

    def get_order(self, order_id: str):
        return dict(self.orders[order_id])


class ExecutionReconciliationTest(unittest.TestCase):
    def setUp(self):
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()
        create_db_and_tables()
        self.client = FakePolyClient()
        self.engine = ExecutionEngine(
            self.client,
            FakeRiskManager(),
            dry_run=False,
            circuit_breaker=FakeCircuitBreaker(),
        )
        self.engine.register_markets([
            {"token_id": "tok-yes", "condition_id": "cond-1", "outcome": "YES"}
        ])

    def tearDown(self):
        db_engine.dispose()
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

    def test_reconcile_partial_then_full_fill_and_close_position(self):
        buy_response = self.engine.execute_limit_order("tok-yes", 0.45, 10, "BUY", "test-buy")
        self.assertEqual(buy_response["execution_status"], "ACCEPTED")
        self.assertEqual(len(self.engine.get_pending_orders()), 1)

        self.client.orders["order-1"]["size_matched"] = "4"
        self.client.orders["order-1"]["status"] = "live"
        self.engine.reconcile_pending_orders()

        with get_session() as session:
            self.assertEqual(len(session.exec(select(Trade)).all()), 1)
            self.assertEqual(session.exec(select(Position)).one().size, 4.0)

        self.client.orders["order-1"]["size_matched"] = "10"
        self.client.orders["order-1"]["status"] = "matched"
        self.engine.reconcile_pending_orders()

        with get_session() as session:
            trades = session.exec(select(Trade)).all()
            position = session.exec(select(Position)).one()
            self.assertEqual(len(trades), 2)
            self.assertEqual(position.size, 10.0)
            self.assertEqual(position.status, "OPEN")

        sell_response = self.engine.execute_limit_order("tok-yes", 0.60, 10, "SELL", "test-sell")
        self.assertEqual(sell_response["execution_status"], "ACCEPTED")
        self.client.orders["order-2"]["size_matched"] = "10"
        self.client.orders["order-2"]["status"] = "matched"
        self.engine.reconcile_pending_orders()

        with get_session() as session:
            trades = session.exec(select(Trade)).all()
            position = session.exec(select(Position)).one()
            self.assertEqual(len(trades), 3)
            self.assertEqual(position.condition_id, "cond-1")
            self.assertEqual(position.token_id, "tok-yes")
            self.assertEqual(position.size, 0.0)
            self.assertEqual(position.status, "CLOSED")

        self.assertEqual(self.engine.get_pending_orders(), [])


if __name__ == "__main__":
    unittest.main()
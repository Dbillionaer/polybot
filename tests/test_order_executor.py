import os
import unittest
from unittest.mock import Mock

from engine.order_executor import OrderExecutor
from tests.mocks.execution import MockCircuitBreaker, MockPolyClient, MockRiskManager


class OrderExecutorTest(unittest.TestCase):
    def setUp(self):
        self._previous_max_spread = os.environ.get("MAX_SPREAD")
        self.client = MockPolyClient()
        self.breaker = MockCircuitBreaker()
        self.refreshed = 0
        self.attempts = []
        self.accepts = []
        self.errors = []
        self.executor = OrderExecutor(
            client=self.client,
            circuit_breaker=self.breaker,
            refresh_mark_to_market=self._refresh,
            record_strategy_attempt=self.attempts.append,
            record_strategy_error=self._record_error,
        )

    def tearDown(self):
        if self._previous_max_spread is None:
            os.environ.pop("MAX_SPREAD", None)
        else:
            os.environ["MAX_SPREAD"] = self._previous_max_spread

    def _refresh(self):
        self.refreshed += 1
        return {"updated": True}

    def _record_error(self, strategy_name: str, context: str, error):
        self.errors.append((strategy_name, context, str(error)))

    def test_dry_run_returns_simulated_response(self):
        response = self.executor.submit_limit_order(
            token_id="tok-1",
            price=0.5,
            size=10,
            side="BUY",
            strategy_name="test",
            effective_dry_run=True,
            risk_manager=MockRiskManager(),
        )
        self.assertEqual(response["execution_status"], "SIMULATED")
        self.assertEqual(self.breaker.successes, 1)

    def test_live_order_posts_when_checks_pass(self):
        os.environ["MAX_SPREAD"] = "1.0"
        response = self.executor.submit_limit_order(
            token_id="tok-1",
            price=0.5,
            size=10,
            side="BUY",
            strategy_name="test",
            effective_dry_run=False,
            risk_manager=MockRiskManager(),
        )
        self.assertEqual(response["orderID"], "order-1")
        self.assertEqual(self.refreshed, 1)
        self.assertEqual(self.attempts, ["test"])

    def test_spread_too_wide_skips_order(self):
        os.environ["MAX_SPREAD"] = "0.001"
        response = self.executor.submit_limit_order(
            token_id="tok-1",
            price=0.5,
            size=10,
            side="BUY",
            strategy_name="test",
            effective_dry_run=False,
            risk_manager=MockRiskManager(),
        )
        self.assertIsNone(response)
        self.assertEqual(len(self.client.orders), 0)

    def test_cancel_live_order(self):
        self.assertTrue(self.executor.cancel_live_order("order-1"))
        self.assertEqual(self.client.cancelled, ["order-1"])


if __name__ == "__main__":
    unittest.main()

"""Tests for strategies/copy_trading.py — Smart Copy-Trading Strategy."""

import threading
import time
import unittest
from unittest.mock import Mock, patch

from strategies.copy_trading import CopyTradingStrategy


class TestCopyTradingStrategy(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures."""
        self.mock_engine = Mock()
        self.mock_engine.risk_manager = Mock()
        self.mock_engine.dry_run = True
        self.mock_engine.execute_limit_order = Mock()

        self.mock_ws = Mock()
        self.mock_ws.subscribe = Mock()

        self.target_wallet = "0x56687bf447db6ffa42ffe2204a05edaa20f55839"
        self.strategy = CopyTradingStrategy(
            engine=self.mock_engine,
            ws=self.mock_ws,
            target_wallet=self.target_wallet,
            size_multiplier=0.1,
        )

    def test_initialization(self):
        """Test strategy initialization."""
        self.assertEqual(self.strategy.name, "CopyTrading")
        self.assertEqual(self.strategy.target_wallet, self.target_wallet)
        self.assertEqual(self.strategy.size_multiplier, 0.1)

    def test_on_market_update(self):
        """Test that market updates are currently ignored (stub)."""
        data = {"event_type": "book", "market": "0xtoken1"}
        self.strategy.on_market_update(data)
        # Currently a no-op
        self.mock_engine.execute_limit_order.assert_not_called()

    def test_on_trade_update(self):
        """Test that trade updates are currently ignored (stub)."""
        data = {"event_type": "trade", "market": "0xtoken1"}
        self.strategy.on_trade_update(data)
        # Currently a no-op
        self.mock_engine.execute_limit_order.assert_not_called()

    def test_run_starts_monitoring_thread(self):
        """Test that run() starts a daemon monitoring thread."""
        with patch('strategies.copy_trading.threading.Thread') as MockThread:
            self.strategy.run()

            # Should start a daemon thread for monitoring
            MockThread.assert_called_once()
            thread_kwargs = MockThread.call_args[1]
            self.assertTrue(thread_kwargs.get("daemon"))
            # Thread name is not explicitly set in implementation

    def test_copy_trading_loop_structure(self):
        """Test the internal _loop function structure (via mocking)."""
        # This is mainly to document expected behavior since the loop is internal
        self.assertTrue(hasattr(self.strategy, 'run'))
        # The actual loop logic is in a nested function started as daemon thread
        # It should poll Falcon for whale activity and mirror trades


if __name__ == "__main__":
    unittest.main()

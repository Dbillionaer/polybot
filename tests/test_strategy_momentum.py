# Tests for strategies/momentum.py
# Tests for Momentum / High-Frequency scalp strategy

import unittest
from unittest.mock import Mock, MagicMock, patch, call
from collections import deque
import time

from strategies.momentum import MomentumStrategy


class TestMomentumStrategy(unittest.TestCase):
    """Tests for MomentumStrategy."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_engine = Mock()
        self.mock_engine.risk_manager = Mock()
        self.mock_engine.dry_run = True
        self.mock_engine.execute_limit_order = Mock()
        
        self.mock_ws = Mock()
        self.mock_ws.subscribe = Mock()
        
        self.token_ids = ["0xtoken1", "0xtoken2"]
        
        self.strategy = MomentumStrategy(
            engine=self.mock_engine,
            ws=self.mock_ws,
            token_ids=self.token_ids,
            imbalance_ratio=5.0,
            volume_surge_mult=3.0,
            scalp_size=50,
        )

    def test_initialization(self):
        """Test strategy initialization."""
        self.assertEqual(self.strategy.name, "HFM")
        self.assertEqual(self.strategy.token_ids, self.token_ids)
        self.assertEqual(self.strategy.imbalance_ratio, 5.0)
        self.assertEqual(self.strategy.volume_surge_mult, 3.0)
        self.assertEqual(self.strategy.scalp_size, 50)
        self.assertIn("0xtoken1", self.strategy.volume_history)
        self.assertIn("0xtoken2", self.strategy.volume_history)

    def test_on_market_update_non_book_event(self):
        """Test that non-book events are ignored."""
        data = {"event_type": "trade", "market": "0xtoken1"}
        
        self.strategy.on_market_update(data)
        
        self.mock_engine.execute_limit_order.assert_not_called()

    def test_on_market_update_wrong_market(self):
        """Test that updates for unknown markets are ignored."""
        data = {
            "event_type": "book",
            "market": "0xunknowntoken",
            "bids": [[0.45, 100]],
            "asks": [[0.55, 100]],
        }
        
        self.strategy.on_market_update(data)
        
        self.mock_engine.execute_limit_order.assert_not_called()

    def test_on_market_update_empty_book(self):
        """Test handling of empty order book."""
        data = {
            "event_type": "book",
            "market": "0xtoken1",
            "bids": [],
            "asks": [],
        }
        
        self.strategy.on_market_update(data)
        
        self.mock_engine.execute_limit_order.assert_not_called()

    def test_on_market_update_buy_imbalance(self):
        """Test buy order on bid-side imbalance."""
        # Create imbalance: bid depth >> ask depth
        data = {
            "event_type": "book",
            "market": "0xtoken1",
            "bids": [[0.45, 500], [0.44, 400], [0.43, 300]],  # Total: 1200
            "asks": [[0.55, 50], [0.56, 40], [0.57, 30]],   # Total: 120
        }
        
        self.mock_engine.risk_manager.check_trade_allowed.return_value = True
        
        self.strategy.on_market_update(data)
        
        # Should execute buy order
        self.mock_engine.execute_limit_order.assert_called_once()
        call_args = self.mock_engine.execute_limit_order.call_args
        self.assertEqual(call_args[0][0], "0xtoken1")
        self.assertEqual(call_args[0][2], 50)  # scalp_size
        self.assertEqual(call_args[0][3], "BUY")

    def test_on_market_update_sell_imbalance(self):
        """Test sell order on ask-side imbalance."""
        # Create imbalance: ask depth >> bid depth
        data = {
            "event_type": "book",
            "market": "0xtoken1",
            "bids": [[0.45, 50], [0.44, 40], [0.43, 30]],   # Total: 120
            "asks": [[0.55, 500], [0.56, 400], [0.57, 300]],  # Total: 1200
        }
        
        self.mock_engine.risk_manager.check_trade_allowed.return_value = True
        
        self.strategy.on_market_update(data)
        
        # Should execute sell order
        self.mock_engine.execute_limit_order.assert_called_once()
        call_args = self.mock_engine.execute_limit_order.call_args
        self.assertEqual(call_args[0][0], "0xtoken1")
        self.assertEqual(call_args[0][2], 50)  # scalp_size
        self.assertEqual(call_args[0][3], "SELL")

    def test_on_market_update_no_imbalance(self):
        """Test that balanced books don't trigger orders."""
        data = {
            "event_type": "book",
            "market": "0xtoken1",
            "bids": [[0.45, 100], [0.44, 100]],
            "asks": [[0.55, 100], [0.56, 100]],
        }
        
        self.strategy.on_market_update(data)
        
        self.mock_engine.execute_limit_order.assert_not_called()

    def test_on_market_update_risk_check_fails(self):
        """Test that orders are blocked when risk check fails."""
        data = {
            "event_type": "book",
            "market": "0xtoken1",
            "bids": [[0.45, 500], [0.44, 400]],
            "asks": [[0.55, 50]],
        }
        
        self.mock_engine.risk_manager.check_trade_allowed.return_value = False
        
        self.strategy.on_market_update(data)
        
        self.mock_engine.execute_limit_order.assert_not_called()

    def test_on_trade_update_non_trade_event(self):
        """Test that non-trade events are ignored in trade handler."""
        data = {"event_type": "book", "market": "0xtoken1"}
        
        self.strategy.on_trade_update(data)
        
        # Should not add to volume history
        self.assertEqual(len(self.strategy.volume_history["0xtoken1"]), 0)

    def test_on_trade_update_wrong_market(self):
        """Test that trades for unknown markets are ignored."""
        data = {
            "event_type": "trade",
            "market": "0xunknowntoken",
            "size": 100,
        }
        
        self.strategy.on_trade_update(data)
        
        # Should not add to volume history
        self.assertNotIn("0xunknowntoken", self.strategy.volume_history)

    def test_on_trade_update_records_volume(self):
        """Test that trades are recorded in volume history."""
        data = {
            "event_type": "trade",
            "market": "0xtoken1",
            "size": 100,
        }
        
        self.strategy.on_trade_update(data)
        
        # Should add to volume history
        self.assertEqual(len(self.strategy.volume_history["0xtoken1"]), 1)

    def test_on_trade_update_volume_surge_detection(self):
        """Test volume surge detection."""
        # Add 9 historical trades with small sizes
        for i in range(9):
            self.strategy.volume_history["0xtoken1"].append((time.time(), 10))
        
        # Add surge trade (10x average)
        data = {
            "event_type": "trade",
            "market": "0xtoken1",
            "size": 100,  # 10x the average of 10
        }
        
        with patch('strategies.momentum.logger') as mock_logger:
            self.strategy.on_trade_update(data)
            # Logger should have logged the surge
            self.assertTrue(mock_logger.info.called)

    def test_on_trade_update_no_surge(self):
        """Test that normal volume doesn't trigger surge detection."""
        # Add 9 historical trades
        for i in range(9):
            self.strategy.volume_history["0xtoken1"].append((time.time(), 10))
        
        # Add normal trade
        data = {
            "event_type": "trade",
            "market": "0xtoken1",
            "size": 15,  # Not a surge
        }
        
        with patch('strategies.momentum.logger') as mock_logger:
            self.strategy.on_trade_update(data)
            # Logger should not have logged surge
            mock_logger.info.assert_not_called()

    def test_run_subscribes_all(self):
        """Test that run() subscribes to all markets."""
        self.strategy.run()
        
        # Should call subscribe for each token
        self.assertEqual(self.mock_ws.subscribe.call_count, len(self.token_ids))

    def test_custom_imbalance_ratio(self):
        """Test strategy with custom imbalance ratio."""
        strategy = MomentumStrategy(
            engine=self.mock_engine,
            ws=self.mock_ws,
            token_ids=["0xtoken1"],
            imbalance_ratio=10.0,  # Higher threshold
        )
        
        # Create moderate imbalance that wouldn't trigger with ratio=10
        data = {
            "event_type": "book",
            "market": "0xtoken1",
            "bids": [[0.45, 500], [0.44, 400]],  # 900
            "asks": [[0.55, 100]],  # 100, ratio = 9
        }
        
        self.mock_engine.risk_manager.check_trade_allowed.return_value = True
        
        strategy.on_market_update(data)
        
        # Should NOT trigger with ratio=10
        self.mock_engine.execute_limit_order.assert_not_called()

    def test_custom_scalp_size(self):
        """Test strategy with custom scalp size."""
        strategy = MomentumStrategy(
            engine=self.mock_engine,
            ws=self.mock_ws,
            token_ids=["0xtoken1"],
            scalp_size=100,  # Double the default
        )
        
        data = {
            "event_type": "book",
            "market": "0xtoken1",
            "bids": [[0.45, 500], [0.44, 400]],
            "asks": [[0.55, 50]],
        }
        
        self.mock_engine.risk_manager.check_trade_allowed.return_value = True
        
        strategy.on_market_update(data)
        
        call_args = self.mock_engine.execute_limit_order.call_args
        self.assertEqual(call_args[0][2], 100)  # Custom scalp size

    def test_volume_history_maxlen(self):
        """Test that volume history is bounded."""
        # Add more than maxlen items
        for i in range(100):
            self.strategy.volume_history["0xtoken1"].append((time.time(), 10))
        
        # Should be capped at maxlen (60)
        self.assertLessEqual(len(self.strategy.volume_history["0xtoken1"]), 60)


if __name__ == "__main__":
    unittest.main()

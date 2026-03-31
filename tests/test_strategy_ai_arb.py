# Tests for strategies/ai_arb.py
# Tests for AI-powered probability arbitrage using Grok (xAI)

 
import unittest
from unittest.mock import Mock, MagicMock, patch
import os

from strategies.ai_arb import AIArbStrategy


class TestAIArbStrategy(unittest.TestCase):
    """Tests for AIArbStrategy."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_engine = Mock()
        self.mock_engine.risk_manager = Mock()
        self.mock_engine.risk_manager.calculate_kelly_size = Mock(return_value=100)
        self.mock_engine.dry_run = True
        self.mock_engine.execute_limit_order = Mock()
        
        self.mock_ws = Mock()
        self.mock_ws.get_last_price = Mock(return_value=0.5)
        self.mock_ws.subscribe = Mock()
        
        self.market_name = "Will BTC reach $100k by EOY?"
        self.token_id = "0xtoken123"
        
        # Patch environment variable
        self.xai_api_key_patcher = patch.dict(
            XAI_API_KEY="test-api-key"
        )
        
        self.strategy = AIArbStrategy(
            engine=self.mock_engine,
            ws=self.mock_ws,
            market_name=self.market_name,
            token_id=self.token_id,
            edge_threshold=0.12,
        )

    def test_initialization(self):
        """Test strategy initialization."""
        self.assertEqual(self.strategy.market_name, self.market_name)
        self.assertEqual(self.strategy.token_id, self.token_id)
        self.assertEqual(self.strategy.edge_threshold, 0.12)
        self.assertEqual(self.strategy.poll_interval, 1800)

    def test_initialization_without_api_key(self):
        """Test that initialization fails without API key."""
        with patch.dict(XAI_API_KEY=None):
            with self.assertRaises(ValueError):
                AIArbStrategy(
                    engine=self.mock_engine,
                    ws=self.mock_ws,
                    market_name=self.market_name,
                    token_id=self.token_id,
                )

    @patch('strategies.ai_arb.OpenAI')
    def test_get_ai_probability_success(self, mock_openai):
        """Test successful AI probability query."""
        mock_response = Mock()
        mock_response.choices = [
            Mock(message=Mock(content="The probability is 0.45"))
        ]
        mock_openai.return_value = mock_response
        
        result = self.strategy.get_ai_probability()
        
        self.assertIsNot(result)
        self.assertEqual(result, 0.45)
        mock_openai.chat.completions.create.assert_called_once()

    @patch('strategies.ai_arb.OpenAI')
    def test_get_ai_probability_api_error(self, mock_openai):
        """Test handling of API error."""
        mock_openai.chat.completions.create.side_effect = Exception("API error")
        
        result = self.strategy.get_ai_probability()
        
        self.assertIsNone(result)

    @patch('strategies.ai_arb.OpenAI')
    def test_get_ai_probability_invalid_response(self, mock_openai):
        """Test handling of invalid API response."""
        mock_response = Mock()
        mock_response.choices = []
        mock_openai.return_value = mock_response
        
        result = self.strategy.get_ai_probability()
        
        self.assertIsNone(result)

    @patch.object
    def test_evaluate_edge_no_price(self, mock_get_price):
        """Test evaluation when no price is available."""
        mock_get_price.return_value = None
        
        result = self.strategy.evaluate_edge()
        
        self.assertIsNone(result)

    @patch.object
    def test_evaluate_edge_no_probability(self, mock_get_prob):
        """Test evaluation when no probability is available."""
        mock_get_prob.return_value = None
        
        result = self.strategy.evaluate_edge()
        
        self.assertIsNone(result)

    @patch.object
    def test_evaluate_edge_bullish_edge(self, mock_get_price, mock_get_prob, mock_calc_kelly):
        """Test evaluation for bullish edge (AI says 0.45, market says 1.30)."""
        mock_get_price.return_value = 1.30
        mock_get_prob.return_value = 0.45
        mock_calc_kelly.return_value = 100  # Large position
        
        self.strategy.evaluate_edge()
        
        # Should execute BUY order
        self.mock_engine.execute_limit_order.assert_called_once()
        call_args = self.mock_engine.execute_limit_order.call_args
        self.assertEqual(call_args[0], self.token_id)  # token_id
        self.assertEqual(call_args[1], 1.30)  # price
        self.assertEqual(call_args[2], 100)  # size
        self.assertEqual(call_args[3], "BUY")  # side

    @patch.object
    def test_evaluate_edge_bearish_edge_trade_blocked(self, mock_get_price, mock_get_prob, mock_calc_kelly, mock_check_trade):
        """Test that trade is blocked when risk check fails."""
        mock_get_price.return_value = 1.30
        mock_get_prob.return_value = 0.45
        mock_calc_kelly.return_value = 100
        mock_check_trade.return_value = False
        
        result = self.strategy.evaluate_edge()
        
        self.assertFalse(result)
        self.mock_engine.execute_limit_order.assert_not_called()

    @patch.object
    def test_evaluate_edge_bearish_edge_dry_run(self, mock_get_price, mock_get_prob, mock_calc_kelly, mock_check_trade):
        """Test that order is logged in dry-run mode."""
        mock_get_price.return_value = 1.30
        mock_get_prob.return_value = 0.45
        mock_calc_kelly.return_value = 100
        mock_check_trade.return_value = True
        self.mock_engine.dry_run = True
        
        self.strategy.evaluate_edge()
        
        # Should still call execute_limit_order in dry-run mode
        self.mock_engine.execute_limit_order.assert_called_once()

    @patch.object
    def test_evaluate_edge_bearish_edge_live(self, mock_get_price, mock_get_prob, mock_calc_kelly, mock_check_trade):
        """Test that order is executed in live mode."""
        mock_get_price.return_value = 1.30
        mock_get_prob.return_value = 0.45
        mock_calc_kelly.return_value = 100
        mock_check_trade.return_value = True
        self.mock_engine.dry_run = False
        
        self.strategy.evaluate_edge()
        
        # Should call execute_limit_order with dry_run=False
        call_args = self.mock_engine.execute_limit_order.call_args
        self.assertEqual(call_args[5], False)  # dry_run=False

    @patch.object
    def test_evaluate_edge_below_threshold(self, mock_get_price, mock_get_prob, mock_calc_kelly):
        """Test that no trade when edge is below threshold."""
        mock_get_price.return_value = 1.30
        mock_get_prob.return_value = 0.51  # Only 1% edge
        mock_calc_kelly.return_value = 0
        
        result = self.strategy.evaluate_edge()
        
        self.assertIsNone(result)
        self.mock_engine.execute_limit_order.assert_not_called()

    @patch.object
    def test_evaluate_edge_negative_edge(self, mock_get_price, mock_get_prob, mock_calc_kelly):
        """Test that no trade when AI probability is lower than market."""
        mock_get_price.return_value = 1.30
        mock_get_prob.return_value = 0.20  # AI says 20%, market says 1.30
        mock_calc_kelly.return_value = 0
        
        result = self.strategy.evaluate_edge()
        
        self.assertIsNone(result)

    def test_on_market_update_non_book_event(self):
        """Test that non-book events are ignored."""
        data = {"event_type": "trade", "market": self.token_id}
        
        self.strategy.on_market_update(data)
        
        self.mock_ws.get_last_price.assert_not_called()

    def test_on_market_update_wrong_market(self):
        """Test that updates for wrong market are ignored."""
        data = {
            "event_type": "book",
            "market": "0xwrongtoken",
            "bids": [[1.30, 100]],
            "asks": [[1.31, 100]],
        }
        
        self.strategy.on_market_update(data)
        
        self.mock_ws.get_last_price.assert_not_called()

    def test_run_starts_loop(self):
        """Test that run() starts the evaluation loop."""
        with patch.object(self.strategy, '_loop', daemon=True) as mock_loop:
            self.strategy.run()
            
            # Verify loop was started
            mock_loop.assert_called_once()


if __name__ == "__main__":
    unittest.main()

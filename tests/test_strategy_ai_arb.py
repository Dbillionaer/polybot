"""Tests for strategies/ai_arb.py — AI-powered probability arbitrage using Grok (xAI)."""

import json
import os
import unittest
from unittest.mock import MagicMock, Mock, patch

from strategies.ai_arb import AIArbStrategy


def _make_strategy(**overrides):
    engine = Mock()
    engine.risk_manager = Mock()
    engine.risk_manager.calculate_kelly_size = Mock(return_value=0)
    engine.risk_manager.check_trade_allowed = Mock(return_value=True)
    engine.dry_run = True
    engine.execute_limit_order = Mock()

    ws = Mock()
    ws.add_callback = Mock()
    ws.subscribe = Mock()

    defaults = dict(
        engine=engine,
        ws=ws,
        market_name="Will BTC reach $100k by EOY?",
        token_id="0xtoken123",
        edge_threshold=0.12,
        poll_interval_sec=1800,
    )
    defaults.update(overrides)

    with patch("strategies.ai_arb.OpenAI") as MockOpenAI:
        mock_ai_client = Mock()
        MockOpenAI.return_value = mock_ai_client
        strategy = AIArbStrategy(**defaults)
        strategy._ai_client = mock_ai_client
    return strategy, engine, ws


class TestAIArbStrategyInit(unittest.TestCase):

    def test_default_attributes(self):
        s, _, _ = _make_strategy()
        self.assertEqual(s.market_name, "Will BTC reach $100k by EOY?")
        self.assertEqual(s.token_id, "0xtoken123")
        self.assertEqual(s.edge_threshold, 0.12)
        self.assertEqual(s.poll_interval_sec, 1800)
        self.assertEqual(s._current_price, 0.5)
        self.assertEqual(s.name, "AI-Arb")
        self.assertEqual(s.token_ids, ["0xtoken123"])

    def test_ws_callbacks_registered(self):
        s, _, ws = _make_strategy()
        self.assertEqual(ws.add_callback.call_count, 2)
        ws.add_callback.assert_any_call("book", s._dispatch_market_update)
        ws.add_callback.assert_any_call("trades", s._dispatch_trade_update)

    def test_custom_threshold_and_interval(self):
        s, _, _ = _make_strategy(edge_threshold=0.20, poll_interval_sec=600)
        self.assertEqual(s.edge_threshold, 0.20)
        self.assertEqual(s.poll_interval_sec, 600)


class TestGetAiProbability(unittest.TestCase):

    def setUp(self):
        self.s, _, _ = _make_strategy()

    def test_returns_tuple_on_success(self):
        mock_resp = Mock()
        mock_resp.choices = [Mock(message=Mock(content=json.dumps({
            "probability": 0.65,
            "reasoning": "Strong bullish signal",
        })))]
        self.s._ai_client.chat.completions.create = Mock(return_value=mock_resp)

        prob, reasoning = self.s.get_ai_probability()

        self.assertAlmostEqual(prob, 0.65)
        self.assertEqual(reasoning, "Strong bullish signal")
        self.s._ai_client.chat.completions.create.assert_called_once()

    def test_returns_none_tuple_on_api_error(self):
        self.s._ai_client.chat.completions.create = Mock(side_effect=Exception("API error"))

        prob, reasoning = self.s.get_ai_probability()

        self.assertIsNone(prob)
        self.assertEqual(reasoning, "")

    def test_returns_none_tuple_on_empty_choices(self):
        mock_resp = Mock()
        mock_resp.choices = []
        self.s._ai_client.chat.completions.create = Mock(return_value=mock_resp)

        prob, reasoning = self.s.get_ai_probability()

        self.assertIsNone(prob)
        self.assertEqual(reasoning, "")

    def test_returns_none_tuple_on_invalid_json(self):
        mock_resp = Mock()
        mock_resp.choices = [Mock(message=Mock(content="not valid json"))]
        self.s._ai_client.chat.completions.create = Mock(return_value=mock_resp)

        prob, reasoning = self.s.get_ai_probability()

        self.assertIsNone(prob)
        self.assertEqual(reasoning, "")


class TestOnMarketUpdate(unittest.TestCase):

    def setUp(self):
        self.s, _, _ = _make_strategy()

    def test_updates_price_from_book(self):
        data = {
            "event_type": "book",
            "market": "0xtoken123",
            "bids": [[0.45, 100]],
            "asks": [[0.55, 200]],
        }
        self.s.on_market_update(data)
        self.assertAlmostEqual(self.s._current_price, 0.50)

    def test_ignores_non_book_event(self):
        self.s._current_price = 0.42
        data = {"event_type": "trade", "market": "0xtoken123"}
        self.s.on_market_update(data)
        self.assertAlmostEqual(self.s._current_price, 0.42)

    def test_ignores_wrong_market(self):
        self.s._current_price = 0.42
        data = {
            "event_type": "book",
            "market": "0xwrongtoken",
            "bids": [[0.45, 100]],
            "asks": [[0.55, 200]],
        }
        self.s.on_market_update(data)
        self.assertAlmostEqual(self.s._current_price, 0.42)

    def test_no_update_when_no_bids(self):
        self.s._current_price = 0.42
        data = {
            "event_type": "book",
            "market": "0xtoken123",
            "bids": [],
            "asks": [[0.55, 200]],
        }
        self.s.on_market_update(data)
        self.assertAlmostEqual(self.s._current_price, 0.42)

    def test_no_update_when_no_asks(self):
        self.s._current_price = 0.42
        data = {
            "event_type": "book",
            "market": "0xtoken123",
            "bids": [[0.45, 100]],
            "asks": [],
        }
        self.s.on_market_update(data)
        self.assertAlmostEqual(self.s._current_price, 0.42)


class TestEvaluateEdge(unittest.TestCase):

    def setUp(self):
        self.s, self.engine, _ = _make_strategy()

    @patch.object(AIArbStrategy, "get_ai_probability", return_value=(None, ""))
    def test_skips_when_ai_returns_none(self, _mock):
        self.s._current_price = 0.50
        self.s.evaluate_edge()
        self.engine.execute_limit_order.assert_not_called()

    def test_skips_when_price_is_zero(self):
        self.s._current_price = 0.0
        with patch.object(AIArbStrategy, "get_ai_probability") as m:
            self.s.evaluate_edge()
            m.assert_not_called()

    @patch.dict(os.environ, {"BANKROLL_USDC": "2000"})
    @patch.object(AIArbStrategy, "get_ai_probability", return_value=(0.70, "Bullish"))
    def test_bullish_edge_places_buy(self, _mock):
        self.s._current_price = 0.50
        self.engine.risk_manager.calculate_kelly_size = Mock(return_value=50)
        self.engine.risk_manager.check_trade_allowed = Mock(return_value=True)

        self.s.evaluate_edge()

        self.engine.execute_limit_order.assert_called_once()
        args, kwargs = self.engine.execute_limit_order.call_args
        self.assertEqual(args[0], "0xtoken123")  # token_id
        self.assertAlmostEqual(args[1], 0.51)       # price = 0.50 + 0.01
        self.assertEqual(args[2], 50)               # size
        self.assertEqual(args[3], "BUY")            # side
        self.assertEqual(args[4], "AI-Arb")         # strategy name
        self.assertTrue(kwargs.get("dry_run"))

    @patch.dict(os.environ, {"BANKROLL_USDC": "1000"})
    @patch.object(AIArbStrategy, "get_ai_probability", return_value=(0.70, "Bullish"))
    def test_bullish_edge_blocked_by_risk(self, _mock):
        self.s._current_price = 0.50
        self.engine.risk_manager.calculate_kelly_size = Mock(return_value=50)
        self.engine.risk_manager.check_trade_allowed = Mock(return_value=False)

        self.s.evaluate_edge()

        self.engine.execute_limit_order.assert_not_called()

    @patch.dict(os.environ, {"BANKROLL_USDC": "1000"})
    @patch.object(AIArbStrategy, "get_ai_probability", return_value=(0.70, "Bullish"))
    def test_bullish_edge_zero_kelly_size(self, _mock):
        self.s._current_price = 0.50
        self.engine.risk_manager.calculate_kelly_size = Mock(return_value=0)

        self.s.evaluate_edge()

        self.engine.execute_limit_order.assert_not_called()

    @patch.dict(os.environ, {"BANKROLL_USDC": "1000"})
    @patch.object(AIArbStrategy, "get_ai_probability", return_value=(0.51, "Slight edge"))
    def test_below_threshold_no_trade(self, _mock):
        self.s._current_price = 0.50
        self.s.edge_threshold = 0.12

        self.s.evaluate_edge()

        self.engine.execute_limit_order.assert_not_called()

    @patch.dict(os.environ, {"BANKROLL_USDC": "1000"})
    @patch.object(AIArbStrategy, "get_ai_probability", return_value=(0.20, "Bearish"))
    def test_negative_edge_no_buy(self, _mock):
        self.s._current_price = 0.50
        self.s.edge_threshold = 0.12

        self.s.evaluate_edge()

        self.engine.execute_limit_order.assert_not_called()

    @patch.dict(os.environ, {"BANKROLL_USDC": "1000"})
    @patch.object(AIArbStrategy, "get_ai_probability", return_value=(0.70, "Live trade"))
    def test_live_mode_passes_dry_run_false(self, _mock):
        self.s._current_price = 0.50
        self.engine.dry_run = False
        self.engine.risk_manager.calculate_kelly_size = Mock(return_value=50)
        self.engine.risk_manager.check_trade_allowed = Mock(return_value=True)

        self.s.evaluate_edge()

        _, kwargs = self.engine.execute_limit_order.call_args
        self.assertFalse(kwargs.get("dry_run"))


class TestRun(unittest.TestCase):

    def test_run_starts_thread_and_subscribes(self):
        s, _, ws = _make_strategy()
        with patch("strategies.ai_arb.threading.Thread") as MockThread:
            s.run()
            ws.subscribe.assert_called()
            MockThread.assert_called_once()
            kwargs = MockThread.call_args
            self.assertTrue(kwargs[1].get("daemon"))
            self.assertEqual(kwargs[1].get("name"), "AI-Arb-loop")


if __name__ == "__main__":
    unittest.main()

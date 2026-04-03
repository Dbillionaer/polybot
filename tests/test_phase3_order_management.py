import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strategies.amm import AMMStrategy
from strategies.logical_arb import LogicalArbStrategy


class FakeWS:
    def __init__(self):
        self.callbacks = []
        self.subscriptions = []

    def add_callback(self, channel, callback):
        self.callbacks.append((channel, callback))

    def subscribe(self, token_id, channel):
        self.subscriptions.append((token_id, channel))


class FakeRiskManager:
    def check_trade_allowed(self, *_args, **_kwargs):
        return True


class FakeClient:
    def __init__(self):
        self.address = "maker-1"
        self.order_books = {
            "tok-1": {"bids": [[0.49, 100]], "asks": [[0.51, 100]]},
        }

    def get_user_balance(self, _token_id):
        return 0.0

    def get_order_book(self, token_id):
        return self.order_books[token_id]


class FakeEngine:
    def __init__(self):
        self.client = FakeClient()
        self.risk_manager = FakeRiskManager()
        self.dry_run = False
        self.placed_orders = []
        self.cancelled_orders = []
        self.pending_orders = set()

    def execute_limit_order(self, token_id, price, size, side, strategy_name, dry_run=False):
        order_id = f"order-{len(self.placed_orders) + 1}"
        self.placed_orders.append((order_id, token_id, round(price, 3), size, side, strategy_name, dry_run))
        self.pending_orders.add(order_id)
        return {"execution_status": "ACCEPTED", "orderID": order_id}

    def cancel_order(self, order_id, reason=""):
        self.cancelled_orders.append((order_id, reason))
        self.pending_orders.discard(order_id)
        return True

    def is_order_pending(self, order_id):
        return order_id in self.pending_orders


class Phase3OrderManagementTest(unittest.TestCase):
    def test_amm_tracks_quote_ownership_and_replaces_changed_quotes(self):
        engine = FakeEngine()
        ws = FakeWS()
        strategy = AMMStrategy(engine, ws, token_ids="tok-1", spread=0.02, size=10)

        strategy.on_market_update({
            "event_type": "book",
            "market": "tok-1",
            "bids": [[0.49, 100]],
            "asks": [[0.51, 100]],
        })
        self.assertEqual(len(engine.placed_orders), 2)
        self.assertEqual(strategy.active_quotes["tok-1"]["BUY"]["order_id"], "order-1")
        self.assertEqual(strategy.active_quotes["tok-1"]["SELL"]["order_id"], "order-2")

        strategy.on_market_update({
            "event_type": "book",
            "market": "tok-1",
            "bids": [[0.49, 100]],
            "asks": [[0.51, 100]],
        })
        self.assertEqual(len(engine.placed_orders), 2)
        self.assertEqual(engine.cancelled_orders, [])

        strategy.on_market_update({
            "event_type": "book",
            "market": "tok-1",
            "bids": [[0.59, 100]],
            "asks": [[0.61, 100]],
        })
        self.assertEqual(len(engine.cancelled_orders), 2)
        self.assertEqual(len(engine.placed_orders), 4)
        self.assertEqual(strategy.active_quotes["tok-1"]["BUY"]["order_id"], "order-3")
        self.assertEqual(strategy.active_quotes["tok-1"]["SELL"]["order_id"], "order-4")

    def test_logical_arb_only_evaluates_condition_families(self):
        engine = FakeEngine()
        ws = FakeWS()
        strategy = LogicalArbStrategy(
            engine,
            ws,
            markets=[
                {"token_id": "tok-a1", "condition_id": "cond-a"},
                {"token_id": "tok-a2", "condition_id": "cond-a"},
                {"token_id": "tok-b1", "condition_id": "cond-b"},
            ],
            threshold=1.05,
            arb_size=7,
        )

        strategy.on_market_update({"event_type": "price", "market": "tok-a1", "price": 0.50})
        strategy.on_market_update({"event_type": "price", "market": "tok-a2", "price": 0.49})
        strategy.on_market_update({"event_type": "price", "market": "tok-b1", "price": 0.80})

        self.assertEqual(engine.placed_orders, [])

        strategy.on_market_update({"event_type": "price", "market": "tok-a2", "price": 0.58})
        self.assertEqual(len(engine.placed_orders), 1)
        order = engine.placed_orders[0]
        self.assertEqual(order[1], "tok-a2")
        self.assertEqual(order[4], "SELL")


if __name__ == "__main__":
    unittest.main()

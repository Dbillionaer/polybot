import unittest

from engine.fill_reconciler import FillReconciler


class FakeBreaker:
    def __init__(self):
        self.errors = []

    def record_error(self, message: str):
        self.errors.append(message)


class FakeRisk:
    def __init__(self):
        self.mtm = None

    def update_mark_to_market(self, value: float):
        self.mtm = value


class FakeClient:
    def __init__(self):
        self.books = {"tok-1": {"bids": [[0.49, 100]], "asks": [[0.51, 100]]}}
        self.orders = {"o1": {"status": "matched", "size_matched": "10", "price": "0.50"}}

    def get_order_book(self, token_id: str):
        return self.books[token_id]

    def get_order(self, order_id: str):
        return self.orders[order_id]


class FakeTelemetry:
    pass


class FillReconcilerTest(unittest.TestCase):
    def test_extract_mid_price(self):
        mid = FillReconciler.extract_mid_price({"bids": [[0.49, 100]], "asks": [[0.51, 100]]})
        self.assertAlmostEqual(mid, 0.50)

    def test_extract_fill_price(self):
        price = FillReconciler.extract_fill_price({"avg_price": "0.42"}, 0.4)
        self.assertEqual(price, 0.42)


if __name__ == "__main__":
    unittest.main()

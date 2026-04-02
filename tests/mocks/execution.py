"""Shared execution-layer test doubles."""

from __future__ import annotations


class MockCircuitBreaker:
    def __init__(self, *, trading_allowed: bool = True):
        self.trading_allowed = trading_allowed
        self.errors: list[str] = []
        self.successes = 0

    def allows_trading(self) -> bool:
        return self.trading_allowed

    def is_open(self) -> bool:
        return self.trading_allowed

    def record_success(self) -> None:
        self.successes += 1

    def record_error(self, message: str) -> None:
        self.errors.append(message)


class MockRiskManager:
    def __init__(self, *, allowed: bool = True):
        self.allowed = allowed

    def check_trade_allowed(self, *_args, **_kwargs):
        return self.allowed


class MockPolyClient:
    def __init__(self, *, books: dict | None = None):
        self.orders: dict[str, dict] = {}
        self.post_count = 0
        self.books = books or {"tok-1": {"bids": [[0.49, 100]], "asks": [[0.51, 100]]}}
        self.cancelled: list[str] = []

    def check_neg_risk(self, _token_id: str) -> bool:
        return False

    def get_order_book(self, token_id: str):
        return self.books[token_id]

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

    def cancel_order(self, order_id: str):
        self.cancelled.append(order_id)
        return True

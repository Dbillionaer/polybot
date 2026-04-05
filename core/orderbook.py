"""Helpers for reading Polymarket order-book payloads safely."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def get_levels(order_book: Any, side: str) -> list[Any]:
    """Return normalized bid/ask levels from dict or object order books."""
    if isinstance(order_book, Mapping):
        levels = order_book.get(side, [])
    else:
        levels = getattr(order_book, side, [])
    return list(levels or [])


def extract_level_price(level: Any) -> float | None:
    """Read the price component from a common order-book level shape."""
    try:
        if isinstance(level, (list, tuple)) and level:
            return float(level[0])
        if isinstance(level, Mapping):
            if "price" in level:
                return float(level["price"])
            if "px" in level:
                return float(level["px"])
        price_attr = getattr(level, "price", None)
        if price_attr is not None:
            return float(price_attr)
    except (TypeError, ValueError):
        return None
    return None


def extract_level_size(level: Any) -> float | None:
    """Read the size component from a common order-book level shape."""
    try:
        if isinstance(level, (list, tuple)) and len(level) > 1:
            return float(level[1])
        if isinstance(level, Mapping):
            if "size" in level:
                return float(level["size"])
            if "quantity" in level:
                return float(level["quantity"])
            if "qty" in level:
                return float(level["qty"])
        size_attr = getattr(level, "size", None)
        if size_attr is not None:
            return float(size_attr)
        quantity_attr = getattr(level, "quantity", None)
        if quantity_attr is not None:
            return float(quantity_attr)
    except (TypeError, ValueError):
        return None
    return None


def extract_best_bid_ask(order_book: Any) -> tuple[float | None, float | None]:
    """Return the best bid and ask prices from a supported order-book shape."""
    bids = get_levels(order_book, "bids")
    asks = get_levels(order_book, "asks")
    if not bids or not asks:
        return None, None
    return extract_level_price(bids[0]), extract_level_price(asks[0])


def extract_mid_price(order_book: Any) -> float | None:
    """Compute a mid price from the best bid and ask when available."""
    best_bid, best_ask = extract_best_bid_ask(order_book)
    if best_bid is None or best_ask is None:
        return None
    return (best_bid + best_ask) / 2.0

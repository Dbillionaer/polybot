"""CLOB API client wrapper for Polymarket."""

from loguru import logger
from py_clob_client.client import ClobClient
from py_clob_client.order_types import BUY, SELL, OrderArgs


class PolyClient:
    """Wrapper for the Polymarket CLOB client."""

    def __init__(self, clob_client: ClobClient):

        self.clob = clob_client
        self.address = clob_client.get_address()

    def get_user_balance(self, asset_id: str):
        """
        Fetches user balance for a specific asset (USDC or Outcome Token).
        """
        try:
            return self.clob.get_balance(asset_id)
        except Exception as e:
            logger.error(f"Error fetching balance for {asset_id}: {e}")
            return None

    def get_order_book(self, token_id: str):
        """
        Fetches the current order book for a specific token.
        """
        try:
            return self.clob.get_order_book(token_id)
        except Exception as e:
            logger.error(f"Error fetching order book for {token_id}: {e}")
            return None

    def post_limit_order(self, token_id: str, price: float, size: int, side: str):
        """
        Posts a limit order.
        side: 'BUY' or 'SELL'
        """
        try:
            order_side = BUY if side.upper() == "BUY" else SELL
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=order_side
            )
            response = self.clob.create_and_post_order(order_args)
            if response.get("status") == "OK":
                order_id = response.get('orderID')
                logger.success(
                    f"Order posted: {side} {size} shares "
                    f"at {price} (ID: {order_id})"
                )
                return response
            else:

                logger.error(f"Order failed: {response}")
                return response
        except Exception as e:
            logger.error(f"Error posting limit order: {e}")
            return None

    def cancel_order(self, order_id: str):
        """
        Cancels an existing order.
        """
        try:
            response = self.clob.cancel_order(order_id)
            logger.info(f"Cancel order {order_id} response: {response}")
            return response
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return None

    def get_market(self, condition_id: str):
        """
        Fetches market details using the CLOB client.
        """
        try:
            return self.clob.get_market(condition_id)
        except Exception as e:
            logger.error(f"Error fetching market {condition_id}: {e}")
            return None

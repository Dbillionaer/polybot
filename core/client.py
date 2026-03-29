"""CLOB API client wrapper for Polymarket — NegRisk-aware."""

import os
from loguru import logger
from py_clob_client.client import ClobClient
from py_clob_client.order_types import BUY, SELL, OrderArgs

from core.retry import clob_retry
from core.negrisk import is_neg_risk_market, NEG_RISK_ADAPTER_ADDRESS, CTF_CONTRACT_ADDRESS


class PolyClient:
    """
    Wrapper for the Polymarket CLOB client.

    Automatically detects NegRisk markets and:
      - Flags orders with neg_risk=True so the CLOB accepts them.
      - Exposes get_redeem_contract() so the auto-claim scheduler routes
        redemptions correctly (standard CTF vs. NegRisk adapter).
    """

    def __init__(self, clob_client: ClobClient):
        self.clob = clob_client
        self.address = clob_client.get_address()

    # ──────────────────────────────────────────────────────────────────────
    # NegRisk helpers
    # ──────────────────────────────────────────────────────────────────────

    def check_neg_risk(self, token_id: str) -> bool:
        """
        Returns True if this token belongs to a NegRisk (adapter) market.
        Logs a prominent warning on first detection so it's never silent.
        """
        result = is_neg_risk_market(token_id)
        if result:
            logger.warning(
                f"[NegRisk] ⚠️  Token {token_id[:16]}… is a NegRisk market. "
                f"Orders will include neg_risk=True. "
                f"Redemption must use adapter {NEG_RISK_ADAPTER_ADDRESS[:14]}…"
            )
        return result

    def get_redeem_contract(self, token_id: str) -> str:
        """Return the correct redemption contract address for a token."""
        if is_neg_risk_market(token_id):
            return NEG_RISK_ADAPTER_ADDRESS
        return os.getenv("CTF_CONTRACT_ADDRESS", CTF_CONTRACT_ADDRESS)

    # ──────────────────────────────────────────────────────────────────────
    # Balance
    # ──────────────────────────────────────────────────────────────────────

    @clob_retry
    def get_user_balance(self, asset_id: str):
        """Fetches user balance for a specific asset (USDC or Outcome Token)."""
        try:
            return self.clob.get_balance(asset_id)
        except Exception as e:
            logger.error(f"Error fetching balance for {asset_id}: {e}")
            raise  # Let the retry decorator handle it

    # ──────────────────────────────────────────────────────────────────────
    # Order book
    # ──────────────────────────────────────────────────────────────────────

    @clob_retry
    def get_order_book(self, token_id: str):
        """Fetches the current order book for a specific token."""
        try:
            return self.clob.get_order_book(token_id)
        except Exception as e:
            logger.error(f"Error fetching order book for {token_id}: {e}")
            raise

    # ──────────────────────────────────────────────────────────────────────
    # Order placement — NegRisk-aware
    # ──────────────────────────────────────────────────────────────────────

    @clob_retry
    def post_limit_order(self, token_id: str, price: float, size: int, side: str):
        """
        Posts a limit order.  Automatically detects NegRisk markets and
        includes neg_risk=True in OrderArgs so the CLOB accepts it.

        side: 'BUY' or 'SELL'
        """
        try:
            order_side = BUY if side.upper() == "BUY" else SELL
            neg_risk = self.check_neg_risk(token_id)

            # Build OrderArgs — pass neg_risk if the kwarg is supported
            try:
                order_args = OrderArgs(
                    token_id=token_id,
                    price=price,
                    size=size,
                    side=order_side,
                    neg_risk=neg_risk,
                )
            except TypeError:
                # Older py-clob-client versions don't accept neg_risk kwarg
                logger.debug(
                    "[NegRisk] OrderArgs does not accept neg_risk kwarg — "
                    "upgrade py-clob-client >= 1.0.10 for NegRisk markets."
                )
                order_args = OrderArgs(
                    token_id=token_id,
                    price=price,
                    size=size,
                    side=order_side,
                )

            response = self.clob.create_and_post_order(order_args)

            if response.get("status") == "OK":
                order_id = response.get("orderID")
                logger.success(
                    f"Order posted: {side} {size} shares @ {price} "
                    f"(ID: {order_id})"
                    + (" [NegRisk]" if neg_risk else "")
                )
                return response
            else:
                logger.error(f"Order failed: {response}")
                raise RuntimeError(f"CLOB rejected order: {response}")
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"Error posting limit order: {e}")
            raise

    # ──────────────────────────────────────────────────────────────────────
    # Cancel
    # ──────────────────────────────────────────────────────────────────────

    @clob_retry
    def cancel_order(self, order_id: str):
        """Cancels an existing order."""
        try:
            response = self.clob.cancel_order(order_id)
            logger.info(f"Cancel order {order_id} response: {response}")
            return response
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            raise

    # ──────────────────────────────────────────────────────────────────────
    # Market metadata
    # ──────────────────────────────────────────────────────────────────────

    @clob_retry
    def get_market(self, condition_id: str):
        """Fetches market details using the CLOB client."""
        try:
            return self.clob.get_market(condition_id)
        except Exception as e:
            logger.error(f"Error fetching market {condition_id}: {e}")
            raise

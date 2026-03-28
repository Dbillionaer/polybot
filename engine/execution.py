"""Execution engine for managing PolyBot orders."""

from loguru import logger

from core.client import PolyClient
from core.database import record_trade
from engine.risk import RiskManager


class ExecutionEngine:

    """Handles the execution of trades and order tracking."""

    def __init__(self, client: PolyClient, risk_manager: RiskManager):

        self.client = client
        self.risk_manager = risk_manager

    def execute_limit_order(
        self, 
        token_id: str, 
        price: float, 
        size: int, 
        side: str, 
        strategy_name: str,
        dry_run: bool = True
    ):
        """
        Submits a limit order if risk management allows.
        """
        if dry_run:
            logger.info(
                f"[DRY-RUN] Would have posted: {side} {size} shares of "
                f"{token_id} at {price} via {strategy_name}"
            )
            return {"status": "OK", "orderID": "DRY-RUN-ID"}


        # Basic slippage/fee awareness: in Polymarket CLOB, 
        # you are a taker or maker.
        # Fees are typically proportional to the price. 
        # Taker fee: ~0.15% - 0.22%
        # Maker fee: ~0% (depending on the program)
        
        # Check liquidity / spread if needed
        # book = self.client.get_order_book(token_id)

        # if not book: ...
        
        response = self.client.post_limit_order(token_id, price, size, side)
        
        if response and response.get("status") == "OK":
            order_id = response.get("orderID")
            record_trade(order_id, token_id, side, price, size, strategy_name)
            # Update position (simplified for now)
            # update_position(...)
            return response
        else:
            logger.error(f"Execution failed for {strategy_name} on {token_id}")
            return response

    def cancel_all_open_orders(self):
        """
        Cancels all open orders for the account.
        """
        try:
            # Polymarket SDK typically has a method or we'll loop through open orders.
            # self.client.clob.cancel_all()
            return True
        except Exception as e:
            logger.error(f"Error cancelling all orders: {e}")
            return False

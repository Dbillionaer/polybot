"""Smart Copy-Trading Strategy."""

import threading
import time

from loguru import logger

from strategies.base import BaseStrategy


class CopyTradingStrategy(BaseStrategy):
    """
    Monitors a specific highly profitable wallet via Gamma/Web3
    and mimics their trades proportionally.
    """
    def __init__(self, engine, ws, target_wallet: str, size_multiplier: float = 0.1):
        super().__init__(engine, ws, "CopyTrading")
        self.target_wallet = target_wallet
        self.size_multiplier = size_multiplier

    def on_market_update(self, data: dict):
        pass

    def on_trade_update(self, data: dict):
        # We could potentially listen to trades WS for maker_address, but generally
        # on-chain monitoring is better for copy trading as maker won't always trigger.
        pass

    def run(self):
        logger.info("Initializing Copy-Trading Strategy via Falcon Agent 556...")
        from core.data import MarketData
        md = MarketData()

        # Identified Whales
        whale_targets = [
            "0x56687bf447db6ffa42ffe2204a05edaa20f55839", # Theo4
            "0x1f2dd6d473f3e824cd2f8a89d9c69fb96f6ad0cf", # Fredi9999
            "0x78b9ac44a6d7d7a076c14e0ad518b301b63c6b76"  # Len9311238
        ]

        # Verify wallets with Score Agent 584 before starting
        logger.info("Verifying whale metrics via Falcon Wallet 360 Agent...")
        for whale in whale_targets:
            stats = md.get_trader_stats(whale)
            if stats:
                logger.info(f"Target {whale[:8]}: Tracking active.")
            else:
                logger.warning(f"Could not verify {whale[:8]}. Proceeding cautiously.")

        def _loop():
            # Track seen trades
            seen_trades = set()
            while True:
                for target in whale_targets:
                    try:
                        history = md.get_falcon_trade_history(target, window_days=1)
                        if not history or "data" not in history:
                            continue

                        # Loop through recent trades in last 24h
                        for trade in history.get("data", []):
                            trade_id = trade.get("id")
                            if trade_id and trade_id not in seen_trades:
                                seen_trades.add(trade_id)

                                # Process the mirror logic
                                market_id = trade.get("market_id")
                                side = trade.get("side") # Buy/Sell
                                outcome = trade.get("outcome") # Yes/No
                                volume = float(trade.get("size", 0))

                                our_size = int(volume * self.size_multiplier)
                                if our_size > 0:
                                    logger.warning(f"MIRROR TRADE DETECTED: {target[:8]} {side} {our_size} shares of {outcome} on market {market_id[:8]}")
                                    # self.engine.execute_limit_order(market_id, outcome, side, our_size, price)

                    except Exception as e:
                        logger.error(f"Error querying target {target}: {e}")
                time.sleep(60) # Poll every 60 seconds

        threading.Thread(target=_loop, daemon=True).start()

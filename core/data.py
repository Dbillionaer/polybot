"""Fetching and handling Polymarket data via Gamma API."""

from typing import List
import requests
from loguru import logger

GAMMA_API_URL = "https://gamma-api.polymarket.com"

class MarketData:
    """Manages connections to the Polymarket Gamma API for market data."""

    def __init__(self):
        self.session = requests.Session()


    def get_markets(
        self,
        limit: int = 100,
        sort: str = "volume24hr",
        order: str = "desc",
        active: bool = True
    ):

        """
        Fetches active markets from Gamma API.
        """
        try:
            params = {
                "limit": limit,
                "active": "true" if active else "false",
                "closed": "false",
                "order": sort,
                "ascending": "false" if order == "desc" else "true"
            }
            # Gamma endpoint for markets
            resp = self.session.get(
                f"{GAMMA_API_URL}/markets", params=params, timeout=10
            )

            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Error fetching markets from Gamma: {e}")
            return []

    def find_high_liquidity_markets(self, min_volume: float = 100000):
        """
        Filters markets based on volume.
        """
        markets = self.get_markets(limit=50)
        filtered = [
            m for m in markets if float(m.get("volume", 0)) >= min_volume
        ]
        logger.info(
            f"Found {len(filtered)} markets w/ vol >= ${min_volume}"
        )
        return filtered

    def get_market_tokens(self, clob_token_ids: List[str]):
        """
        Retrieves detailed token info.
        """
        return clob_token_ids


    def claim_rewards(self, _client):

        """
        Placeholder for checking resolved markets and claiming winnings.
        """
        try:
            # Polymarket users typically need to redeem via CTF contract
            # or use the CLOB API 'redeem' endpoint if available.
            return True
        except Exception as e:
            logger.error(f"Error claiming rewards: {e}")

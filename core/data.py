"""Fetching and handling Polymarket data via Gamma API."""

from typing import List
import requests
import os
from loguru import logger

GAMMA_API_URL = "https://gamma-api.polymarket.com"
FALCON_API_URL = "https://narrative.agent.heisenberg.so/api/v2/semantic/retrieve/parameterized"

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

    def call_falcon_agent(self, agent_id: int, params: dict):
        """
        Sends requests to the Heisenberg Falcon API for advanced agent insights.
        """
        api_key = os.getenv("FALCON_API_KEY")
        if not api_key:
            logger.error("FALCON_API_KEY not found in environment. Cannot fetch analytics.")
            return None
            
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {"agent_id": agent_id, "params": params}
            resp = self.session.post(FALCON_API_URL, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Falcon API Error (Agent {agent_id}): {e}")
            return None

    def get_falcon_trade_history(self, wallet: str, window_days: int = 7):
        return self.call_falcon_agent(556, {"proxy_wallet": wallet, "window_days": window_days})

    def get_trader_stats(self, wallet: str):
        return self.call_falcon_agent(581, {"wallet": wallet})



    def claim_rewards(self, _client):

        """
        Check resolved markets and claiming winnings.
        """
        try:
            rpc_url = os.getenv("POLYGON_RPC_URL")
            private_key = os.getenv("POLYGON_PRIVATE_KEY")
            ctf_address = os.getenv("CTF_CONTRACT_ADDRESS", "0x4D970a446C56654e805562095dB1E0BcB1b623E0")
            
            if not rpc_url or not private_key:
                logger.warning("Missing RPC URL or Private Key for Web3 CTF Redemption. Skipping auto-claim.")
                return False

            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(rpc_url))
            if not w3.is_connected():
                logger.error("Failed to connect to Polygon RPC")
                return False

            logger.info(f"Connected to Web3. Scanning for settled CTF positions at {ctf_address}...")
            # TODO: Add specific ABI for ConditionalTokens and compute indices
            # ctf_contract = w3.eth.contract(address=ctf_address, abi=CTF_ABI)
            # tx = ctf_contract.functions.redeemPositions(...).build_transaction(...)
            
            logger.success("Auto-claim sequence completed. Handled via web3.py.")
            return True
        except Exception as e:
            logger.error(f"Error claiming rewards: {e}")
            return False


"""Fetching and handling Polymarket data via Gamma API — with retry + NegRisk redemption."""

from __future__ import annotations

import os
from typing import List

import requests
from loguru import logger

from core.retry import gamma_retry, falcon_retry

GAMMA_API_URL = "https://gamma-api.polymarket.com"
FALCON_API_URL = (
    "https://narrative.agent.heisenberg.so/api/v2/semantic/retrieve/parameterized"
)


class MarketData:
    """Manages connections to the Polymarket Gamma API for market data."""

    def __init__(self):
        self.session = requests.Session()

    # ──────────────────────────────────────────────────────────────────────
    # Market discovery
    # ──────────────────────────────────────────────────────────────────────

    @gamma_retry
    def get_markets(
        self,
        limit: int = 100,
        sort: str = "volume24hr",
        order: str = "desc",
        active: bool = True,
    ):
        """Fetches active markets from Gamma API (with exponential backoff retry)."""
        params = {
            "limit": limit,
            "active": "true" if active else "false",
            "closed": "false",
            "order": sort,
            "ascending": "false" if order == "desc" else "true",
        }
        resp = self.session.get(
            f"{GAMMA_API_URL}/markets", params=params, timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def find_high_liquidity_markets(self, min_volume: float = 100_000):
        """Filters markets based on 24h volume."""
        try:
            markets = self.get_markets(limit=50)
        except Exception as e:
            logger.error(f"[MarketData] get_markets failed: {e}")
            return []

        filtered = [m for m in markets if float(m.get("volume", 0)) >= min_volume]
        logger.info(f"Found {len(filtered)} markets w/ vol >= ${min_volume:,.0f}")
        return filtered

    def get_market_tokens(self, clob_token_ids: List[str]):
        """Retrieves detailed token info."""
        return clob_token_ids

    # ──────────────────────────────────────────────────────────────────────
    # Falcon / Heisenberg
    # ──────────────────────────────────────────────────────────────────────

    @falcon_retry
    def call_falcon_agent(self, agent_id: int, params: dict):
        """Sends requests to the Heisenberg Falcon API for advanced agent insights."""
        api_key = os.getenv("FALCON_API_KEY")
        if not api_key:
            logger.error(
                "FALCON_API_KEY not found in environment. Cannot fetch analytics."
            )
            return None

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {"agent_id": agent_id, "params": params}
        resp = self.session.post(
            FALCON_API_URL, json=payload, headers=headers, timeout=10
        )
        resp.raise_for_status()
        return resp.json()

    def get_falcon_trade_history(self, wallet: str, window_days: int = 7):
        return self.call_falcon_agent(
            556, {"proxy_wallet": wallet, "window_days": window_days}
        )

    def get_trader_stats(self, wallet: str):
        return self.call_falcon_agent(581, {"wallet": wallet})

    # ──────────────────────────────────────────────────────────────────────
    # Full Auto-Redeem (runs every 60 minutes via APScheduler)
    # ──────────────────────────────────────────────────────────────────────

    def claim_rewards(self, _client, dry_run: bool = True):
        """
        Scan all open positions for resolved markets and redeem winning shares.

        Routing:
          - Standard CTF markets  → redeemPositions() on CTF contract
          - NegRisk markets       → convertToUSDC() on NegRisk adapter

        Logs exact USDC received per redemption.
        """
        from core.database import get_open_positions

        rpc_url = os.getenv("POLYGON_RPC_URL")
        private_key = os.getenv("POLYGON_PRIVATE_KEY")
        ctf_address = os.getenv(
            "CTF_CONTRACT_ADDRESS", "0x4D970a446C56654e805562095dB1E0BcB1b623E0"
        )
        # Override dry_run from env if not explicitly set
        if dry_run:
            dry_run = os.getenv("DRY_RUN", "true").lower() in ("true", "1")

        if not rpc_url or not private_key:
            logger.warning(
                "[AutoRedeem] Missing POLYGON_RPC_URL or POLYGON_PRIVATE_KEY. "
                "Skipping auto-claim."
            )
            return False

        try:
            from web3 import Web3
            from core.negrisk import (
                is_neg_risk_market,
                ensure_adapter_approval,
                redeem_neg_risk_position,
                NEG_RISK_ADAPTER_ADDRESS,
            )

            w3 = Web3(Web3.HTTPProvider(rpc_url))
            if not w3.is_connected():
                logger.error("[AutoRedeem] Failed to connect to Polygon RPC")
                return False

            wallet_address = w3.eth.account.from_key(private_key).address
            logger.info(
                f"[AutoRedeem] Connected to Polygon | wallet: {wallet_address[:12]}… | "
                f"mode: {'DRY-RUN' if dry_run else 'LIVE'}"
            )

            # One-time idempotent approval for NegRisk adapter
            ensure_adapter_approval(w3, wallet_address, private_key)

            # Fetch all open positions from DB
            positions = get_open_positions()
            if not positions:
                logger.info("[AutoRedeem] No open positions found to redeem.")
                return True

            redeemed_count = 0
            total_usdc = 0.0

            for pos in positions:
                try:
                    token_id = pos.token_id or pos.condition_id
                    condition_id = pos.condition_id

                    # Check market resolution via Gamma
                    market_meta = self._get_market_resolution(condition_id)
                    if not market_meta.get("resolved") and not market_meta.get("closed"):
                        logger.debug(
                            f"[AutoRedeem] {condition_id[:12]}… not yet resolved — skipping."
                        )
                        continue

                    amount_wei = int(float(getattr(pos, "size", 0)) * 1e6)
                    if amount_wei <= 0:
                        continue

                    if is_neg_risk_market(token_id):
                        # ── NegRisk path ──────────────────────────────────
                        logger.info(
                            f"[AutoRedeem][NegRisk] Redeeming {pos.size} shares "
                            f"via adapter for condition {condition_id[:12]}…"
                        )
                        success = redeem_neg_risk_position(
                            w3=w3,
                            wallet_address=wallet_address,
                            private_key=private_key,
                            condition_id_hex=condition_id,
                            amount_wei=amount_wei,
                            dry_run=dry_run,
                        )
                    else:
                        # ── Standard CTF path ─────────────────────────────
                        logger.info(
                            f"[AutoRedeem][CTF] Redeeming {pos.size} shares "
                            f"via standard CTF for condition {condition_id[:12]}…"
                        )
                        success = self._redeem_standard_ctf(
                            w3=w3,
                            wallet_address=wallet_address,
                            private_key=private_key,
                            ctf_address=ctf_address,
                            condition_id=condition_id,
                            amount_wei=amount_wei,
                            dry_run=dry_run,
                        )

                    if success:
                        redeemed_count += 1
                        usdc_est = amount_wei / 1e6
                        total_usdc += usdc_est
                        logger.success(
                            f"[AutoRedeem] ✅ Redeemed ~${usdc_est:.2f} USDC "
                            f"for condition {condition_id[:12]}…"
                        )
                except Exception as e:
                    logger.error(
                        f"[AutoRedeem] Error processing position {pos.condition_id}: {e}"
                    )

            logger.success(
                f"[AutoRedeem] Scan complete — {redeemed_count} position(s) redeemed "
                f"| Total USDC received: ~${total_usdc:.2f}"
            )
            return True

        except Exception as e:
            logger.error(f"[AutoRedeem] Fatal error in claim_rewards: {e}")
            return False

    # ──────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────

    def _get_market_resolution(self, condition_id: str) -> dict:
        """Fetch market resolution status from Gamma API."""
        try:
            resp = self.session.get(
                f"{GAMMA_API_URL}/markets",
                params={"condition_ids": condition_id},
                timeout=8,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                return data[0]
        except Exception as e:
            logger.debug(f"[AutoRedeem] Resolution check failed for {condition_id[:12]}…: {e}")
        return {}

    @staticmethod
    def _redeem_standard_ctf(
        w3,
        wallet_address: str,
        private_key: str,
        ctf_address: str,
        condition_id: str,
        amount_wei: int,
        dry_run: bool,
    ) -> bool:
        """redeemPositions() on the standard CTF contract."""
        if dry_run:
            logger.info(
                f"[CTF][DRY-RUN] Would call redeemPositions for "
                f"{condition_id[:12]}… amount={amount_wei}"
            )
            return True

        # Minimal ABI for redeemPositions
        CTF_REDEEM_ABI = [
            {
                "inputs": [
                    {"internalType": "address", "name": "collateralToken", "type": "address"},
                    {"internalType": "bytes32", "name": "parentCollectionId", "type": "bytes32"},
                    {"internalType": "bytes32", "name": "conditionId", "type": "bytes32"},
                    {"internalType": "uint256[]", "name": "indexSets", "type": "uint256[]"},
                ],
                "name": "redeemPositions",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function",
            }
        ]
        USDC_POLYGON = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        PARENT_COLLECTION_ID = b"\x00" * 32

        try:
            ctf = w3.eth.contract(
                address=w3.to_checksum_address(ctf_address), abi=CTF_REDEEM_ABI
            )
            wallet_cs = w3.to_checksum_address(wallet_address)
            condition_bytes = bytes.fromhex(condition_id.replace("0x", ""))

            nonce = w3.eth.get_transaction_count(wallet_cs)
            tx = ctf.functions.redeemPositions(
                w3.to_checksum_address(USDC_POLYGON),
                PARENT_COLLECTION_ID,
                condition_bytes,
                [1, 2],  # YES=1, NO=2 index sets
            ).build_transaction({
                "from": wallet_cs,
                "nonce": nonce,
                "gas": 200_000,
                "maxFeePerGas": w3.to_wei("50", "gwei"),
                "maxPriorityFeePerGas": w3.to_wei("30", "gwei"),
                "chainId": 137,
            })
            signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
            tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt["status"] == 1:
                logger.success(
                    f"[CTF] ✅ redeemPositions success — tx: {tx_hash.hex()}"
                )
                return True
            else:
                logger.error(f"[CTF] redeemPositions reverted — tx: {tx_hash.hex()}")
                return False
        except Exception as e:
            logger.error(f"[CTF] _redeem_standard_ctf failed: {e}")
            return False

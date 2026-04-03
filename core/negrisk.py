"""
NegRisk Adapter support for Polymarket.

Many Polymarket markets (especially politics / sports multi-outcome) use the
official NegRisk CTF Adapter contract instead of the standard Conditional-Token
Framework (CTF).  Standard redeemPositions() WILL FAIL on these markets.

Key differences:
  - Orders need neg_risk=True passed to the CLOB client.
  - Redemption must call convertToUSDC() on the adapter, not redeemPositions on CTF.
  - The adapter needs a one-time ERC-1155 approval from the wallet before first use.

References:
  Adapter contract: 0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296 (Polygon mainnet)
  CTF contract:     0x4D970a446C56654e805562095dB1E0BcB1b623E0 (Polygon mainnet)
"""

from __future__ import annotations

import os
from functools import lru_cache

import requests
from loguru import logger

# ── Contract addresses ────────────────────────────────────────────────────────
NEG_RISK_ADAPTER_ADDRESS = os.getenv(
    "NEG_RISK_ADAPTER_ADDRESS",
    "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"
)
CTF_CONTRACT_ADDRESS = os.getenv(
    "CTF_CONTRACT_ADDRESS",
    "0x4D970a446C56654e805562095dB1E0BcB1b623E0"
)
GAMMA_API_URL = "https://gamma-api.polymarket.com"


# ── Minimal ABIs for on-chain calls ───────────────────────────────────────────

# ERC-1155 setApprovalForAll (needed so adapter can move CTF tokens on our behalf)
ERC1155_APPROVAL_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "operator", "type": "address"},
            {"internalType": "bool", "name": "approved", "type": "bool"},
        ],
        "name": "setApprovalForAll",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "account", "type": "address"},
            {"internalType": "address", "name": "operator", "type": "address"},
        ],
        "name": "isApprovedForAll",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# NegRisk adapter — convertToUSDC converts winning outcome tokens → USDC
NEG_RISK_ADAPTER_ABI = [
    {
        # Convert a winning outcome token position into USDC directly
        "inputs": [
            {"internalType": "bytes32", "name": "conditionId", "type": "bytes32"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "convertToUSDC",
        "outputs": [{"internalType": "uint256", "name": "usdcAmount", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        # Merge opposing YES/NO positions back into USDC (NegRisk version)
        "inputs": [
            {"internalType": "bytes32", "name": "conditionId", "type": "bytes32"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "mergePositions",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


# ── Market detection ──────────────────────────────────────────────────────────

@lru_cache(maxsize=512)
def _fetch_market_meta(token_id: str) -> dict[str, object]:
    """
    Fetch market metadata from Gamma API.  Cached per token_id to avoid hammering.
    Returns {} on any failure.
    """
    try:
        resp = requests.get(
            f"{GAMMA_API_URL}/markets",
            params={"clob_token_ids": token_id},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning(f"[NegRisk] Gamma lookup failed for {token_id[:10]}…: {e}")
    return {}


def is_neg_risk_market(token_id: str) -> bool:
    """
    Returns True if this token belongs to a NegRisk market.
    Detection order:
      1. Gamma API field neg_risk == True
      2. negRisk flag in response keys (camelCase variant)
      3. Presence of NEG_RISK_ADAPTER_ADDRESS in fpmm / resolver fields
    """
    meta = _fetch_market_meta(token_id)
    if not meta:
        return False

    # Direct boolean flags
    if meta.get("neg_risk") is True or meta.get("negRisk") is True:
        logger.debug(f"[NegRisk] ✓ Detected neg_risk market via flag: {token_id[:16]}…")
        return True

    # String-based partial match (future-proof)
    meta_str = str(meta).lower()
    if NEG_RISK_ADAPTER_ADDRESS.lower() in meta_str or "negrisk" in meta_str:
        logger.debug(f"[NegRisk] ✓ Detected neg_risk market via string match: {token_id[:16]}…")
        return True

    return False


def get_redeem_contract(token_id: str) -> str:
    """Return the correct redeem contract address for a given token."""
    if is_neg_risk_market(token_id):
        return NEG_RISK_ADAPTER_ADDRESS
    return CTF_CONTRACT_ADDRESS


# ── On-chain helpers ──────────────────────────────────────────────────────────

def ensure_adapter_approval(w3, wallet_address: str, private_key: str) -> bool:
    """
    One-time idempotent ERC-1155 setApprovalForAll so the NegRisk adapter
    can move CTF tokens on behalf of our wallet.

    Safe to call every startup — skips the tx if already approved.
    """
    try:
        ctf = w3.eth.contract(
            address=w3.to_checksum_address(CTF_CONTRACT_ADDRESS),
            abi=ERC1155_APPROVAL_ABI,
        )
        adapter_cs = w3.to_checksum_address(NEG_RISK_ADAPTER_ADDRESS)
        wallet_cs = w3.to_checksum_address(wallet_address)

        already_approved = ctf.functions.isApprovedForAll(wallet_cs, adapter_cs).call()
        if already_approved:
            logger.info("[NegRisk] Adapter approval already set — skipping tx.")
            return True

        logger.info(
            f"[NegRisk] ⚙  Setting ERC-1155 approval for adapter {NEG_RISK_ADAPTER_ADDRESS[:14]}…"
        )
        nonce = w3.eth.get_transaction_count(wallet_cs)
        tx = ctf.functions.setApprovalForAll(adapter_cs, True).build_transaction({
            "from": wallet_cs,
            "nonce": nonce,
            "gas": 80_000,
            "maxFeePerGas": w3.to_wei("50", "gwei"),
            "maxPriorityFeePerGas": w3.to_wei("30", "gwei"),
            "chainId": 137,
        })
        signed = w3.eth.account.sign_transaction(tx, private_key=private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        if receipt["status"] == 1:
            logger.success(
                f"[NegRisk] ✅ Adapter approval granted — tx: {tx_hash.hex()}"
            )
            return True
        else:
            logger.error(f"[NegRisk] Approval tx reverted: {tx_hash.hex()}")
            return False
    except Exception as e:
        logger.error(f"[NegRisk] ensure_adapter_approval failed: {e}")
        return False


def redeem_neg_risk_position(
    w3,
    wallet_address: str,
    private_key: str,
    condition_id_hex: str,
    amount_wei: int,
    dry_run: bool = True,
) -> bool:
    """
    Calls convertToUSDC() on the NegRisk adapter for a settled winning position.
    Returns True on success.
    """
    if dry_run:
        logger.info(
            f"[NegRisk][DRY-RUN] Would call convertToUSDC for condition "
            f"{condition_id_hex[:12]}… amount={amount_wei}"
        )
        return True

    try:
        adapter = w3.eth.contract(
            address=w3.to_checksum_address(NEG_RISK_ADAPTER_ADDRESS),
            abi=NEG_RISK_ADAPTER_ABI,
        )
        wallet_cs = w3.to_checksum_address(wallet_address)
        condition_bytes = bytes.fromhex(condition_id_hex.replace("0x", ""))

        nonce = w3.eth.get_transaction_count(wallet_cs)
        tx = adapter.functions.convertToUSDC(condition_bytes, amount_wei).build_transaction({
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

        usdc_received_raw = receipt.get("logs", [{}])[0].get("data", "0x0")
        try:
            usdc_received = int(usdc_received_raw, 16) / 1e6
        except Exception:
            usdc_received = 0.0

        if receipt["status"] == 1:
            logger.success(
                f"[NegRisk] ✅ Redeemed via adapter — "
                f"USDC received: ${usdc_received:.4f} | tx: {tx_hash.hex()}"
            )
            return True
        else:
            logger.error(f"[NegRisk] convertToUSDC reverted: {tx_hash.hex()}")
            return False
    except Exception as e:
        logger.error(f"[NegRisk] redeem_neg_risk_position failed: {e}")
        return False

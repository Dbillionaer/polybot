"""Authentication module for PolyBot."""

import os
from dotenv import load_dotenv

from loguru import logger
from eth_account import Account
from py_clob_client.client import ClobClient

load_dotenv()

def get_polygon_account():
    """Get polygon account from private key."""
    pk = os.getenv("POLYGON_PRIVATE_KEY")
    if not pk or pk == "0x...":
        raise ValueError("POLYGON_PRIVATE_KEY not set in .env")
    return Account.from_key(pk)

def initialize_clob_client():

    """
    Initializes the Polymarket CLOB Client with L1/L2 credentials.
    """
    host = "https://clob.polymarket.com"
    chain_id = 137


    pk = os.getenv("POLYGON_PRIVATE_KEY")
    api_key = os.getenv("POLY_API_KEY")
    api_secret = os.getenv("POLY_API_SECRET")
    api_passphrase = os.getenv("POLY_API_PASSPHRASE")

    # Initialize with PK for L1 operations (signing)
    client = ClobClient(
        host=host,
        chain_id=chain_id,
        key=pk
    )

    # Derive or use existing L2 credentials
    if not (api_key and api_secret and api_passphrase):
        logger.info(
            "L2 credentials missing. Deriving from L1 private key..."
        )
        creds = client.create_or_derive_api_creds()
        logger.success("Successfully derived L2 credentials.")
        # Note: In production, save these to .env to avoid signing every time

        api_key = creds.api_key

        api_secret = creds.api_secret
        api_passphrase = creds.api_passphrase


    client.set_api_creds(api_key, api_secret, api_passphrase)
    logger.info(f"CLOB Client initialized: {client.get_address()}")

    return client

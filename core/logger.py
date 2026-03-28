"""Logging configuration and alert integrations."""

import os
import sys

import requests
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# Configure loguru
logger.remove()

_log_format = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)
logger.add(sys.stderr, level="INFO", format=_log_format)
logger.add("logs/bot.log", rotation="10 MB", level="DEBUG")


def send_telegram_alert(message: str):
    """Sends a message to the configured Telegram chat."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": f"🤖 *PolyBot Alert*:\n{message}",
                "parse_mode": "Markdown"
            }
            requests.post(url, json=payload, timeout=5)
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Telegram alert: {e}")


def send_discord_alert(message: str):
    """Sends a message to the configured Discord webhook."""
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if webhook_url:
        try:
            payload = {"content": f"🚀 **PolyBot Alert**:\n{message}"}
            requests.post(webhook_url, json=payload, timeout=5)
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Discord alert: {e}")


def alert(message: str, level: str = "info"):
    """
    Sends alerts to configured channels and logs the message.
    """
    if level == "error":

        logger.error(message)
    elif level == "success":
        logger.success(message)
    else:
        logger.info(message)

    # Send to external channels
    send_telegram_alert(message)
    send_discord_alert(message)

"""WebSocket module for connecting to Polymarket."""

import asyncio
import json
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import websockets
from loguru import logger
from websockets.asyncio.client import ClientConnection


class PolyWebSocket:
    """Manages WebSocket connections and subscriptions to Polymarket."""

    def __init__(

        self,
        uri: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    ) -> None:
        self.uri = uri
        self.subscriptions: list[dict[str, str]] = []
        self.callbacks: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self._subscription_keys: set[tuple[str, str]] = set()
        self._callback_keys: dict[str, set[tuple[int, ...]]] = {}
        self.is_running = False
        self.is_connected = False
        self.last_message_at: datetime | None = None
        self.last_error: str | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._websocket: ClientConnection | None = None

    @staticmethod
    def _callback_identity(callback: Callable[[dict[str, Any]], None]) -> tuple[int, ...]:
        """Create a stable identity for functions and bound methods."""
        bound_self = getattr(callback, "__self__", None)
        bound_func = getattr(callback, "__func__", None)
        if bound_self is not None and bound_func is not None:
            return (id(bound_self), id(bound_func))
        return (id(callback),)

    def add_callback(self, channel: str, callback: Callable[[dict[str, Any]], None]) -> bool:
        """Adds a callback function for a specific channel."""
        if channel not in self.callbacks:

            self.callbacks[channel] = []
            self._callback_keys[channel] = set()
        callback_key = self._callback_identity(callback)
        if callback_key in self._callback_keys[channel]:
            logger.debug(f"WebSocket callback already registered for channel={channel}")
            return False
        self._callback_keys[channel].add(callback_key)
        self.callbacks[channel].append(callback)
        return True

    def subscribe(self, market_id: str, channel: str = "book") -> bool:
        """Queues a subscription for the given market and channel."""
        market_key = str(market_id)
        channel_key = str(channel)
        subscription_key = (channel_key, market_key)
        if subscription_key in self._subscription_keys:
            logger.debug(f"WebSocket subscription already queued for {channel_key}:{market_key[:12]}…")
            return False

        sub = {
            "type": "subscribe",

            "channel": channel_key,
            "market": market_key
        }
        self._subscription_keys.add(subscription_key)
        self.subscriptions.append(sub)
        if self._loop and self._loop.is_running() and self._websocket and self.is_connected:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._send_subscription(sub), self._loop
                )
                future.add_done_callback(self._log_subscription_result)
            except RuntimeError as exc:
                logger.debug(f"WebSocket subscription enqueue skipped: {exc}")
        return True

    def status_summary(self) -> dict[str, Any]:
        """Expose websocket health and deduplicated subscription counts."""
        return {
            "is_running": self.is_running,
            "is_connected": self.is_connected,
            "subscription_count": len(self.subscriptions),
            "callback_channels": {channel: len(callbacks) for channel, callbacks in self.callbacks.items()},
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "last_error": self.last_error,
        }

    async def _send_subscription(self, sub: dict[str, Any]) -> None:
        """Send a subscription immediately when a websocket is active."""
        if self._websocket is None:
            return
        await self._websocket.send(json.dumps(sub))

    @staticmethod
    def _log_subscription_result(future: Any) -> None:
        """Log asynchronous subscription delivery failures without crashing callers."""
        try:
            future.result()
        except Exception as exc:
            logger.debug(f"WebSocket subscription send failed: {exc}")

    async def _run(self) -> None:
        while self.is_running:
            try:
                async with websockets.connect(self.uri) as websocket:
                    self._websocket = websocket
                    self.is_connected = True
                    self.last_error = None
                    logger.info(f"Connected to WebSocket: {self.uri}")

                    # Send all subscriptions
                    for sub in self.subscriptions:
                        await self._send_subscription(sub)

                    while self.is_running:
                        message = await websocket.recv()
                        self.last_message_at = datetime.now(timezone.utc)
                        data = json.loads(message)

                        channel = data.get("channel")
                        if not channel and data.get("event_type") == "trade":
                            channel = "trades"
                        elif not channel and data.get("event_type"):
                            channel = data.get("event_type")

                        if "event_type" not in data and channel:
                            data["event_type"] = "trade" if channel == "trades" else channel

                        if channel in self.callbacks:
                            for cb in self.callbacks[channel]:
                                try:
                                    cb(data)
                                except Exception as e:
                                    logger.error(
                                        f"Error in WS callback: {e}"
                                    )

            except Exception as e:
                self.is_connected = False
                self.last_error = str(e)
                self._websocket = None
                logger.error(
                    f"WebSocket connection error: {e}. Retrying in 5s..."
                )
                await asyncio.sleep(5)
            finally:
                self.is_connected = False
                self._websocket = None

    def start(self) -> None:
        """Starts the WebSocket connection in a separate thread."""
        self.is_running = True

        self._thread = threading.Thread(
            target=self._start_event_loop, daemon=True
        )
        self._thread.start()

    def _start_event_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._run())

    def stop(self) -> None:
        """Stops the WebSocket connection."""
        self.is_running = False
        self.is_connected = False
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)

"""WebSocket module for connecting to Polymarket."""

import asyncio
import json
import threading
from typing import Callable, Dict, List

import websockets
from loguru import logger


class PolyWebSocket:
    """Manages WebSocket connections and subscriptions to Polymarket."""

    def __init__(

        self,
        uri: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    ):
        self.uri = uri
        self.subscriptions: List[Dict] = []
        self.callbacks: Dict[str, List[Callable]] = {}
        self.is_running = False
        self._loop = None
        self._thread = None

    def add_callback(self, channel: str, callback: Callable):
        """Adds a callback function for a specific channel."""
        if channel not in self.callbacks:

            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)

    def subscribe(self, market_id: str, channel: str = "book"):
        """Queues a subscription for the given market and channel."""
        sub = {
            "type": "subscribe",

            "channel": channel,
            "market": market_id
        }
        self.subscriptions.append(sub)

    async def _run(self):
        while self.is_running:
            try:
                async with websockets.connect(self.uri) as websocket:
                    logger.info(f"Connected to WebSocket: {self.uri}")

                    # Send all subscriptions
                    for sub in self.subscriptions:
                        await websocket.send(json.dumps(sub))

                    while self.is_running:
                        message = await websocket.recv()
                        data = json.loads(message)

                        channel = data.get("channel")
                        if channel in self.callbacks:
                            for cb in self.callbacks[channel]:
                                try:
                                    cb(data)
                                except Exception as e:
                                    logger.error(
                                        f"Error in WS callback: {e}"
                                    )

            except Exception as e:
                logger.error(
                    f"WebSocket connection error: {e}. Retrying in 5s..."
                )
                await asyncio.sleep(5)

    def start(self):
        """Starts the WebSocket connection in a separate thread."""
        self.is_running = True

        self._thread = threading.Thread(
            target=self._start_event_loop, daemon=True
        )

        self._thread.start()

    def _start_event_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._run())

    def stop(self):
        """Stops the WebSocket connection."""
        self.is_running = False
        if self._loop:

            self._loop.stop()

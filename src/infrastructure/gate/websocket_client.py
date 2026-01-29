"""Gate.io Futures WebSocket client for real-time data."""

import asyncio
import json
import logging
import time
import threading
from typing import Any, Callable, Dict, List, Optional

from core.config import Config
from core.logging_config import setup_logging

logger = setup_logging()

import websocket as ws_client


class GateWebSocketClient:
    """WebSocket client for Gate.io Futures API."""

    def __init__(self, config: Config):
        self.config = config
        self.ws: Optional[ws_client.WebSocketApp] = None
        self.is_connected = False
        self.subscriptions: Dict[str, Callable] = {}
        self.message_handlers: Dict[str, Callable] = {}
        self.ping_thread: Optional[threading.Thread] = None
        self.event = threading.Event()
        self.event_loop = None  # Store reference to main event loop

    async def connect(self) -> bool:
        """Connect to Gate.io WebSocket."""
        try:
            # Gate.io WebSocket URL for futures (USDT settled)
            ws_url = "wss://fx-ws.gateio.ws/v4/ws/usdt"
            logger.info(f"Connecting to Gate.io WebSocket: {ws_url}")

            # Store reference to current event loop for thread-safe async calls
            self.event_loop = asyncio.get_running_loop()

            # Custom headers as per Gate.io documentation
            custom_headers = {"X-Gate-Size-Decimal": "1"}

            # Create WebSocket connection
            self.ws = ws_client.WebSocketApp(
                ws_url,
                header=custom_headers,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )

            # Start WebSocket in a separate thread
            ws_thread = threading.Thread(target=self._run_websocket, daemon=True)
            ws_thread.start()

            # Wait for connection to establish
            timeout = 10
            start_time = time.time()
            while not self.is_connected and (time.time() - start_time) < timeout:
                await asyncio.sleep(0.1)

            if self.is_connected:
                return True
            else:
                logger.error("Gate.io WebSocket connection timeout")
                return False

        except Exception as e:
            logger.error(f"Failed to connect to Gate.io WebSocket: {e}")
            return False

    def _run_websocket(self):
        """Run WebSocket in separate thread."""
        try:
            self.ws.run_forever(ping_interval=10)
        except Exception as e:
            logger.error(f"Gate.io WebSocket thread error: {e}")

    async def disconnect(self) -> None:
        """Disconnect from Gate.io WebSocket."""
        self.is_connected = False
        self.event.set()  # Stop ping thread

        if self.ws:
            self.ws.close()

        logger.info("Disconnected from Gate.io WebSocket")

    async def reconnect(self) -> bool:
        """Reconnect to Gate.io WebSocket."""
        logger.info("Reconnecting to Gate.io WebSocket...")
        await self.disconnect()
        await asyncio.sleep(1)
        if not await self.connect():
            return False
        # Re-subscribe to previous subscriptions
        callback = self.message_handlers.get("futures.tickers")
        if callback:
            await self.subscribe_tickers(callback)
        return True

    async def subscribe_tickers(self, callback: Callable[[Dict[str, Any]], None]) -> bool:
        """Subscribe to futures ticker updates."""
        try:
            if not self.is_connected or not self.ws:
                logger.error("Gate.io WebSocket not connected")
                return False

            # Subscribe to futures tickers (following Gate.io documentation format)
            current_time = int(time.time())
            subscription_message = {
                "time": current_time,
                "channel": "futures.tickers",
                "event": "subscribe",
                "payload": ["!all"]  # Subscribe to all futures tickers
            }

            self.ws.send(json.dumps(subscription_message))
            self.message_handlers["futures.tickers"] = callback

            logger.info("Subscribed to Gate.io futures tickers")
            return True

        except Exception as e:
            logger.error(f"Failed to subscribe to Gate.io tickers: {e}")
            return False

    def _on_open(self, ws):
        """WebSocket on_open callback."""
        self.is_connected = True

    def _on_message(self, ws, message):
        """WebSocket on_message callback."""
        try:
            data = json.loads(message)

            # Handle subscription confirmations
            if data.get("event") == "subscribe" and data.get("channel") == "futures.tickers":
                logger.info(f"Gate.io subscription confirmed: {data}")
                return

            # Handle ticker updates
            if data.get("channel") == "futures.tickers":
                callback = self.message_handlers.get("futures.tickers")
                if callback:
                    # Gate.io WebSocket sends ticker data in "result" field as array
                    results = data.get("result", [])
                    if isinstance(results, list):
                        # Run callback in stored event loop
                        if self.event_loop and self.event_loop.is_running():
                            asyncio.run_coroutine_threadsafe(self._handle_ticker_results(results, callback), self.event_loop)
                        else:
                            logger.error("Gate.io: No valid event loop available for async callback")
                    else:
                        logger.warning(f"Unexpected result format: {results}")

        except Exception as e:
            logger.error(f"Error handling Gate.io WebSocket message: {e}")

    def _on_error(self, ws, error):
        """WebSocket on_error callback."""
        logger.error(f"Gate.io WebSocket error: {error}")
        self.is_connected = False

    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket on_close callback."""
        logger.info(f"Gate.io WebSocket closed: {close_status_code}, {close_msg}")
        self.is_connected = False

    async def _handle_ticker_results(self, results: List[Dict[str, Any]], callback: Callable):
        """Handle ticker results in async context."""
        for result in results:
            try:
                await callback(result)
            except Exception as e:
                logger.error(f"Error in ticker callback: {e}")

    def _ping_loop(self):
        """Send ping messages to keep connection alive."""
        while not self.event.wait(10):  # Send ping every 10 seconds
            if self.ws and self.is_connected:
                try:
                    # Send ping
                    self.ws.send(json.dumps({"channel": "futures.ping"}))
                except Exception as e:
                    logger.debug(f"Ping failed: {e}")
                    break

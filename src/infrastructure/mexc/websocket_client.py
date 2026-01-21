"""MEXC Futures WebSocket client for real-time data."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import websockets
from websockets.exceptions import ConnectionClosedError, WebSocketException
from websockets.protocol import State

from core.config import Config
from core.logging_config import setup_logging

logger = setup_logging()


class MexcWebSocketClient:
    """WebSocket client for MEXC Futures API."""

    def __init__(self, config: Config):
        self.config = config
        self.ws: Optional[websockets.WebSocketServerProtocol] = None
        self.is_connected = False
        self.subscriptions: Dict[str, Callable] = {}
        self.ping_task: Optional[asyncio.Task] = None
        self.reconnect_task: Optional[asyncio.Task] = None
        self.message_handlers: Dict[str, Callable] = {}

    async def connect(self) -> bool:
        """Connect to MEXC WebSocket."""
        try:
            logger.info(f"Connecting to MEXC WebSocket: {self.config.mexc_ws_url}")
            self.ws = await websockets.connect(
                self.config.mexc_ws_url,
                ping_interval=None,  # We'll handle ping manually
                close_timeout=5
            )
            self.is_connected = True
            logger.info("Successfully connected to MEXC WebSocket")

            # Start ping task
            self.ping_task = asyncio.create_task(self._ping_loop())

            # Start message handler
            asyncio.create_task(self._message_handler())

            return True

        except Exception as e:
            logger.error(f"Failed to connect to MEXC WebSocket: {e}")
            self.is_connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        self.is_connected = False

        if self.ping_task:
            self.ping_task.cancel()
            try:
                await self.ping_task
            except asyncio.CancelledError:
                pass

        if self.reconnect_task:
            self.reconnect_task.cancel()
            try:
                await self.reconnect_task
            except asyncio.CancelledError:
                pass

        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")

        logger.info("Disconnected from MEXC WebSocket")

    async def subscribe_tickers(self, callback: Callable[[Dict[str, Any]], None]) -> bool:
        """Subscribe to all tickers updates."""
        if not self.is_connected or not self.ws:
            logger.error("WebSocket not connected")
            return False

        try:
            subscription_msg = {
                "method": "sub.tickers",
                "param": {}
            }

            await self.ws.send(json.dumps(subscription_msg))
            self.subscriptions["push.tickers"] = callback
            logger.info("Subscribed to MEXC tickers")
            return True

        except Exception as e:
            logger.error(f"Failed to subscribe to tickers: {e}")
            return False

    async def unsubscribe_tickers(self) -> bool:
        """Unsubscribe from tickers updates."""
        if not self.is_connected or not self.ws:
            return False

        try:
            unsubscribe_msg = {
                "method": "unsub.tickers",
                "param": {}
            }

            await self.ws.send(json.dumps(unsubscribe_msg))
            self.subscriptions.pop("push.tickers", None)
            logger.info("Unsubscribed from MEXC tickers")
            return True

        except Exception as e:
            logger.error(f"Failed to unsubscribe from tickers: {e}")
            return False

    def add_message_handler(self, channel: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Add custom message handler for specific channel."""
        self.message_handlers[channel] = handler

    async def _ping_loop(self) -> None:
        """Send ping messages every 10-20 seconds."""
        while self.is_connected:
            try:
                if self.ws and self.ws.state == State.OPEN:
                    ping_msg = {"method": "ping"}
                    await self.ws.send(json.dumps(ping_msg))
                    logger.debug("Sent ping to MEXC WebSocket")
                else:
                    break

                await asyncio.sleep(15)  # Ping every 15 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in ping loop: {e}")
                break

    async def _message_handler(self) -> None:
        """Handle incoming WebSocket messages."""
        while self.is_connected:
            try:
                if not self.ws or self.ws.state != State.OPEN:
                    break

                message = await self.ws.recv()
                data = json.loads(message)

                channel = data.get("channel")
                if channel:
                    # Handle pong responses
                    if channel == "pong":
                        logger.debug("Received pong from MEXC WebSocket")
                        continue

                    # Handle subscriptions
                    if channel in self.subscriptions:
                        await self._call_handler(self.subscriptions[channel], data)

                    # Handle custom message handlers
                    elif channel in self.message_handlers:
                        await self._call_handler(self.message_handlers[channel], data)

                    else:
                        logger.debug(f"Unhandled channel: {channel}")

            except ConnectionClosedError:
                logger.warning("MEXC WebSocket connection closed")
                self.is_connected = False
                break
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse WebSocket message: {e}")
                continue
            except Exception as e:
                logger.error(f"Error in message handler: {e}")
                continue

    async def _call_handler(self, handler: Callable, data: Dict[str, Any]) -> None:
        """Safely call message handler."""
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(data)
            else:
                handler(data)
        except Exception as e:
            logger.error(f"Error in message handler: {e}")

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for WebSocket connection."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        return headers

    async def reconnect(self) -> None:
        """Reconnect to WebSocket with exponential backoff."""
        if self.reconnect_task and not self.reconnect_task.done():
            return

        async def _reconnect_loop():
            backoff = 1
            max_backoff = 60

            while not self.is_connected:
                logger.info(f"Attempting to reconnect in {backoff} seconds...")
                await asyncio.sleep(backoff)

                if await self.connect():
                    logger.info("Successfully reconnected to MEXC WebSocket")
                    # Re-subscribe to previous subscriptions
                    for channel, callback in self.subscriptions.items():
                        if channel == "push.tickers":
                            await self.subscribe_tickers(callback)
                    break

                backoff = min(backoff * 2, max_backoff)

        self.reconnect_task = asyncio.create_task(_reconnect_loop())
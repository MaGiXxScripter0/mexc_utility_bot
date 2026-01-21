"""Base class for fair price alert services."""

import asyncio
import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Callable

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from core.config import Config
from core.logging_config import setup_logging
from core.markdown_service import MarkdownService
from core.utils.network_prefixes import NetworkPrefixUtils
from core.utils import BuyLimitCalculator

logger = setup_logging()


class BaseFairPriceAlertService(ABC):
    """Base class for fair price alert services."""

    def __init__(self, config: Config, markdown_service: MarkdownService, exchange_name: str, exchange_emoji: str):
        self.config = config
        self.markdown_service = markdown_service
        self.exchange_name = exchange_name
        self.exchange_emoji = exchange_emoji
        self.bot: Optional[Bot] = None
        self.alerted_symbols: Set[str] = set()
        self.alert_lock: asyncio.Lock = asyncio.Lock()
        self.monitoring_task: Optional[asyncio.Task] = None
        self.is_running = False

    async def start(self) -> bool:
        """Start the fair price monitoring service."""
        try:
            logger.info(f"Starting {self.exchange_name} fair price alert service...")

            # Initialize Telegram bot
            logger.debug(f"Initializing {self.exchange_name} Telegram bot...")
            self.bot = Bot(
                token=self.config.bot_token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML)
            )
            logger.debug(f"{self.exchange_name} Telegram bot initialized successfully")

            # Connect to WebSocket
            logger.debug(f"Connecting to {self.exchange_name} WebSocket...")
            if not await self.connect_websocket():
                logger.error(f"Failed to connect to {self.exchange_name} WebSocket - service startup aborted")
                return False
            logger.info(f"{self.exchange_name} WebSocket connected successfully")

            # Subscribe to ticker updates
            logger.debug(f"Subscribing to {self.exchange_name} ticker updates...")
            async def ticker_callback(ticker_data):
                """Handle incoming ticker data."""
                try:
                    logger.debug(f"{self.exchange_name}: Received ticker data: {ticker_data}")
                    # Process the ticker data - this will be implemented in subclasses
                    await self._process_ticker_data(ticker_data)
                except Exception as e:
                    logger.error(f"{self.exchange_name}: Error in ticker callback: {e}")

            subscription_success = await self.subscribe_tickers(ticker_callback)
            if not subscription_success:
                logger.error(f"Failed to subscribe to {self.exchange_name} ticker updates")
                return False

            # Start monitoring loop
            logger.debug(f"Starting {self.exchange_name} monitoring loop...")
            self.monitoring_task = asyncio.create_task(self.run_monitoring_loop())

            self.is_running = True
            threshold = 5.0  # Current threshold setting
            logger.info(f"🎉 {self.exchange_name} fair price alert service started successfully (threshold: {threshold:.1f}%)")
            return True

        except Exception as e:
            logger.error(f"Failed to start {self.exchange_name} fair price alert service: {e}")
            # Cleanup on failure
            await self._cleanup_on_failure()
            return False

    async def _cleanup_on_failure(self) -> None:
        """Cleanup resources on startup failure."""
        try:
            if self.bot:
                await self.bot.session.close()
            await self.disconnect_websocket()
        except Exception as e:
            logger.warning(f"Error during cleanup on startup failure: {e}")

    async def stop(self) -> None:
        """Stop the fair price monitoring service."""
        self.is_running = False

        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass

        await self.disconnect_websocket()

        if self.bot:
            await self.bot.session.close()

        logger.info(f"{self.exchange_name} fair price alert service stopped")

    @abstractmethod
    async def connect_websocket(self) -> bool:
        """Connect to exchange WebSocket."""
        pass

    @abstractmethod
    async def disconnect_websocket(self) -> None:
        """Disconnect from exchange WebSocket."""
        pass

    @abstractmethod
    async def subscribe_tickers(self, callback: Callable) -> bool:
        """Subscribe to ticker updates."""
        pass

    @abstractmethod
    async def _process_ticker_data(self, ticker_data: Dict[str, Any]) -> None:
        """Process incoming ticker data."""
        pass

    @abstractmethod
    async def get_index_info(self, symbol: str) -> str:
        """Get index weights information."""
        pass

    @abstractmethod
    async def get_dex_info(self, coin: str) -> str:
        """Get DEX/networks information."""
        pass

    @abstractmethod
    async def get_buying_limit_info(self, symbol: str, token_price: float) -> str:
        """Get buying limit information."""
        pass

    def _should_alert(self, last_price: float, fair_price: float, symbol: str) -> bool:
        """Check if we should send an alert for this symbol."""
        try:
            # Validate input prices
            if fair_price <= 0 or last_price <= 0:
                logger.debug(f"{self.exchange_name} {symbol}: Invalid prices - last: {last_price}, fair: {fair_price}")
                return False

            # Calculate spread percentage
            spread_pct = ((last_price - fair_price) / fair_price) * 100
            abs_spread_pct = abs(spread_pct)

            # Log spread calculation for debugging
            logger.debug(f"{self.exchange_name} {symbol}: Spread calculation - last: {last_price:.8f}, fair: {fair_price:.8f}, spread: {spread_pct:+.4f}%")

            # Check alert threshold (currently set to 0% which means alert on any spread)
            threshold = 5.0 # This matches the current setting
            should_alert = abs_spread_pct >= threshold

            if should_alert:
                logger.info(f"{self.exchange_name} {symbol}: ALERT TRIGGERED - spread: {spread_pct:+.4f}% (threshold: {threshold:.1f}%)")
            else:
                logger.debug(f"{self.exchange_name} {symbol}: No alert - spread: {spread_pct:+.4f}% below threshold: {threshold:.1f}%")

            return should_alert

        except (ValueError, TypeError) as e:
            logger.warning(f"{self.exchange_name} {symbol}: Error calculating spread - last: {last_price}, fair: {fair_price}, error: {e}")
            return False
        except Exception as e:
            logger.error(f"{self.exchange_name} {symbol}: Unexpected error in _should_alert: {e}")
            return False

    async def _send_alert(self, ticker_data: Dict[str, Any], alert_type: str, emoji: str) -> None:
        """Send alert message."""
        try:
            logger.debug(f"Preparing to send {self.exchange_name} alert...")

            symbol = self._extract_symbol(ticker_data)
            last_price = self._extract_last_price(ticker_data)
            fair_price = self._extract_fair_price(ticker_data)
            volume_24h = self._extract_volume(ticker_data)

            logger.debug(f"{self.exchange_name} alert data - symbol: {symbol}, last: {last_price}, fair: {fair_price}, volume: {volume_24h}")

            # Calculate spread
            spread_pct = ((last_price - fair_price) / fair_price) * 100
            spread_str = f"{spread_pct:+.2f}%"

            # Get additional data
            base_symbol = self._extract_base_symbol(symbol)
            logger.debug(f"{self.exchange_name} fetching additional data for {symbol} (base: {base_symbol})")

            # Get index weights for the symbol
            index_info = await self.get_index_info(symbol)
            logger.debug(f"{self.exchange_name} {symbol} index info: {index_info}")

            # Get DEX/networks info for the base coin
            dex_info = await self.get_dex_info(base_symbol)
            logger.debug(f"{self.exchange_name} {base_symbol} DEX info: {dex_info}")

            # Get buying limit info (only for MEXC)
            buying_limit_info = ""
            if self.exchange_name == "MEXC":
                buying_limit_info = await self.get_buying_limit_info(symbol, last_price)
                logger.debug(f"{self.exchange_name} {symbol} buying limit: {buying_limit_info}")

            # Format message with Markdown
            message = self._format_alert_message(symbol, last_price, fair_price, spread_str, volume_24h, alert_type, emoji, index_info, dex_info, buying_limit_info)
            logger.debug(f"{self.exchange_name} formatted alert message for {symbol}")

            markdown_v2_message = self.markdown_service.convert_to_markdown_v2(message)

            logger.info(f"Sending {self.exchange_name} alert to {len(self.config.alert_chats)} Telegram chat(s)...")
            sent_count = 0
            for alert_chat in self.config.alert_chats:
                try:
                    await self.bot.send_message(
                        chat_id=alert_chat.chat_id,
                        text=markdown_v2_message,
                        message_thread_id=alert_chat.message_thread_id,
                        parse_mode="MarkdownV2",
                        disable_web_page_preview=True
                    )
                    sent_count += 1
                    target_desc = f"{alert_chat.chat_id}:{alert_chat.message_thread_id}" if alert_chat.message_thread_id else alert_chat.chat_id
                    logger.debug(f"✅ Sent {self.exchange_name} alert to chat {target_desc}")
                except Exception as telegram_error:
                    target_desc = f"{alert_chat.chat_id}:{alert_chat.message_thread_id}" if alert_chat.message_thread_id else alert_chat.chat_id
                    logger.error(f"❌ Telegram API error sending {self.exchange_name} alert to chat {target_desc}: {telegram_error}")
                    # Try to send a simplified version without MarkdownV2
                    try:
                        simple_message = f"{emoji} {self.exchange_name} Fair Price Alert\n\n{symbol}: {spread_str}\nLast: {last_price:.8f}\nFair: {fair_price:.8f}"
                        await self.bot.send_message(
                            chat_id=alert_chat.chat_id,
                            text=simple_message,
                            message_thread_id=alert_chat.message_thread_id,
                            disable_web_page_preview=True
                        )
                        sent_count += 1
                        logger.warning(f"✅ Sent simplified {self.exchange_name} alert to chat {target_desc} (MarkdownV2 failed)")
                    except Exception as fallback_error:
                        logger.error(f"❌ Complete failure sending {self.exchange_name} alert to chat {target_desc}: {fallback_error}")

            if sent_count > 0:
                logger.info(f"✅ Sent {self.exchange_name} fair price alert for {symbol}: {spread_str} (to {sent_count}/{len(self.config.alert_chats)} chats)")
            else:
                logger.error(f"❌ Failed to send {self.exchange_name} alert to any chat")

        except Exception as e:
            logger.error(f"❌ Failed to prepare {self.exchange_name} alert for {symbol}: {e}")
            logger.debug(f"Alert data that failed: {ticker_data}", exc_info=True)

    def _format_alert_message(self, symbol: str, last_price: float, fair_price: float,
                            spread_str: str, volume_24h: float, alert_type: str, emoji: str,
                            index_info: str, dex_info: str, buying_limit: str) -> str:
        """Format alert message with Markdown."""
        # Escape special characters for MarkdownV2
        symbol_escaped = self._escape_symbol(symbol)
        base_symbol = self._escape_base_symbol(symbol)

        # Format prices
        last_price_fmt = f"{last_price:,.8f}".rstrip('0').rstrip('.')
        fair_price_fmt = f"{fair_price:,.8f}".rstrip('0').rstrip('.')
        volume_fmt = f"{int(volume_24h):,}"

        # Format timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        message = f"""{emoji} **Fair Price Alert** | {alert_type}

{self.exchange_emoji} **{self.exchange_name}**

📊 **Ticker:** {self._get_ticker_link(symbol, symbol_escaped)}
📋 **Copy:** `{base_symbol}`
💰 **Last Price:** `{last_price_fmt}`
🎯 **Fair Price:** `{fair_price_fmt}`
📈 **Spread:** `{spread_str}`
📊 **Volume 24h:** `{volume_fmt}`"""

        # Add Index Pool only if available
        if index_info:
            message += f"\n🏛️ **Index Pool:** {index_info}"

        message += f"\n🌐 **DEX Networks:** {dex_info}"

        # Add Buy Limit only if available (MEXC only)
        if buying_limit:
            message += f"\n💰 **Buy Limit:** {buying_limit}"

        message += f"\n\n🕐 **{timestamp}**"

        return message

    @abstractmethod
    def _extract_symbol(self, ticker_data: Dict[str, Any]) -> str:
        """Extract symbol from ticker data."""
        pass

    @abstractmethod
    def _extract_last_price(self, ticker_data: Dict[str, Any]) -> float:
        """Extract last price from ticker data."""
        pass

    @abstractmethod
    def _extract_fair_price(self, ticker_data: Dict[str, Any]) -> float:
        """Extract fair price from ticker data."""
        pass

    @abstractmethod
    def _extract_volume(self, ticker_data: Dict[str, Any]) -> float:
        """Extract volume from ticker data."""
        pass

    @abstractmethod
    def _extract_base_symbol(self, symbol: str) -> str:
        """Extract base symbol."""
        pass

    @abstractmethod
    def _escape_symbol(self, symbol: str) -> str:
        """Escape symbol for Markdown."""
        pass

    @abstractmethod
    def _escape_base_symbol(self, symbol: str) -> str:
        """Escape base symbol for Markdown."""
        pass

    @abstractmethod
    def _get_ticker_link(self, symbol: str, symbol_escaped: str) -> str:
        """Get ticker link."""
        pass

    async def _remove_alert_cooldown(self, symbol: str, delay: int) -> None:
        """Remove symbol from alerted list after cooldown period."""
        await asyncio.sleep(delay)
        self.alerted_symbols.discard(symbol)
        logger.debug(f"Removed alert cooldown for {symbol}")

    async def run_monitoring_loop(self) -> None:
        """Main monitoring loop."""
        logger.info(f"Starting {self.exchange_name} fair price monitoring loop (checking every 10s)")

        consecutive_failures = 0
        max_consecutive_failures = 5

        while self.is_running:
            try:
                # Check connection status
                if not self.is_websocket_connected():
                    consecutive_failures += 1
                    logger.warning(f"{self.exchange_name} WebSocket disconnected (failure #{consecutive_failures}), attempting to reconnect...")

                    if consecutive_failures >= max_consecutive_failures:
                        logger.error(f"{self.exchange_name} WebSocket reconnection failed {max_consecutive_failures} times, giving up")
                        await asyncio.sleep(60)  # Wait longer before trying again
                        consecutive_failures = 0
                        continue

                    if not await self.reconnect_websocket():
                        logger.error(f"{self.exchange_name} WebSocket reconnection failed, will retry in 30s")
                        await asyncio.sleep(30)
                        continue

                    # Reconnection successful
                    consecutive_failures = 0
                    logger.info(f"{self.exchange_name} WebSocket reconnected successfully")

                # Log periodic status
                logger.debug(f"{self.exchange_name} monitoring active - WebSocket: {'✅' if self.is_websocket_connected() else '❌'}, Alerts sent: {len(self.alerted_symbols)} symbols cooling down")

                await asyncio.sleep(10)  # Check every 10 seconds

            except asyncio.CancelledError:
                logger.info(f"{self.exchange_name} monitoring loop cancelled")
                break
            except Exception as e:
                consecutive_failures += 1
                logger.error(f"Error in {self.exchange_name} monitoring loop (failure #{consecutive_failures}): {e}")
                await asyncio.sleep(30)

        logger.info(f"{self.exchange_name} fair price monitoring loop stopped")

    @abstractmethod
    def is_websocket_connected(self) -> bool:
        """Check if WebSocket is connected."""
        pass

    @abstractmethod
    async def reconnect_websocket(self) -> bool:
        """Reconnect WebSocket."""
        pass
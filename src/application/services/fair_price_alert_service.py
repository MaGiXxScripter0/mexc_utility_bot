"""Service for monitoring fair price alerts using MEXC WebSocket."""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from core.config import Config
from core.logging_config import setup_logging
from core.markdown_service import MarkdownService
from infrastructure.mexc.websocket_client import MexcWebSocketClient
from infrastructure.mexc.client import MexcClient
from core.utils.network_prefixes import NetworkPrefixUtils
from core.utils import BuyLimitCalculator

logger = setup_logging()


class FairPriceAlertService:
    """Service for monitoring and alerting fair price discrepancies."""

    def __init__(self, config: Config, markdown_service: MarkdownService, mexc_client: MexcClient):
        self.config = config
        self.markdown_service = markdown_service
        self.mexc_client = mexc_client
        self.ws_client = MexcWebSocketClient(config)
        self.bot: Optional[Bot] = None
        self.alerted_symbols: Set[str] = set()
        self.monitoring_task: Optional[asyncio.Task] = None
        self.is_running = False

    async def start(self) -> bool:
        """Start the fair price monitoring service."""
        try:
            # Initialize Telegram bot
            self.bot = Bot(
                token=self.config.bot_token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML)
            )

            # Connect to WebSocket
            if not await self.ws_client.connect():
                logger.error("Failed to connect to MEXC WebSocket")
                return False

            # Subscribe to ticker updates
            if not await self.ws_client.subscribe_tickers(self._handle_ticker_update):
                logger.error("Failed to subscribe to MEXC tickers")
                return False

            self.is_running = True
            logger.info("Fair price alert service started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start fair price alert service: {e}")
            return False

    async def stop(self) -> None:
        """Stop the fair price monitoring service."""
        self.is_running = False

        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass

        await self.ws_client.disconnect()

        if self.bot:
            await self.bot.session.close()

        logger.info("Fair price alert service stopped")

    def _should_alert(self, last_price: float, fair_price: float, symbol: str) -> bool:
        """Check if we should send an alert for this symbol."""
        try:
            if fair_price <= 0 or last_price <= 0:
                return False

            # Calculate spread percentage
            spread_pct = ((last_price - fair_price) / fair_price) * 100

            # Alert if spread is significant (>5%)
            return abs(spread_pct) >= 5.0

        except (ValueError, TypeError):
            return False

    async def _handle_ticker_update(self, data: Dict[str, Any]) -> None:
        """Handle ticker update from WebSocket."""
        try:
            ticker_data = data.get("data", [])
            if not isinstance(ticker_data, list):
                return

            for ticker in ticker_data:
                await self._process_ticker(ticker)

        except Exception as e:
            logger.error(f"Error processing ticker update: {e}")

    async def _process_ticker(self, ticker: Dict[str, Any]) -> None:
        """Process individual ticker data."""
        try:
            symbol = ticker.get("symbol", "").replace("_", "/")
            if not symbol:
                return

            last_price_str = ticker.get("lastPrice", "0")
            fair_price_str = ticker.get("fairPrice", "0")
            volume_24h = ticker.get("volume24", "0")

            last_price = float(last_price_str)
            fair_price = float(fair_price_str)

            if self._should_alert(last_price, fair_price, symbol):
                # Check if we already alerted for this symbol recently
                if symbol in self.alerted_symbols:
                    return

                # Send alert
                await self._send_alert(ticker)

                # Mark as alerted to avoid spam
                self.alerted_symbols.add(symbol)

                # Remove from alerted symbols after 1 hour
                asyncio.create_task(self._remove_alert_cooldown(symbol, 120))

        except Exception as e:
            logger.error(f"Error processing ticker {ticker.get('symbol', 'unknown')}: {e}")

    async def _send_alert(self, ticker: Dict[str, Any]) -> None:
        """Send alert message to Telegram channel."""
        try:
            symbol = ticker.get("symbol", "").replace("_", "/")
            last_price = float(ticker.get("lastPrice", "0"))
            fair_price = float(ticker.get("fairPrice", "0"))
            volume_24h = float(ticker.get("volume24", "0"))

            # Calculate spread
            spread_pct = ((last_price - fair_price) / fair_price) * 100
            spread_str = f"{spread_pct:+.2f}%"

            # Determine alert type
            if spread_pct > 0:
                alert_type = "🔴 SHORT"
                emoji = "⚠️"
            else:
                alert_type = "🟢 LONG"
                emoji = "ℹ️"

            # Get additional data
            base_symbol = symbol.split('/')[0]
            normalized_symbol = symbol.replace('/', '_')

            # Get index weights for the symbol
            index_info = await self._get_index_info(normalized_symbol)

            # Get DEX/networks info for the base coin
            dex_info = await self._get_dex_info(base_symbol)

            # Get maximum buying limit in USD
            buying_limit_info = await self._get_buying_limit_info(normalized_symbol, last_price)

            # Format message with Markdown
            message = self._format_alert_message(symbol, last_price, fair_price, spread_str, volume_24h, alert_type, emoji, index_info, dex_info, buying_limit_info)

            markdown_v2_message = self.markdown_service.convert_to_markdown_v2(message)


            await self.bot.send_message(
                chat_id=self.config.alert_chat_id,
                text=markdown_v2_message,
                parse_mode="MarkdownV2",
                disable_web_page_preview=True
            )

            logger.info(f"Sent fair price alert for {symbol}: {spread_str}")

        except Exception as e:
            logger.error(f"Failed to send alert for {ticker.get('symbol', 'unknown')}: {e}")

    async def _get_index_info(self, symbol: str) -> str:
        """Get index weights information for a symbol."""
        try:
            ok, err, idxw = await self.mexc_client.fetch_index_weights(symbol)

            if not ok:
                logger.debug(f"Index API failed for {symbol}: {err}")
                return "MEXC"
            if not idxw:
                logger.debug(f"No index data for {symbol}")
                return "MEXC"

            # Check if index weights should be shown
            if idxw.get("showIndexSymbolWeight") != 1:
                logger.debug(f"Index weights disabled for {symbol}")
                return "MEXC"

            # Get index composition
            rows = idxw.get("indexPrice", [])
            if not rows:
                logger.debug(f"Empty index data for {symbol}")
                return "MEXC"

            # Filter and format weights > 0%
            valid_weights = []
            for r in rows:
                weight_pct = self._pct(float(r.get("wight", 0)))
                if weight_pct > 0:
                    market_name = r.get("marketName", "N/A")
                    valid_weights.append(f"{market_name} {weight_pct:.1f}%")

            if valid_weights:
                # Return top 3 weights only for alerts (to keep them concise)
                top_weights = valid_weights[:3]
                return f"{' • '.join(top_weights)}"
            else:
                logger.debug(f"No valid weights found for {symbol}")
                return "MEXC"

        except Exception as e:
            logger.warning(f"Failed to get index info for {symbol}: {e}")
            return "MEXC"

    @staticmethod
    def _pct(w: float) -> float:
        """Convert weight to percentage."""
        return round(w * 100, 1)

    async def _get_dex_info(self, coin: str) -> str:
        """Get DEX/networks information for a coin."""
        try:
            ok, err, networks = await self.mexc_client.fetch_wallet_networks(coin)
            if not ok or not networks:
                return "N/A"

            # Get top 5 networks with deposit/withdraw enabled
            active_networks = []
            for network in networks[:5]:
                if network.get("depositEnable", False) or network.get("withdrawEnable", False):
                    network_name = network.get("network", "N/A")
                    if network_name and network_name.upper() != "UNKNOWN":
                        addr = network.get("contract") or network.get("contractAddress") or None
                        if not addr:
                            continue

                        # Determine network prefix for DexScreener
                        network_prefix = NetworkPrefixUtils.get_dexscreener_prefix(network_name)

                        # Create DexScreener link
                        dexscreener_url = f"https://dexscreener.com/{network_prefix}/{addr}"

                        active_networks.append(f'[{network_name}]({dexscreener_url})')

            if active_networks:
                return ", ".join(active_networks)
            else:
                return "N/A"

        except Exception as e:
            logger.warning(f"Failed to get DEX info for {coin}: {e}")
            return "N/A"

    async def _get_buying_limit_info(self, symbol: str, token_price: float) -> str:
        """Get maximum buying limit in USD based on account balance and contract limits."""
        try:
            # No account assets access - using only contract limits
            has_api_access = False
            usdt_balance = 0.0

            # Get contract details for position limits
            ok_contract, err_contract, contract_data = await self.mexc_client.fetch_contract_detail(symbol)

            max_position_tokens = 0.0
            if ok_contract and contract_data:
                try:
                    max_vol = float(contract_data.get("maxVol", "0"))
                    contract_size = float(contract_data.get("contractSize", "1"))
                    max_position_tokens = max_vol * contract_size
                except (ValueError, TypeError):
                    pass

            return BuyLimitCalculator.calculate_buy_limit_from_data(contract_data, token_price)

        except Exception as e:
            logger.warning(f"Failed to get buying limit info for {symbol}: {e}")
            return "Error"


    def _format_alert_message(self, symbol: str, last_price: float, fair_price: float,
                            spread_str: str, volume_24h: float, alert_type: str, emoji: str,
                            index_info: str = "MEXC", dex_info: str = "N/A", buying_limit: str = "N/A") -> str:
        """Format alert message with Markdown."""
        # Escape special characters for MarkdownV2
        symbol_escaped = symbol.replace('.', '\\.').replace('-', '\\-')
        base_symbol = symbol.split('/')[0].replace('.', '\\.').replace('-', '\\-')

        # Format prices
        last_price_fmt = f"{last_price:,.8f}".rstrip('0').rstrip('.')
        fair_price_fmt = f"{fair_price:,.8f}".rstrip('0').rstrip('.')
        volume_fmt = f"{int(volume_24h):,}"

        # Format timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        message = f"""{emoji} **Fair Price Alert** | {alert_type}

🏦 **MEXC**

📊 **Ticker:** [{symbol_escaped}](https://www\\.mexc\\.com/ru\\-RU/futures/{symbol_escaped})
📋 **Copy:** `{base_symbol}`
💰 **Last Price:** `{last_price_fmt}`
🎯 **Fair Price:** `{fair_price_fmt}`
📈 **Spread:** `{spread_str}`
📊 **Volume 24h:** `{volume_fmt}`
🏛️ **Index Pool:** {index_info}
🌐 **DEX Networks:** {dex_info}
💰 **Buy Limit:** {buying_limit}

🕐 **{timestamp}**"""

        return message

    async def _remove_alert_cooldown(self, symbol: str, delay: int) -> None:
        """Remove symbol from alerted list after cooldown period."""
        await asyncio.sleep(delay)
        self.alerted_symbols.discard(symbol)
        logger.debug(f"Removed alert cooldown for {symbol}")

    async def run_monitoring_loop(self) -> None:
        """Main monitoring loop."""
        logger.info("Starting fair price monitoring loop")

        while self.is_running:
            try:
                # Check connection status
                if not self.ws_client.is_connected:
                    logger.warning("WebSocket disconnected, attempting to reconnect...")
                    if not await self.ws_client.reconnect():
                        logger.error("Failed to reconnect WebSocket")
                        await asyncio.sleep(30)
                        continue

                await asyncio.sleep(10)  # Check every 10 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(30)

        logger.info("Fair price monitoring loop stopped")
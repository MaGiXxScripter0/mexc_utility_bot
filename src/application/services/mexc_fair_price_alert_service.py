"""MEXC Fair Price Alert Service."""

import asyncio
from typing import Any, Dict, Optional

from infrastructure.mexc.websocket_client import MexcWebSocketClient
from infrastructure.mexc.client import MexcClient
from core.config import Config
from core.logging_config import setup_logging
from core.markdown_service import MarkdownService
from core.utils.network_prefixes import NetworkPrefixUtils
from core.utils import BuyLimitCalculator
from .base_fair_price_alert_service import BaseFairPriceAlertService

logger = setup_logging()


class MexcFairPriceAlertService(BaseFairPriceAlertService):
    """Fair price alert service for MEXC."""

    def __init__(self, config: Config, markdown_service: MarkdownService, mexc_client: MexcClient):
        super().__init__(config, markdown_service, "MEXC", "🏦")
        self.mexc_client = mexc_client
        self.ws_client = MexcWebSocketClient(config)

    async def connect_websocket(self) -> bool:
        """Connect to MEXC WebSocket."""
        try:
            logger.info("MEXC: Initiating WebSocket connection...")
            connected = await self.ws_client.connect()
            if connected:
                logger.info("MEXC: WebSocket connected successfully")
                return True
            else:
                logger.error("MEXC: WebSocket connection failed")
                return False
        except Exception as e:
            logger.error(f"MEXC: WebSocket connection error: {e}")
            return False

    async def disconnect_websocket(self) -> None:
        """Disconnect from MEXC WebSocket."""
        await self.ws_client.disconnect()

    def is_websocket_connected(self) -> bool:
        """Check if MEXC WebSocket is connected."""
        return self.ws_client.is_connected

    async def reconnect_websocket(self) -> bool:
        """Reconnect MEXC WebSocket."""
        return await self.ws_client.reconnect()

    async def subscribe_tickers(self, callback) -> bool:
        """Subscribe to MEXC ticker updates."""
        logger.info("MEXC: Subscribing to ticker updates...")

        async def handle_ticker_update(data: Dict[str, Any]) -> None:
            try:
                # Use the callback provided by base class for uniform processing
                await callback(data)

            except Exception as e:
                logger.error(f"MEXC: Error in ticker update handler: {e}")
                logger.debug(f"MEXC: Problematic data: {data}", exc_info=True)

        success = await self.ws_client.subscribe_tickers(handle_ticker_update)
        if success:
            logger.info("MEXC: Successfully subscribed to ticker updates")
        else:
            logger.error("MEXC: Failed to subscribe to ticker updates")

        return success

    async def _process_ticker_data(self, ticker_data: Dict[str, Any]) -> None:
        """Process incoming ticker data from WebSocket."""
        try:
            ticker_array = ticker_data.get("data", [])
            if not isinstance(ticker_array, list):
                logger.debug("MEXC: Received non-list ticker data, skipping")
                return

            logger.debug(f"MEXC: Processing {len(ticker_array)} ticker updates")
            processed_count = 0

            for ticker in ticker_array:
                try:
                    await self._process_mexc_ticker(ticker, None)
                    processed_count += 1
                except Exception as ticker_error:
                    logger.error(f"MEXC: Error processing individual ticker: {ticker_error}")
                    continue

            logger.debug(f"MEXC: Successfully processed {processed_count}/{len(ticker_array)} tickers")

        except Exception as e:
            logger.error(f"MEXC: Error processing ticker data batch: {e}")
            logger.debug(f"MEXC: Problematic data: {ticker_data}", exc_info=True)

    async def _process_mexc_ticker(self, ticker: Dict[str, Any], callback) -> None:
        """Process individual MEXC ticker data."""
        try:
            symbol = ticker.get("symbol", "").replace("_", "/")
            if not symbol:
                logger.debug("MEXC: Skipping ticker with empty symbol")
                return

            last_price_str = ticker.get("lastPrice", "0")
            fair_price_str = ticker.get("fairPrice", "0")

            try:
                last_price = float(last_price_str)
                fair_price = float(fair_price_str)
            except (ValueError, TypeError) as e:
                logger.warning(f"MEXC {symbol}: Invalid price data - last: '{last_price_str}', fair: '{fair_price_str}' - {e}")
                return

            logger.debug(f"MEXC {symbol}: Processing ticker - last: {last_price:.8f}, fair: {fair_price:.8f}")

            if self._should_alert(last_price, fair_price, symbol):
                # Check if we already alerted for this symbol recently
                if symbol in self.alerted_symbols:
                    logger.debug(f"MEXC {symbol}: Skipping alert (already alerted recently)")
                    return

                # Determine alert type
                spread_pct = ((last_price - fair_price) / fair_price) * 100
                if spread_pct > 0:
                    alert_type = "🔴 SHORT"
                    emoji = "⚠️"
                else:
                    alert_type = "🟢 LONG"
                    emoji = "ℹ️"

                logger.info(f"MEXC {symbol}: Preparing alert - type: {alert_type}, spread: {spread_pct:+.4f}%")

                # Send alert
                await self._send_alert(ticker, alert_type, emoji)

                # Mark as alerted to avoid spam
                self.alerted_symbols.add(symbol)
                logger.debug(f"MEXC {symbol}: Added to cooldown list (total cooling down: {len(self.alerted_symbols)})")

                # Remove from alerted symbols after 5 minutes (increased cooldown to prevent duplicates)
                asyncio.create_task(self._remove_alert_cooldown(symbol, 300))

        except Exception as e:
            logger.error(f"Error processing MEXC ticker {ticker.get('symbol', 'unknown')}: {e}")
            logger.debug(f"MEXC ticker data that caused error: {ticker}", exc_info=True)

    async def get_index_info(self, symbol: str) -> str:
        """Get index weights information for MEXC."""
        try:
            normalized_symbol = symbol.replace('/', '_')
            logger.debug(f"MEXC fetching index weights for {symbol} (normalized: {normalized_symbol})")

            ok, err, idxw = await self.mexc_client.fetch_index_weights(normalized_symbol)

            if not ok:
                logger.debug(f"MEXC index API failed for {symbol}: {err}")
                return "MEXC"
            if not idxw:
                logger.debug(f"No MEXC index data for {symbol}")
                return "MEXC"

            # Check if index weights should be shown
            if idxw.get("showIndexSymbolWeight") != 1:
                logger.debug(f"MEXC index weights disabled for {symbol}")
                return "MEXC"

            # Get index composition
            rows = idxw.get("indexPrice", [])
            if not rows:
                logger.debug(f"Empty MEXC index data for {symbol}")
                return "MEXC"

            # Filter and format weights > 0%
            valid_weights = []
            for r in rows:
                try:
                    weight_pct = self._pct(float(r.get("wight", 0)))
                    if weight_pct > 0:
                        market_name = r.get("marketName", "N/A")
                        valid_weights.append(f"{market_name} {weight_pct:.1f}%")
                except (ValueError, TypeError, KeyError):
                    logger.debug(f"MEXC invalid weight data for {symbol}: {r} - {e}")
                    continue

            if valid_weights:
                # Return top 3 weights only for alerts (to keep them concise)
                top_weights = valid_weights[:3]
                result = f"{' • '.join(top_weights)}"
                logger.debug(f"MEXC index info for {symbol}: {result}")
                return result
            else:
                logger.debug(f"No valid MEXC weights found for {symbol}")
                return "MEXC"

        except Exception as e:
            logger.warning(f"Failed to get MEXC index info for {symbol}: {e}")
            return "MEXC"

    async def get_dex_info(self, coin: str) -> str:
        """Get DEX/networks information for MEXC."""
        try:
            logger.debug(f"MEXC fetching wallet networks for {coin}")
            ok, err, networks = await self.mexc_client.fetch_wallet_networks(coin)
            if not ok:
                logger.debug(f"MEXC wallet networks API failed for {coin}: {err}")
                return "N/A"
            if not networks:
                logger.debug(f"No MEXC network data for {coin}")
                return "N/A"

            # Get top 5 networks with deposit/withdraw enabled
            active_networks = []
            processed_count = 0

            for network in networks[:5]:
                try:
                    processed_count += 1
                    if network.get("depositEnable", False) or network.get("withdrawEnable", False):
                        network_name = network.get("network", "N/A")
                        if network_name and network_name.upper() != "UNKNOWN":
                            addr = network.get("contract") or network.get("contractAddress") or None
                            if not addr:
                                logger.debug(f"MEXC {coin}: Skipping network {network_name} (no contract address)")
                                continue

                            # Determine network prefix for DexScreener
                            network_prefix = NetworkPrefixUtils.get_dexscreener_prefix(network_name)
                            if not network_prefix:
                                logger.debug(f"MEXC {coin}: Unknown network prefix for {network_name}")
                                continue

                            # Create DexScreener link
                            dexscreener_url = f"https://dexscreener.com/{network_prefix}/{addr}"
                            active_networks.append(f'[{network_name}]({dexscreener_url})')
                except Exception as network_error:
                    logger.debug(f"MEXC {coin}: Error processing network {network.get('network', 'unknown')}: {network_error}")
                    continue

            logger.debug(f"MEXC {coin}: Processed {processed_count} networks, found {len(active_networks)} active")

            if active_networks:
                result = ", ".join(active_networks)
                logger.debug(f"MEXC DEX info for {coin}: {result}")
                return result
            else:
                return "N/A"

        except Exception as e:
            logger.warning(f"Failed to get MEXC DEX info for {coin}: {e}")
            return "N/A"

    async def get_buying_limit_info(self, symbol: str, token_price: float) -> str:
        """Get maximum buying limit in USD for MEXC."""
        try:
            normalized_symbol = symbol.replace('/', '_')
            return BuyLimitCalculator.calculate_buy_limit_from_data(await self._get_contract_data(normalized_symbol), token_price)

        except Exception as e:
            logger.warning(f"Failed to get MEXC buying limit info for {symbol}: {e}")
            return "Error"

    async def _get_contract_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get contract data for symbol."""
        ok_contract, err_contract, contract_data = await self.mexc_client.fetch_contract_detail(symbol)
        return contract_data if ok_contract else None

    @staticmethod
    def _pct(w: float) -> float:
        """Convert weight to percentage."""
        return round(w * 100, 1)

    def _extract_symbol(self, ticker_data: Dict[str, Any]) -> str:
        """Extract symbol from MEXC ticker data."""
        return ticker_data.get("symbol", "").replace("_", "/")

    def _extract_last_price(self, ticker_data: Dict[str, Any]) -> float:
        """Extract last price from MEXC ticker data."""
        return float(ticker_data.get("lastPrice", "0"))

    def _extract_fair_price(self, ticker_data: Dict[str, Any]) -> float:
        """Extract fair price from MEXC ticker data."""
        return float(ticker_data.get("fairPrice", "0"))

    def _extract_volume(self, ticker_data: Dict[str, Any]) -> float:
        """Extract volume from MEXC ticker data."""
        return float(ticker_data.get("volume24", "0"))

    def _extract_base_symbol(self, symbol: str) -> str:
        """Extract base symbol from MEXC symbol."""
        return symbol.split('/')[0]

    def _escape_symbol(self, symbol: str) -> str:
        """Escape MEXC symbol for Markdown."""
        return symbol.replace('.', '\\.').replace('-', '\\-')

    def _escape_base_symbol(self, symbol: str) -> str:
        """Escape base symbol for Markdown."""
        return symbol.split('/')[0].replace('.', '\\.').replace('-', '\\-')

    def _get_ticker_link(self, symbol: str, symbol_escaped: str) -> str:
        """Get MEXC ticker link."""
        # Replace / with _ for URL format
        url_symbol = symbol.replace('/', '_')
        return f"[{symbol_escaped}](https://www.mexc.com/ru-RU/futures/{url_symbol})"
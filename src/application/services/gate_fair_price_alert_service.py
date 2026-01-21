"""Gate.io Fair Price Alert Service."""

import asyncio
from typing import Any, Dict, Optional

from infrastructure.gate.websocket_client import GateWebSocketClient
from infrastructure.gate.client import GateClient
from core.config import Config
from core.logging_config import setup_logging
from core.markdown_service import MarkdownService
from core.utils.network_prefixes import NetworkPrefixUtils
from core.utils import BuyLimitCalculator
from .base_fair_price_alert_service import BaseFairPriceAlertService

logger = setup_logging()


class GateFairPriceAlertService(BaseFairPriceAlertService):
    """Fair price alert service for Gate.io."""

    def __init__(self, config: Config, markdown_service: MarkdownService, gate_client: GateClient):
        super().__init__(config, markdown_service, "GATE.IO", "🏛️")
        self.gate_client = gate_client
        self.ws_client = GateWebSocketClient(config)

    async def connect_websocket(self) -> bool:
        """Connect to Gate.io WebSocket."""
        try:
            logger.info("Gate.io: Initiating WebSocket connection...")
            connected = await self.ws_client.connect()
            if connected:
                logger.info("Gate.io: WebSocket connected successfully")
                return True
            else:
                logger.error("Gate.io: WebSocket connection failed")
                return False
        except Exception as e:
            logger.error(f"Gate.io: WebSocket connection error: {e}")
            return False

    async def disconnect_websocket(self) -> None:
        """Disconnect from Gate.io WebSocket."""
        await self.ws_client.disconnect()

    def is_websocket_connected(self) -> bool:
        """Check if Gate.io WebSocket is connected."""
        return self.ws_client.is_connected

    async def reconnect_websocket(self) -> bool:
        """Reconnect Gate.io WebSocket."""
        return await self.ws_client.reconnect()

    async def subscribe_tickers(self, callback) -> bool:
        """Subscribe to Gate.io ticker updates."""
        logger.info("Gate.io: Subscribing to ticker updates...")

        async def handle_ticker_update(ticker_data: Dict[str, Any]) -> None:
            try:
                # Use the callback provided by base class for uniform processing
                await callback(ticker_data)

            except Exception as e:
                logger.error(f"Gate.io: Error in ticker update handler: {e}")
                logger.debug(f"Gate.io: Problematic ticker data: {ticker_data}", exc_info=True)

        success = await self.ws_client.subscribe_tickers(handle_ticker_update)
        if success:
            logger.info("Gate.io: Successfully subscribed to ticker updates")
        else:
            logger.error("Gate.io: Failed to subscribe to ticker updates")

        return success

    async def _process_ticker_data(self, ticker_data: Dict[str, Any]) -> None:
        """Process incoming ticker data from WebSocket."""
        try:
            logger.debug(f"Gate.io: Processing individual ticker update: {ticker_data.get('contract', 'unknown')}")
            await self._process_gate_ticker(ticker_data)
            logger.debug("Gate.io: Successfully processed ticker update")

        except Exception as e:
            logger.error(f"Gate.io: Error processing ticker data: {e}")
            logger.debug(f"Gate.io: Problematic ticker data: {ticker_data}", exc_info=True)

    async def _process_gate_ticker(self, ticker: Dict[str, Any]) -> None:
        """Process individual Gate.io ticker data."""
        try:
            contract_name = ticker.get("contract")
            if not contract_name:
                logger.debug("Gate.io: Skipping ticker with empty contract name")
                return

            last_price_str = ticker.get("last", "0")
            mark_price_str = ticker.get("mark_price", "0")

            try:
                last_price = float(last_price_str)
                mark_price = float(mark_price_str)
            except (ValueError, TypeError) as e:
                logger.warning(f"Gate.io {contract_name}: Invalid price data - last: '{last_price_str}', mark: '{mark_price_str}' - {e}")
                return

            logger.debug(f"Gate.io {contract_name}: Processing ticker - last: {last_price:.8f}, mark: {mark_price:.8f}")

            if self._should_alert(last_price, mark_price, contract_name):
                # Check if we already alerted for this symbol recently
                if contract_name in self.alerted_symbols:
                    logger.debug(f"Gate.io {contract_name}: Skipping alert (already alerted recently)")
                    return

                # Determine alert type
                spread_pct = ((last_price - mark_price) / mark_price) * 100
                if spread_pct > 0:
                    alert_type = "🔴 SHORT"
                    emoji = "⚠️"
                else:
                    alert_type = "🟢 LONG"
                    emoji = "ℹ️"

                logger.info(f"Gate.io {contract_name}: Preparing alert - type: {alert_type}, spread: {spread_pct:+.4f}%")

                # Send alert
                await self._send_alert(ticker, alert_type, emoji)

                # Mark as alerted to avoid spam
                self.alerted_symbols.add(contract_name)
                logger.debug(f"Gate.io {contract_name}: Added to cooldown list (total cooling down: {len(self.alerted_symbols)})")

                # Remove from alerted symbols after 2 minutes
                asyncio.create_task(self._remove_alert_cooldown(contract_name, 120))

        except Exception as e:
            logger.error(f"Error processing Gate.io ticker {ticker.get('contract', 'unknown')}: {e}")
            logger.debug(f"Gate.io ticker data that caused error: {ticker}", exc_info=True)

    async def get_index_info(self, symbol: str) -> str:
        """Get index weights information for Gate.io."""
        try:
            # Normalize symbol format for API call
            normalized_symbol = symbol.replace("_", "/")
            logger.debug(f"Gate.io normalizing symbol for index: {symbol} -> {normalized_symbol}")

            ok, err, index_data = await self.gate_client.fetch_index_constituents(normalized_symbol)

            if not ok:
                logger.debug(f"Gate.io index API failed for {symbol}: {err}")
                return "GATE.IO"
            if not index_data or not isinstance(index_data, dict):
                logger.debug(f"No Gate.io index data for {symbol}")
                return "GATE.IO"

            constituents = index_data.get("constituents", [])
            if not constituents:
                logger.debug(f"Empty Gate.io index data for {symbol}")
                return "GATE.IO"

            # Filter and format weights > 0%
            valid_weights = []
            for constituent in constituents:
                try:
                    weight_pct = float(constituent.get("weight", "0")) * 100
                    if weight_pct > 0:
                        exchange_name = constituent.get("exchange", "N/A")
                        valid_weights.append(f"{exchange_name} {weight_pct:.1f}%")
                except (ValueError, TypeError):
                    continue

            if valid_weights:
                # Return top 3 weights only for alerts (to keep them concise)
                top_weights = valid_weights[:3]
                result = f"{' • '.join(top_weights)}"
                logger.debug(f"Gate.io index info for {symbol}: {result}")
                return result
            else:
                logger.debug(f"No valid Gate.io weights found for {symbol}")
                return "GATE.IO"

        except Exception as e:
            logger.warning(f"Failed to get Gate.io index info for {symbol}: {e}")
            return "GATE.IO"

    async def get_dex_info(self, coin: str) -> str:
        """Get DEX/networks information for Gate.io."""
        try:
            ok, err, currency_data = await self.gate_client.fetch_currency_info(coin)
            if not ok or not currency_data:
                return "N/A"

            networks = currency_data.get("chains", [])
            if not networks:
                return "N/A"

            # Get top 5 networks with deposit/withdraw enabled
            active_networks = []
            for network in networks[:5]:
                # Check if deposit and withdraw are not disabled
                if not network.get("deposit_disabled", True) or not network.get("withdraw_disabled", True):
                    network_name = network.get("name", "N/A")
                    if network_name and network_name.upper() != "UNKNOWN":
                        addr = network.get("addr") or None
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
            logger.warning(f"Failed to get Gate.io DEX info for {coin}: {e}")
            return "N/A"

    async def get_buying_limit_info(self, symbol: str, token_price: float) -> str:
        """Get maximum buying limit in USD for Gate.io."""
        try:
            return BuyLimitCalculator.calculate_buy_limit_from_data(await self._get_contract_data(symbol), token_price)

        except Exception as e:
            logger.warning(f"Failed to get Gate.io buying limit info for {symbol}: {e}")
            return "Error"

    async def _get_contract_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get contract data for symbol."""
        ok_contracts, err_contracts, contracts = await self.gate_client.fetch_futures_contracts()
        if ok_contracts and contracts:
            for contract in contracts:
                if contract.get("name") == symbol:
                    return contract
        return None

    def _extract_symbol(self, ticker_data: Dict[str, Any]) -> str:
        """Extract symbol from Gate.io ticker data."""
        return ticker_data.get("contract", "")

    def _extract_last_price(self, ticker_data: Dict[str, Any]) -> float:
        """Extract last price from Gate.io ticker data."""
        return float(ticker_data.get("last", "0"))

    def _extract_fair_price(self, ticker_data: Dict[str, Any]) -> float:
        """Extract fair price from Gate.io ticker data (mark_price for Gate.io)."""
        return float(ticker_data.get("mark_price", "0"))

    def _extract_volume(self, ticker_data: Dict[str, Any]) -> float:
        """Extract volume from Gate.io ticker data."""
        return float(ticker_data.get("volume_24h", "0"))

    def _extract_base_symbol(self, symbol: str) -> str:
        """Extract base symbol from Gate.io symbol."""
        return symbol.split('_')[0] if '_' in symbol else symbol

    def _escape_symbol(self, symbol: str) -> str:
        """Escape Gate.io symbol for Markdown."""
        return symbol.replace('.', '\\.').replace('-', '\\-').replace('_', '\\_')

    def _escape_base_symbol(self, symbol: str) -> str:
        """Escape base symbol for Markdown."""
        base = symbol.split('_')[0] if '_' in symbol else symbol
        return base.replace('.', '\\.').replace('-', '\\-')

    def _get_ticker_link(self, symbol: str, symbol_escaped: str) -> str:
        """Get Gate.io ticker link."""
        return f"[{symbol_escaped}](https://www.gate.io/futures/{symbol.upper()})"
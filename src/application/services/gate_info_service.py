"""Gate.io information service - business logic for formatting exchange data."""

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from infrastructure.gate.client import GateClient
from infrastructure.gate.dtos import (
    GateFuturesContractData,
    GateFuturesTickerData,
    GateSpotTickerData,
    GateCurrencyNetworkData,
)
from core.logging_config import setup_logging
from core.markdown_service import MarkdownService
from .base_message_builder import BaseMessageBuilder

logger = setup_logging()


class GateInfoService(BaseMessageBuilder):
    """
    Service for fetching and formatting Gate.io information.
    """

    def __init__(self, gate_client: GateClient, markdown_service: MarkdownService):
        self.gate_client = gate_client
        self.markdown_service = markdown_service

    @staticmethod
    def _normalize_futures_symbol(raw: str) -> str:
        """Normalize futures symbol."""
        symbol = raw.strip().replace("-", "_").replace("/", "_").upper()

        # If no underscore found, assume it's base currency and add _USDT
        if "_" not in symbol:
            # Common quote currencies to check
            quote_currencies = ["USDT", "USD", "BTC", "ETH", "BNB"]
            if not any(symbol.endswith(quote) for quote in quote_currencies):
                symbol = f"{symbol}_USDT"

        return symbol

    @staticmethod
    def _futures_to_spot_symbol(fut: str) -> Optional[str]:
        """Convert futures symbol to spot symbol."""
        if "_" not in fut:
            return None
        a, b = fut.split("_", 1)
        if not a or not b:
            return None
        return f"{a}_{b}".upper()

    @staticmethod
    def _is_probably_spot_symbol_ok(s: str) -> bool:
        """Check if spot symbol looks valid."""
        return bool(s and not s[0].isdigit())

    @staticmethod
    def _fmt_num(x: Any) -> str:
        """Format number value."""
        try:
            return f"{float(x):,.4f}".rstrip("0").rstrip(".")
        except (ValueError, TypeError):
            return str(x)

    @staticmethod
    def _pct(w: float) -> float:
        """Convert weight to percentage."""
        return round(w * 100, 2)

    async def get_gate_info(self, symbol: str) -> Tuple[str, List[str]]:
        """
        Get formatted Gate.io information for symbol.

        Args:
            symbol: Futures symbol to get info for

        Returns:
            Tuple of (formatted_message, errors_list)
        """
        logger.info(f"Processing Gate.io info request for symbol: {symbol}")

        normalized_symbol = self._normalize_futures_symbol(symbol)
        errors = []

        # Prepare parallel API calls
        api_tasks = [
            self.gate_client.fetch_futures_contracts(),
            self.gate_client.fetch_futures_tickers(),
        ]

        # Execute all API calls in parallel
        logger.info(f"Making {len(api_tasks)} parallel API calls for {normalized_symbol}")
        start_time = time.monotonic()
        api_results = await asyncio.gather(*api_tasks, return_exceptions=True)
        api_time = time.monotonic() - start_time
        logger.info(f"Parallel API calls completed in {api_time:.2f}s")

        # Unpack results
        contracts_result = api_results[0]
        tickers_result = api_results[1]

        # Process contracts
        ok_contracts, err_contracts, contracts = contracts_result
        contract = None
        if ok_contracts and contracts:
            for c in contracts:
                if c.get("name") == normalized_symbol:
                    contract = c
                    break
        elif not ok_contracts:
            errors.append(f"contracts: {err_contracts}")

        # Process tickers
        ok_tickers, err_tickers, tickers = tickers_result
        ft = None
        if ok_tickers and tickers:
            for t in tickers:
                if t.get("contract") == normalized_symbol:
                    ft = t
                    break
        elif not ok_tickers:
            errors.append(f"futures tickers: {err_tickers}")

        # Process additional API calls (index and currency) if contract exists
        index_constituents = None
        index_price = None
        index_time = None
        networks_coin = None
        networks = None

        if contract:
            # Extract underlying currency
            underlying = str(contract.get("underlying", "")).strip().upper()
            if not underlying:
                # Extract base currency from contract name (e.g., "1_USDT" -> "1")
                contract_name = str(contract.get("name", "")).strip()
                if "_" in contract_name:
                    underlying = contract_name.split("_")[0].upper()

            # Prepare additional parallel calls
            additional_tasks = []
            if underlying:
                additional_tasks.append(self.gate_client.fetch_currency_info(underlying))

            # Always try to get index data
            additional_tasks.append(self.gate_client.fetch_index_constituents(normalized_symbol))

            # Execute additional calls in parallel
            if additional_tasks:
                logger.info(f"Making {len(additional_tasks)} additional parallel API calls")
                additional_start_time = time.monotonic()
                additional_results = await asyncio.gather(*additional_tasks, return_exceptions=True)
                additional_api_time = time.monotonic() - additional_start_time
                logger.info(f"Additional parallel API calls completed in {additional_api_time:.2f}s")

                # Process currency info (first result if exists)
                if underlying and len(additional_results) > 0:
                    ok_currency, err_currency, currency_data = additional_results[0]
                    if ok_currency and currency_data:
                        networks_coin = underlying
                        networks = currency_data.get("chains", [])
                    elif not ok_currency:
                        errors.append(f"currency ({underlying}): {err_currency}")

                # Process index data (last result)
                if len(additional_results) > (1 if underlying else 0):
                    index_result_idx = 1 if underlying else 0
                    ok_index, err_index, index_data = additional_results[index_result_idx]
                    if ok_index and index_data and isinstance(index_data, dict):
                        index_constituents = index_data.get("constituents", [])
                        index_price = index_data.get("value")
                        index_time = index_data.get("time")
                    # Don't add error for missing index - it's optional

        # Build the message as regular markdown
        regular_markdown = self._build_gate_message(
            symbol=normalized_symbol,
            contract=contract,
            ft=ft,
            networks_coin=networks_coin,
            networks=networks,
            index_constituents=index_constituents,
            index_price=index_price,
            errs=errors,
        )

        # Convert to Telegram MarkdownV2 format
        markdown_v2_message = self.markdown_service.convert_to_markdown_v2(regular_markdown)

        return markdown_v2_message, errors

    def _build_gate_message(
        self,
        symbol: str,
        contract: Optional[GateFuturesContractData],
        ft: Optional[GateFuturesTickerData],
        networks_coin: Optional[str],
        networks: Optional[List[GateCurrencyNetworkData]],
        index_constituents: Optional[List[dict]],
        index_price: Optional[str],
        errs: List[str],
    ) -> str:
        """Build formatted Gate.io information message."""
        lines = []

        # Header: 🏛️ *{SYMBOL}* | Status 🟢
        lines.append(f"🏛️ *{symbol}* | Status 🟢")
        lines.append("")

        if ft:
            last_price = self._fmt_money(ft.get('last', '—'))
            mark_price = self._fmt_money(ft.get('mark_price', '—'))
            index_price = self._fmt_money(ft.get('index_price', '—'))
            volume_raw = ft.get('volume_24h', '0')

            # Format large numbers
            volume_formatted = self._fmt_large_num(volume_raw)

            # Calculate spread and recommendation
            spread_str, recommendation = self._calculate_spread_and_recommendation(
                ft.get('last'), ft.get('mark_price')
            )

            # Spread line
            lines.append(self._build_spread_line(spread_str, recommendation))
            lines.append("")

            # Prices line
            lines.append(self._build_prices_line(last_price, mark_price, index_price))
            lines.append("")

            # 24h line
            lines.append(self._build_volume_line(volume_formatted))
            lines.append("")
        else:
            lines.append("Нет данных о фьючерсах")
            lines.append("")

        # Index Weights: *Index:* {перечисление бирж с весами через •}
        if index_constituents and len(index_constituents) > 0:
            # Filter and sort constituents by weight > 0
            valid_constituents = []
            for constituent in index_constituents:
                try:
                    weight_pct = float(constituent.get("weight", "0")) * 100
                    if weight_pct > 0:
                        exchange_name = constituent.get("exchange", "N/A")
                        valid_constituents.append(f"{exchange_name} {weight_pct:.1f}\\%")
                except (ValueError, TypeError):
                    continue

            if valid_constituents:
                lines.append(f"*Index:* {' • '.join(valid_constituents)}")
            else:
                lines.append("*Index:* 100% Gate.io")
        else:
            lines.append("*Index:* 100% Gate.io")
        lines.append("")

        # Networks & Contracts
        if networks_coin and networks:
            for n in networks:
                addr = n.get("addr") or None
                if not addr:
                    continue

                net_name = (n.get("name") or "UNKNOWN").upper()
                dep = "❌" if n.get("deposit_disabled") else "✅"
                wdr = "❌" if n.get("withdraw_disabled") else "✅"

                # Network line: *{NETWORK_NAME}:* D: {✅/❌} | W: {✅/❌}
                lines.append(f"*{net_name}:* D: {dep} | W: {wdr}")

                # Contract line: `{CONTRACT}`
                lines.append(f"`{addr}`")

                # Links: [DexScreener]({url}) | [GMGN]({url})
                network_prefix = "bsc"  # Default
                gmgn_network = "bsc"

                if "ETH" in net_name or "ERC20" in net_name:
                    network_prefix = "ethereum"
                    gmgn_network = "eth"
                elif "POLYGON" in net_name or "MATIC" in net_name:
                    network_prefix = "polygon"
                    gmgn_network = "polygon"
                elif "ARB" in net_name or "ARBITRUM" in net_name:
                    network_prefix = "arbitrum"
                    gmgn_network = "arbitrum"

                dexscreener_url = f"https://dexscreener.com/{network_prefix}/{addr}"
                gmgn_url = f"https://gmgn.ai/{gmgn_network}/token/{addr}"

                lines.append(f"[DexScreener]({dexscreener_url}) | [GMGN]({gmgn_url})")
                lines.append("")
        else:
            lines.append("Нет информации по сетям")
            lines.append("(возможно токен не поддерживает депозит/вывод)")
            lines.append("")

        # Trade link: 🔗 [Trade]({TRADE_LINK})
        trade_url = f"https://www.gate.io/futures/{symbol.lower()}"
        lines.append(f"🔗 [Trade]({trade_url})")
        lines.append("")

        # Errors
        if errs:
            lines.append("**⚠️ Заметки / Ошибки**")
            for e in errs[:5]:
                lines.append(f"• {str(e)}")

        return "\n".join(lines)

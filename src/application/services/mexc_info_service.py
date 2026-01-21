"""CEX information service - business logic for formatting exchange data."""

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from infrastructure.mexc.client import MexcClient
from infrastructure.mexc.dtos import (
    ContractDetailData,
    FuturesTickerData,
    IndexWeightsData,
    NetworkItem,
    Spot24HData,
)
from core.logging_config import setup_logging
from .base_message_builder import BaseMessageBuilder
from core.markdown_service import MarkdownService
from core.utils.network_prefixes import NetworkPrefixUtils
from core.utils import BuyLimitCalculator

logger = setup_logging()


class MexcInfoService(BaseMessageBuilder):
    """
    Service for fetching and formatting CEX information.
    """

    def __init__(self, mexc_client: MexcClient, markdown_service: MarkdownService):
        self.mexc_client = mexc_client
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
        return f"{a}{b}".upper()

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

    async def get_cex_info(self, symbol: str) -> Tuple[str, List[str]]:
        """
        Get formatted CEX information for symbol.

        Args:
            symbol: Futures symbol to get info for

        Returns:
            Tuple of (formatted_message, errors_list)
        """
        logger.info(f"Processing CEX info request for symbol: {symbol}")

        normalized_symbol = self._normalize_futures_symbol(symbol)
        errors = []

        # Prepare parallel API calls
        api_tasks = [
            self.mexc_client.fetch_contract_detail(normalized_symbol),
            self.mexc_client.fetch_index_weights(normalized_symbol),
            self.mexc_client.fetch_futures_ticker(normalized_symbol),
        ]

        # Execute all API calls in parallel
        logger.info(f"Making {len(api_tasks)} parallel API calls for {normalized_symbol}")
        start_time = time.monotonic()
        api_results = await asyncio.gather(*api_tasks, return_exceptions=True)
        api_time = time.monotonic() - start_time
        logger.info(f"Parallel API calls completed in {api_time:.2f}s")

        # Unpack results
        contract_result = api_results[0]
        idxw_result = api_results[1]
        ft_result = api_results[2]

        # Process results with exception handling
        def safe_unpack(result, name: str):
            if isinstance(result, Exception):
                return False, f"Exception: {str(result)}", None
            elif isinstance(result, tuple) and len(result) == 3:
                return result
            else:
                return False, f"Invalid result format for {name}", None

        ok_contract, err_contract, contract = safe_unpack(contract_result, "contract")
        ok_idxw, err_idxw, idxw = safe_unpack(idxw_result, "index weights")
        ok_ft, err_ft, ft = safe_unpack(ft_result, "futures ticker")

        # Collect errors
        if not ok_contract and err_contract:
            errors.append(f"contract: {err_contract}")
        if not ok_idxw and err_idxw:
            errors.append(f"index weights: {err_idxw}")
        if not ok_ft and err_ft:
            errors.append(f"futures ticker: {err_ft}")

        networks_coin = None
        networks = None
        if contract:
            base_coin = str(contract.get("baseCoin", "")).strip().upper()
            quote_coin = str(contract.get("quoteCoin", "")).strip().upper()
            preferred = base_coin or quote_coin

            if preferred:
                ok_nets, err_nets, nets = await self.mexc_client.fetch_wallet_networks(preferred)
                if ok_nets:
                    networks_coin = preferred
                    networks = nets
                else:
                    errors.append(f"networks ({preferred}): {err_nets}")

        # Build the message as regular markdown
        regular_markdown = self._build_cex_message(
            symbol=normalized_symbol,
            contract=contract,
            idxw=idxw,
            ft=ft,
            networks_coin=networks_coin,
            networks=networks,
            errs=errors,
        )

        # Convert to Telegram MarkdownV2 format
        markdown_v2_message = self.markdown_service.convert_to_markdown_v2(regular_markdown)

        return markdown_v2_message, errors

    def _build_cex_message(
        self,
        symbol: str,
        contract: Optional[ContractDetailData],
        idxw: Optional[IndexWeightsData],
        ft: Optional[FuturesTickerData],
        networks_coin: Optional[str],
        networks: Optional[List[NetworkItem]],
        errs: List[str],
    ) -> str:
        """Build formatted CEX information message."""
        lines = []

        base_coin = contract.get("baseCoin", "—").upper() if contract else "—"

        # Header: 🔔 *{SYMBOL}/USDT* | Status 🟢
        lines.append(f"🔔 *{symbol}* | Status 🟢")
        lines.append("")

        if ft:
            last_price = self._fmt_money(ft.get('lastPrice', '—'))
            fair_price = self._fmt_money(ft.get('fairPrice', '—'))
            index_price = self._fmt_money(ft.get('indexPrice', '—'))
            volume_raw = ft.get('volume24', '0')
            amount_raw = ft.get('amount24', '0')

            # Format large numbers
            volume_formatted = self._fmt_large_num(volume_raw)
            amount_formatted = self._fmt_large_num(amount_raw)

            # Calculate spread and recommendation
            spread_str, recommendation = self._calculate_spread_and_recommendation(
                ft.get('lastPrice'), ft.get('fairPrice')
            )

            # Spread line
            lines.append(self._build_spread_line(spread_str, recommendation))
            lines.append("")

            # Prices line
            lines.append(self._build_prices_line(last_price, fair_price, index_price))
            lines.append("")

            # 24h line
            lines.append(self._build_volume_line(volume_formatted, amount_formatted))
            lines.append("")

            # Buy Limit: calculate maximum USD that can be spent
            raw_last_price = ft.get('lastPrice')
            try:
                token_price = float(raw_last_price) if raw_last_price else 0.0
            except (ValueError, TypeError):
                token_price = 0.0
            buy_limit_info = BuyLimitCalculator.calculate_buy_limit_from_data(contract, token_price)
            lines.append(f"*Buy Limit:* {buy_limit_info}")
            lines.append("")
        else:
            lines.append("Нет данных о фьючерсах")
            lines.append("")

        # Index Weights: *Index:* {перечисление бирж с весами через •}
        if idxw and idxw.get("showIndexSymbolWeight") == 1:
            rows = idxw.get("indexPrice", [])
            if rows:
                # Filter and sort weights > 0%
                valid_weights = []
                for r in rows:
                    weight_pct = self._pct(float(r.get("wight", 0)))
                    if weight_pct > 0:
                        valid_weights.append(f"{r.get('marketName', 'N/A')} {weight_pct:.1f}%")

                if valid_weights:
                    lines.append(f"*Index:* {' • '.join(valid_weights)}")
                else:
                    lines.append("*Index:* 100% MEXC")
            else:
                lines.append("*Index:* 100% MEXC")
        else:
            lines.append("*Index:* 100% MEXC")
        lines.append("")

        # Networks & Contracts
        if networks_coin and networks and networks_coin.upper() == base_coin:
            for n in networks:
                addr = n.get("contract") or n.get("contractAddress") or None
                if not addr:
                    continue

                net_name = (n.get("network") or "UNKNOWN").upper()
                dep = "✅" if n.get("depositEnable") else "❌"
                wdr = "✅" if n.get("withdrawEnable") else "❌"

                # Network line: *{NETWORK_NAME}:* D: {✅/❌} | W: {✅/❌}
                lines.append(f"*{net_name}:* D: {dep} | W: {wdr}")

                # Contract line: `{CONTRACT}`
                lines.append(f"`{addr}`")

                # Links: [DexScreener]({url}) | [GMGN]({url})
                dexscreener_url, gmgn_url = NetworkPrefixUtils.get_scanner_links(net_name, addr)

                lines.append(f"[DexScreener]({dexscreener_url}) \\| [GMGN]({gmgn_url})")
                lines.append("")
        else:
            lines.append("Нет информации по сетям")
            lines.append("(возможно токен не поддерживает депозит/вывод)")
            lines.append("")

        # Trade link: [Trade]({TRADE_LINK})
        trade_url = f"https://futures.mexc.com/exchange/{symbol}"
        lines.append(f"🔗 [Trade]({trade_url})")
        lines.append("")

        # Errors
        if errs:
            lines.append("**⚠️ Заметки / Ошибки**")
            for e in errs[:5]:
                lines.append(f"• {str(e)}")

        return "\n".join(lines)

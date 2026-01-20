"""CEX Aggregator Service - aggregates data from multiple exchanges."""

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from infrastructure.mexc.client import MexcClient
from infrastructure.gate.client import GateClient
from infrastructure.http_client import HttpClient
from infrastructure.mexc.dtos import ContractDetailData, FuturesTickerData, NetworkItem
from infrastructure.gate.dtos import GateFuturesContractData, GateFuturesTickerData, GateCurrencyNetworkData

from .base_message_builder import BaseMessageBuilder


class ExchangeData:
    """Container for exchange-specific data."""

    def __init__(self, name: str):
        self.name = name
        self.spot_price: Optional[str] = None
        self.futures_price: Optional[str] = None
        self.contracts: List[Dict[str, Any]] = []
        self.networks: List[Dict[str, Any]] = []
        self.spot_url: Optional[str] = None
        self.futures_url: Optional[str] = None


class CexAggregatorService:
    """Service for aggregating cryptocurrency data from multiple exchanges."""

    def __init__(self, mexc_client: MexcClient, gate_client: GateClient, http_client: HttpClient, markdown_service):
        self.mexc_client = mexc_client
        self.gate_client = gate_client
        self.http_client = http_client
        self.markdown_service = markdown_service

    async def get_aggregated_info(self, symbol: str) -> Tuple[str, List[str]]:
        """Get aggregated information for symbol from all exchanges."""
        import time
        import logging
        logger = logging.getLogger(__name__)

        start_time = time.monotonic()
        errors = []

        # Get all data in parallel: MEXC data, Gate data, and spot prices
        logger.debug(f"Starting parallel API requests for symbol: {symbol}")
        mexc_task = self._get_mexc_data(symbol)
        gate_task = self._get_gate_data(symbol)
        spot_task = self._get_spot_prices(symbol)

        # Wait for all tasks to complete
        api_start = time.monotonic()
        mexc_data, mexc_errs = await mexc_task
        gate_data, gate_errs = await gate_task
        spot_prices = await spot_task
        api_time = time.monotonic() - api_start

        errors.extend(mexc_errs)
        errors.extend(gate_errs)

        logger.debug(f"API requests completed in {api_time:.2f}s - MEXC: {'OK' if mexc_data else 'FAIL'}, GATE: {'OK' if gate_data else 'FAIL'}, SPOT: {len(spot_prices)} prices")

        # Build the aggregated message
        build_start = time.monotonic()
        message = self._build_aggregated_message(symbol, mexc_data, gate_data, spot_prices, errors)
        build_time = time.monotonic() - build_start

        total_time = time.monotonic() - start_time
        logger.debug(f"Message built in {build_time:.2f}s, total time: {total_time:.2f}s")

        return message, errors

    async def _get_mexc_data(self, symbol: str) -> Tuple[Optional[ExchangeData], List[str]]:
        """Get data from MEXC."""
        errors = []

        try:
            data = ExchangeData("MEXC")
            normalized_symbol = self._normalize_mexc_symbol(symbol)

            # Get contract details and futures ticker in parallel
            tasks = [
                self.mexc_client.fetch_contract_detail(normalized_symbol),
                self.mexc_client.fetch_futures_ticker(normalized_symbol),
                self.mexc_client.fetch_wallet_networks(normalized_symbol.split('_')[0] if '_' in normalized_symbol else symbol)
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)
            data.spot_url = f"https://www.mexc.com/exchange/{normalized_symbol}"
            
            # Process contract details
            if len(results) > 0 and not isinstance(results[0], Exception):
                ok_contract, err_contract, contract = results[0]
                if ok_contract and contract:
                    data.futures_url = f"https://futures.mexc.com/exchange/{normalized_symbol}"
                    # Contract info will be extracted later from networks

            # Process futures ticker
            if len(results) > 1 and not isinstance(results[1], Exception):
                ok_ft, err_ft, ft = results[1]
                if ok_ft and ft:
                    last_price = ft.get('lastPrice')
                    if last_price:
                        data.futures_price = f"{BaseMessageBuilder._fmt_money(last_price)}$"

            # Process networks (contracts)
            if len(results) > 2 and not isinstance(results[2], Exception):
                ok_nets, err_nets, nets = results[2]
                if ok_nets and nets:
                    for net in nets[:1]:  # Take first network
                        data.contracts.append({
                            'address': net.get('contract', ''),
                            'network': net.get('network', ''),
                            'deposit_enabled': net.get('depositEnable', False),
                            'withdraw_enabled': net.get('withdrawEnable', False)
                        })

            return data, errors

        except Exception as e:
            errors.append(f"MEXC error: {str(e)}")
            return None, errors

    def _normalize_mexc_symbol(self, symbol: str) -> str:
        """Normalize symbol for MEXC."""
        symbol = symbol.strip().replace("-", "_").replace("/", "_").upper()
        if "_" not in symbol:
            symbol = f"{symbol}_USDT"
        return symbol

    async def _get_gate_data(self, symbol: str) -> Tuple[Optional[ExchangeData], List[str]]:
        """Get data from Gate.io."""
        errors = []

        try:
            data = ExchangeData("GATE")
            normalized_symbol = symbol.upper()

            # Get futures contracts, tickers, and currency info in parallel
            tasks = [
                self.gate_client.fetch_futures_contracts(),
                self.gate_client.fetch_futures_tickers(),
                self.gate_client.fetch_spot_tickers(f"{normalized_symbol}_USDT"),
                self.gate_client.fetch_currency_info(normalized_symbol)
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process futures contracts
            futures_contract = None
            if len(results) > 0 and not isinstance(results[0], Exception):
                ok_contracts, err_contracts, contracts = results[0]
                if ok_contracts and contracts:
                    # Find contract by symbol
                    for contract in contracts:
                        if contract.get('name', '').upper() == f"{normalized_symbol}_USDT":
                            futures_contract = contract
                            data.futures_url = f"https://www.gate.io/futures/USDT/{normalized_symbol}_USDT"
                            break

            # Process futures tickers
            if len(results) > 1 and not isinstance(results[1], Exception):
                ok_tickers, err_tickers, tickers = results[1]
                if ok_tickers and tickers:
                    # Find ticker by symbol
                    for ticker in tickers:
                        if ticker.get('contract', '').upper() == f"{normalized_symbol}_USDT":
                            last_price = ticker.get('last')
                            if last_price:
                                data.futures_price = f"{BaseMessageBuilder._fmt_money(last_price)}$"
                            break

            # Process spot tickers
            if len(results) > 2 and not isinstance(results[2], Exception):
                ok_spot, err_spot, spot_tickers = results[2]
                if ok_spot and spot_tickers:
                    for ticker in spot_tickers:
                        if ticker.get('currency_pair', '').upper() == f"{normalized_symbol}_USDT":
                            last_price = ticker.get('last')
                            if last_price:
                                data.spot_url = f"https://www.gate.io/trade/{normalized_symbol}_USDT"
                            break

            # Process currency info (networks)
            if len(results) > 3 and not isinstance(results[3], Exception):
                ok_currency, err_currency, currency_data = results[3]
                if ok_currency and currency_data:
                    chains = currency_data.get('chains', [])
                    for chain in chains[:1]:  # Take first chain
                        data.contracts.append({
                            'address': chain.get('addr', ''),
                            'network': chain.get('name', ''),
                            'deposit_enabled': not chain.get('deposit_disabled', False),
                            'withdraw_enabled': not chain.get('withdraw_disabled', False)
                        })

            return data, errors

        except Exception as e:
            errors.append(f"Gate.io error: {str(e)}")
            return None, errors

    def _build_aggregated_message(self, symbol: str, mexc_data: Optional[ExchangeData],
                                gate_data: Optional[ExchangeData], spot_prices: Dict[str, str], errors: List[str]) -> str:
        """Build the aggregated message."""
        lines = []

        # Header
        lines.append(f"**Coin:** `{symbol}` | Status 🟢")
        lines.append("")

        # Contracts Info
        if mexc_data and mexc_data.contracts or gate_data and gate_data.contracts:
            lines.append("➖➖➖**Contracts Info**➖➖➖")
            lines.append("")

            # Group contracts by address and network
            contract_groups = {}

            # Collect MEXC contracts
            if mexc_data and mexc_data.contracts:
                for contract in mexc_data.contracts:
                    addr = contract.get('address', '').lower()
                    network = self._normalize_network_name(contract.get('network', ''))
                    key = f"{addr}|{network}"

                    if key not in contract_groups:
                        contract_groups[key] = {
                            'address': contract['address'],
                            'network': network,
                            'exchanges': []
                        }
                    contract_groups[key]['exchanges'].append('MEXC')

            # Collect Gate contracts
            if gate_data and gate_data.contracts:
                for contract in gate_data.contracts:
                    addr = contract.get('address', '').lower()
                    network = self._normalize_network_name(contract.get('network', ''))
                    key = f"{addr}|{network}"

                    if key not in contract_groups:
                        contract_groups[key] = {
                            'address': contract['address'],
                            'network': network,
                            'exchanges': []
                        }
                    contract_groups[key]['exchanges'].append('GATE')

            # Display grouped contracts
            for contract_group in contract_groups.values():
                exchanges_str = ", ".join(contract_group['exchanges'])
                lines.append(f"↱ **Contract:** {contract_group['address']} ({exchanges_str})")
                lines.append(f"↳ **Network:** {contract_group['network']}")
                lines.append("")

        # Exchanges Info
        lines.append("➖➖➖**Exchanges Info**➖➖➖")
        lines.append("")

        # MEXC info
        mexc_spot_price = spot_prices.get('MEXC')
        mexc_spot_display = f"{BaseMessageBuilder._fmt_money(mexc_spot_price)}$" if mexc_spot_price else "N/A"
        mexc_futures_display = mexc_data.futures_price if mexc_data and mexc_data.futures_price else "N/A"

        lines.append(f"↱ **MEXC** | S: {mexc_spot_display} | F: {mexc_futures_display}")

        if mexc_data and mexc_data.contracts:
            contract = mexc_data.contracts[0]
            network = contract['network']
            deposit_status = "✅" if contract.get('deposit_enabled', False) else "❌"
            withdraw_status = "✅" if contract.get('withdraw_enabled', False) else "❌"
            lines.append(f"⇨ {network} - D {deposit_status} | W {withdraw_status}")
        else:
            lines.append("⇨ N/A - D ❌ | W ❌")

        spot_link = (mexc_data.spot_url if mexc_data and mexc_data.spot_url else "N/A") if mexc_spot_price else "N/A"
        futures_link = mexc_data.futures_url if mexc_data and mexc_data.futures_url else "N/A"
        lines.append(f"↳ **Links:** [Spot]({spot_link}) | [Futures]({futures_link})")
        lines.append("")

        # Gate info
        gate_spot_price = spot_prices.get('GATE')
        gate_spot_display = f"{BaseMessageBuilder._fmt_money(gate_spot_price)}$" if gate_spot_price else "N/A"
        gate_futures_display = gate_data.futures_price if gate_data and gate_data.futures_price else "N/A"

        lines.append(f"↱ **GATE** | S: {gate_spot_display} | F: {gate_futures_display}")

        if gate_data and gate_data.contracts:
            contract = gate_data.contracts[0]
            network = contract['network']
            deposit_status = "✅" if contract.get('deposit_enabled', False) else "❌"
            withdraw_status = "✅" if contract.get('withdraw_enabled', False) else "❌"
            lines.append(f"⇨ {network} - D {deposit_status} | W {withdraw_status}")
        else:
            lines.append("⇨ N/A - D ❌ | W ❌")

        spot_link = (gate_data.spot_url if gate_data and gate_data.spot_url else "N/A") if gate_spot_price else "N/A"
        futures_link = gate_data.futures_url if gate_data and gate_data.futures_url else "N/A"
        lines.append(f"↳ **Links:** [Spot]({spot_link}) | [Futures]({futures_link})")
        lines.append("")

        # Convert to markdown
        regular_markdown = "\n".join(lines)
        return self.markdown_service.convert_to_markdown_v2(regular_markdown)

    async def _get_spot_prices(self, symbol: str) -> Dict[str, str]:
        """Get spot prices from both exchanges in parallel."""
        async def get_price(exchange: str, symbol: str) -> Optional[str]:
            """Get spot price for a specific exchange."""
            try:
                if exchange == 'GATE':
                    # Convert symbol format: 1 -> 1_USDT for Gate.io
                    gate_symbol = f"{symbol}_USDT" if '_' not in symbol else symbol
                    url = "https://api.gateio.ws/api/v4/spot/tickers"
                    params = {"currency_pair": gate_symbol}

                    ok, error, data = await self.http_client.get_json(url, params)
                    if ok and isinstance(data, list) and len(data) > 0:
                        return data[0].get('last')

                elif exchange == 'MEXC':
                    # Convert symbol format: 1 -> 1USDT for MEXC
                    mexc_symbol = f"{symbol}USDT" if '_' not in symbol else symbol.replace('_', '')
                    url = "https://api.mexc.com/api/v3/ticker/price"
                    params = {"symbol": mexc_symbol}

                    ok, error, data = await self.http_client.get_json(url, params)
                    if ok and isinstance(data, dict):
                        return data.get('price')

            except Exception:
                pass

            return None

        # Get prices in parallel
        gate_task = get_price('GATE', symbol)
        mexc_task = get_price('MEXC', symbol)

        gate_price, mexc_price = await asyncio.gather(gate_task, mexc_task)

        spot_prices = {}
        if gate_price:
            spot_prices['GATE'] = gate_price
        if mexc_price:
            spot_prices['MEXC'] = mexc_price

        return spot_prices

    def _normalize_network_name(self, network: str) -> str:
        """Normalize network names to standard format."""
        network_lower = network.lower()

        # BSC variations
        if 'bnb' in network_lower and ('smart chain' in network_lower or 'bep20' in network_lower or 'bsc' in network_lower):
            return 'BSC'

        # Polygon/MATIC variations
        if 'polygon' in network_lower or 'matic' in network_lower:
            return 'Polygon'

        # ETH variations
        if 'eth' in network_lower and ('ethereum' in network_lower or 'erc20' in network_lower):
            return 'ETH'

        # SOL variations
        if 'sol' in network_lower:
            return 'SOL'

        # Return original if no match
        return network

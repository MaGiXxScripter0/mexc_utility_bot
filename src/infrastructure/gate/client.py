from typing import Any, Dict, List, Optional, Tuple

from infrastructure.http_client import HttpClient
from infrastructure.gate.dtos import (
    GateFuturesContractData,
    GateFuturesTickerData,
    GateSpotTickerData,
    GateCurrencyData,
    extract_gate_contract,
    extract_gate_futures_ticker,
    extract_gate_spot_ticker,
)
from core.config import Config
from core.logging_config import setup_logging

logger = setup_logging()


class GateClient:
    """
    Gate.io API client for public endpoints.
    All requests are public, no authentication required.
    """

    def __init__(self, config: Config, http_client: HttpClient):
        self.config = config
        self.http_client = http_client

    async def fetch_futures_contracts(self) -> Tuple[bool, str, Optional[List[GateFuturesContractData]]]:
        """
        Fetch all futures contracts.

        Returns:
            Tuple of (success, error_message, contracts_list)
        """
        ok, err, data = await self.http_client.get_json(
            f"{self.config.gate_base_url}/futures/usdt/contracts"
        )

        if not ok:
            return False, err, None

        if not isinstance(data, list):
            return False, "invalid response format", None

        return True, "", data

    async def fetch_futures_tickers(self) -> Tuple[bool, str, Optional[List[GateFuturesTickerData]]]:
        """
        Fetch all futures tickers.

        Returns:
            Tuple of (success, error_message, tickers_list)
        """
        ok, err, data = await self.http_client.get_json(
            f"{self.config.gate_base_url}/futures/usdt/tickers"
        )

        if not ok:
            return False, err, None

        if not isinstance(data, list):
            return False, "invalid response format", None

        return True, "", data

    async def fetch_spot_tickers(self, currency_pair: Optional[str] = None) -> Tuple[bool, str, Optional[List[GateSpotTickerData]]]:
        """
        Fetch spot tickers.

        Args:
            currency_pair: Optional specific currency pair filter

        Returns:
            Tuple of (success, error_message, tickers_list)
        """
        params = {}
        if currency_pair:
            params["currency_pair"] = currency_pair

        ok, err, data = await self.http_client.get_json(
            f"{self.config.gate_base_url}/spot/tickers",
            params=params
        )

        if not ok:
            return False, err, None

        if not isinstance(data, list):
            return False, "invalid response format", None

        return True, "", data

    async def fetch_currency_info(self, currency: str) -> Tuple[bool, str, Optional[GateCurrencyData]]:
        """
        Fetch currency information including networks.

        Args:
            currency: Currency symbol (e.g., "BTC")

        Returns:
            Tuple of (success, error_message, currency_data)
        """
        ok, err, data = await self.http_client.get_json(
            f"{self.config.gate_base_url}/spot/currencies/{currency.upper()}"
        )

        if not ok:
            return False, err, None

        if not isinstance(data, dict):
            return False, "invalid response format", None

        return True, "", data

    async def fetch_index_constituents(self, index_symbol: str) -> Tuple[bool, str, Optional[List[dict]]]:
        """
        Fetch index constituents for a symbol.

        Args:
            index_symbol: Index symbol (e.g., "1_USDT")

        Returns:
            Tuple of (success, error_message, constituents_list)
        """

        # Try the apiw endpoint with browser-like headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Cache-Control": "max-age=0",
            "Sec-Ch-Ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://www.gate.com/"
        }

        ok, err, data = await self.http_client.get_json(
            f"https://www.gate.com/apiw/v2/futures/common/index/breakdown",
            params={"index": index_symbol},
            headers=headers
        )

        if ok:
            if isinstance(data, dict):
                # Check for successful response - either code=200 or direct data
                if data.get("code") == 200 or "data" in data:
                    index_data = data.get("data", {})
                    # Return the full index_data dict containing constituents, value, time
                    return True, "", index_data
            else:
                logger.warning(f"Unexpected index API response type: {type(data)}, data: {data}")

        # Fallback: return None if API is not accessible
        return False, err or "API not accessible", None

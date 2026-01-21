import hmac
import hashlib
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Protocol, Tuple

from infrastructure.http_client import HttpClient
from infrastructure.mexc.dtos import (
    ContractDetailData,
    FuturesTickerData,
    IndexWeightsData,
    NetworkItem,
    ServerTimeResponse,
    Spot24HData,
    extract_contract_detail,
    extract_first_or_dict,
)
from core.config import Config
from core.logging_config import setup_logging

logger = setup_logging()


class TimeSyncProtocol(Protocol):
    """Protocol for time synchronization."""

    def now_ms(self) -> int:
        """Get current timestamp in milliseconds with offset."""
        ...


class MexcTimeSync:
    """MEXC server time synchronization."""

    def __init__(self):
        self.offset_ms = 0

    async def sync(self, http_client: HttpClient, server_time_url: str) -> None:
        """Synchronize with MEXC server time."""
        ok, err, data = await http_client.get_json(server_time_url)
        if ok and isinstance(data, dict):
            server_time = data.get("serverTime")
            if server_time:
                server = int(server_time)
                local = int(time.time() * 1000)
                self.offset_ms = server - local
                logger.info(f"Time offset synchronized: {self.offset_ms} ms")
                return

        logger.warning(f"Time sync failed: {err}")

    def now_ms(self) -> int:
        """Get current timestamp with offset."""
        return int(time.time() * 1000) + self.offset_ms


class MexcClient:
    """
    MEXC API client with time synchronization and request signing.
    """

    def __init__(self, config: Config, http_client: HttpClient, time_sync: TimeSyncProtocol):
        self.config = config
        self.http_client = http_client
        self.time_sync = time_sync

    def _sign_request(self, params: Dict[str, Any]) -> str:
        """Sign request parameters with API secret."""
        if not self.config.mexc_api_secret:
            raise ValueError("MEXC API secret not configured")

        query = urllib.parse.urlencode(params, doseq=True)
        return hmac.new(
            self.config.mexc_api_secret.encode(),
            query.encode(),
            hashlib.sha256
        ).hexdigest()

    async def fetch_futures_ticker(self, symbol: str) -> Tuple[bool, str, Optional[FuturesTickerData]]:
        """
        Fetch futures ticker data.

        Args:
            symbol: Futures symbol

        Returns:
            Tuple of (success, error_message, ticker_data)
        """
        ok, err, data = await self.http_client.get_json(
            self.config.futures_ticker_url,
            params={"symbol": symbol}
        )

        if not ok or not data:
            return False, err, None

        ticker_data = extract_first_or_dict(data.get("data"))
        return bool(ticker_data), "" if ticker_data else "no data", ticker_data

    async def fetch_contract_detail(self, symbol: str) -> Tuple[bool, str, Optional[ContractDetailData]]:
        """
        Fetch contract detail.

        Args:
            symbol: Contract symbol

        Returns:
            Tuple of (success, error_message, contract_data)
        """
        # Try specific symbol first
        ok, err, data = await self.http_client.get_json(
            self.config.contract_detail_url,
            params={"symbol": symbol}
        )

        if ok and isinstance(data, dict):
            return extract_contract_detail(data, symbol)

        # Fallback: fetch all and search
        ok, err, data = await self.http_client.get_json(self.config.contract_detail_url)
        if not ok or not data or not isinstance(data, dict):
            return False, err, None

        return extract_contract_detail(data, symbol)

    async def fetch_index_weights(self, symbol: str) -> Tuple[bool, str, Optional[IndexWeightsData]]:
        """
        Fetch index weights.

        Args:
            symbol: Symbol for index weights

        Returns:
            Tuple of (success, error_message, weights_data)
        """
        ok, err, data = await self.http_client.get_json(
            self.config.index_weights_url,
            params={"symbol": symbol}
        )

        if not ok or not data:
            return False, err, None

        if not data.get("success"):
            error_msg = data.get("message") or data.get("msg") or "api error"
            return False, error_msg, None

        return True, "", data.get("data", {})

    async def fetch_spot_24h(self, spot_symbol: str) -> Tuple[bool, str, Optional[Spot24HData]]:
        """
        Fetch spot 24h ticker data.

        Args:
            spot_symbol: Spot symbol

        Returns:
            Tuple of (success, error_message, spot_data)
        """
        ok, err, data = await self.http_client.get_json(
            self.config.spot_24h_url,
            params={"symbol": spot_symbol}
        )

        if not ok or not data:
            return False, err, None

        if data.get("symbol") == spot_symbol:
            return True, "", data

        return False, "no spot data", None

    async def fetch_wallet_networks(self, coin: str) -> Tuple[bool, str, Optional[List[NetworkItem]]]:
        """
        Fetch wallet networks for coin.

        Args:
            coin: Coin symbol

        Returns:
            Tuple of (success, error_message, networks_list)
        """
        if not self.config.has_mexc_credentials:
            return False, "MEXC credentials not configured", None

        params = {
            "timestamp": self.time_sync.now_ms(),
            "recvWindow": 60000
        }
        params["signature"] = self._sign_request(params)

        headers = {"X-MEXC-APIKEY": self.config.mexc_api_key}

        ok, err, data = await self.http_client.get_json(
            self.config.wallet_networks_url,
            params=params,
            headers=headers
        )

        if not ok or not data:
            return False, err, None

        if not isinstance(data, list):
            return False, "invalid response format", None

        coin_upper = coin.upper()
        for item in data:
            if isinstance(item, dict) and str(item.get("coin", "")).upper() == coin_upper:
                networks = item.get("networkList") or []
                return True, "", networks if isinstance(networks, list) else []

        return False, f"coin {coin_upper} not found", None



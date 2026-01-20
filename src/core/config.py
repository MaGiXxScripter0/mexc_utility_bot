import os
from dataclasses import dataclass
from typing import Dict, Optional

from dotenv import load_dotenv

from core.logging_config import setup_logging

logger = setup_logging()


@dataclass(frozen=True)
class Config:
    """Application configuration loaded from environment variables."""

    # Bot configuration
    bot_token: str

    # MEXC API configuration
    mexc_api_key: Optional[str]
    mexc_api_secret: Optional[str]

    # Gate.io API configuration
    gate_api_key: Optional[str]
    gate_api_secret: Optional[str]

    # Proxy configuration
    http_proxy: Optional[str]

    # API endpoints
    mexc_futures_public: str = "https://contract.mexc.com/api/v1"
    mexc_futures_web: str = "https://www.mexc.com/api/platform/futures/api/v1"
    mexc_spot: str = "https://api.mexc.com"
    gate_base_url: str = "https://api.gateio.ws/api/v4"

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from environment variables."""
        load_dotenv()

        bot_token = os.getenv("BOT_TOKEN", "").strip()
        if not bot_token:
            raise ValueError("BOT_TOKEN environment variable is required")

        mexc_api_key = os.getenv("MEXC_API_KEY", "").strip() or None
        mexc_api_secret = os.getenv("MEXC_API_SECRET", "").strip() or None

        gate_api_key = os.getenv("GATE_API_KEY", "").strip() or None
        gate_api_secret = os.getenv("GATE_API_SECRET", "").strip() or None

        http_proxy = os.getenv("HTTP_PROXY", "").strip() or None

        return cls(
            bot_token=bot_token,
            mexc_api_key=mexc_api_key,
            mexc_api_secret=mexc_api_secret,
            gate_api_key=gate_api_key,
            gate_api_secret=gate_api_secret,
            http_proxy=http_proxy,
        )

    @property
    def has_mexc_credentials(self) -> bool:
        """Check if MEXC API credentials are available."""
        return bool(self.mexc_api_key and self.mexc_api_secret)

    @property
    def has_gate_credentials(self) -> bool:
        """Check if Gate.io API credentials are available."""
        return bool(self.gate_api_key and self.gate_api_secret)

    @property
    def index_weights_url(self) -> str:
        return f"{self.mexc_futures_web}/contract/market_price_v2"

    @property
    def contract_detail_url(self) -> str:
        return f"{self.mexc_futures_public}/contract/detail"

    @property
    def futures_ticker_url(self) -> str:
        return f"{self.mexc_futures_public}/contract/ticker"

    @property
    def spot_24h_url(self) -> str:
        return f"{self.mexc_spot}/api/v3/ticker/24hr"

    @property
    def wallet_networks_url(self) -> str:
        return f"{self.mexc_spot}/api/v3/capital/config/getall"

    @property
    def mexc_server_time_url(self) -> str:
        return f"{self.mexc_spot}/api/v3/time"

    def get_proxy_url(self) -> Optional[str]:
        """Get the proxy URL if configured."""
        return self.http_proxy

    def parse_proxy(self) -> Optional[Dict[str, str]]:
        """
        Parse proxy URL into aiohttp format.

        Supports formats:
        - http://host:port:username:password
        - http://username:password@host:port
        - http://host:port

        Returns:
            Dict with 'http' and 'https' proxy URLs, or None if no proxy
        """
        if not self.http_proxy:
            return None

        try:
            proxy_url = self.http_proxy.strip()

            # Handle format: http://host:port:username:password
            if proxy_url.startswith('http://'):
                parts = proxy_url[7:].split(':')  # Remove 'http://'
                if len(parts) == 4:
                    host, port, username, password = parts
                    proxy_with_auth = f"http://{username}:{password}@{host}:{port}"
                    return {
                        'http': proxy_with_auth,
                        'https': proxy_with_auth
                    }

            # Handle standard format: http://username:password@host:port
            elif '@' in proxy_url and proxy_url.startswith('http://'):
                return {
                    'http': proxy_url,
                    'https': proxy_url
                }

            # Handle format without auth: http://host:port
            elif proxy_url.startswith('http://') and proxy_url.count(':') == 1:
                return {
                    'http': proxy_url,
                    'https': proxy_url
                }

            else:
                logger.warning(f"Unsupported proxy format: {proxy_url}")
                return None

        except Exception as e:
            logger.error(f"Error parsing proxy URL: {e}")
            return None

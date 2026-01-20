import asyncio
import json
from typing import Any, Dict, Optional, Tuple

import aiohttp

from core.logging_config import setup_logging

logger = setup_logging()


class HttpClientError(Exception):
    """Base exception for HTTP client errors."""
    pass


class HttpClient:
    """
    HTTP client wrapper over aiohttp with structured error handling.
    """

    def __init__(self, timeout: float = 15.0, verify_ssl: bool = True):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.verify_ssl = verify_ssl
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self) -> None:
        """Initialize the HTTP session."""
        if self._session is None:
            connector = None
            if not self.verify_ssl:
                connector = aiohttp.TCPConnector(verify_ssl=False)
                logger.warning("SSL verification disabled for HTTP client")

            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                connector=connector
            )
            logger.debug("HTTP client session started")

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None
            logger.debug("HTTP client session closed")

    async def get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, str, Optional[Any]]:
        """
        Perform GET request and parse JSON response.

        Args:
            url: Request URL
            params: Query parameters
            headers: Request headers

        Returns:
            Tuple of (success, error_message, data)
        """
        if not self._session:
            raise HttpClientError("HTTP session not started")

        try:
            # Add default headers if none provided
            if not headers:
                headers = {}
            if 'User-Agent' not in headers:
                headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

            async with self._session.get(url, params=params, headers=headers) as response:
                response_text = await response.text()

                if response.status != 200:
                    error_msg = f"HTTP {response.status}: {response_text[:200]}"
                    logger.warning(f"HTTP request failed: {url} - {error_msg}")
                    return False, error_msg, None

                try:
                    data = json.loads(response_text)
                    return True, "", data
                except json.JSONDecodeError as e:
                    error_msg = f"JSON decode error: {e}"
                    logger.error(f"Failed to parse JSON from {url}: {error_msg}")
                    return False, error_msg, None

        except asyncio.TimeoutError:
            error_msg = f"Request timeout after {self.timeout.total}s"
            logger.warning(f"Timeout for {url}: {error_msg}")
            return False, error_msg, None
        except aiohttp.ClientError as e:
            error_msg = f"Client error: {e}"
            logger.error(f"HTTP client error for {url}: {error_msg}")
            return False, error_msg, None
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.exception(f"Unexpected error during HTTP request to {url}")
            return False, error_msg, None

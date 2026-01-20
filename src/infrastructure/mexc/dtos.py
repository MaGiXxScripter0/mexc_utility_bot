"""Data Transfer Objects for MEXC API responses."""

from typing import Any, Dict, List, Optional, Tuple, TypedDict


class ServerTimeResponse(TypedDict):
    """MEXC server time response."""
    serverTime: int


class FuturesTickerData(TypedDict):
    """Futures ticker data structure."""
    symbol: str
    lastPrice: str
    fairPrice: str
    indexPrice: str
    volume24: str
    amount24: str


class FuturesTickerResponse(TypedDict):
    """Futures ticker API response."""
    data: List[FuturesTickerData]


class ContractDetailData(TypedDict):
    """Contract detail data structure."""
    symbol: str
    baseCoin: str
    quoteCoin: str
    # Add other fields as needed


class ContractDetailResponse(TypedDict):
    """Contract detail API response."""
    data: List[ContractDetailData]


class IndexWeightItem(TypedDict):
    """Index weight item structure."""
    marketName: str
    wight: str  # Note: API returns 'wight' (typo in API)


class IndexWeightsData(TypedDict):
    """Index weights data structure."""
    showIndexSymbolWeight: int
    indexPrice: List[IndexWeightItem]


class IndexWeightsResponse(TypedDict):
    """Index weights API response."""
    success: bool
    message: Optional[str]
    msg: Optional[str]  # Alternative message field
    data: IndexWeightsData


class Spot24HData(TypedDict):
    """Spot 24h ticker data structure."""
    symbol: str
    # Add other fields as needed


class NetworkItem(TypedDict):
    """Network item for wallet configuration."""
    network: str
    depositEnable: bool
    withdrawEnable: bool
    contractAddress: Optional[str]


class WalletNetworksResponse(TypedDict):
    """Wallet networks API response."""
    coin: str
    networkList: List[NetworkItem]


# Utility functions for data extraction
def extract_first_or_dict(data: Any) -> Optional[Dict[str, Any]]:
    """
    Extract first item from list or return dict if data is dict.

    Args:
        data: Raw API response data

    Returns:
        Extracted dictionary or None
    """
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data:
        if isinstance(data[0], dict):
            return data[0]
    return None


def extract_contract_detail(data: Any, symbol: str) -> Tuple[bool, str, Optional[ContractDetailData]]:
    """
    Extract contract detail for specific symbol.

    Args:
        data: Raw API response data
        symbol: Symbol to find

    Returns:
        Tuple of (success, error_message, contract_data)
    """
    if isinstance(data, dict):
        contract_data = extract_first_or_dict(data.get("data"))
        if contract_data:
            return True, "", contract_data

    # Fallback: search in list
    if isinstance(data, dict):
        for item in data.get("data", []):
            if isinstance(item, dict) and str(item.get("symbol", "")).upper() == symbol.upper():
                return True, "", item

    return False, "symbol not found", None

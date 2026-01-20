"""Data Transfer Objects for Gate.io API responses."""

from typing import Any, Dict, List, Optional, Tuple, TypedDict


class GateFuturesContractData(TypedDict):
    """Gate.io futures contract data structure."""
    name: str
    underlying: str
    cycle: str
    type: str
    quanto_multiplier: str
    leverage_min: str
    leverage_max: str
    maintenance_rate: str
    mark_type: str
    mark_price: str
    index_price: str
    last_price: str
    maker_fee_rate: str
    taker_fee_rate: str
    order_price_round: str
    mark_price_round: str
    funding_rate: str
    order_size_min: int
    order_size_max: int
    order_price_deviate: str
    ref_rebate_rate: str
    funding_interval: int
    funding_next_apply: int
    risk_limit_base: str
    risk_limit_step: str
    risk_limit_max: str
    orderbook_id: int
    trade_id: int
    trade_size: int
    position_size: int
    config_change_time: int
    in_delisting: bool


class GateFuturesTickerData(TypedDict):
    """Gate.io futures ticker data structure."""
    contract: str
    last: str
    mark_price: str
    index_price: str
    volume_24h: str
    quanto_base_rate: Optional[str]


class GateSpotTickerData(TypedDict):
    """Gate.io spot ticker data structure."""
    currency_pair: str
    last: str
    lowest_ask: str
    highest_bid: str
    change_percentage: str
    base_volume: str
    quote_volume: str
    high_24h: str
    low_24h: str


class GateCurrencyNetworkData(TypedDict):
    """Gate.io currency network data structure."""
    name: str
    addr: Optional[str]
    withdraw_disabled: bool
    withdraw_delayed: bool
    deposit_disabled: bool


class GateCurrencyData(TypedDict):
    """Gate.io currency data structure."""
    currency: str
    chains: List[GateCurrencyNetworkData]


class GateIndexConstituentData(TypedDict):
    """Gate.io index constituent data structure."""
    exchange: str
    price: str
    weight: str


# Utility functions for data extraction
def extract_gate_contract(data: Any, symbol: str) -> Tuple[bool, str, Optional[GateFuturesContractData]]:
    """
    Extract contract data for specific symbol from Gate.io contracts list.

    Args:
        data: Raw API response data (list of contracts)
        symbol: Symbol to find

    Returns:
        Tuple of (success, error_message, contract_data)
    """
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and str(item.get("name", "")).upper() == symbol.upper():
                return True, "", item

    return False, "contract not found", None


def extract_gate_futures_ticker(data: Any, symbol: str) -> Tuple[bool, str, Optional[GateFuturesTickerData]]:
    """
    Extract futures ticker data for specific symbol from Gate.io tickers list.

    Args:
        data: Raw API response data (list of tickers)
        symbol: Symbol to find

    Returns:
        Tuple of (success, error_message, ticker_data)
    """
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and str(item.get("contract", "")).upper() == symbol.upper():
                return True, "", item

    return False, "futures ticker not found", None


def extract_gate_spot_ticker(data: Any, symbol: str) -> Tuple[bool, str, Optional[GateSpotTickerData]]:
    """
    Extract spot ticker data for specific symbol from Gate.io tickers list.

    Args:
        data: Raw API response data (list of tickers)
        symbol: Symbol to find

    Returns:
        Tuple of (success, error_message, ticker_data)
    """
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and str(item.get("currency_pair", "")).upper() == symbol.upper():
                return True, "", item

    return False, "spot ticker not found", None

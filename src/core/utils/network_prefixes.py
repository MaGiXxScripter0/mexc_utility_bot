"""Network prefix utilities for DEX scanners."""

from typing import Tuple


class NetworkPrefixUtils:
    """Utility class for determining network prefixes for DEX scanners."""

    @staticmethod
    def get_dexscreener_prefix(network_name: str) -> str:
        """Get DexScreener network prefix based on network name."""
        net_name = network_name.upper()

        if "ETH" in net_name or "ERC20" in net_name:
            return "ethereum"
        elif "POLYGON" in net_name or "MATIC" in net_name:
            return "polygon"
        elif "ARB" in net_name or "ARBITRUM" in net_name:
            return "arbitrum"
        elif "OP" in net_name or "OPTIMISM" in net_name:
            return "optimism"
        elif "BSC" in net_name or "BNB" in net_name:
            return "bsc"
        elif "SOL" in net_name or "SOLANA" in net_name:
            return "solana"
        elif "TRON" in net_name or "TRC20" in net_name:
            return "tron"
        else:
            return "bsc"  # Default fallback

    @staticmethod
    def get_gmgn_prefix(network_name: str) -> str:
        """Get GMGN network prefix based on network name."""
        net_name = network_name.upper()

        if "ETH" in net_name or "ERC20" in net_name:
            return "eth"
        elif "POLYGON" in net_name or "MATIC" in net_name:
            return "polygon"
        elif "ARB" in net_name or "ARBITRUM" in net_name:
            return "arbitrum"
        elif "OP" in net_name or "OPTIMISM" in net_name:
            return "optimism"
        elif "BSC" in net_name or "BNB" in net_name:
            return "bsc"
        elif "SOL" in net_name or "SOLANA" in net_name:
            return "solana"
        else:
            return "bsc"  # Default fallback

    @staticmethod
    def get_scanner_links(network_name: str, contract_address: str) -> Tuple[str, str]:
        """Get DexScreener and GMGN links for a network and contract."""
        dexscreener_prefix = NetworkPrefixUtils.get_dexscreener_prefix(network_name)
        gmgn_prefix = NetworkPrefixUtils.get_gmgn_prefix(network_name)

        dexscreener_url = f"https://dexscreener.com/{dexscreener_prefix}/{contract_address}"
        gmgn_url = f"https://gmgn.ai/{gmgn_prefix}/token/{contract_address}"

        return dexscreener_url, gmgn_url
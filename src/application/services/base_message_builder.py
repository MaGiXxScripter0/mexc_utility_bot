"""Base message builder for CEX services."""

from typing import Any, List, Optional


class BaseMessageBuilder:
    """Base class for building formatted cryptocurrency exchange messages."""

    @staticmethod
    def _fmt_money(x: Any) -> str:
        """Format price/money value."""
        try:
            val = float(x)
            if val >= 1:
                return f"{val:,.4f}"
            elif val >= 0.0001:
                return f"{val:.6f}"
            else:
                return f"{val:.8f}"
        except (ValueError, TypeError):
            return str(x) if x else "—"

    @staticmethod
    def _fmt_large_num(num) -> str:
        """Format large numbers with K/M/B suffixes."""
        try:
            val = float(num)
            if val >= 1_000_000_000:
                return f"{val/1_000_000_000:.1f}B"
            elif val >= 1_000_000:
                return f"{val/1_000_000:.1f}M"
            elif val >= 1_000:
                return f"{val/1_000:.1f}K"
            else:
                return f"{val:.0f}"
        except (ValueError, TypeError):
            return str(num) if num else "0"

    @staticmethod
    def _calculate_spread_and_recommendation(last_price: Any, mark_price: Any) -> tuple[str, str]:
        """Calculate spread percentage and trading recommendation.

        Returns:
            tuple: (spread_str, recommendation)
        """
        try:
            last_val = float(last_price)
            mark_val = float(mark_price)
            if mark_val > 0:
                spread_pct = ((last_val - mark_val) / mark_val) * 100

                if spread_pct > 0:
                    recommendation = "📉 SHORT (цена выше справедливой)"
                    spread_str = f"-{abs(spread_pct):.2f}%"
                elif spread_pct < 0:
                    recommendation = "📈 LONG (цена ниже справедливой)"
                    spread_str = f"+{abs(spread_pct):.2f}%"
                else:
                    recommendation = ""
                    spread_str = "0.00%"
            else:
                spread_str = "—"
                recommendation = ""
        except (ValueError, TypeError):
            spread_str = "—"
            recommendation = ""

        return spread_str, recommendation

    @staticmethod
    def _build_prices_line(last_price: str, mark_price: str, index_price: str) -> str:
        """Build the prices line."""
        return f"Last: `{last_price}` | Fair: `{mark_price}` | Index: `{index_price}`"

    @staticmethod
    def _build_spread_line(spread_str: str, recommendation: str = "") -> str:
        """Build the spread line."""
        if recommendation:
            return f"*Spread:* `{spread_str}` {recommendation}"
        else:
            return f"*Spread:* `{spread_str}`"

    @staticmethod
    def _build_volume_line(volume_formatted: str, amount_formatted: Optional[str] = None) -> str:
        """Build the 24h volume line."""
        if amount_formatted:
            return f"*24h:* Vol: `{volume_formatted}` | Amt: `{amount_formatted} USDT`"
        else:
            return f"*24h:* Vol: `{volume_formatted}`"

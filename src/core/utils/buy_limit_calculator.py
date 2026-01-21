"""Buy limit calculation utilities."""

from typing import Any, Dict, Optional


class BuyLimitCalculator:
    """Utility class for calculating buy limits from contract data."""

    @staticmethod
    def calculate_buy_limit_from_data(contract_data: Optional[Dict[str, Any]], token_price: float) -> str:
        """Calculate maximum buying limit in USD from contract data."""
        try:
            # Validate token_price
            if token_price is None or not isinstance(token_price, (int, float)):
                return "Invalid Price"
            if token_price <= 0:
                return "Invalid Price"

            # Get position limits from contract details
            max_position_tokens = 0.0
            if contract_data:
                try:
                    max_vol = float(contract_data.get("maxVol", "0"))
                    contract_size = float(contract_data.get("contractSize", "1"))
                    max_position_tokens = max_vol * contract_size
                except (ValueError, TypeError):
                    pass

            # Calculate maximum token limit based on available data
            max_tokens = max_position_tokens

            # Format result based on available data
            if max_tokens == 0:
                # No limits available
                return "API Required"
            else:
                # We have some limit data available
                # Calculate USD value
                max_usd_value = max_tokens * token_price

                # Format USD value with proper precision
                if max_usd_value >= 1000:
                    formatted_usd = f"{max_usd_value:,.0f}"
                elif max_usd_value >= 1:
                    formatted_usd = f"{max_usd_value:,.2f}"
                else:
                    formatted_usd = f"{max_usd_value:.4f}"

                return f"${formatted_usd}"

        except Exception as e:
            return "Error"
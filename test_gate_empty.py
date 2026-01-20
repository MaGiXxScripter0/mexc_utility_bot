#!/usr/bin/env python3
"""Test script for Gate.io with empty/invalid index constituents."""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from core.config import Config
from core.markdown_service import MarkdownService
from infrastructure.http_client import HttpClient
from infrastructure.gate.client import GateClient
from application.services.gate_info_service import GateInfoService

class MockGateClient(GateClient):
    """Gate client that returns mock data."""

    async def fetch_index_constituents(self, index_symbol: str):
        """Return mock data with empty constituents."""
        if index_symbol == "EMPTY":
            # Return data with empty constituents list
            mock_data = {
                'value': '0.013491',
                'time': '2026-01-20T22:52:19Z',
                'constituents': [],  # Empty list
                'index': index_symbol,
                'all_constituents': None
            }
            return True, "", mock_data
        elif index_symbol == "ZERO_WEIGHTS":
            # Return data with zero weights
            mock_data = {
                'value': '0.013491',
                'time': '2026-01-20T22:52:19Z',
                'constituents': [
                    {'symbol': '1_USDT', 'exchange': 'BinanceAlpha', 'weight': '0', 'price': '0.01356575'},
                    {'symbol': '1_WBNB', 'exchange': 'PancakeV3', 'weight': '0', 'price': '0.0134589'}
                ],
                'index': index_symbol,
                'all_constituents': None
            }
            return True, "", mock_data
        elif index_symbol == "INVALID_WEIGHTS":
            # Return data with invalid weights
            mock_data = {
                'value': '0.013491',
                'time': '2026-01-20T22:52:19Z',
                'constituents': [
                    {'symbol': '1_USDT', 'exchange': 'BinanceAlpha', 'weight': 'invalid', 'price': '0.01356575'},
                    {'symbol': '1_WBNB', 'exchange': 'PancakeV3', 'weight': '0.5', 'price': '0.0134589'}
                ],
                'index': index_symbol,
                'all_constituents': None
            }
            return True, "", mock_data
        else:
            # Call parent for real data
            return await super().fetch_index_constituents(index_symbol)

async def test_gate_edge_cases():
    """Test Gate.io service with edge cases."""
    config = Config.load()
    http_client = HttpClient(verify_ssl=False)
    await http_client.start()

    try:
        gate_client = MockGateClient(config, http_client)
        markdown_service = MarkdownService()
        gate_service = GateInfoService(gate_client, markdown_service)

        test_cases = ["EMPTY", "ZERO_WEIGHTS", "INVALID_WEIGHTS"]

        for test_case in test_cases:
            print(f"\nTesting case: {test_case}")
            text, errors = await gate_service.get_gate_info(test_case)

            # Write to file
            with open(f'gate_output_{test_case.lower()}.txt', 'w', encoding='utf-8') as f:
                f.write(text)

            print(f"Message written to gate_output_{test_case.lower()}.txt (length: {len(text)})")
            print(f"Errors: {errors}")

            # Check the index line
            lines = text.split('\n')
            index_line = None
            for line in lines:
                if '_Index:_' in line:
                    index_line = line
                    break

            if index_line:
                print(f"Index line: {index_line}")
            else:
                print("No index line found")

    finally:
        await http_client.close()

if __name__ == "__main__":
    asyncio.run(test_gate_edge_cases())

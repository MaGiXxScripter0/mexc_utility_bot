#!/usr/bin/env python3
"""Test script for Gate.io functionality."""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from core.config import Config
from infrastructure.http_client import HttpClient
from infrastructure.gate.client import GateClient

async def test_gate_index():
    """Test Gate.io index constituents API."""
    config = Config.load()
    http_client = HttpClient(verify_ssl=False)
    await http_client.start()

    try:
        gate_client = GateClient(config, http_client)

        # Test multiple symbols
        test_symbols = ["1_USDT", "BTC_USDT", "ETH_USDT", "INVALID_SYMBOL"]

        for symbol in test_symbols:
            print(f"\nTesting Gate.io index constituents API for {symbol}...")
            ok, err, data = await gate_client.fetch_index_constituents(symbol)

            print(f"Success: {ok}")
            print(f"Error: {err}")

            if data and isinstance(data, dict):
                constituents = data.get('constituents', [])
                print(f"Constituents count: {len(constituents)}")
                if constituents:
                    print(f"First constituent: {constituents[0]}")
            else:
                print("No data returned")

        print(f"Success: {ok}")
        print(f"Error: {err}")
        print(f"Data: {data}")
        print(f"Data type: {type(data)}")

        if data and isinstance(data, dict):
            print(f"Constituents: {data.get('constituents', [])}")
            print(f"Value: {data.get('value')}")
            print(f"Time: {data.get('time')}")

    finally:
        await http_client.close()

if __name__ == "__main__":
    asyncio.run(test_gate_index())

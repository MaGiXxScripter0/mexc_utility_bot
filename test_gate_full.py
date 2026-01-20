#!/usr/bin/env python3
"""Test script for full Gate.io functionality."""

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

async def test_gate_full():
    """Test full Gate.io service."""
    config = Config.load()
    http_client = HttpClient(verify_ssl=False)
    await http_client.start()

    try:
        gate_client = GateClient(config, http_client)
        markdown_service = MarkdownService()
        gate_service = GateInfoService(gate_client, markdown_service)

        print("Testing full Gate.io service for 1_USDT...")
        text, errors = await gate_service.get_gate_info("1_USDT")

        print("\nTesting with BTC_USDT...")
        text2, errors2 = await gate_service.get_gate_info("BTC_USDT")

        # Write second test to file
        with open('gate_output_btc.txt', 'w', encoding='utf-8') as f:
            f.write(text2)

        print(f"BTC message written to gate_output_btc.txt (length: {len(text2)})")
        print(f"BTC Errors: {errors2}")

        print("Generated message:")
        print("=" * 50)

        # Write to file to avoid encoding issues
        with open('gate_output.txt', 'w', encoding='utf-8') as f:
            f.write(text)

        print(f"Message written to gate_output.txt (length: {len(text)})")
        print("=" * 50)
        print(f"Errors: {errors}")

        # Check if "поломалась" appears anywhere
        if "поломалась" in text:
            print("❌ Found 'поломалась' in the message!")
        else:
            print("✅ No 'поломалась' found in the message")

        # Also check the index line specifically
        lines = text.split('\n')
        index_line = None
        for line in lines:
            if line.startswith('*Index:*'):
                index_line = line
                break

        if index_line:
            print(f"Index line: {index_line}")
        else:
            print("No index line found")

    finally:
        await http_client.close()

if __name__ == "__main__":
    asyncio.run(test_gate_full())

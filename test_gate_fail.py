#!/usr/bin/env python3
"""Test script for Gate.io when index API fails."""

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

class FailingGateClient(GateClient):
    """Gate client that always fails index API."""

    async def fetch_index_constituents(self, index_symbol: str):
        """Always return failure for index constituents."""
        return False, "API not accessible", None

async def test_gate_with_failing_index():
    """Test Gate.io service when index API fails."""
    config = Config.load()
    http_client = HttpClient(verify_ssl=False)
    await http_client.start()

    try:
        # Use failing client
        gate_client = FailingGateClient(config, http_client)
        markdown_service = MarkdownService()
        gate_service = GateInfoService(gate_client, markdown_service)

        print("Testing Gate.io service with failing index API for 1_USDT...")
        text, errors = await gate_service.get_gate_info("1_USDT")

        # Write to file
        with open('gate_output_fail.txt', 'w', encoding='utf-8') as f:
            f.write(text)

        print(f"Message written to gate_output_fail.txt (length: {len(text)})")
        print(f"Errors: {errors}")

        # Check the index line
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
    asyncio.run(test_gate_with_failing_index())

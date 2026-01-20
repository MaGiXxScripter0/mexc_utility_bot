"""MEXC Telegram Bot - Clean Architecture Entry Point."""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from src.bot.main import main

if __name__ == "__main__":
    asyncio.run(main())
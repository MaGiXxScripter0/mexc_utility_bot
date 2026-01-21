#!/usr/bin/env python3
"""
Test script to send alert message to Telegram topic.
Usage: python test_alert.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from core.config import Config
from core.logging_config import setup_logging
from core.markdown_service import MarkdownService

logger = setup_logging()


async def send_test_alert():
    """Send a test alert message to the specified topic."""

    # Load configuration
    try:
        config = Config.load()
        markdown_service = MarkdownService()
        logger.info("Configuration loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return

    # Create bot
    try:
        bot = Bot(
            token=config.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN_V2)
        )
        logger.info("Bot created successfully")
    except Exception as e:
        logger.error(f"Failed to create bot: {e}")
        return

    # Try to send to the specific topic from the URL: https://t.me/c/2658323170/20365
    # Convert URL format to API format:
    # c/2658323170 -> -1002658323170 (supergroup ID)
    # 20365 -> message_thread_id
    target_chat_id = "-1002658323170"  # From c/2658323170
    target_thread_id = 20365  # From /20365

    logger.info(f"Using chat: {target_chat_id}, topic: {target_thread_id}")
    # Test message data
    symbol = "BTC/USDT"
    price = 50000.0
    spread = "+1.01%"

    # Format message using markdown service
    test_message = f"""123123"""

    try:
        logger.info(f"Sending test message to chat {target_chat_id}, topic {target_thread_id}")
        print(f'${target_chat_id}_${target_thread_id}')
        await bot.send_message(
            chat_id=target_chat_id,
            text=test_message,
            message_thread_id=target_thread_id,
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True
        )

        logger.info("✅ Test message sent successfully!")

    except Exception as e:
        logger.error(f"❌ Failed to send test message: {e}")
        logger.debug(f"Error details: {e}", exc_info=True)

    finally:
        # Close bot session
        await bot.session.close()


async def main():
    """Main function."""
    logger.info("Starting test alert script...")

    try:
        await send_test_alert()
    except KeyboardInterrupt:
        logger.info("Script interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1

    logger.info("Test alert script completed")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
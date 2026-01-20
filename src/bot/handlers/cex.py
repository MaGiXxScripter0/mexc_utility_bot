"""CEX aggregator command handler."""

import time
import logging
from typing import Protocol

from aiogram import types
from aiogram.enums import ChatType

from bot.handlers.mexc import handle_mexc_command

logger = logging.getLogger(__name__)


class CexAggregatorServiceProtocol(Protocol):
    """Protocol for CEX aggregator service."""

    async def get_aggregated_info(self, symbol: str) -> tuple[str, list[str]]:
        """Get aggregated CEX information."""
        ...


async def handle_cex_command(message: types.Message, cex_service: CexAggregatorServiceProtocol) -> None:
    """
    Handle /cex command - aggregate data from multiple exchanges.

    Args:
        message: Telegram message
        cex_service: CEX aggregator service
    """
    start_time = time.monotonic()

    try:
        # Parse symbol from command
        text = message.text or ""
        parts = text.split(maxsplit=1)

        if len(parts) < 2 or not parts[1].strip():
            await message.reply(
                "❌ **Ошибка:** Укажите символ токена\n\n"
                "Пример: `/cex BTC` или `/cex ETH`",
                parse_mode="MarkdownV2"
            )
            return

        symbol = parts[1].strip().upper()

        # Show typing indicator
        await message.bot.send_chat_action(message.chat.id, "typing")

        # Get aggregated info with timing
        api_start_time = time.monotonic()
        text, errors = await cex_service.get_aggregated_info(symbol)
        api_time = time.monotonic() - api_start_time

        # Send response
        try:
            await message.reply(text, parse_mode="MarkdownV2", disable_web_page_preview=True)
        except Exception as e:
            # Fallback without markdown
            await message.reply(text, disable_web_page_preview=True)

        # Log performance
        total_time = time.monotonic() - start_time
        if errors:
            logger.warning(f"CEX command completed with {len(errors)} errors - API: {api_time:.2f}s, Total: {total_time:.2f}s")
        else:
            logger.info(f"CEX command completed successfully - API: {api_time:.2f}s, Total: {total_time:.2f}s")

    except Exception as e:
        error_time = time.monotonic() - start_time
        print(f"❌ CEX command failed after {error_time:.2f}s: {str(e)}")

        await message.reply(
            f"❌ **Ошибка при получении данных**\n\n"
            f"Попробуйте позже или используйте команды `/mexc` или `/gate` по отдельности",
            parse_mode="MarkdownV2"
        )


async def handle_cex_group_command(message: types.Message, cex_service: CexAggregatorServiceProtocol) -> None:
    """
    Handle /cex command in groups - reply to the command message.
    """
    # Check if this is a reply to our message or a direct command
    if message.reply_to_message and message.reply_to_message.from_user.id == message.bot.id:
        # This is a reply to our message, ignore
        return

    await handle_cex_command(message, cex_service)
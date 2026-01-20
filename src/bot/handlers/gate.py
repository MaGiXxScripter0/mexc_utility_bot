"""Telegram bot handlers for Gate.io commands."""

import time
from typing import Protocol

from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from core.logging_config import setup_logging

logger = setup_logging()


class GateServiceProtocol(Protocol):
    """Protocol for Gate.io information service."""

    async def get_gate_info(self, symbol: str) -> tuple[str, list[str]]:
        """Get formatted Gate.io information."""
        ...


async def handle_gate_command(message: Message, gate_service: GateServiceProtocol) -> None:
    """
    Handle /gate command.

    Args:
        message: Telegram message
        gate_service: Gate.io information service
    """
    start_time = time.monotonic()

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply("Пример: `/gate BTC_USDT`", parse_mode=ParseMode.MARKDOWN_V2)
        return

    symbol = parts[1].strip()
    symbol_parts = symbol.split("_")
    symbol_name = symbol_parts[0] if symbol_parts else ""
    symbol_quote = symbol_parts[1] if len(symbol_parts) > 1 and symbol_parts[1] else "USDT"
    symbol = f"{symbol_name}_{symbol_quote}"

    logger.info(f"Processing /gate command for symbol: {symbol}")

    try:
        # Get formatted message from service
        api_start_time = time.monotonic()
        text, errors = await gate_service.get_gate_info(symbol)
        api_time = time.monotonic() - api_start_time

        # Log the message content
        logger.info(f"Generated message (length {len(text)}, API time: {api_time:.2f}s):\n{text[:800]}...")

        # Send with MarkdownV2 (already converted by service)
        try:
            await message.answer(text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
            total_time = time.monotonic() - start_time
            logger.info(f"Gate command completed - API: {api_time:.2f}s, Total: {total_time:.2f}s")

        except TelegramBadRequest as e:
            logger.error(f"Markdown parse error: {e}")

            # Fallback: send without parse_mode
            try:
                await message.answer(text, disable_web_page_preview=True)
                total_time = time.monotonic() - start_time
                logger.info(f"Gate command completed (fallback) - API: {api_time:.2f}s, Total: {total_time:.2f}s")

            except Exception as e2:
                logger.error(f"Fallback also failed: {e2}")
                await message.reply("Не удалось отправить сообщение из-за ограничений Telegram.", disable_web_page_preview=True)

    except Exception as e:
        logger.exception("Unexpected error in handle_gate_command")
        await message.reply("Внутренняя ошибка бота.")

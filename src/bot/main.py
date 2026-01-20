"""Telegram bot main entry point with dependency injection."""

import asyncio
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command

from core.config import Config
from core.logging_config import setup_logging
from core.markdown_service import MarkdownService
from infrastructure.http_client import HttpClient
from infrastructure.mexc.client import MexcClient, MexcTimeSync
from infrastructure.gate.client import GateClient
from application.services.cex_info_service import MexcInfoService
from application.services.gate_info_service import GateInfoService
from application.services.cex_aggregator_service import CexAggregatorService

from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram import Bot
from bot.handlers.mexc import handle_mexc_command
from bot.handlers.gate import handle_gate_command
from bot.handlers.cex import handle_cex_command, handle_cex_group_command

logger = setup_logging()


class DependencyContainer:
    """Dependency injection container."""

    def __init__(self, config: Config):
        self.config = config
        self._http_client: HttpClient | None = None
        self._gate_http_client: HttpClient | None = None
        self._time_sync: MexcTimeSync | None = None
        self._mexc_client: MexcClient | None = None
        self._gate_client: GateClient | None = None
        self._cex_service: MexcInfoService | None = None
        self._gate_service: GateInfoService | None = None
        self._cex_aggregator_service: CexAggregatorService | None = None
        self._markdown_service: MarkdownService | None = None

    async def start(self) -> None:
        """Initialize all dependencies."""
        logger.info("Initializing dependency container...")

        # HTTP client (with SSL verification for MEXC)
        self._http_client = HttpClient(verify_ssl=True)
        await self._http_client.start()

        # Gate HTTP client (without SSL verification to handle certificate issues)
        self._gate_http_client = HttpClient(verify_ssl=False)
        await self._gate_http_client.start()

        # Time sync
        self._time_sync = MexcTimeSync()
        await self._time_sync.sync(self._http_client, self.config.mexc_server_time_url)

        # MEXC client
        self._mexc_client = MexcClient(self.config, self._http_client, self._time_sync)

        # Gate client
        self._gate_client = GateClient(self.config, self._gate_http_client)

        # Markdown service
        self._markdown_service = MarkdownService()

        # CEX service
        self._cex_service = MexcInfoService(self._mexc_client, self._markdown_service)

        # Gate service
        self._gate_service = GateInfoService(self._gate_client, self._markdown_service)

        # CEX aggregator service
        self._cex_aggregator_service = CexAggregatorService(
            self._mexc_client, self._gate_client, self._http_client, self._markdown_service
        )

        logger.info("Dependency container initialized successfully")

    async def close(self) -> None:
        """Clean up all dependencies."""
        logger.info("Closing dependency container...")

        if self._http_client:
            await self._http_client.close()

        if self._gate_http_client:
            await self._gate_http_client.close()

        logger.info("Dependency container closed")

    @property
    def cex_service(self) -> MexcInfoService:
        """Get CEX information service."""
        if self._cex_service is None:
            raise RuntimeError("Dependency container not initialized")
        return self._cex_service

    @property
    def gate_service(self) -> GateInfoService:
        """Get Gate.io information service."""
        if self._gate_service is None:
            raise RuntimeError("Dependency container not initialized")
        return self._gate_service

    @property
    def cex_aggregator_service(self) -> CexAggregatorService:
        """Get CEX aggregator service."""
        if self._cex_aggregator_service is None:
            raise RuntimeError("Dependency container not initialized")
        return self._cex_aggregator_service

    @property
    def markdown_service(self) -> MarkdownService:
        """Get markdown service."""
        if self._markdown_service is None:
            raise RuntimeError("Dependency container not initialized")
        return self._markdown_service


@asynccontextmanager
async def lifespan(container: DependencyContainer):
    """Async context manager for dependency lifecycle."""
    await container.start()
    try:
        yield container
    finally:
        await container.close()


async def create_dispatcher(container: DependencyContainer) -> Dispatcher:
    """Create and configure Telegram dispatcher."""
    dp = Dispatcher()

    # Register handlers
    @dp.message(Command("start"))
    async def start_handler(message):
        start_text = container.markdown_service.convert_to_markdown_v2("Команды:\n• `/cex BTC` (все биржи)\n• `/mexc 1_USDT` (MEXC)\n• `/gate BTC_USDT` (Gate.io)")
        await message.reply(start_text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)

    # Handle /mexc command in all chat types (private, group, supergroup)
    @dp.message(Command("mexc", ignore_case=True))
    async def mexc_handler(message):
        await handle_mexc_command(message, container.cex_service)

    # Additional handler for /mexc in group chats
    @dp.message(lambda message: message.text and message.text.lower().startswith('/mexc') and message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP])
    async def mexc_group_handler(message):
        # Only process if bot is mentioned or it's a direct command to the bot
        text_lower = message.text.lower()
        if '@' not in text_lower or '@' in text_lower:  # Allow all /mexc commands in groups for now
            await handle_mexc_command(message, container.cex_service)

    # Handle /gate command in all chat types (private, group, supergroup)
    @dp.message(Command("gate", ignore_case=True))
    async def gate_handler(message):
        await handle_gate_command(message, container.gate_service)

    # Additional handler for /gate in group chats
    @dp.message(lambda message: message.text and message.text.lower().startswith('/gate') and message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP])
    async def gate_group_handler(message):
        # Only process if bot is mentioned or it's a direct command to the bot
        text_lower = message.text.lower()
        if '@' not in text_lower or '@' in text_lower:  # Allow all /gate commands in groups for now
            await handle_gate_command(message, container.gate_service)

    # Handle /cex command in all chat types (private, group, supergroup)
    @dp.message(Command("cex", ignore_case=True))
    async def cex_handler(message):
        await handle_cex_command(message, container.cex_aggregator_service)

    # Additional handler for /cex in group chats
    @dp.message(lambda message: message.text and message.text.lower().startswith('/cex') and message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP])
    async def cex_group_handler(message):
        # Only process if bot is mentioned or it's a direct command to the bot
        text_lower = message.text.lower()
        if '@' not in text_lower or '@' in text_lower:  # Allow all /cex commands in groups for now
            await handle_cex_group_command(message, container.cex_aggregator_service)

    return dp


async def time_sync_loop(container: DependencyContainer) -> None:
    """Background task for periodic time synchronization."""
    while True:
        await asyncio.sleep(600)  # 10 minutes
        if container._time_sync and container._http_client:
            await container._time_sync.sync(
                container._http_client,
                container.config.mexc_server_time_url
            )


async def main() -> None:
    """Main application entry point."""
    try:
        # Load configuration
        config = Config.load()
        logger.info("Configuration loaded successfully")

        # Create dependency container
        container = DependencyContainer(config)

        # Initialize dependencies
        async with lifespan(container):
            # Create bot and dispatcher
            bot = Bot(
                token=config.bot_token,
                default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN_V2)
            )

            dp = await create_dispatcher(container)

            # Start time sync background task
            sync_task = asyncio.create_task(time_sync_loop(container))

            logger.info("Bot starting...")

            try:
                # Start polling
                await dp.start_polling(bot)
            finally:
                # Clean up
                sync_task.cancel()
                await bot.session.close()

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Critical error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())

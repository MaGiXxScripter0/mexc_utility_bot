#!/usr/bin/env python3
"""Cron job script for monitoring MEXC fair price alerts."""

import asyncio
import signal
import sys
from contextlib import asynccontextmanager

from src.core.config import Config
from src.core.logging_config import setup_logging
from src.core.markdown_service import MarkdownService
from src.infrastructure.http_client import HttpClient
from src.infrastructure.mexc.client import MexcClient, MexcTimeSync
from src.application.services.fair_price_alert_service import FairPriceAlertService

logger = setup_logging()


@asynccontextmanager
async def lifespan(service: FairPriceAlertService):
    """Async context manager for service lifecycle."""
    await service.start()
    try:
        yield service
    finally:
        await service.stop()


async def main() -> None:
    """Main entry point for fair price monitoring."""
    try:
        # Load configuration
        config = Config.load()
        logger.info("Configuration loaded successfully")

        # Create services
        markdown_service = MarkdownService()

        # Create HTTP client and time sync for MEXC client
        proxy_config = config.parse_proxy()
        http_client = HttpClient(verify_ssl=True, proxy_config=proxy_config)
        await http_client.start()

        time_sync = MexcTimeSync()
        await time_sync.sync(http_client, config.mexc_server_time_url)

        mexc_client = MexcClient(config, http_client, time_sync)
        alert_service = FairPriceAlertService(config, markdown_service, mexc_client)

        # Setup signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            asyncio.create_task(alert_service.stop())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Start monitoring
        async with lifespan(alert_service):
            logger.info("Fair price monitoring started. Press Ctrl+C to stop.")

            # Run monitoring loop
            await alert_service.run_monitoring_loop()

    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
    except Exception as e:
        logger.critical(f"Critical error in fair price monitor: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
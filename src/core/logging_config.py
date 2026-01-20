import logging
import sys
from typing import Optional


def setup_logging(
    level: int = logging.INFO,
    format_string: Optional[str] = None,
    logger_name: str = "mexc_bot"
) -> logging.Logger:
    """
    Setup centralized logging configuration.

    Args:
        level: Logging level (default: INFO)
        format_string: Custom format string (optional)
        logger_name: Name for the logger

    Returns:
        Configured logger instance
    """
    if format_string is None:
        format_string = '%(asctime)s | %(levelname)-7s | %(name)s | %(message)s'

    # Configure root logger
    logging.basicConfig(
        level=level,
        format=format_string,
        datefmt='%Y-%m-%d %H:%M:%S',
        stream=sys.stdout,
        force=True  # Override any existing configuration
    )

    # Create and return named logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)

    return logger

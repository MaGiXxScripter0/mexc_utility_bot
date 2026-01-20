"""Markdown processing service using telegramify_markdown."""

from typing import Optional

import telegramify_markdown
from telegramify_markdown import customize

from core.logging_config import setup_logging

logger = setup_logging()


class MarkdownService:
    """Service for converting and processing Markdown content."""

    def __init__(self):
        """Initialize the markdown service with custom settings."""
        # Configure telegramify_markdown with proper settings
        # customize.markdown_symbol.head_level_1 = "📌"
        # customize.markdown_symbol.link = "🔗"
        # customize.strict_markdown = True
        # customize.cite_expandable = True

        logger.info("Markdown service initialized with telegramify_markdown customizations")

    def convert_to_markdown_v2(self, markdown_text: str, max_line_length: Optional[int] = None) -> str:
        """
        Convert markdown text to Telegram MarkdownV2 format.

        Args:
            markdown_text: Input markdown text
            max_line_length: Maximum line length for links/images (optional)

        Returns:
            Converted text in Telegram MarkdownV2 format
        """
        try:
            converted = telegramify_markdown.markdownify(
                markdown_text,
                max_line_length=max_line_length,
                normalize_whitespace=False
            )
            logger.debug(f"Converted markdown text (length: {len(converted)})")
            return converted
        except Exception as e:
            logger.error(f"Error converting markdown: {e}")
            return markdown_text  # Return original text on error

    def convert_to_regular_markdown(self, markdown_text: str) -> str:
        """
        Return markdown text as-is (for regular Markdown mode).

        Args:
            markdown_text: Input markdown text

        Returns:
            Original markdown text (no conversion)
        """
        return markdown_text


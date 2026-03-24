"""
Currents Service
Wraps ClaudeClient + NewsFetcher for theological news analysis

Follows study_generator.py singleton pattern.
"""

import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lectionary_engines.claude_client import ClaudeClient
from lectionary_engines.news_fetcher import NewsFetcher
from lectionary_engines.protocols import currents_protocol


class CurrentsService:
    """
    Service for generating theological news analysis

    Wraps ClaudeClient and NewsFetcher for use in web application.
    """

    def __init__(self, api_key: str):
        """
        Initialize the Currents service

        Args:
            api_key: Anthropic API key
        """
        self.claude = ClaudeClient(api_key)
        self.news_fetcher = NewsFetcher()

    def fetch_headlines(
        self, source: str = "npr", limit: int = 10
    ) -> List[Dict[str, str]]:
        """
        Fetch headlines from RSS feeds

        Args:
            source: RSS source key
            limit: Max headlines to return

        Returns:
            List of headline dicts
        """
        return self.news_fetcher.fetch_headlines(source=source, limit=limit)

    def fetch_story_context(self, url: str) -> str:
        """
        Extract article text from a URL

        Args:
            url: Article URL

        Returns:
            Article text
        """
        return self.news_fetcher.fetch_story_context(url)

    def analyze_story(
        self,
        news_context: str,
        date: Optional[str] = None,
        source_info: str = "",
    ) -> Dict[str, Any]:
        """
        Generate a Currents theological analysis

        Args:
            news_context: The news story/event text to analyze
            date: Date string (defaults to today)
            source_info: Source attribution

        Returns:
            dict with keys: content, word_count, date, headline_summary
        """
        if not date:
            date = datetime.now().strftime("%B %d, %Y")

        # Build user message using protocol
        user_message = currents_protocol.INPUT_WRAPPER(
            news_context=news_context,
            date=date,
            source_info=source_info,
        )

        # Call Claude with Currents protocol
        content = self.claude.generate_study(
            text=user_message,
            reference=f"Currents Analysis - {date}",
            system_prompt=currents_protocol.SYSTEM_PROMPT,
            max_tokens=currents_protocol.OUTPUT_CONSTRAINTS["max_tokens"],
        )

        # Extract a headline summary from the first line or section
        headline_summary = news_context[:200].split("\n")[0].strip()
        if len(headline_summary) > 150:
            headline_summary = headline_summary[:147] + "..."

        return {
            "content": content,
            "word_count": len(content.split()),
            "date": date,
            "headline_summary": headline_summary,
        }

"""
Currents Service
Wraps ClaudeClient + NewsFetcher for theological news analysis

Follows study_generator.py singleton pattern.
"""

import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from datetime import datetime

from lectionary_engines.claude_client import ClaudeClient
from lectionary_engines.news_fetcher import NewsFetcher
from lectionary_engines.protocols import currents_protocol
from lectionary_engines.theme_extractor import MODEL as THEME_EXTRACTOR_MODEL
from lectionary_engines.json_extraction import extract_first_json

# General-news sources used for auto headline selection - skips the niche
# ones (Popular Mechanics, Rolling Stone, NatGeo) since a "current event"
# integrated into a study should read as a real news event, not a hobbyist
# feed item.
AUTO_SELECT_SOURCES = ["ap", "guardian", "npr"]

HEADLINE_SELECTION_PROMPT = """You are picking the single most theologically resonant news headline for a biblical study, out of a short list of today's actual headlines.

Given a list of themes drawn from the passage, and a numbered list of headlines, return ONLY JSON: {"index": N} where N is the 0-based index of the best match, or {"index": null} if none of the headlines have a real, non-forced connection to these themes.

Be honest - a forced connection is worse than no connection. Only pick a headline if it would let someone write a genuinely specific, non-generic reflection connecting it to these themes."""


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

    def auto_select_headline(
        self,
        themes: List[str],
        sources: Optional[List[str]] = None,
        limit_per_source: int = 6,
    ) -> Optional[Dict[str, str]]:
        """
        Fetch today's headlines and have Claude pick the single most
        thematically relevant one, instead of requiring a user to browse
        and paste one manually.

        Args:
            themes: Theme keywords from theme_extractor.extract_themes()
            sources: RSS source keys to pull from (defaults to AUTO_SELECT_SOURCES)
            limit_per_source: Max headlines to fetch per source

        Returns:
            Dict with news_context, news_date, headline, source - or None
            if fetching failed, nothing was found, or nothing was a real
            match. Callers should treat None as "skip auto news this time,"
            not an error - generation should never be blocked by this.
        """
        if not themes:
            return None

        headlines: List[Dict[str, str]] = []
        for source in (sources or AUTO_SELECT_SOURCES):
            try:
                headlines.extend(self.fetch_headlines(source=source, limit=limit_per_source))
            except Exception:
                continue  # one source failing shouldn't sink the others

        if not headlines:
            return None

        listing = "\n".join(
            f"{i}. [{h['source']}] {h['title']} — {h['summary'][:150]}"
            for i, h in enumerate(headlines)
        )
        user_message = f"Themes: {', '.join(themes)}\n\nHeadlines:\n{listing}"

        try:
            raw = self.claude.complete(
                system_prompt=HEADLINE_SELECTION_PROMPT,
                user_message=user_message,
                model=THEME_EXTRACTOR_MODEL,
                max_tokens=150,
                temperature=0.3,
            )
            # Haiku sometimes adds an explanation after the JSON despite being
            # told not to (observed live) - extract_first_json parses just
            # the JSON value and ignores anything around it, rather than
            # requiring the whole response to be clean JSON.
            selection = extract_first_json(raw)
            index = selection.get("index") if isinstance(selection, dict) else None
        except Exception:
            return None

        if index is None or not isinstance(index, int) or not (0 <= index < len(headlines)):
            return None

        chosen = headlines[index]

        try:
            story_context = self.fetch_story_context(chosen["link"]) if chosen.get("link") else chosen["summary"]
        except Exception:
            story_context = chosen["summary"]

        if not story_context or not story_context.strip():
            story_context = chosen["summary"]

        return {
            "news_context": story_context,
            "news_date": chosen.get("date") or datetime.now().strftime("%B %d, %Y"),
            "headline": chosen["title"],
            "source": chosen["source"],
        }

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

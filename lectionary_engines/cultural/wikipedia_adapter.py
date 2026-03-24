"""
Wikipedia Adapter for Cultural Sources

Queries Wikipedia for year-specific cultural information.
Uses pages like "1985 in music", "1985 in film", "1985 in American television".
"""

import aiohttp
import asyncio
import ssl
import certifi
from typing import List, Optional, Dict, Any
from .base_adapter import BaseAdapter, CulturalArtifact


def get_ssl_context():
    """Get SSL context that works on macOS"""
    try:
        return ssl.create_default_context(cafile=certifi.where())
    except:
        # Fallback: disable verification (dev only)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx


class WikipediaAdapter(BaseAdapter):
    """
    Adapter for Wikipedia cultural year pages.

    Fetches content from Wikipedia's year-specific pages for music,
    film, television, and general events.
    """

    BASE_URL = "https://en.wikipedia.org/api/rest_v1/page/summary"
    SEARCH_URL = "https://en.wikipedia.org/w/api.php"

    # Categories of year pages to query
    YEAR_PAGE_PATTERNS = [
        "{year} in music",
        "{year} in film",
        "{year} in American television",
        "{year} in the United States",
        "{year}",  # General year page
    ]

    @property
    def name(self) -> str:
        return "Wikipedia"

    @property
    def category(self) -> str:
        return "news"  # Wikipedia covers multiple categories

    async def _fetch_page_summary(self, title: str) -> Optional[Dict[str, Any]]:
        """Fetch a Wikipedia page summary via REST API"""
        url = f"{self.BASE_URL}/{title.replace(' ', '_')}"
        headers = {
            "User-Agent": "LectionaryEngines/1.0 (Biblical Study Tool; contact@example.com)"
        }
        try:
            connector = aiohttp.TCPConnector(ssl=get_ssl_context())
            async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
                    return None
        except Exception as e:
            print(f"Wikipedia fetch error for {title}: {e}")
            return None

    async def _search_wikipedia(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search Wikipedia for articles matching a query"""
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "format": "json",
        }
        headers = {
            "User-Agent": "LectionaryEngines/1.0 (Biblical Study Tool; contact@example.com)"
        }
        try:
            connector = aiohttp.TCPConnector(ssl=get_ssl_context())
            async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
                async with session.get(self.SEARCH_URL, params=params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("query", {}).get("search", [])
                    return []
        except Exception as e:
            print(f"Wikipedia search error: {e}")
            return []

    async def search(
        self,
        themes: List[str],
        limit: int = 5,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None
    ) -> List[CulturalArtifact]:
        """
        Search Wikipedia for articles matching themes within era.

        For Wikipedia, we search for articles that mention the themes
        and try to identify cultural artifacts within them.
        """
        start = year_start or self.era_start
        end = year_end or self.era_end

        artifacts = []

        # Build search query with era context
        for theme in themes[:3]:  # Limit themes to avoid too many requests
            query = f"{theme} {start}s {end}s"
            results = await self._search_wikipedia(query, limit=limit)

            for result in results:
                # Try to extract year from title or snippet
                title = result.get("title", "")
                snippet = result.get("snippet", "")

                # Create artifact from search result
                artifact = CulturalArtifact(
                    title=title,
                    creator="Wikipedia",
                    year=self._extract_year(title, snippet, start, end) or start,
                    category="news",
                    source_name=self.name,
                    quote_or_description=self._clean_snippet(snippet),
                    context=f"From Wikipedia article: {title}",
                    themes=[theme],
                    url=f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    confidence=0.7,
                )
                artifacts.append(artifact)

                if len(artifacts) >= limit:
                    break

            if len(artifacts) >= limit:
                break

        return artifacts[:limit]

    async def get_by_year(
        self,
        year: int,
        limit: int = 10
    ) -> List[CulturalArtifact]:
        """
        Get notable events/artifacts from a specific year.

        Fetches Wikipedia's year summary pages for comprehensive coverage.
        """
        if not self.is_in_era(year):
            return []

        artifacts = []

        # Fetch year-specific pages
        for pattern in self.YEAR_PAGE_PATTERNS:
            title = pattern.format(year=year)
            summary = await self._fetch_page_summary(title)

            if summary and summary.get("extract"):
                category = self._category_from_pattern(pattern)
                artifact = CulturalArtifact(
                    title=f"{year} in {category.title() if category != 'general' else 'History'}",
                    creator="Wikipedia",
                    year=year,
                    category=category,
                    source_name=self.name,
                    quote_or_description=summary.get("extract", "")[:500],
                    context=f"Summary of {year} in {category}",
                    themes=self._extract_themes_from_text(summary.get("extract", "")),
                    url=summary.get("content_urls", {}).get("desktop", {}).get("page", ""),
                    confidence=0.9,
                )
                artifacts.append(artifact)

                if len(artifacts) >= limit:
                    break

        return artifacts[:limit]

    async def get_year_highlights(
        self,
        year: int,
        categories: List[str] = None
    ) -> Dict[str, str]:
        """
        Get structured highlights from a year across categories.

        Returns a dict with category -> summary text.
        Useful for providing cultural context to Claude.
        """
        if categories is None:
            categories = ["music", "film", "television", "general"]

        highlights = {}

        category_patterns = {
            "music": "{year} in music",
            "film": "{year} in film",
            "television": "{year} in American television",
            "general": "{year} in the United States",
        }

        for cat in categories:
            pattern = category_patterns.get(cat, "{year}")
            title = pattern.format(year=year)
            summary = await self._fetch_page_summary(title)

            if summary and summary.get("extract"):
                highlights[cat] = summary.get("extract", "")

        return highlights

    def _extract_year(
        self,
        title: str,
        snippet: str,
        default_start: int,
        default_end: int
    ) -> Optional[int]:
        """Try to extract a year from title or snippet"""
        import re
        # Look for 4-digit years in the target range
        years = re.findall(r'\b(19[7-9]\d)\b', title + " " + snippet)
        for year_str in years:
            year = int(year_str)
            if default_start <= year <= default_end:
                return year
        return None

    def _clean_snippet(self, snippet: str) -> str:
        """Clean up Wikipedia search snippet (remove HTML tags)"""
        import re
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', snippet)
        # Remove extra whitespace
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def _category_from_pattern(self, pattern: str) -> str:
        """Extract category from year page pattern"""
        if "music" in pattern:
            return "music"
        elif "film" in pattern:
            return "film"
        elif "television" in pattern:
            return "tv"
        else:
            return "news"

    def _extract_themes_from_text(self, text: str) -> List[str]:
        """Extract potential themes from text (basic implementation)"""
        # This is a simple keyword extraction - could be enhanced
        theme_keywords = [
            "politics", "economy", "war", "peace", "technology",
            "music", "film", "television", "sports", "culture",
            "protest", "movement", "crisis", "celebration"
        ]
        text_lower = text.lower()
        return [theme for theme in theme_keywords if theme in text_lower]

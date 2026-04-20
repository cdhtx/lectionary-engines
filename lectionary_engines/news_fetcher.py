"""
News Fetcher - Retrieve headlines and story context from RSS feeds

Supports multiple news sources via RSS. Follows text_fetcher.py patterns.
"""

import re
import requests
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from datetime import datetime


# RSS feed sources
RSS_SOURCES = {
    "ap": {
        "name": "Associated Press",
        "url": "https://feeds.apnews.com/rss/apf-topnews",
        "fallback_url": "https://feeds.apnews.com/rss/APTopNews",
    },
    "guardian": {
        "name": "The Guardian",
        "url": "https://www.theguardian.com/world/rss",
        "fallback_url": "https://www.theguardian.com/us-news/rss",
    },
    "npr": {
        "name": "NPR",
        "url": "https://feeds.npr.org/1001/rss.xml",
    },
    "bbc": {
        "name": "BBC",
        "url": "https://feeds.bbci.co.uk/news/rss.xml",
    },
    "nytimes": {
        "name": "New York Times",
        "url": "https://rss.nytimes.com/services/xml/rss/nf/HomePage.xml",
    },
    "popular_mechanics": {
        "name": "Popular Mechanics",
        "url": "https://www.popularmechanics.com/rss/all.xml/",
    },
    "rolling_stone": {
        "name": "Rolling Stone",
        "url": "https://www.rollingstone.com/feed/",
    },
    "natgeo": {
        "name": "National Geographic",
        "url": "https://feeds.nationalgeographic.com/ng/News/News_Main",
        "fallback_url": "https://www.nationalgeographic.com/pages/topic/rss",
    },
}


class NewsFetcher:
    """Fetches news headlines and story context from RSS feeds"""

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

    def fetch_headlines(
        self, source: str = "npr", limit: int = 10
    ) -> List[Dict[str, str]]:
        """
        Fetch headlines from an RSS feed

        Args:
            source: RSS source key ('ap', 'reuters', 'npr', 'bbc')
            limit: Maximum number of headlines to return

        Returns:
            List of dicts with title, summary, link, date
        """
        source_config = RSS_SOURCES.get(source)
        if not source_config:
            raise ValueError(
                f"Unknown source: {source}. Choose from: {', '.join(RSS_SOURCES.keys())}"
            )

        urls_to_try = [source_config["url"]]
        if "fallback_url" in source_config:
            urls_to_try.append(source_config["fallback_url"])

        last_error = None
        for url in urls_to_try:
            try:
                response = requests.get(url, headers=self.headers, timeout=15)
                response.raise_for_status()

                # Try xml parser first, fall back to html.parser
                try:
                    soup = BeautifulSoup(response.content, "xml")
                except Exception:
                    soup = BeautifulSoup(response.content, "html.parser")
                items = soup.find_all("item", limit=limit)

                if not items:
                    soup = BeautifulSoup(response.content, "html.parser")
                    items = soup.find_all("item", limit=limit)

                headlines = []
                for item in items:
                    title_tag = item.find("title")
                    desc_tag = item.find("description")
                    link_tag = item.find("link")
                    date_tag = item.find("pubDate")

                    title = title_tag.get_text().strip() if title_tag else ""
                    summary = ""
                    if desc_tag:
                        # Strip HTML from description
                        summary = BeautifulSoup(
                            desc_tag.get_text(), "html.parser"
                        ).get_text().strip()

                    link = ""
                    if link_tag:
                        link = link_tag.get_text().strip() if link_tag.string else (link_tag.next_sibling.strip() if link_tag.next_sibling else "")

                    date = date_tag.get_text().strip() if date_tag else ""

                    if title:
                        headlines.append(
                            {
                                "title": title,
                                "summary": summary[:300],
                                "link": link,
                                "date": date,
                                "source": source_config["name"],
                            }
                        )

                if headlines:
                    return headlines

            except Exception as e:
                last_error = e
                continue

        raise Exception(
            f"Failed to fetch headlines from {source_config['name']}: {last_error}"
        )

    def fetch_story_context(self, url: str) -> str:
        """
        Extract article text from a URL for use as analysis context

        Args:
            url: Article URL to fetch

        Returns:
            Extracted article text (truncated to ~2000 words)
        """
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Remove script, style, nav, footer, header elements
            for tag in soup.find_all(
                ["script", "style", "nav", "footer", "header", "aside", "form"]
            ):
                tag.decompose()

            # Try common article content selectors
            article = None
            for selector in [
                "article",
                '[role="main"]',
                ".article-body",
                ".story-body",
                ".article-content",
                ".post-content",
                "main",
            ]:
                article = soup.select_one(selector)
                if article:
                    break

            if not article:
                article = soup.find("body")

            if not article:
                return ""

            # Get text from paragraphs
            paragraphs = article.find_all("p")
            text = "\n\n".join(p.get_text().strip() for p in paragraphs if p.get_text().strip())

            # Clean up
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = re.sub(r" +", " ", text)

            # Truncate to ~2000 words
            words = text.split()
            if len(words) > 2000:
                text = " ".join(words[:2000]) + "..."

            return text.strip()

        except Exception as e:
            raise Exception(f"Failed to fetch story from {url}: {e}")

    def list_sources(self) -> List[Dict[str, str]]:
        """List available RSS sources"""
        return [
            {"key": key, "name": config["name"]}
            for key, config in RSS_SOURCES.items()
        ]

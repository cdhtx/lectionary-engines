# web/services/signal_generator.py
"""
Generates one cross-canon signal: a single Claude call with the web search
tool, validated and saved as a Signal row. Nothing is saved unless the
response is complete, parses, and cites at least one search source.
"""

import json
import logging
import os
from typing import List, Optional
from urllib.parse import urlparse

import anthropic
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from lectionary_engines.protocols.signals_protocol import (
    SYSTEM_PROMPT,
    SignalParseError,
    build_user_prompt,
    parse_signal,
)
from web.models import Signal

logger = logging.getLogger(__name__)

DEFAULT_SIGNALS_MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 16000  # thinking counts against this, so keep real headroom
MAX_ATTEMPTS = 2
RECENT_LIMIT = 30
SEARCH_MAX_USES = 8
MAX_SOURCES = 12
FALLBACK_SOURCES = 5

WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": SEARCH_MAX_USES}


def _collect_sources(response) -> List[dict]:
    """Unique {title, url} pairs from the response's web search results."""
    seen, sources = set(), []
    for block in response.content:
        if block.type != "web_search_tool_result":
            continue
        results = block.content
        if not isinstance(results, list):  # an error object, not a result list
            continue
        for r in results:
            url = getattr(r, "url", None)
            if url and url.lower().startswith(("http://", "https://")) and url not in seen:
                seen.add(url)
                sources.append({"title": getattr(r, "title", "") or url, "url": url})
    return sources[:MAX_SOURCES]


def _site(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _select_sources(found: List[dict], used: List[str]) -> List[dict]:
    """
    Keep the search results the model says it relied on (in its order). If it
    named none that match a real result, fall back to the first few distinct sites.
    """
    by_url = {s["url"]: s for s in found}
    chosen = [by_url[u] for u in dict.fromkeys(used) if u in by_url]
    if chosen:
        return chosen
    seen, fallback = set(), []
    for s in found:
        site = _site(s["url"])
        if site in seen:
            continue
        seen.add(site)
        fallback.append(s)
        if len(fallback) == FALLBACK_SOURCES:
            break
    return fallback


def generate_signal(db: Session, client, model: Optional[str] = None) -> Optional[Signal]:
    """
    Generate and save one signal. `client` is an anthropic.Anthropic instance.
    Returns the saved Signal, or None if nothing usable was produced (the
    reason is logged and the next scheduled check will try again).
    """
    model = model or os.getenv("SIGNALS_MODEL") or DEFAULT_SIGNALS_MODEL
    recent = db.query(Signal).order_by(Signal.created_at.desc()).limit(RECENT_LIMIT).all()
    user_prompt = build_user_prompt([{"title": s.title, "theme": s.theme} for s in recent])
    db.rollback()  # end the read transaction before the long Claude call

    input_tokens = output_tokens = searches = 0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=[WEB_SEARCH_TOOL],
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.APIError as e:
            logger.warning("Signal generation API error (attempt %s): %s", attempt, e)
            return None

        usage = response.usage
        input_tokens += usage.input_tokens or 0
        output_tokens += usage.output_tokens or 0
        tool_usage = getattr(usage, "server_tool_use", None)
        searches += getattr(tool_usage, "web_search_requests", 0) or 0

        if response.stop_reason != "end_turn":
            logger.warning("Signal generation attempt %s stopped with %s; discarding", attempt, response.stop_reason)
            continue

        sources = _collect_sources(response)
        if not sources:
            logger.warning("Signal generation attempt %s had no web search sources; discarding", attempt)
            continue

        text = "".join(b.text for b in response.content if b.type == "text")
        try:
            data = parse_signal(text)
        except SignalParseError as e:
            logger.warning("Signal generation attempt %s unusable: %s", attempt, e)
            continue

        signal = Signal(
            title=data["title"][:200],
            theme=data["theme"][:200],
            signal_detected=data["signal_detected"],
            connection=data["connection"],
            nature_of_connection=data["nature_of_connection"],
            intratextual=data["intratextual"],
            modern_illustration=data["modern_illustration"],
            modern_illustration_category=data["modern_illustration_category"],
            dig_deeper=json.dumps(data["dig_deeper"]),
            sources=json.dumps(_select_sources(sources, data["sources_used"])),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            search_count=searches,
        )
        try:
            db.add(signal)
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logger.warning("Signal generation could not save the signal: %s", e)
            return None
        return signal

    logger.warning("Signal generation produced nothing usable after %s attempts", MAX_ATTEMPTS)
    return None

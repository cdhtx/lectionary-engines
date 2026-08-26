"""
Tests for CurrentsService.auto_select_headline

Uses fake claude/news_fetcher stand-ins swapped onto a real CurrentsService
instance, so these run without hitting the real API or network.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from web.services.currents_service import CurrentsService


class FakeClaude:
    def __init__(self, response_text):
        self.response_text = response_text

    def complete(self, **kwargs):
        return self.response_text


class FakeNewsFetcher:
    def __init__(self, headlines_by_source=None, story_context=None, raise_on_fetch=False):
        self.headlines_by_source = headlines_by_source or {}
        self.story_context = story_context
        self.raise_on_fetch = raise_on_fetch

    def fetch_headlines(self, source, limit=10):
        if self.raise_on_fetch:
            raise Exception("network down")
        return self.headlines_by_source.get(source, [])

    def fetch_story_context(self, url):
        if self.story_context is None:
            raise Exception("fetch failed")
        return self.story_context


def make_service(claude_response, headlines_by_source, story_context="Full article text."):
    service = CurrentsService(api_key="fake-key")
    service.claude = FakeClaude(claude_response)
    service.news_fetcher = FakeNewsFetcher(headlines_by_source, story_context)
    return service


SAMPLE_HEADLINES = {
    "ap": [
        {"title": "Local team wins championship", "summary": "Sports summary", "link": "http://example.com/1", "date": "Mon", "source": "AP"},
        {"title": "City council debates housing plan", "summary": "A story about displacement and belonging", "link": "http://example.com/2", "date": "Mon", "source": "AP"},
    ],
}


def test_returns_none_with_no_themes():
    service = make_service('{"index": 0}', SAMPLE_HEADLINES)
    assert service.auto_select_headline([]) is None


def test_selects_matched_headline():
    service = make_service('{"index": 1}', SAMPLE_HEADLINES)
    result = service.auto_select_headline(["displacement", "belonging"])
    assert result is not None
    assert result["headline"] == "City council debates housing plan"
    assert result["news_context"] == "Full article text."
    assert result["source"] == "AP"


def test_returns_none_when_claude_finds_no_real_match():
    service = make_service('{"index": null}', SAMPLE_HEADLINES)
    result = service.auto_select_headline(["exile", "wilderness"])
    assert result is None


def test_returns_none_when_no_headlines_fetched():
    service = make_service('{"index": 0}', {})
    result = service.auto_select_headline(["some theme"])
    assert result is None


def test_out_of_range_index_returns_none():
    service = make_service('{"index": 99}', SAMPLE_HEADLINES)
    result = service.auto_select_headline(["some theme"])
    assert result is None


def test_malformed_claude_response_returns_none():
    service = make_service("not json", SAMPLE_HEADLINES)
    result = service.auto_select_headline(["some theme"])
    assert result is None


def test_selects_headline_when_claude_adds_trailing_explanation():
    # Regression test: Haiku sometimes ignores "return ONLY JSON" and adds
    # commentary after the JSON object. A naive fence-stripping regex fails
    # to parse this (the string no longer ends with a clean closing fence),
    # silently discarding a valid selection. See lectionary_engines/json_extraction.py.
    raw = (
        '```json\n{"index": 1}\n```\n\n'
        "This headline connects directly to the themes because it addresses "
        "systemic issues of displacement and belonging in a concrete way"
    )
    service = make_service(raw, SAMPLE_HEADLINES)
    result = service.auto_select_headline(["displacement", "belonging"])
    assert result is not None
    assert result["headline"] == "City council debates housing plan"


def test_one_source_failing_does_not_sink_others():
    service = CurrentsService(api_key="fake-key")
    service.claude = FakeClaude('{"index": 0}')

    class PartiallyBrokenFetcher:
        def fetch_headlines(self, source, limit=10):
            if source == "ap":
                raise Exception("ap is down")
            return SAMPLE_HEADLINES["ap"]

        def fetch_story_context(self, url):
            return "Article text."

    service.news_fetcher = PartiallyBrokenFetcher()
    result = service.auto_select_headline(["some theme"], sources=["ap", "guardian"])
    assert result is not None


def test_story_context_fetch_failure_falls_back_to_summary():
    service = CurrentsService(api_key="fake-key")
    service.claude = FakeClaude('{"index": 0}')
    service.news_fetcher = FakeNewsFetcher(SAMPLE_HEADLINES, story_context=None)
    result = service.auto_select_headline(["some theme"])
    assert result is not None
    assert result["news_context"] == "Sports summary"

"""
Tests for WikipediaAdapter.search_topics()

Monkeypatches _search_wikipedia() (the low-level network call) so these
run without hitting the real Wikipedia API.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lectionary_engines.cultural.wikipedia_adapter import WikipediaAdapter


def make_result(title, snippet="A description."):
    return {"title": title, "snippet": snippet}


def test_searches_all_categories_by_default():
    wiki = WikipediaAdapter({})

    async def fake_search(query, limit=10):
        return [make_result(f"Result for {query}")]

    wiki._search_wikipedia = fake_search
    results = asyncio.run(wiki.search_topics(["healing"], limit_per_category=3))

    assert set(results.keys()) == set(WikipediaAdapter.CROSS_DISCIPLINARY_QUERY_TEMPLATES.keys())


def test_restricts_to_requested_categories():
    wiki = WikipediaAdapter({})

    async def fake_search(query, limit=10):
        return [make_result(f"Result for {query}")]

    wiki._search_wikipedia = fake_search
    results = asyncio.run(
        wiki.search_topics(["healing"], categories=["etymology", "biography"], limit_per_category=3)
    )

    assert set(results.keys()) == {"etymology", "biography"}


def test_artifacts_tagged_with_real_category_not_hardcoded_news():
    wiki = WikipediaAdapter({})

    async def fake_search(query, limit=10):
        return [make_result("Some Article")]

    wiki._search_wikipedia = fake_search
    results = asyncio.run(wiki.search_topics(["healing"], categories=["etymology"], limit_per_category=3))

    assert results["etymology"][0].category == "etymology"


def test_query_uses_the_categorys_template():
    wiki = WikipediaAdapter({})
    seen_queries = []

    async def fake_search(query, limit=10):
        seen_queries.append(query)
        return []

    wiki._search_wikipedia = fake_search
    asyncio.run(wiki.search_topics(["blindness"], categories=["biography"], limit_per_category=3))

    assert seen_queries == ["blindness biography"]


def test_dedupes_titles_within_a_category():
    wiki = WikipediaAdapter({})

    async def fake_search(query, limit=10):
        return [make_result("Same Title"), make_result("Same Title")]

    wiki._search_wikipedia = fake_search
    results = asyncio.run(
        wiki.search_topics(["healing", "shame"], categories=["biography"], limit_per_category=5)
    )

    titles = [a.title for a in results["biography"]]
    assert titles.count("Same Title") == 1


def test_respects_limit_per_category():
    wiki = WikipediaAdapter({})

    async def fake_search(query, limit=10):
        return [make_result(f"Article {i}") for i in range(10)]

    wiki._search_wikipedia = fake_search
    results = asyncio.run(wiki.search_topics(["healing"], categories=["art"], limit_per_category=2))

    assert len(results["art"]) == 2


def test_unknown_category_is_skipped():
    wiki = WikipediaAdapter({})

    async def fake_search(query, limit=10):
        return [make_result("Should not appear")]

    wiki._search_wikipedia = fake_search
    results = asyncio.run(wiki.search_topics(["healing"], categories=["not_a_real_category"]))

    assert results == {}


def test_empty_search_results_give_empty_category_list():
    wiki = WikipediaAdapter({})

    async def fake_search(query, limit=10):
        return []

    wiki._search_wikipedia = fake_search
    results = asyncio.run(wiki.search_topics(["healing"], categories=["travel"]))

    assert results["travel"] == []

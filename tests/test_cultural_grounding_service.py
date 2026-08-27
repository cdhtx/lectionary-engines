"""
Tests for web.services.cultural_grounding_service

No pytest-asyncio dependency in this project, so async test bodies are
driven with asyncio.run() from plain sync test functions.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lectionary_engines.cultural.base_adapter import CulturalArtifact
from lectionary_engines.cultural.wikipedia_adapter import WikipediaAdapter
import web.services.cultural_grounding_service as service_module
from web.services.cultural_grounding_service import build_grounding_for_passage


class FakeResonanceEngine:
    def __init__(self, classic_artifacts=None, contemporary_artifacts=None, raise_error=False, wiki_adapter=None):
        self.classic_artifacts = classic_artifacts or []
        self.contemporary_artifacts = contemporary_artifacts or []
        self.raise_error = raise_error
        self.calls = []
        # search_topics() looks up a WikipediaAdapter instance from
        # engine.adapters - give it one (real class, no config needed
        # since we monkeypatch its search_topics directly in each test).
        self.adapters = [wiki_adapter if wiki_adapter is not None else WikipediaAdapter({})]

    async def find_resonances(self, themes, limit_per_source, year_start, year_end):
        self.calls.append((year_start, year_end))
        if self.raise_error:
            raise Exception("adapter blew up")
        if year_end <= 1999:
            return self.classic_artifacts
        return self.contemporary_artifacts


def make_artifact(title):
    return CulturalArtifact(
        title=title, creator="Someone", year=1985, category="music",
        source_name="Wikipedia", quote_or_description="desc", context="",
    )


def no_cross_disciplinary_wiki():
    """A WikipediaAdapter whose search_topics() returns nothing, so tests
    that only care about the pop-culture path aren't affected by it."""
    wiki = WikipediaAdapter({})

    async def empty_search_topics(themes, categories=None, limit_per_category=3):
        return {}

    wiki.search_topics = empty_search_topics
    return wiki


def test_no_themes_returns_empty_string_without_calling_resonance(monkeypatch):
    fake_engine = FakeResonanceEngine(wiki_adapter=no_cross_disciplinary_wiki())
    monkeypatch.setattr(service_module, "get_resonance_engine", lambda tmdb_api_key=None: fake_engine)

    result = asyncio.run(build_grounding_for_passage(themes=[]))
    assert result == ""
    assert fake_engine.calls == []  # short-circuited before touching resonance at all


def test_themes_found_queries_both_eras(monkeypatch):
    fake_engine = FakeResonanceEngine(
        classic_artifacts=[make_artifact("Purple Rain")],
        contemporary_artifacts=[make_artifact("Folklore")],
        wiki_adapter=no_cross_disciplinary_wiki(),
    )
    monkeypatch.setattr(service_module, "get_resonance_engine", lambda tmdb_api_key=None: fake_engine)

    result = asyncio.run(build_grounding_for_passage(themes=["hope", "loss"]))
    assert "Purple Rain" in result
    assert "Folklore" in result
    assert len(fake_engine.calls) == 2
    classic_call, contemporary_call = fake_engine.calls
    assert classic_call == (1977, 1999)
    assert contemporary_call[1] - contemporary_call[0] == 15


def test_both_eras_and_cross_disciplinary_empty_returns_empty_string(monkeypatch):
    fake_engine = FakeResonanceEngine(wiki_adapter=no_cross_disciplinary_wiki())
    monkeypatch.setattr(service_module, "get_resonance_engine", lambda tmdb_api_key=None: fake_engine)

    result = asyncio.run(build_grounding_for_passage(themes=["hope"]))
    assert result == ""


def test_resonance_engine_error_degrades_to_empty_string_not_exception(monkeypatch):
    fake_engine = FakeResonanceEngine(raise_error=True, wiki_adapter=no_cross_disciplinary_wiki())
    monkeypatch.setattr(service_module, "get_resonance_engine", lambda tmdb_api_key=None: fake_engine)

    result = asyncio.run(build_grounding_for_passage(themes=["hope"]))
    assert result == ""


def test_cross_disciplinary_results_are_included(monkeypatch):
    wiki = WikipediaAdapter({})

    async def fake_search_topics(themes, categories=None, limit_per_category=3):
        return {
            "etymology": [
                CulturalArtifact(
                    title="Folk etymology", creator="Wikipedia", year=0, category="etymology",
                    source_name="Wikipedia", quote_or_description="desc", context="",
                )
            ]
        }

    wiki.search_topics = fake_search_topics
    fake_engine = FakeResonanceEngine(wiki_adapter=wiki)
    monkeypatch.setattr(service_module, "get_resonance_engine", lambda tmdb_api_key=None: fake_engine)

    result = asyncio.run(build_grounding_for_passage(themes=["healing"]))
    assert "Folk etymology" in result
    assert "Etymology & Word Origins" in result


def test_cross_disciplinary_error_degrades_gracefully(monkeypatch):
    wiki = WikipediaAdapter({})

    async def broken_search_topics(themes, categories=None, limit_per_category=3):
        raise Exception("wikipedia is down")

    wiki.search_topics = broken_search_topics
    fake_engine = FakeResonanceEngine(
        classic_artifacts=[make_artifact("Purple Rain")], wiki_adapter=wiki
    )
    monkeypatch.setattr(service_module, "get_resonance_engine", lambda tmdb_api_key=None: fake_engine)

    # Cross-disciplinary blowing up shouldn't take down the pop-culture
    # grounding that already succeeded.
    result = asyncio.run(build_grounding_for_passage(themes=["healing"]))
    assert "Purple Rain" in result


def test_no_wikipedia_adapter_present_skips_cross_disciplinary_gracefully(monkeypatch):
    fake_engine = FakeResonanceEngine(classic_artifacts=[make_artifact("Purple Rain")])
    fake_engine.adapters = []  # no WikipediaAdapter at all
    monkeypatch.setattr(service_module, "get_resonance_engine", lambda tmdb_api_key=None: fake_engine)

    result = asyncio.run(build_grounding_for_passage(themes=["healing"]))
    assert "Purple Rain" in result

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
import web.services.cultural_grounding_service as service_module
from web.services.cultural_grounding_service import build_grounding_for_passage


class FakeClaude:
    def __init__(self, response_text):
        self.response_text = response_text

    def complete(self, **kwargs):
        return self.response_text


class FakeResonanceEngine:
    def __init__(self, classic_artifacts=None, contemporary_artifacts=None, raise_error=False):
        self.classic_artifacts = classic_artifacts or []
        self.contemporary_artifacts = contemporary_artifacts or []
        self.raise_error = raise_error
        self.calls = []

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


def test_no_themes_returns_empty_string_without_calling_resonance(monkeypatch):
    fake_engine = FakeResonanceEngine()
    monkeypatch.setattr(service_module, "get_resonance_engine", lambda tmdb_api_key=None: fake_engine)

    result = asyncio.run(
        build_grounding_for_passage(FakeClaude("not valid json"), "John 3:16", "some text")
    )
    assert result == ""
    assert fake_engine.calls == []  # short-circuited before touching resonance at all


def test_themes_found_queries_both_eras(monkeypatch):
    fake_engine = FakeResonanceEngine(
        classic_artifacts=[make_artifact("Purple Rain")],
        contemporary_artifacts=[make_artifact("Folklore")],
    )
    monkeypatch.setattr(service_module, "get_resonance_engine", lambda tmdb_api_key=None: fake_engine)

    result = asyncio.run(
        build_grounding_for_passage(FakeClaude('["hope", "loss"]'), "John 3:16", "some text")
    )
    assert "Purple Rain" in result
    assert "Folklore" in result
    assert len(fake_engine.calls) == 2
    classic_call, contemporary_call = fake_engine.calls
    assert classic_call == (1977, 1999)
    assert contemporary_call[1] - contemporary_call[0] == 15


def test_both_eras_empty_returns_empty_string(monkeypatch):
    fake_engine = FakeResonanceEngine()
    monkeypatch.setattr(service_module, "get_resonance_engine", lambda tmdb_api_key=None: fake_engine)

    result = asyncio.run(
        build_grounding_for_passage(FakeClaude('["hope"]'), "John 3:16", "some text")
    )
    assert result == ""


def test_resonance_engine_error_degrades_to_empty_string_not_exception(monkeypatch):
    fake_engine = FakeResonanceEngine(raise_error=True)
    monkeypatch.setattr(service_module, "get_resonance_engine", lambda tmdb_api_key=None: fake_engine)

    result = asyncio.run(
        build_grounding_for_passage(FakeClaude('["hope"]'), "John 3:16", "some text")
    )
    assert result == ""

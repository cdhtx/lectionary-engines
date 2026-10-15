# tests/test_signal_generator.py
import json
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.models import Base, Signal
from web.services.signal_generator import DEFAULT_SIGNALS_MODEL, generate_signal


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _valid_json(theme="hospitality", title="The Unfinished Meal"):
    return json.dumps({
        "title": title,
        "theme": theme,
        "signal_detected": "A pattern.",
        "connection": "Genesis 18 and Luke 24.",
        "nature_of_connection": "Inversion.",
        "intratextual": "Also Judges 19.",
        "modern_illustration": "A report on a refugee kitchen.",
        "modern_illustration_category": "news",
        "dig_deeper": [
            {"title": "Gilead", "author": "Marilynne Robinson", "kind": "fiction", "why": "Grace."},
            {"title": "Making Room", "author": "Christine Pohl", "kind": "nonfiction", "why": "History."},
        ],
    })


def _response(text, results=None, stop_reason="end_turn", search_requests=1):
    results = results if results is not None else [NS(type="web_search_result", title="Src", url="https://example.com/a")]
    return NS(
        content=[
            NS(type="web_search_tool_result", content=results),
            NS(type="text", text=text),
        ],
        stop_reason=stop_reason,
        usage=NS(input_tokens=1000, output_tokens=500, server_tool_use=NS(web_search_requests=search_requests)),
    )


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_saves_valid_signal_with_sources_and_usage(db):
    client = FakeClient(_response(_valid_json()))
    signal = generate_signal(db, client)

    assert signal is not None
    row = db.query(Signal).one()
    assert row.title == "The Unfinished Meal"
    assert row.model == DEFAULT_SIGNALS_MODEL
    assert row.sources_list == [{"title": "Src", "url": "https://example.com/a"}]
    assert (row.input_tokens, row.output_tokens, row.search_count) == (1000, 500, 1)
    call = client.calls[0]
    assert call["model"] == DEFAULT_SIGNALS_MODEL
    assert call["max_tokens"] == 16000
    assert call["tools"][0]["type"] == "web_search_20250305"


def test_model_override_and_env(db, monkeypatch):
    monkeypatch.setenv("SIGNALS_MODEL", "claude-opus-5-5")
    client = FakeClient(_response(_valid_json()))
    generate_signal(db, client)
    assert client.calls[0]["model"] == "claude-opus-5-5"


def test_retries_once_after_bad_json_then_saves(db):
    client = FakeClient(_response("not json"), _response(_valid_json()))
    assert generate_signal(db, client) is not None
    assert len(client.calls) == 2
    assert db.query(Signal).count() == 1


def test_two_failures_save_nothing(db):
    client = FakeClient(_response("not json"), _response("still not json"))
    assert generate_signal(db, client) is None
    assert db.query(Signal).count() == 0


@pytest.mark.parametrize("stop_reason", ["max_tokens", "pause_turn"])
def test_truncated_or_paused_response_saves_nothing(db, stop_reason):
    client = FakeClient(
        _response(_valid_json(), stop_reason=stop_reason),
        _response(_valid_json(), stop_reason=stop_reason),
    )
    assert generate_signal(db, client) is None
    assert db.query(Signal).count() == 0


def test_no_sources_saves_nothing(db):
    client = FakeClient(_response(_valid_json(), results=[]), _response(_valid_json(), results=[]))
    assert generate_signal(db, client) is None


def test_search_error_object_counts_as_no_sources(db):
    error_obj = NS(type="web_search_tool_result_error", error_code="unavailable")
    client = FakeClient(_response(_valid_json(), results=error_obj), _response(_valid_json(), results=error_obj))
    assert generate_signal(db, client) is None


def test_recent_themes_are_sent_to_the_model(db):
    db.add(Signal(title="Old", theme="exile", signal_detected="s", connection="c",
                  nature_of_connection="n", intratextual="i", modern_illustration="m",
                  modern_illustration_category="art"))
    db.commit()
    client = FakeClient(_response(_valid_json("a new theme")))
    generate_signal(db, client)
    assert "exile" in client.calls[0]["messages"][0]["content"]


def test_api_error_returns_none_without_raising(db):
    import anthropic

    class Boom:
        messages = None

        def __init__(self):
            self.messages = self

        def create(self, **kwargs):
            raise anthropic.APIConnectionError(request=NS())

    assert generate_signal(db, Boom()) is None


def test_long_title_and_theme_are_truncated_to_200(db):
    client = FakeClient(_response(_valid_json(theme="t" * 300, title="x" * 300)))
    signal = generate_signal(db, client)
    assert signal is not None
    row = db.query(Signal).one()
    assert row.title == "x" * 200
    assert row.theme == "t" * 200

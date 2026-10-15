# tests/test_signals_protocol.py
import json

import pytest

from lectionary_engines.protocols.signals_protocol import (
    SignalParseError,
    build_user_prompt,
    parse_signal,
)


def _valid():
    return {
        "title": "The Unfinished Meal",
        "theme": "hospitality",
        "signal_detected": "A pattern.",
        "connection": "Genesis 18 and Luke 24.",
        "nature_of_connection": "Inversion.",
        "intratextual": "Also Judges 19.",
        "modern_illustration": "A 2026 report on a refugee kitchen.",
        "modern_illustration_category": "news",
        "dig_deeper": [
            {"title": "Gilead", "author": "Marilynne Robinson", "kind": "fiction", "why": "Hospitality as grace."},
            {"title": "Making Room", "author": "Christine Pohl", "kind": "nonfiction", "why": "History of the practice."},
        ],
    }


def test_parse_accepts_valid_json():
    assert parse_signal(json.dumps(_valid()))["title"] == "The Unfinished Meal"


def test_parse_finds_json_inside_prose_and_code_fences():
    text = "Here is the signal:\n```json\n" + json.dumps(_valid()) + "\n```\nHope that helps."
    assert parse_signal(text)["theme"] == "hospitality"


@pytest.mark.parametrize("field", [
    "title", "theme", "signal_detected", "connection",
    "nature_of_connection", "intratextual", "modern_illustration",
])
def test_parse_rejects_missing_or_blank_text_field(field):
    data = _valid()
    data[field] = "  "
    with pytest.raises(SignalParseError):
        parse_signal(json.dumps(data))


def test_parse_rejects_unknown_category():
    data = _valid()
    data["modern_illustration_category"] = "sports"
    with pytest.raises(SignalParseError):
        parse_signal(json.dumps(data))


def test_parse_requires_two_complete_dig_deeper_entries():
    data = _valid()
    data["dig_deeper"] = data["dig_deeper"][:1]
    with pytest.raises(SignalParseError):
        parse_signal(json.dumps(data))
    data = _valid()
    del data["dig_deeper"][0]["author"]
    with pytest.raises(SignalParseError):
        parse_signal(json.dumps(data))


def test_parse_rejects_non_json_and_error_object():
    with pytest.raises(SignalParseError):
        parse_signal("I could not find anything.")
    with pytest.raises(SignalParseError):
        parse_signal(json.dumps({"error": "no verifiable example found"}))


def test_user_prompt_lists_recent_themes_to_avoid():
    prompt = build_user_prompt([{"title": "Old One", "theme": "exile"}])
    assert "exile" in prompt and "Old One" in prompt


def test_user_prompt_without_history_has_no_avoid_list():
    assert "Avoid" not in build_user_prompt([])

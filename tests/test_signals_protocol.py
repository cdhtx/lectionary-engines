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


# ---- clean_text: citation markup and dashes ----

from lectionary_engines.protocols.signals_protocol import clean_text


def test_clean_text_strips_cite_tags_and_keeps_the_words():
    raw = 'In 2026, <cite index="4-1">the remains of 11 students</cite> came home.'
    assert clean_text(raw) == "In 2026, the remains of 11 students came home."


def test_clean_text_handles_the_malformed_paren_variant_seen_in_production():
    raw = 'In October, (cite index="4-1">the remains came home</cite>. Her family waited.'
    assert clean_text(raw) == "In October, the remains came home. Her family waited."


def test_clean_text_replaces_em_and_en_dashes():
    assert clean_text("a pattern — and a surprise") == "a pattern, and a surprise"
    assert clean_text("Exodus 16–17") == "Exodus 16-17"


def test_clean_text_leaves_normal_text_alone():
    assert clean_text("Plain text, with a comma.") == "Plain text, with a comma."


def test_parse_signal_cleans_every_text_field_and_dig_deeper():
    data = _valid()
    data["signal_detected"] = 'A <cite index="1-1">pattern</cite> — noticed.'
    data["dig_deeper"][0]["why"] = 'Grace — <cite index="2-1">fully</cite>.'
    parsed = parse_signal(json.dumps(data))
    assert parsed["signal_detected"] == "A pattern, noticed."
    assert parsed["dig_deeper"][0]["why"] == "Grace, fully."


def test_parse_signal_returns_sources_used_when_present_and_empty_otherwise():
    data = _valid()
    assert parse_signal(json.dumps(data))["sources_used"] == []
    data["sources_used"] = ["https://a.example/1", "", 5, "https://b.example/2"]
    assert parse_signal(json.dumps(data))["sources_used"] == ["https://a.example/1", "https://b.example/2"]


def test_prompt_asks_for_plain_text_and_sources_used():
    from lectionary_engines.protocols.signals_protocol import SYSTEM_PROMPT

    assert "sources_used" in SYSTEM_PROMPT
    assert "—" not in SYSTEM_PROMPT and "–" not in SYSTEM_PROMPT

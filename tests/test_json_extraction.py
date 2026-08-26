"""
Tests for lectionary_engines.json_extraction
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lectionary_engines.json_extraction import extract_first_json


def test_clean_json_object():
    assert extract_first_json('{"index": 7}') == {"index": 7}


def test_clean_json_array():
    assert extract_first_json('["a", "b", "c"]') == ["a", "b", "c"]


def test_fenced_json():
    assert extract_first_json('```json\n{"index": 3}\n```') == {"index": 3}


def test_fenced_json_no_language_tag():
    assert extract_first_json('```\n{"index": 3}\n```') == {"index": 3}


def test_json_with_trailing_prose():
    # The real failure mode: model returns valid JSON but keeps talking
    # afterward despite being told to return ONLY JSON.
    raw = '```json\n{"index": 7}\n```\n\nThis headline connects because...'
    assert extract_first_json(raw) == {"index": 7}


def test_json_with_trailing_prose_truncated_mid_sentence():
    # Same failure, but the trailing prose got cut off by max_tokens -
    # no closing anything, just a hard stop.
    raw = '{"index": 7}\n\nThis headline connects to wealth and greed because it addresses'
    assert extract_first_json(raw) == {"index": 7}


def test_null_value_in_object():
    assert extract_first_json('{"index": null}') == {"index": None}


def test_no_json_present_returns_none():
    assert extract_first_json("Sorry, I can't help with that.") is None


def test_empty_string_returns_none():
    assert extract_first_json("") is None


def test_malformed_json_returns_none():
    assert extract_first_json('{"index": }') is None


def test_array_with_trailing_prose():
    raw = '["hope", "loss"]\nThese are the two dominant themes I found.'
    assert extract_first_json(raw) == ["hope", "loss"]

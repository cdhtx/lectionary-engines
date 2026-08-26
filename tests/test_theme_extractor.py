"""
Tests for lectionary_engines.theme_extractor

Uses a fake ClaudeClient stand-in (just needs a .complete() method) so
these run without hitting the real API.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lectionary_engines.theme_extractor import extract_themes


class FakeClaude:
    def __init__(self, response_text):
        self.response_text = response_text
        self.last_call = None

    def complete(self, **kwargs):
        self.last_call = kwargs
        return self.response_text


def test_parses_clean_json_array():
    fake = FakeClaude('["betrayal by a friend", "public shame and restoration"]')
    result = extract_themes(fake, "John 13:21-30", "some text")
    assert result == ["betrayal by a friend", "public shame and restoration"]


def test_strips_markdown_code_fences():
    fake = FakeClaude('```json\n["waiting on unclear timing"]\n```')
    result = extract_themes(fake, "Luke 2:25-35", "some text")
    assert result == ["waiting on unclear timing"]


def test_truncates_to_eight_themes():
    themes = [f"theme {i}" for i in range(12)]
    fake = FakeClaude(str(themes).replace("'", '"'))
    result = extract_themes(fake, "Psalm 23", "some text")
    assert len(result) == 8


def test_malformed_json_returns_empty_list():
    fake = FakeClaude("not valid json at all")
    result = extract_themes(fake, "Mark 5:1-5", "some text")
    assert result == []


def test_non_list_json_returns_empty_list():
    fake = FakeClaude('{"theme": "not a list"}')
    result = extract_themes(fake, "Mark 5:1-5", "some text")
    assert result == []


def test_claude_exception_returns_empty_list():
    class BrokenClaude:
        def complete(self, **kwargs):
            raise Exception("API down")

    result = extract_themes(BrokenClaude(), "Mark 5:1-5", "some text")
    assert result == []


def test_empty_strings_are_filtered_out():
    fake = FakeClaude('["real theme", "", "   ", "another theme"]')
    result = extract_themes(fake, "Mark 5:1-5", "some text")
    assert result == ["real theme", "another theme"]


def test_passes_reference_and_truncated_text_to_claude():
    fake = FakeClaude('["theme one"]')
    long_text = "x" * 5000
    extract_themes(fake, "John 3:16", long_text)
    assert "John 3:16" in fake.last_call["user_message"]
    assert len(fake.last_call["user_message"]) < 3200  # text truncated to 3000 chars + prefix

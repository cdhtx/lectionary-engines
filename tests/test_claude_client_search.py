from types import SimpleNamespace as NS

from lectionary_engines.claude_client import _final_text


def _b(type_, text=None):
    return NS(type=type_, text=text)


def test_final_text_drops_narration_before_and_between_searches():
    content = [
        _b("text", "Let me verify that quote. "),
        _b("server_tool_use"),
        _b("web_search_tool_result"),
        _b("text", "One more check. "),
        _b("server_tool_use"),
        _b("web_search_tool_result"),
        _b("text", "# Palimpsest Study\n\n"),
        _b("text", "The real study."),
    ]
    assert _final_text(content) == "# Palimpsest Study\n\nThe real study."


def test_final_text_without_tools_keeps_everything():
    assert _final_text([_b("text", "a"), _b("text", "b")]) == "ab"

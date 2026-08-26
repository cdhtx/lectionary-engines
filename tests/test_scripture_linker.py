"""
Tests for lectionary_engines.scripture_linker
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lectionary_engines.scripture_linker import link_scripture_references


def test_simple_reference():
    result = link_scripture_references("Consider John 3:16 carefully.")
    assert 'href="https://www.biblegateway.com/passage/?search=John%203%3A16&version=NRSVUE"' in result
    assert 'class="scripture-link"' in result
    assert ">John 3:16</a>" in result


def test_verse_range():
    result = link_scripture_references("See Mark 5:1-5 for context.")
    assert 'href="https://www.biblegateway.com/passage/?search=Mark%205%3A1-5&version=NRSVUE"' in result
    assert ">Mark 5:1-5</a>" in result


def test_en_dash_verse_range():
    # Moravian/RCL sources use en dashes, and Claude mirrors that
    # formatting straight into generated study titles/content.
    result = link_scripture_references("Mark 2:13–28 opens the study.")
    assert ">Mark 2:13–28</a>" in result
    assert 'href="https://www.biblegateway.com/passage/?search=Mark%202%3A13%E2%80%9328&version=NRSVUE"' in result


def test_cross_chapter_range():
    result = link_scripture_references("Read Genesis 1:1-2:3 in full.")
    assert ">Genesis 1:1-2:3</a>" in result
    assert "search=Genesis%201%3A1-2%3A3" in result


def test_half_verse_suffix():
    result = link_scripture_references("2 Thessalonians 2:3a-16, 17 is the reading.")
    assert ">2 Thessalonians 2:3a-16</a>" in result


def test_chapter_only_reference():
    result = link_scripture_references("Turn to Psalm 23 for comfort.")
    assert 'href="https://www.biblegateway.com/passage/?search=Psalm%2023&version=NRSVUE"' in result
    assert ">Psalm 23</a>" in result


def test_numbered_book():
    result = link_scripture_references("1 Corinthians 13:4-7 describes love.")
    assert ">1 Corinthians 13:4-7</a>" in result


def test_book_alias_resolves_to_canonical_search():
    result = link_scripture_references("Gen 1:1 begins the story.")
    assert 'href="https://www.biblegateway.com/passage/?search=Gen%201%3A1&version=NRSVUE"' in result
    assert ">Gen 1:1</a>" in result


def test_translation_maps_to_version_code():
    result = link_scripture_references("John 3:16 is well known.", translation="NIV")
    assert "version=NIV" in result


def test_unrecognized_translation_falls_back_to_default():
    result = link_scripture_references("John 3:16 is well known.", translation="Klingon")
    assert "version=NRSVUE" in result


def test_multiple_references_in_one_string():
    result = link_scripture_references("Compare Romans 8:28 with Philippians 4:13.")
    assert ">Romans 8:28</a>" in result
    assert ">Philippians 4:13</a>" in result


def test_links_open_in_new_tab_safely():
    result = link_scripture_references("John 3:16 is well known.")
    assert 'target="_blank"' in result
    assert 'rel="noopener noreferrer"' in result


def test_fenced_code_block_is_untouched():
    text = "Explanation.\n\n```\nJohn 3:16\n```\n\nMore text with Mark 5:1-5."
    result = link_scripture_references(text)
    assert "```\nJohn 3:16\n```" in result  # unlinked inside the fence
    assert ">Mark 5:1-5</a>" in result  # linked outside the fence


def test_already_linked_reference_is_not_double_linked():
    text = "[John 3:16](https://example.com/already-a-link)"
    result = link_scripture_references(text)
    assert result == text


def test_non_reference_numbers_are_left_alone():
    result = link_scripture_references("The meeting is at 3:16 PM in room 12.")
    assert "biblegateway" not in result


def test_empty_string_returns_empty():
    assert link_scripture_references("") == ""

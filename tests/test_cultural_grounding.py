"""
Tests for lectionary_engines.protocols.cultural_grounding
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lectionary_engines.cultural.base_adapter import CulturalArtifact
from lectionary_engines.protocols.cultural_grounding import build_grounding_block


def make_artifact(title="Test Song", year=1985, creator="Test Artist", themes=None, description="A description."):
    return CulturalArtifact(
        title=title,
        creator=creator,
        year=year,
        category="music",
        source_name="Wikipedia",
        quote_or_description=description,
        context="",
        themes=themes or [],
    )


def test_empty_lists_return_empty_string():
    assert build_grounding_block([], []) == ""


def test_classic_only_includes_classic_section_not_contemporary():
    result = build_grounding_block([make_artifact(title="Purple Rain", year=1984)], [])
    assert "Classic era (1977-1999)" in result
    assert "Contemporary" not in result
    assert "Purple Rain" in result


def test_contemporary_only_includes_contemporary_section_not_classic():
    result = build_grounding_block([], [make_artifact(title="Folklore", year=2020)])
    assert "Contemporary" in result
    assert "Classic era" not in result
    assert "Folklore" in result


def test_both_eras_included_when_both_present():
    result = build_grounding_block(
        [make_artifact(title="Purple Rain", year=1984)],
        [make_artifact(title="Folklore", year=2020)],
    )
    assert "Purple Rain" in result
    assert "Folklore" in result
    assert "Classic era (1977-1999)" in result
    assert "Contemporary" in result


def test_includes_themes_when_present():
    result = build_grounding_block(
        [make_artifact(themes=["hope", "perseverance"])], []
    )
    assert "hope, perseverance" in result


def test_omits_theme_bracket_when_no_themes():
    result = build_grounding_block([make_artifact(themes=[])], [])
    assert "[themes:" not in result


def test_limits_to_eight_artifacts_per_era():
    artifacts = [make_artifact(title=f"Song {i}") for i in range(12)]
    result = build_grounding_block(artifacts, [])
    assert result.count("Song ") == 8


def test_instructs_claude_to_prefer_real_over_invented():
    result = build_grounding_block([make_artifact()], [])
    assert "not invented from memory" in result
    assert "may still draw on your own knowledge" in result


def test_instructs_claude_to_develop_not_just_namedrop():
    result = build_grounding_block([make_artifact()], [])
    assert "actually develop it" in result


def make_cross_disciplinary_artifact(title, description="A description."):
    return CulturalArtifact(
        title=title,
        creator="Wikipedia",
        year=0,
        category="etymology",
        source_name="Wikipedia",
        quote_or_description=description,
        context="",
        themes=[],
    )


def test_cross_disciplinary_section_included_when_present():
    result = build_grounding_block(
        [], [], cross_disciplinary={"etymology": [make_cross_disciplinary_artifact("Folk etymology")]}
    )
    assert "Etymology & Word Origins" in result
    assert "Folk etymology" in result


def test_cross_disciplinary_omits_year():
    result = build_grounding_block(
        [], [], cross_disciplinary={"biography": [make_cross_disciplinary_artifact("Mary Ingalls")]}
    )
    assert "Mary Ingalls* (0" not in result


def test_cross_disciplinary_categories_only_shown_when_nonempty():
    result = build_grounding_block(
        [],
        [],
        cross_disciplinary={
            "etymology": [make_cross_disciplinary_artifact("Folk etymology")],
            "travel": [],
        },
    )
    assert "Etymology & Word Origins" in result
    assert "Travel & Geography" not in result


def test_pop_culture_and_cross_disciplinary_both_included():
    result = build_grounding_block(
        [make_artifact(title="Purple Rain")],
        [],
        cross_disciplinary={"art": [make_cross_disciplinary_artifact("Chinese art")]},
    )
    assert "Purple Rain" in result
    assert "Chinese art" in result
    assert "Art" in result


def test_none_cross_disciplinary_does_not_error():
    result = build_grounding_block([make_artifact()], [], cross_disciplinary=None)
    assert "Test Song" in result


def test_empty_cross_disciplinary_dict_with_empty_eras_returns_empty_string():
    assert build_grounding_block([], [], cross_disciplinary={}) == ""
    assert build_grounding_block([], [], cross_disciplinary={"etymology": []}) == ""

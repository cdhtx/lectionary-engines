"""
Tests for the Palimpsest layer parser: splits a Palimpsest study's flat
markdown content into its five named PaRDeS layers, so the study view
can render each as an addressable section for spatial navigation. See
docs/superpowers/specs/2026-08-28-tier-3-palimpsest-design.md.
"""

from web.services.palimpsest_layers import RAIL_LABELS, parse_palimpsest_layers


VALID_PALIMPSEST_MARKDOWN = """# Palimpsest Study: John 3:16-21

This text rewards layered reading because it moves from cosmic love to concrete judgment in a single breath.

## Layer One: Peshat (Simple/Literal)

John uses agape throughout. The Greek kosmos here means the whole created order, not merely humanity.

This is what the text says. Now we explore what it means.

## Layer Two: Remez (Hint/Allegory)

The lifting up of the Son of Man echoes the bronze serpent in Numbers 21 - healing through looking at the very thing that wounds.

The text hints at realities beyond itself. Now we see how communities have read these hints.

## Layer Three: Derash (Search/Interpretation)

Augustine reads this as pure grace; Wesley reads it as prevenient grace inviting response. Both readings persist because the text itself is generative, not because either resolves it.

Traditions differ, and rightly so. Now we enter the mystery that transcends all readings.

## Layer Four: Sod (Secret/Mystery)

Light entering darkness.

Not explained. Witnessed.

Sit for a moment in that light before turning the page.

## Layer Five: Incarnation (Contemporary Body)

### For Individuals in Transition

Ask: what have I been avoiding stepping into the light on?

### For Post-Institutional Seekers

You do not need an institution's permission to be loved by this text.

### For Leaders and Coaches

Ask your directee: where in your leadership are you hiding in the dark rather than risking exposure?

### For Worship Communities

Use this as a call to confession that ends in assurance, not shame.

### For Content Creators

A short-form piece: "The verse everyone quotes and no one finishes reading."

### For Professional Contexts

Judgment in this text is diagnostic, not punitive - a useful reframe for performance conversations.

---

**The Palimpsest Through-Line**: From literal meaning through allegorical connections through interpretive traditions through mystical silence into contemporary embodiment.
"""


def test_valid_content_splits_into_five_layers_in_order():
    result = parse_palimpsest_layers(VALID_PALIMPSEST_MARKDOWN)

    assert result is not None
    assert [layer["key"] for layer in result["layers"]] == [
        "peshat", "remez", "derash", "sod", "incarnation",
    ]


def test_intro_text_before_first_layer_is_captured_separately():
    result = parse_palimpsest_layers(VALID_PALIMPSEST_MARKDOWN)

    assert result is not None
    assert "This text rewards layered reading" in result["intro_markdown"]
    assert "Layer One" not in result["intro_markdown"]


def test_each_layer_contains_only_its_own_content():
    result = parse_palimpsest_layers(VALID_PALIMPSEST_MARKDOWN)

    assert result is not None
    layers_by_key = {layer["key"]: layer["markdown"] for layer in result["layers"]}

    assert "agape" in layers_by_key["peshat"]
    assert "bronze serpent" not in layers_by_key["peshat"]

    assert "bronze serpent" in layers_by_key["remez"]
    assert "Augustine" not in layers_by_key["remez"]

    assert "Augustine" in layers_by_key["derash"]
    assert "Sit for a moment" not in layers_by_key["derash"]

    assert "Sit for a moment" in layers_by_key["sod"]
    assert "Individuals in Transition" not in layers_by_key["sod"]


def test_incarnation_layer_keeps_its_six_subheadings_intact():
    result = parse_palimpsest_layers(VALID_PALIMPSEST_MARKDOWN)

    assert result is not None
    incarnation = next(layer for layer in result["layers"] if layer["key"] == "incarnation")

    for subheading in [
        "For Individuals in Transition",
        "For Post-Institutional Seekers",
        "For Leaders and Coaches",
        "For Worship Communities",
        "For Content Creators",
        "For Professional Contexts",
    ]:
        assert subheading in incarnation["markdown"]


def test_missing_layer_returns_none():
    missing_sod = VALID_PALIMPSEST_MARKDOWN.replace(
        "## Layer Four: Sod (Secret/Mystery)", "## Layer Four: Something Else Entirely"
    )

    assert parse_palimpsest_layers(missing_sod) is None


def test_layers_out_of_order_returns_none():
    # Swap Remez's and Derash's heading lines, producing the order
    # Peshat, Derash, Remez, Sod, Incarnation.
    out_of_order = VALID_PALIMPSEST_MARKDOWN.replace(
        "## Layer Two: Remez (Hint/Allegory)", "## Layer Two: TEMP_REMEZ_MARKER"
    ).replace(
        "## Layer Three: Derash (Search/Interpretation)", "## Layer Two: Remez (Hint/Allegory)"
    ).replace(
        "## Layer Two: TEMP_REMEZ_MARKER", "## Layer Three: Derash (Search/Interpretation)"
    )

    assert parse_palimpsest_layers(out_of_order) is None


def test_non_palimpsest_content_returns_none():
    threshold_style_content = """# Threshold Study: Mark 5:1-5

## Threshold One: Archaeological Dive

Some content here.

## Threshold Two: Theological Combustion

More content here.
"""

    assert parse_palimpsest_layers(threshold_style_content) is None


def test_heading_text_variance_still_matches_on_keyword():
    varied_heading = VALID_PALIMPSEST_MARKDOWN.replace(
        "## Layer One: Peshat (Simple/Literal)", "## Layer 1: Peshat"
    )

    result = parse_palimpsest_layers(varied_heading)

    assert result is not None
    assert result["layers"][0]["key"] == "peshat"


def test_heading_with_two_keywords_matches_the_first_one():
    # A heading that mentions a second layer's keyword in passing (e.g. to
    # contrast with what's coming later) must still be attributed to the
    # FIRST keyword it contains, since that's the layer the heading is
    # actually naming. A greedy regex would wrongly grab the last keyword
    # on the line instead.
    two_keyword_heading = VALID_PALIMPSEST_MARKDOWN.replace(
        "## Layer One: Peshat (Simple/Literal)",
        "## Layer One: Peshat (Simple/Literal) - not yet time for Remez",
    )

    result = parse_palimpsest_layers(two_keyword_heading)

    assert result is not None
    assert result["layers"][0]["key"] == "peshat"
    assert [layer["key"] for layer in result["layers"]] == [
        "peshat", "remez", "derash", "sod", "incarnation",
    ]


def test_empty_content_returns_none():
    assert parse_palimpsest_layers("") is None


def test_rail_labels_keys_match_parser_keys_in_same_order():
    result = parse_palimpsest_layers(VALID_PALIMPSEST_MARKDOWN)

    assert result is not None
    assert [item["key"] for item in RAIL_LABELS] == [layer["key"] for layer in result["layers"]]

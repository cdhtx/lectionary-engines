import markdown

from lectionary_engines.protocols import threshold_protocol, palimpsest_protocol, collision_protocol
from lectionary_engines.protocols.format_protocol import STUDY_FORMAT_BLOCK
from web.services.palimpsest_layers import parse_palimpsest_layers
from web.services.study_callouts import decorate_callouts


def _render(md_text):
    return decorate_callouts(markdown.markdown(md_text, extensions=["extra", "nl2br", "sane_lists"]))


def test_known_labels_get_a_class():
    html = _render("> **Key insight:** one.\n\nText.\n\n> **Core line:** two.\n\nText.\n\n> **Try this:** three.\n\nText.\n\n> **Sit with this:** four.")
    for css in ("callout-insight", "callout-pull", "callout-practice", "callout-question"):
        assert f'class="callout {css}"' in html


def test_plain_and_unknown_blockquotes_are_untouched():
    html = _render("> For God so loved the world.\n\nText.\n\n> **Note:** something else.")
    assert "callout" not in html
    assert html.count("<blockquote>") == 2


def test_all_three_engine_prompts_carry_the_format_block():
    for proto in (threshold_protocol, palimpsest_protocol, collision_protocol):
        assert proto.SYSTEM_PROMPT.endswith(STUDY_FORMAT_BLOCK)


def test_callouts_do_not_disturb_palimpsest_layer_parsing():
    body = "Intro.\n\n" + "\n\n".join(
        f"## {name}\n\n> **Key insight:** point.\n\nText." for name in
        ("Peshat", "Remez", "Derash", "Sod", "Incarnation"))
    assert parse_palimpsest_layers(body) is not None

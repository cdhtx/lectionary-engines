"""
Contract tests for the CSS design token layer.

Undefined CSS custom properties fail silently in browsers - the property is
simply dropped and the element renders with an inherited or initial value.
These tests turn that silent failure into a loud one.
"""

import re
from pathlib import Path

CSS_PATH = Path(__file__).parent.parent / "web" / "static" / "css" / "styles.css"


def _css() -> str:
    return CSS_PATH.read_text()


def _root_block() -> str:
    """The contents of the first :root { ... } block."""
    match = re.search(r":root\s*\{(.*?)\n\}", _css(), re.DOTALL)
    assert match, ":root block not found in styles.css"
    return match.group(1)


def _defined_tokens() -> set:
    return set(re.findall(r"(--[\w-]+)\s*:", _root_block()))


def _used_tokens() -> set:
    return set(re.findall(r"var\(\s*(--[\w-]+)", _css()))


def test_every_referenced_token_is_defined():
    missing = _used_tokens() - _defined_tokens()
    assert not missing, f"CSS variables used but never defined: {sorted(missing)}"


def test_engine_colors_use_beta_palette():
    root = _root_block()
    assert "#E95B13" in root, "Threshold must be burnt orange #E95B13"
    assert "#1565B5" in root, "Palimpsest must be primary blue #1565B5"
    assert "#007D8A" in root, "Collision must be deep teal #007D8A"


def test_old_engine_colors_are_gone():
    # Guards against a well-meaning revert toward the pre-Beta palette.
    root = _root_block()
    for old_hex, name in [("#6b2d5b", "plum"), ("#1e5631", "forest"), ("#8b2500", "sienna")]:
        assert old_hex not in root.lower(), f"Pre-Beta {name} {old_hex} still present"

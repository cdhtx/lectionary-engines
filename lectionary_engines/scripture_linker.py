"""
Scripture Reference Linker

Detects biblical references (e.g. "John 3:16-21", "1 Corinthians 13:4-7",
"Genesis 1:1-2:3", "Psalm 23") inside generated markdown and rewrites them
as links to Bible Gateway, using a given translation.

Runs at render time rather than being baked into stored content, so it
applies retroactively to every study already in the database and never
needs a backfill migration.
"""

import re
from urllib.parse import quote

from .text_fetcher import SUPPORTED_TRANSLATIONS

# Canonical book name -> extra abbreviations/aliases that show up in
# generated studies and lectionary sources. Longest-first ordering is
# handled in _build_pattern(), not here.
BOOK_ALIASES = {
    "Genesis": ["Gen"],
    "Exodus": ["Exod", "Ex"],
    "Leviticus": ["Lev"],
    "Numbers": ["Num"],
    "Deuteronomy": ["Deut"],
    "Joshua": ["Josh"],
    "Judges": ["Judg"],
    "Ruth": [],
    "1 Samuel": ["1 Sam"],
    "2 Samuel": ["2 Sam"],
    "1 Kings": [],
    "2 Kings": [],
    "1 Chronicles": ["1 Chron"],
    "2 Chronicles": ["2 Chron"],
    "Ezra": [],
    "Nehemiah": ["Neh"],
    "Esther": ["Esth"],
    "Job": [],
    "Psalm": ["Psalms", "Ps"],
    "Proverbs": ["Prov"],
    "Ecclesiastes": ["Eccl"],
    "Song of Solomon": ["Song of Songs", "Song"],
    "Isaiah": ["Isa"],
    "Jeremiah": ["Jer"],
    "Lamentations": ["Lam"],
    "Ezekiel": ["Ezek"],
    "Daniel": ["Dan"],
    "Hosea": ["Hos"],
    "Joel": [],
    "Amos": [],
    "Obadiah": ["Obad"],
    "Jonah": [],
    "Micah": ["Mic"],
    "Nahum": ["Nah"],
    "Habakkuk": ["Hab"],
    "Zephaniah": ["Zeph"],
    "Haggai": ["Hag"],
    "Zechariah": ["Zech"],
    "Malachi": ["Mal"],
    "Matthew": ["Matt"],
    "Mark": [],
    "Luke": [],
    "John": [],
    "Acts": [],
    "Romans": ["Rom"],
    "1 Corinthians": ["1 Cor"],
    "2 Corinthians": ["2 Cor"],
    "Galatians": ["Gal"],
    "Ephesians": ["Eph"],
    "Philippians": ["Phil"],
    "Colossians": ["Col"],
    "1 Thessalonians": ["1 Thess"],
    "2 Thessalonians": ["2 Thess"],
    "1 Timothy": ["1 Tim"],
    "2 Timothy": ["2 Tim"],
    "Titus": [],
    "Philemon": ["Phlm"],
    "Hebrews": ["Heb"],
    "James": ["Jas"],
    "1 Peter": ["1 Pet"],
    "2 Peter": ["2 Pet"],
    "1 John": [],
    "2 John": [],
    "3 John": [],
    "Jude": [],
    "Revelation": ["Rev"],
}

# chapter:verse portion, after the book name.
# Supports: "3", "3:16", "3:16-21", "3:16-4:2", with optional a/b/c
# half-verse suffixes ("16a") that the engines' own lectionary sources use.
# Range dash accepts both an ASCII hyphen and an en dash (–) - the
# Moravian/RCL sources scraped by text_fetcher.py use en dashes, and Claude
# mirrors that formatting straight into generated study content.
_LOCATION_PATTERN = r"""
    (?P<chapter>\d{1,3})
    (?:
        :(?P<verse_start>\d{1,3}[a-c]?)
        (?:[-–](?:(?P<xchap>\d{1,3}):)?(?P<verse_end>\d{1,3}[a-c]?))?
    )?
"""

_COMPILED_PATTERN = None


def _build_pattern() -> re.Pattern:
    global _COMPILED_PATTERN
    if _COMPILED_PATTERN is not None:
        return _COMPILED_PATTERN

    aliases = []
    for canonical, extras in BOOK_ALIASES.items():
        aliases.append(canonical)
        aliases.extend(extras)

    # Longest first so e.g. "Song of Solomon" is tried before "Song",
    # and "1 Thessalonians" before "1 Thess".
    aliases.sort(key=len, reverse=True)
    book_alternation = "|".join(re.escape(a) for a in aliases)

    pattern = rf"\b(?P<book>{book_alternation})\.?\s+{_LOCATION_PATTERN}\b"
    _COMPILED_PATTERN = re.compile(pattern, re.VERBOSE)
    return _COMPILED_PATTERN


def _canonical_book(matched_book: str) -> str:
    """Map a matched alias back to its canonical book name."""
    for canonical, extras in BOOK_ALIASES.items():
        if matched_book == canonical or matched_book in extras:
            return canonical
    return matched_book  # pragma: no cover - unreachable given _build_pattern


def _bible_gateway_url(reference_text: str, translation: str) -> str:
    version = SUPPORTED_TRANSLATIONS.get(translation, SUPPORTED_TRANSLATIONS["NRSVue"])
    return f"https://www.biblegateway.com/passage/?search={quote(reference_text)}&version={version}"


def link_scripture_references(markdown_text: str, translation: str = "NRSVue") -> str:
    """
    Wrap biblical references in a markdown string with links to Bible Gateway.

    Args:
        markdown_text: Raw study/analysis markdown (not yet HTML-rendered).
        translation: Translation code the study was generated with
                     (falls back to NRSVue if unrecognized).

    Returns:
        The same markdown with references replaced by raw `<a>` tags
        (python-markdown passes inline HTML through untouched, so this
        renders correctly without relying on markdown link syntax). Text
        inside fenced code blocks and existing markdown links is left
        untouched.
    """
    if not markdown_text:
        return markdown_text

    pattern = _build_pattern()

    # Skip fenced code blocks entirely (``` ... ```) so any Book:Verse-looking
    # text a user pasted as an example isn't touched.
    fence_pattern = re.compile(r"```.*?```", re.DOTALL)
    protected_spans = [m.span() for m in fence_pattern.finditer(markdown_text)]

    def in_protected_span(pos: int) -> bool:
        return any(start <= pos < end for start, end in protected_spans)

    def replace(match: re.Match) -> str:
        start = match.start()
        if in_protected_span(start):
            return match.group(0)

        # Already the text of an existing markdown link, e.g. "[John 3:16](...)" -
        # don't nest a second link inside it.
        preceding_char = markdown_text[start - 1] if start > 0 else ""
        following_text = markdown_text[match.end():match.end() + 2]
        if preceding_char == "[" and following_text == "](":
            return match.group(0)

        reference_text = match.group(0)
        url = _bible_gateway_url(reference_text, translation)
        return (
            f'<a href="{url}" target="_blank" rel="noopener noreferrer" '
            f'class="scripture-link">{reference_text}</a>'
        )

    return pattern.sub(replace, markdown_text)

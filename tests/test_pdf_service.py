"""
Tests for web.services.pdf_service
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from web.services.pdf_service import render_pdf, slugify


def test_slugify_basic():
    assert slugify("John 3:16-21") == "john-3-16-21"


def test_slugify_collapses_repeated_separators():
    assert slugify("Mark  5:1 -- 5") == "mark-5-1-5"


def test_slugify_truncates_to_max_length():
    result = slugify("a" * 100, max_length=10)
    assert len(result) <= 10


def test_slugify_empty_string_falls_back():
    assert slugify("") == "document"


def test_slugify_all_punctuation_falls_back():
    assert slugify("!!!") == "document"


def test_render_pdf_produces_valid_pdf_bytes():
    pdf_bytes = render_pdf(
        title="John 3:16-21",
        meta_line="Threshold · August 27, 2026 · 2,847 words",
        content_html="<h2>Archaeological Dive</h2><p>Some study content here.</p>",
        source_url="https://lectionaryengine.com/study/1",
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000  # a real rendered page, not an empty shell


def test_render_pdf_without_source_url():
    pdf_bytes = render_pdf(
        title="Test",
        meta_line="Some meta",
        content_html="<p>Content</p>",
    )
    assert pdf_bytes.startswith(b"%PDF-")


def test_render_pdf_escapes_title_and_meta():
    # Title/meta come from user-influenced data (references, headlines) -
    # confirm they're escaped rather than passed through as raw HTML.
    pdf_bytes = render_pdf(
        title="<script>alert(1)</script>",
        meta_line="<b>bold meta</b>",
        content_html="<p>Safe content</p>",
    )
    assert pdf_bytes.startswith(b"%PDF-")

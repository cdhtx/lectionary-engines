"""
Tests for the unified Library query.

Seeds an in-memory SQLite DB with rows across all four content models and
verifies: cross-type ordering, type filtering, search filtering per the
type-specific field mapping, and pagination correctness when results span
more than one type on the same page.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.models import Base, CulturalResonance, CurrentsAnalysis, Study, WorkshopPrep
from web.services.library_service import search_library


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def _seed_one_of_each(db, base_time):
    db.add(Study(
        engine="threshold", reference="John 3:16-21", content="For God so loved the world",
        created_at=base_time - timedelta(days=1),
    ))
    db.add(WorkshopPrep(
        lens="apostolic_journalist", lens_name="The Apostolic Journalist",
        reference="Luke 14:1-14", content="Sabbath hospitality reading",
        created_at=base_time - timedelta(days=2),
    ))
    db.add(CurrentsAnalysis(
        analysis_date="August 20, 2026", headline_summary="A Test Headline",
        content="Some news analysis content", created_at=base_time - timedelta(days=3),
    ))
    db.add(CulturalResonance(
        themes='["hospitality", "empire"]', reference=None,
        content="Resonance content about hospitality", created_at=base_time - timedelta(days=4),
    ))
    db.commit()


def test_no_filter_returns_all_four_types_ordered_by_recency(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    result = search_library(db)

    assert result["total"] == 4
    content_types = [r["content_type"] for r in result["results"]]
    assert content_types == ["study", "workshop", "currents", "resonance"]


def test_content_type_filter_returns_only_that_type(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    result = search_library(db, content_type="workshop")

    assert result["total"] == 1
    assert result["results"][0]["content_type"] == "workshop"
    assert result["results"][0]["title"] == "Luke 14:1-14"


def test_unrecognized_content_type_is_treated_as_no_filter(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    result = search_library(db, content_type="not-a-real-type")

    assert result["total"] == 4


def test_search_matches_study_reference_and_content(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    result = search_library(db, q="John 3")

    assert result["total"] == 1
    assert result["results"][0]["content_type"] == "study"


def test_search_matches_currents_headline_since_it_has_no_reference_field(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    result = search_library(db, q="Test Headline")

    assert result["total"] == 1
    assert result["results"][0]["content_type"] == "currents"


def test_resonance_title_falls_back_to_joined_themes_when_reference_is_null(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    result = search_library(db, content_type="resonance")

    assert result["results"][0]["title"] == "Hospitality, Empire"


def test_urls_are_correct_per_type(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    result = search_library(db)
    by_type = {r["content_type"]: r for r in result["results"]}

    assert by_type["study"]["url"].startswith("/study/")
    assert by_type["workshop"]["url"].startswith("/workshop/")
    assert by_type["currents"]["url"].startswith("/currents/")
    assert by_type["resonance"]["url"].startswith("/resonance/")


def test_resonance_title_falls_back_gracefully_when_themes_elements_are_not_strings(db):
    # themes is valid JSON but its elements don't support .title() (e.g.
    # non-string values from malformed/legacy data) - search_library must
    # not raise, and should fall back to the raw themes string.
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    db.add(CulturalResonance(
        themes="[1, 2, 3]", reference=None,
        content="Resonance content with malformed themes",
        created_at=base_time,
    ))
    db.commit()

    result = search_library(db, content_type="resonance")

    assert result["total"] == 1
    assert result["results"][0]["title"] == "[1, 2, 3]"


def test_pagination_is_correct_across_types_on_the_same_page(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    result = search_library(db, page=1, per_page=2)

    assert result["total"] == 4
    assert result["total_pages"] == 2
    assert len(result["results"]) == 2
    # Most recent 2 overall: study (day -1), workshop (day -2)
    assert [r["content_type"] for r in result["results"]] == ["study", "workshop"]
    assert result["has_next"] is True
    assert result["has_prev"] is False

    page2 = search_library(db, page=2, per_page=2)
    assert [r["content_type"] for r in page2["results"]] == ["currents", "resonance"]
    assert page2["has_next"] is False
    assert page2["has_prev"] is True


def test_zero_or_negative_page_behaves_like_page_one(db):
    # /browse?page=0 or ?page=-3 are directly reachable via the route with
    # no upstream validation - search_library() must clamp internally
    # rather than emit a negative SQL OFFSET (which Postgres rejects).
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    page_one = search_library(db, page=1, per_page=2)
    zero_page = search_library(db, page=0, per_page=2)
    negative_page = search_library(db, page=-3, per_page=2)

    assert [r["content_type"] for r in zero_page["results"]] == [r["content_type"] for r in page_one["results"]]
    assert [r["content_type"] for r in negative_page["results"]] == [r["content_type"] for r in page_one["results"]]
    assert zero_page["page"] == 1
    assert negative_page["page"] == 1


def test_zero_or_negative_per_page_does_not_raise(db):
    base_time = datetime(2026, 8, 28, 12, 0, 0)
    _seed_one_of_each(db, base_time)

    zero_per_page = search_library(db, per_page=0)
    negative_per_page = search_library(db, per_page=-5)

    assert zero_per_page["total"] == 4
    assert len(zero_per_page["results"]) >= 1
    assert negative_per_page["total"] == 4
    assert len(negative_per_page["results"]) >= 1


def test_pagination_has_no_duplicate_or_dropped_rows_when_created_at_ties(db):
    # UNION ALL across four branches has unspecified tie order on Postgres
    # (MergeAppend/top-N heapsort), unlike a plain single-table ORDER BY.
    # The tiebreaker (content_type, id) must keep pagination stable even
    # when created_at collides exactly.
    tied_time = datetime(2026, 8, 28, 12, 0, 0)
    db.add(Study(engine="threshold", reference="Ref A", content="content a", created_at=tied_time))
    db.add(Study(engine="threshold", reference="Ref B", content="content b", created_at=tied_time))
    db.add(Study(engine="threshold", reference="Ref C", content="content c", created_at=tied_time))
    db.commit()

    page1 = search_library(db, page=1, per_page=2)
    page2 = search_library(db, page=2, per_page=2)

    ids_seen = [r["id"] for r in page1["results"]] + [r["id"] for r in page2["results"]]
    assert len(ids_seen) == len(set(ids_seen)) == 3

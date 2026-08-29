"""
Tests for reading-progress persistence: scroll-based reading progress,
shared across all four Library content types via one table. See
docs/superpowers/specs/2026-08-29-tier-1c-today-chrome-design.md.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.models import Base, ReadingProgress
from web.services.reading_progress_service import (
    get_current_read,
    get_progress_map,
    save_progress,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def test_save_progress_creates_a_row_on_first_save(db):
    save_progress(db, user_id=1, content_type="study", content_id=10, percent=25)

    row = db.query(ReadingProgress).filter(
        ReadingProgress.user_id == 1,
        ReadingProgress.content_type == "study",
        ReadingProgress.content_id == 10,
    ).first()
    assert row is not None
    assert row.percent == 25


def test_save_progress_increases_percent_on_higher_value(db):
    save_progress(db, user_id=1, content_type="study", content_id=10, percent=25)
    save_progress(db, user_id=1, content_type="study", content_id=10, percent=60)

    row = db.query(ReadingProgress).filter(ReadingProgress.content_id == 10).first()
    assert row.percent == 60


def test_save_progress_does_not_decrease_percent_on_lower_value(db):
    save_progress(db, user_id=1, content_type="study", content_id=10, percent=60)
    save_progress(db, user_id=1, content_type="study", content_id=10, percent=25)

    row = db.query(ReadingProgress).filter(ReadingProgress.content_id == 10).first()
    assert row.percent == 60


def test_save_progress_is_scoped_per_user_and_content_type(db):
    save_progress(db, user_id=1, content_type="study", content_id=10, percent=50)
    save_progress(db, user_id=2, content_type="study", content_id=10, percent=15)
    save_progress(db, user_id=1, content_type="workshop", content_id=10, percent=80)

    rows = db.query(ReadingProgress).filter(ReadingProgress.content_id == 10).all()
    by_key = {(r.user_id, r.content_type): r.percent for r in rows}
    assert by_key == {(1, "study"): 50, (2, "study"): 15, (1, "workshop"): 80}


def test_get_current_read_returns_none_when_no_progress_exists(db):
    assert get_current_read(db, user_id=1) is None


def test_get_current_read_returns_most_recently_updated_incomplete_item(db):
    save_progress(db, user_id=1, content_type="study", content_id=1, percent=40)
    save_progress(db, user_id=1, content_type="workshop", content_id=2, percent=70)

    result = get_current_read(db, user_id=1)

    assert result == {"content_type": "workshop", "content_id": 2, "percent": 70}


def test_get_current_read_ignores_completed_items(db):
    save_progress(db, user_id=1, content_type="study", content_id=1, percent=100)

    assert get_current_read(db, user_id=1) is None


def test_get_current_read_ignores_other_users(db):
    save_progress(db, user_id=2, content_type="study", content_id=1, percent=50)

    assert get_current_read(db, user_id=1) is None


def test_get_progress_map_returns_percent_by_content_id(db):
    save_progress(db, user_id=1, content_type="study", content_id=1, percent=30)
    save_progress(db, user_id=1, content_type="study", content_id=2, percent=90)

    result = get_progress_map(db, user_id=1, content_type="study", content_ids=[1, 2, 3])

    assert result == {1: 30, 2: 90}


def test_get_progress_map_is_scoped_to_the_given_content_type(db):
    save_progress(db, user_id=1, content_type="workshop", content_id=1, percent=55)

    result = get_progress_map(db, user_id=1, content_type="study", content_ids=[1])

    assert result == {}

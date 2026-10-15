# tests/test_signal_model.py
import json
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.models import Base, Signal


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_signal_round_trips_json_fields_and_defaults_created_at():
    db = _db()
    db.add(Signal(
        title="The Unfinished Meal",
        theme="hospitality",
        signal_detected="s",
        connection="c",
        nature_of_connection="n",
        intratextual="i",
        modern_illustration="m",
        modern_illustration_category="culture",
        dig_deeper=json.dumps([{"title": "Gilead", "author": "M. Robinson", "kind": "fiction", "why": "w"}]),
        sources=json.dumps([{"title": "T", "url": "https://example.com"}]),
        model="claude-sonnet-5-5",
        input_tokens=10, output_tokens=20, search_count=2,
    ))
    db.commit()

    row = db.query(Signal).one()
    assert isinstance(row.created_at, datetime)
    assert row.dig_deeper_list[0]["title"] == "Gilead"
    assert row.sources_list[0]["url"] == "https://example.com"


def test_signal_json_properties_tolerate_empty_or_bad_json():
    s = Signal(title="t", theme="x", signal_detected="s", connection="c",
               nature_of_connection="n", intratextual="i", modern_illustration="m",
               modern_illustration_category="art", dig_deeper="not json", sources=None)
    assert s.dig_deeper_list == []
    assert s.sources_list == []

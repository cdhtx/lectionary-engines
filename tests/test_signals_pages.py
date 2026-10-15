import json
from datetime import datetime, timedelta
from unittest.mock import patch

from web.models import Signal


def _signal(i, title=None, **overrides):
    fields = dict(
        title=title or f"Signal {i}",
        theme=f"theme {i}",
        signal_detected=f"detected {i}",
        connection=f"connection {i}",
        nature_of_connection=f"nature {i}",
        intratextual=f"intratextual {i}",
        modern_illustration=f"illustration {i}",
        modern_illustration_category="culture",
        dig_deeper=json.dumps([{"title": f"Book {i}", "author": "Author", "kind": "fiction", "why": "Because."}]),
        sources=json.dumps([{"title": "Source", "url": "https://example.com/s"}]),
        created_at=datetime(2026, 10, 1) + timedelta(days=i),
    )
    fields.update(overrides)
    return Signal(**fields)


def _seed(SessionLocal, count, **overrides):
    s = SessionLocal()
    for i in range(count):
        s.add(_signal(i, **overrides))
    s.commit()
    s.close()


def test_signals_page_empty_state(study_client):
    client, _ = study_client
    response = client.get("/signals")
    assert response.status_code == 200
    assert "first signal is on its way" in response.text


def test_signals_page_shows_three_newest_with_all_five_parts(study_client):
    client, SessionLocal = study_client
    _seed(SessionLocal, 5)

    body = client.get("/signals").text

    assert "Signal 4" in body and "Signal 3" in body and "Signal 2" in body
    assert "Signal 1" not in body and "Signal 0" not in body
    assert body.index("Signal 4") < body.index("Signal 3") < body.index("Signal 2")
    for label in ("Signal detected", "Connection", "Nature of the connection",
                  "Intratextual", "Modern illustration", "Dig deeper"):
        assert label in body
    assert "Book 4" in body
    assert "https://example.com/s" in body
    assert "/signals?n=6" in body  # explore more


def test_explore_more_reveals_next_three_and_hides_link_at_the_end(study_client):
    client, SessionLocal = study_client
    _seed(SessionLocal, 5)

    body = client.get("/signals?n=6").text
    assert "Signal 0" in body and "Signal 1" in body
    assert "Explore more" not in body


def test_exactly_three_signals_has_no_explore_more(study_client):
    client, SessionLocal = study_client
    _seed(SessionLocal, 3)
    assert "Explore more" not in client.get("/signals").text


def test_bad_n_values_are_clamped_not_errors(study_client):
    client, SessionLocal = study_client
    _seed(SessionLocal, 5)
    for value in ("abc", "-5", "0", "9999", ""):
        response = client.get(f"/signals?n={value}")
        assert response.status_code == 200, value
    assert "Signal 0" not in client.get("/signals?n=-5").text  # fell back to 3


def test_signal_text_is_escaped(study_client):
    client, SessionLocal = study_client
    s = SessionLocal()
    s.add(_signal(1, title="<script>alert(1)</script>"))
    s.commit()
    s.close()
    body = client.get("/signals").text
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


@patch("web.services.lectionary_widget_service.TextFetcher")
def test_today_widget_shows_latest_three_and_links_to_all(mock_fetcher_class, study_client):
    mock_fetcher_class.return_value.fetch_sunday_lectionary_readings.return_value = {}
    client, SessionLocal = study_client
    _seed(SessionLocal, 5)

    body = client.get("/").text

    assert "Signal 4" in body and "Signal 2" in body
    assert "Signal 1" not in body
    assert 'href="/signals"' in body


@patch("web.services.lectionary_widget_service.TextFetcher")
def test_today_widget_empty_state(mock_fetcher_class, study_client):
    mock_fetcher_class.return_value.fetch_sunday_lectionary_readings.return_value = {}
    client, _ = study_client
    response = client.get("/")
    assert response.status_code == 200
    assert "first signal is on its way" in response.text


@patch("web.services.lectionary_widget_service.TextFetcher")
def test_pages_never_call_claude(mock_fetcher_class, study_client):
    mock_fetcher_class.return_value.fetch_sunday_lectionary_readings.return_value = {}
    client, SessionLocal = study_client
    _seed(SessionLocal, 1)
    with patch("web.services.signal_generator.generate_signal") as gen, \
         patch("lectionary_engines.claude_client.anthropic.Anthropic") as anth:
        client.get("/signals")
        client.get("/")
    gen.assert_not_called()
    anth.assert_not_called()

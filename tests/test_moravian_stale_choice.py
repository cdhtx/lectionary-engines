"""
Route tests for the stale-Moravian-entry choice on POST /generate.

When source=moravian and moravian.org hasn't published today's entry, the
user gets two buttons ("run with <older day>'s text" / "wait for refresh")
instead of a silently stale study. The buttons must appear ONLY in that
case - a current entry, or any other source, runs straight through.
"""

from unittest.mock import MagicMock, patch

from web.models import Study

STALE = {"entry_date": "2026-10-11", "today": "2026-10-12", "is_current": False}
CURRENT = {"entry_date": "2026-10-12", "today": "2026-10-12", "is_current": True}

FORM = {
    "engine": "threshold",
    "source": "moravian",
    "translation": "NRSVue",
    "moravian_context": "What does faith look like on a Monday?",
    "run_validation": "false",
}


def _generator(status):
    gen = MagicMock()
    gen.moravian_status.return_value = status
    gen.fetch_moravian.return_value = ("Psalm 23 | (Moravian text from Sunday, October 11, 2026)", "text")
    gen.generate_study.return_value = {
        "engine": "threshold",
        "reference": "Psalm 23",
        "content": "study content",
        "metadata": {"word_count": 42},
        "biblical_text": "text",
    }
    return gen


@patch("web.routes.studies.extract_themes", return_value=[])
@patch("web.routes.studies.get_generator_service")
def test_stale_entry_shows_choice_instead_of_running(mock_get_generator, _themes, study_client):
    client, SessionLocal = study_client
    gen = _generator(STALE)
    mock_get_generator.return_value = gen

    response = client.post("/generate", data=FORM)

    assert response.status_code == 200
    assert "Sunday, October 11" in response.text
    assert "Monday, October 12" in response.text
    assert "Run with Sunday" in response.text
    assert "Wait for refresh" in response.text
    # The form is carried through so nothing the user typed is lost...
    assert 'name="moravian_context"' in response.text
    assert "What does faith look like on a Monday?" in response.text
    # ...and nothing ran: no fetch, no Claude call, no Study row.
    gen.fetch_moravian.assert_not_called()
    gen.generate_study.assert_not_called()
    db = SessionLocal()
    assert db.query(Study).count() == 0
    db.close()


@patch("web.routes.studies.extract_themes", return_value=[])
@patch("web.routes.studies.get_generator_service")
def test_allow_stale_runs_on_the_older_entry(mock_get_generator, _themes, study_client):
    client, SessionLocal = study_client
    gen = _generator(STALE)
    mock_get_generator.return_value = gen

    response = client.post("/generate", data={**FORM, "allow_stale": "1"})

    assert response.status_code == 200
    assert "Wait for refresh" not in response.text
    gen.fetch_moravian.assert_called_once_with(allow_stale=True)
    db = SessionLocal()
    study = db.query(Study).one()
    assert f"/study/{study.id}" in response.text
    db.close()


@patch("web.routes.studies.extract_themes", return_value=[])
@patch("web.routes.studies.get_generator_service")
def test_current_entry_runs_without_any_choice(mock_get_generator, _themes, study_client):
    client, SessionLocal = study_client
    gen = _generator(CURRENT)
    mock_get_generator.return_value = gen

    response = client.post("/generate", data=FORM)

    assert response.status_code == 200
    assert "Wait for refresh" not in response.text
    assert "Run with" not in response.text
    gen.fetch_moravian.assert_called_once_with(allow_stale=False)
    db = SessionLocal()
    assert db.query(Study).count() == 1
    db.close()


@patch("web.routes.studies.get_generator_service")
def test_other_sources_never_check_moravian(mock_get_generator, study_client):
    client, _ = study_client
    gen = _generator(STALE)
    gen.fetch_text.return_value = "For God so loved the world"
    mock_get_generator.return_value = gen

    with patch("web.routes.studies.extract_themes", return_value=[]):
        response = client.post("/generate", data={
            "engine": "threshold", "source": "run", "reference": "John 3:16",
            "translation": "NRSVue", "run_validation": "false",
        })

    assert "Wait for refresh" not in response.text
    gen.moravian_status.assert_not_called()


@patch("web.routes.studies.get_generator_service")
def test_status_endpoint_reports_whether_entry_is_current(mock_get_generator, study_client):
    client, _ = study_client
    mock_get_generator.return_value = _generator(STALE)
    assert client.get("/api/moravian/status").json() == STALE

    mock_get_generator.return_value = _generator(CURRENT)
    assert client.get("/api/moravian/status").json() == CURRENT

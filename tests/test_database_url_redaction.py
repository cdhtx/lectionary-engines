from web.database import redacted_database_url


def test_password_is_hidden_in_postgres_url(monkeypatch):
    monkeypatch.setattr("web.database.DATABASE_URL", "postgresql+psycopg2://postgres:s3cretpw@db.internal:5432/railway")
    shown = redacted_database_url()
    assert "s3cretpw" not in shown
    assert "db.internal:5432/railway" in shown


def test_sqlite_url_is_unchanged(monkeypatch):
    monkeypatch.setattr("web.database.DATABASE_URL", "sqlite:///./lectionary.db")
    assert redacted_database_url() == "sqlite:///./lectionary.db"

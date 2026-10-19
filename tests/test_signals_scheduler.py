import asyncio
import threading
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from web.models import Base, Signal
from web.services import signals_scheduler
from web.services.signals_scheduler import run_if_due, signal_is_due, signals_enabled, signals_loop

NOW = datetime.utcnow()


@pytest.fixture(autouse=True)
def _reset_backoff():
    signals_scheduler._last_failed_at = None
    yield
    signals_scheduler._last_failed_at = None


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _add_signal(factory, age_hours):
    db = factory()
    db.add(Signal(title="t", theme="x", signal_detected="s", connection="c", nature_of_connection="n",
                  intratextual="i", modern_illustration="m", modern_illustration_category="art",
                  created_at=NOW - timedelta(hours=age_hours)))
    db.commit()
    db.close()


def test_due_when_no_signals(session_factory):
    db = session_factory()
    assert signal_is_due(db, now=NOW) is True


def test_not_due_at_47_hours(session_factory):
    _add_signal(session_factory, 47)
    assert signal_is_due(session_factory(), now=NOW) is False


def test_due_at_49_hours(session_factory):
    _add_signal(session_factory, 49)
    assert signal_is_due(session_factory(), now=NOW) is True


def test_newest_signal_is_what_counts(session_factory):
    _add_signal(session_factory, 100)
    _add_signal(session_factory, 1)
    assert signal_is_due(session_factory(), now=NOW) is False


def test_run_if_due_generates_when_due_and_skips_when_not(session_factory):
    with patch("web.services.signals_scheduler.generate_signal") as gen:
        gen.return_value = object()
        assert run_if_due(session_factory, client_factory=lambda: "client") is True
        assert gen.call_count == 1

    _add_signal(session_factory, 1)
    with patch("web.services.signals_scheduler.generate_signal") as gen:
        assert run_if_due(session_factory, client_factory=lambda: "client") is False
        gen.assert_not_called()


def test_run_if_due_returns_false_when_generation_fails(session_factory):
    with patch("web.services.signals_scheduler.generate_signal", return_value=None):
        assert run_if_due(session_factory, client_factory=lambda: "client") is False


def test_overlapping_checks_generate_only_once(session_factory):
    started = threading.Event()
    release = threading.Event()
    calls = []

    def slow_generate(db, client):
        calls.append(1)
        started.set()
        release.wait(timeout=5)
        return object()

    with patch("web.services.signals_scheduler.generate_signal", side_effect=slow_generate):
        t = threading.Thread(target=run_if_due, args=(session_factory, lambda: "c"))
        t.start()
        assert started.wait(timeout=5)
        second = run_if_due(session_factory, client_factory=lambda: "c")  # lock is held
        release.set()
        t.join(timeout=5)

    assert second is False
    assert len(calls) == 1


def test_signals_enabled_reads_env(monkeypatch):
    monkeypatch.delenv("SIGNALS_ENABLED", raising=False)
    assert signals_enabled() is True
    monkeypatch.setenv("SIGNALS_ENABLED", "false")
    assert signals_enabled() is False
    monkeypatch.setenv("SIGNALS_ENABLED", "TRUE")
    assert signals_enabled() is True


def test_loop_survives_a_failing_check_and_keeps_going():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return False

    async def fake_sleep(_):
        if len(calls) >= 2:
            raise asyncio.CancelledError()

    async def run():
        with patch("web.services.signals_scheduler.run_if_due", side_effect=flaky), \
             patch("web.services.signals_scheduler.asyncio.sleep", side_effect=fake_sleep):
            with pytest.raises(asyncio.CancelledError):
                await signals_loop(interval=0)

    asyncio.run(run())
    assert len(calls) == 2


def test_failed_generation_backs_off_immediate_retry(session_factory):
    with patch("web.services.signals_scheduler.generate_signal", return_value=None) as gen:
        assert run_if_due(session_factory, client_factory=lambda: "c") is False
        assert run_if_due(session_factory, client_factory=lambda: "c") is False
    assert gen.call_count == 1
    assert not signals_scheduler._generation_lock.locked()


def test_generation_retried_after_backoff_elapses(session_factory):
    signals_scheduler._last_failed_at = (
        datetime.utcnow() - signals_scheduler.FAILURE_BACKOFF - timedelta(minutes=1)
    )
    with patch("web.services.signals_scheduler.generate_signal", return_value=object()) as gen:
        assert run_if_due(session_factory, client_factory=lambda: "c") is True
    assert gen.call_count == 1


def test_exception_sets_backoff_and_reraises(session_factory):
    with patch("web.services.signals_scheduler.generate_signal", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            run_if_due(session_factory, client_factory=lambda: "c")
    assert signals_scheduler._last_failed_at is not None
    assert not signals_scheduler._generation_lock.locked()


def test_success_clears_backoff(session_factory):
    signals_scheduler._last_failed_at = (
        datetime.utcnow() - signals_scheduler.FAILURE_BACKOFF - timedelta(minutes=1)
    )
    with patch("web.services.signals_scheduler.generate_signal", return_value=object()):
        run_if_due(session_factory, client_factory=lambda: "c")
    assert signals_scheduler._last_failed_at is None


def test_not_due_does_not_set_backoff(session_factory):
    _add_signal(session_factory, 1)
    with patch("web.services.signals_scheduler.generate_signal") as gen:
        assert run_if_due(session_factory, client_factory=lambda: "c") is False
    gen.assert_not_called()
    assert signals_scheduler._last_failed_at is None

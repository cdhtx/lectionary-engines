"""
Keeps the Signals feed fresh: an hourly check inside the web process asks
the database whether the newest signal is 48+ hours old and generates one
if so. "Is a signal due" is answered from the database, so redeploys and
restarts lose nothing; the next check catches up.
"""

import asyncio
import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from web.database import SessionLocal
from web.models import Signal
from web.services.signal_generator import generate_signal

logger = logging.getLogger(__name__)

SIGNAL_INTERVAL = timedelta(hours=48)
CHECK_INTERVAL_SECONDS = 3600

FAILURE_BACKOFF = timedelta(hours=6)

_generation_lock = threading.Lock()
_last_failed_at: Optional[datetime] = None


def signals_enabled() -> bool:
    return os.getenv("SIGNALS_ENABLED", "true").lower() != "false"


def signal_is_due(db: Session, now: Optional[datetime] = None) -> bool:
    now = now or datetime.utcnow()
    newest = db.query(func.max(Signal.created_at)).scalar()
    return newest is None or now - newest >= SIGNAL_INTERVAL


def _default_client():
    from lectionary_engines.claude_client import ClaudeClient
    from web.config import WebConfig

    return ClaudeClient(WebConfig.load().anthropic_api_key).client


def run_if_due(session_factory=SessionLocal, client_factory: Optional[Callable] = None) -> bool:
    """
    Generate one signal if one is due. Returns True only if a new signal was
    saved. After a failed generation, further attempts wait FAILURE_BACKOFF. If another check is already generating, returns False immediately.
    """
    if not _generation_lock.acquire(blocking=False):
        return False
    global _last_failed_at
    try:
        if _last_failed_at is not None and datetime.utcnow() - _last_failed_at < FAILURE_BACKOFF:
            return False
        db = session_factory()
        try:
            if not signal_is_due(db):
                return False
            client = (client_factory or _default_client)()
            try:
                signal = generate_signal(db, client)
            except Exception:
                _last_failed_at = datetime.utcnow()
                raise
            if signal is None:
                _last_failed_at = datetime.utcnow()
                return False
            _last_failed_at = None
            return True
        finally:
            db.close()
    finally:
        _generation_lock.release()


async def signals_loop(interval: float = CHECK_INTERVAL_SECONDS):
    """Check for a due signal, then sleep. A failed check is logged, never raised."""
    while True:
        try:
            await run_in_threadpool(run_if_due)
        except Exception:
            logger.exception("Signals check failed")
        await asyncio.sleep(interval)

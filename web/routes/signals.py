"""
Signals routes - thematic overlap among this week's lectionary readings
"""

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from lectionary_engines.claude_client import ClaudeClient

from ..config import WebConfig
from ..database import get_db
from ..services.signals_service import get_this_week_signals

router = APIRouter()

WEB_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

config = WebConfig.load()


@router.get("/signals")
async def signals_page(request: Request, db: Session = Depends(get_db)):
    """
    Signals page - shows thematic overlap detected among this week's
    four lectionary readings.
    """
    claude = ClaudeClient(config.anthropic_api_key)
    connections = await run_in_threadpool(get_this_week_signals, db, claude)

    return templates.TemplateResponse("signals.html", {
        "request": request,
        "connections": connections,
    })

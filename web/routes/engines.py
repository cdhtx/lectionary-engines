"""
Engines routes - the static "about the three engines" directory page
"""

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter()

WEB_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


@router.get("/engines")
async def engines_directory(request: Request):
    """
    Engines directory - consolidated reference for all three interpretation
    engines. Fully static: no DB query, no template context beyond `request`.
    """
    return templates.TemplateResponse("engines.html", {"request": request})

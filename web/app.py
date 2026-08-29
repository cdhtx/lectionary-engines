"""
Lectionary Engines Web Application
FastAPI-based web interface for biblical interpretation engines
"""

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.concurrency import run_in_threadpool
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from sqlalchemy import or_
import markdown
import json
from pathlib import Path

from .database import init_db, close_db, get_db
from .routes import studies, profiles, workshop, resonance, currents, engines, signals
from .routes import auth as auth_routes
from .models import Base, Study, User
from .config import WebConfig
from .auth import decode_session_cookie, COOKIE_NAME, PUBLIC_PATHS
from .services.pdf_service import render_pdf, slugify
from .services.palimpsest_layers import parse_palimpsest_layers, RAIL_LABELS
from lectionary_engines.scripture_linker import link_scripture_references

# Load configuration
config = WebConfig.load()

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan - startup and shutdown events
    """
    # Startup: Initialize database
    print("Starting Lectionary Engines Web Application...")
    init_db()
    print(f"API Key configured: {'✓' if config.anthropic_api_key else '✗'}")
    print(f"Default translation: {config.default_translation}")
    print(f"Default engine: {config.default_engine}")
    print(f"Server running at http://{config.web_host}:{config.web_port}")

    yield

    # Shutdown: Close database connections
    print("Shutting down...")
    close_db()


# ── Auth middleware ───────────────────────────────────────────
from contextlib import contextmanager


@contextmanager
def _middleware_db():
    """
    AuthMiddleware runs outside FastAPI's dependency injection (it's raw
    ASGI middleware, not a route with Depends()), so it can't use
    Depends(get_db) directly. Calling SessionLocal() straight from here
    would silently bypass app.dependency_overrides[get_db] - which is
    exactly what every test fixture in this codebase uses to point routes
    at an in-memory test database instead of the real lectionary.db. This
    helper looks up whatever provider is currently active for get_db
    (the test override if one is set, the real get_db otherwise) and
    drives its generator manually, the same way FastAPI's own dependency
    resolution would, including running its cleanup (db.close()) when
    this context manager exits.
    """
    provider = app.dependency_overrides.get(get_db, get_db)
    db_gen = provider()
    db = next(db_gen)
    try:
        yield db
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Always allow: login/logout/static/health/admin (admin has its own Basic Auth)
        if (
            path in PUBLIC_PATHS
            or path.startswith("/static/")
            or path.startswith("/admin/")
        ):
            return await call_next(request)

        token = request.cookies.get(COOKIE_NAME)
        user_id = token and decode_session_cookie(token)
        if not user_id:
            return RedirectResponse(url=f"/login?next={path}", status_code=303)

        # Attach the current user to request.state so base.html's header
        # (rendered on every page) can read request.state.user directly -
        # every route already passes `request` into its template context,
        # so no individual route handler needs to change. Tasks 5 and 6
        # add more request.state attachments inside this same `with`
        # block (reusing the one db session for the whole request rather
        # than opening several) - do not close this block off here in a
        # way that later tasks can't extend.
        with _middleware_db() as db:
            request.state.user = db.query(User).filter(User.id == user_id, User.is_active == True).first()

        return await call_next(request)


# Create FastAPI application
app = FastAPI(
    title="Lectionary Engines",
    description="Biblical interpretation through three hermeneutical frameworks",
    version="0.1.0",
    lifespan=lifespan
)

# Get the web directory path
WEB_DIR = Path(__file__).parent

# Attach auth middleware
app.add_middleware(AuthMiddleware)

# Mount static files
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

# Set up Jinja2 templates
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

# Include API routers
app.include_router(auth_routes.router, tags=["auth"])
app.include_router(studies.router, tags=["studies"])
app.include_router(profiles.router, tags=["profiles"])
app.include_router(workshop.router, tags=["workshop"])
app.include_router(resonance.router, tags=["resonance"])
app.include_router(currents.router, tags=["currents"])
app.include_router(engines.router, tags=["engines"])
app.include_router(signals.router, tags=["signals"])


# ============================================================================
# HTML Page Routes (Server-Rendered)
# ============================================================================

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    """
    Today homepage - This Week in the Lectionary, Signals, engine cards,
    quick actions, and recent studies
    """
    from lectionary_engines.claude_client import ClaudeClient
    from .services.lectionary_widget_service import get_this_week_readings
    from .services.signals_service import get_this_week_signals

    # Get recent studies (last 5)
    recent_studies = db.query(Study).order_by(Study.created_at.desc()).limit(5).all()

    this_week = get_this_week_readings(db)

    claude = ClaudeClient(config.anthropic_api_key)
    signals = get_this_week_signals(db, claude)[:3]  # top 3 for the compact widget; full list on /signals

    return templates.TemplateResponse("index.html", {
        "request": request,
        "recent_studies": recent_studies,
        "this_week": this_week,
        "signals": signals,
        "config": config
    })


@app.get("/profiles", response_class=HTMLResponse)
async def profiles_page(request: Request, db: Session = Depends(get_db)):
    """Profiles management page"""
    from .models import UserProfile
    profiles = db.query(UserProfile).order_by(
        UserProfile.is_default.desc(),
        UserProfile.name.asc()
    ).all()
    return templates.TemplateResponse("profiles.html", {
        "request": request,
        "profiles": profiles
    })


@app.get("/generate", response_class=HTMLResponse)
async def generate_page(request: Request):
    """
    Study generation page - shows form for generating new study
    """
    return templates.TemplateResponse("generate.html", {
        "request": request,
        "engines": ["threshold", "palimpsest", "collision"],
        "translations": ["NRSVue", "NIV", "CEB", "NLT", "MSG"],
        "default_translation": config.default_translation,
        "default_engine": config.default_engine
    })


@app.get("/study/{study_id}", response_class=HTMLResponse)
async def view_study(request: Request, study_id: int, db: Session = Depends(get_db)):
    """
    Study view page - displays a single study with beautiful formatting
    """
    study = db.query(Study).filter(Study.id == study_id).first()

    if not study:
        return templates.TemplateResponse("404.html", {
            "request": request,
            "message": "Study not found"
        }, status_code=404)

    # Convert markdown to HTML, linking scripture references to Bible Gateway
    # first so they render as normal markdown links.
    linked_content = link_scripture_references(study.content, study.translation)

    parsed_layers = None
    if study.engine == "palimpsest":
        parsed_layers = parse_palimpsest_layers(linked_content)

    palimpsest_rail = None
    if parsed_layers:
        md = markdown.Markdown(extensions=['extra', 'nl2br', 'sane_lists'])
        html_parts = [md.convert(parsed_layers["intro_markdown"])]
        for layer in parsed_layers["layers"]:
            md.reset()
            layer_html = md.convert(layer["markdown"])
            html_parts.append(
                f'<section id="layer-{layer["key"]}" class="palimpsest-layer">{layer_html}</section>'
            )
        study_html = "".join(html_parts)
        palimpsest_rail = RAIL_LABELS
    else:
        md = markdown.Markdown(extensions=[
            'extra',          # Tables, footnotes, etc.
            'nl2br',          # Newline to <br>
            'sane_lists',     # Better list handling
        ])
        study_html = md.convert(linked_content)

    # Parse validation data if present
    validation = None
    if study.validation_data:
        try:
            validation_dict = json.loads(study.validation_data)
            # Convert nested dicts to objects for easier template access
            validation = type('Validation', (), {
                'overall_score': validation_dict.get('overall_score', 0),
                'recommendation': validation_dict.get('recommendation', 'review'),
                'vibe': validation_dict.get('vibe', ''),
                'accuracy': type('Accuracy', (), validation_dict.get('accuracy', {}))(),
                'helpfulness': type('Helpfulness', (), validation_dict.get('helpfulness', {}))(),
                'faithfulness': type('Faithfulness', (), validation_dict.get('faithfulness', {}))(),
                'flags': validation_dict.get('flags', []),
                'summary': validation_dict.get('summary', '')
            })()
        except (json.JSONDecodeError, TypeError):
            validation = None

    return templates.TemplateResponse("study.html", {
        "request": request,
        "study": study,
        "study_html": study_html,
        "palimpsest_rail": palimpsest_rail,
        "validation": validation
    })


@app.get("/study/{study_id}/pdf")
async def download_study_pdf(request: Request, study_id: int, db: Session = Depends(get_db)):
    """
    Download a study as a PDF
    """
    study = db.query(Study).filter(Study.id == study_id).first()

    if not study:
        return templates.TemplateResponse("404.html", {
            "request": request,
            "message": "Study not found"
        }, status_code=404)

    linked_content = link_scripture_references(study.content, study.translation)
    md = markdown.Markdown(extensions=['extra', 'nl2br', 'sane_lists'])
    study_html = md.convert(linked_content)

    meta_parts = [study.engine.title(), study.created_at.strftime('%B %d, %Y')]
    if study.word_count:
        meta_parts.append(f"{study.word_count} words")
    if study.translation:
        meta_parts.append(study.translation)

    # PDF generation is synchronous CPU work (reportlab) - run off the
    # event loop like every other potentially-slow call in this app.
    pdf_bytes = await run_in_threadpool(
        render_pdf,
        title=study.reference,
        meta_line=" · ".join(meta_parts),
        content_html=study_html,
        source_url=str(request.url).replace("/pdf", ""),
    )

    filename = f"{slugify(study.reference)}-{study.engine}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/browse", response_class=HTMLResponse)
async def browse_studies(
    request: Request,
    page: int = 1,
    type: str = None,
    q: str = None,
    theme: str = None,
    season: str = None,
    source: str = None,
    db: Session = Depends(get_db)
):
    """
    Library page - unified browse across studies, workshop preps,
    currents analyses, and resonance results, with content_type/theme/
    season/source faceting
    """
    from .services.library_service import search_library, get_library_facets

    search_term = q.strip() if q and q.strip() else None
    # search_library() matches theme/season/source with an exact,
    # case-sensitive comparison against lowercase-stored values (see its
    # docstring) - normalize here so a hand-typed or shared URL like
    # ?theme=Hospitality still matches instead of silently returning zero
    # results. Stored season/source values (season_for_date(), Study.source)
    # are already lowercase, so lowercasing here is safe and matches.
    theme = theme.strip().lower() if theme else None
    season = season.strip().lower() if season else None
    source = source.strip().lower() if source else None
    result = search_library(
        db, content_type=type, q=search_term, theme=theme, season=season, source=source,
        page=page, per_page=config.studies_per_page,
    )
    facets = get_library_facets(db)

    return templates.TemplateResponse("browse.html", {
        "request": request,
        "results": result["results"],
        "page": result["page"],
        "total_pages": result["total_pages"],
        "has_prev": result["has_prev"],
        "has_next": result["has_next"],
        "total": result["total"],
        "type_filter": type,
        "search_query": search_term or "",
        "theme_filter": theme,
        "season_filter": season,
        "source_filter": source,
        "facets": facets,
    })


@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint
    """
    from .database import DATABASE_URL
    study_count = db.query(Study).count()
    db_type = "postgres" if "postgresql" in DATABASE_URL else "sqlite"
    db_hint = DATABASE_URL[:30] + "..." if len(DATABASE_URL) > 30 else DATABASE_URL
    return {
        "status": "healthy",
        "api_key_configured": bool(config.anthropic_api_key),
        "database_type": db_type,
        "database_url_prefix": db_hint,
        "study_count": study_count,
    }


# Run the application
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "web.app:app",
        host=config.web_host,
        port=config.web_port,
        reload=True
    )

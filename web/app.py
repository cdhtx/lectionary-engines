"""
Lectionary Engines Web Application
FastAPI-based web interface for biblical interpretation engines
"""

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
import markdown
import json
from pathlib import Path

from .database import init_db, close_db, get_db
from .routes import studies, profiles, workshop, resonance, currents
from .routes import auth as auth_routes
from .models import Study
from .config import WebConfig
from .auth import decode_session_cookie, COOKIE_NAME, PUBLIC_PATHS

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
        if not token or not decode_session_cookie(token):
            return RedirectResponse(url=f"/login?next={path}", status_code=303)

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


# ============================================================================
# HTML Page Routes (Server-Rendered)
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    """
    Home page - shows welcome message and recent studies
    """
    # Get recent studies (last 5)
    recent_studies = db.query(Study).order_by(Study.created_at.desc()).limit(5).all()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "recent_studies": recent_studies,
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

    # Convert markdown to HTML
    md = markdown.Markdown(extensions=[
        'extra',          # Tables, footnotes, etc.
        'nl2br',          # Newline to <br>
        'sane_lists',     # Better list handling
    ])
    study_html = md.convert(study.content)

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
        "validation": validation
    })


@app.get("/browse", response_class=HTMLResponse)
async def browse_studies(
    request: Request,
    page: int = 1,
    engine: str = None,
    source: str = None,
    db: Session = Depends(get_db)
):
    """
    Browse studies page - lists all studies with filtering
    """
    # Calculate pagination
    per_page = config.studies_per_page
    skip = (page - 1) * per_page

    # Build query
    query = db.query(Study)

    # Apply filters
    if engine:
        query = query.filter(Study.engine == engine)
    if source:
        query = query.filter(Study.source == source)

    # Order by most recent first
    query = query.order_by(Study.created_at.desc())

    # Get total count before pagination
    total = query.count()

    # Get studies for this page
    studies_list = query.offset(skip).limit(per_page).all()

    # Calculate pagination info
    total_pages = (total + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages

    return templates.TemplateResponse("browse.html", {
        "request": request,
        "studies": studies_list,
        "page": page,
        "total_pages": total_pages,
        "has_prev": has_prev,
        "has_next": has_next,
        "total": total,
        "engine_filter": engine,
        "source_filter": source
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

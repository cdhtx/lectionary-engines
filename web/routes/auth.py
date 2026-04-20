"""
Auth routes: login, logout, admin user management.
"""

import os
import secrets
from pathlib import Path

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..auth import (
    hash_password,
    verify_password,
    create_session_cookie,
    COOKIE_NAME,
    COOKIE_MAX_AGE,
    require_login,
)

router = APIRouter()

WEB_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

# HTTP Basic for admin panel
security = HTTPBasic()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")


def _check_admin(credentials: HTTPBasicCredentials = Depends(security)):
    ok = (
        credentials.username == "admin"
        and secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    )
    if not ok:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# ── Login ────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "next": next,
        "error": None,
    })


@router.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "next": next,
            "error": "Invalid email or password.",
        })

    token = create_session_cookie(user.id)
    response = RedirectResponse(url=next or "/", status_code=303)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=os.getenv("RAILWAY_ENVIRONMENT") is not None or os.getenv("RENDER") is not None,
    )
    return response


# ── Logout ───────────────────────────────────────────────────

@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


# ── Admin: user management ───────────────────────────────────

@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    db: Session = Depends(get_db),
    _admin: str = Depends(_check_admin),
    message: str = None,
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "users": users,
        "message": message,
    })


@router.post("/admin/users/create", response_class=HTMLResponse)
async def admin_create_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
    _admin: str = Depends(_check_admin),
):
    email = email.lower().strip()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        users = db.query(User).order_by(User.created_at.desc()).all()
        return templates.TemplateResponse("admin_users.html", {
            "request": request,
            "users": users,
            "error": f"A user with email {email} already exists.",
        })

    user = User(
        email=email,
        name=name.strip(),
        password_hash=hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.commit()

    return RedirectResponse(
        url=f"/admin/users?message=User+{name}+created+successfully",
        status_code=303,
    )


@router.post("/admin/users/{user_id}/toggle")
async def admin_toggle_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: str = Depends(_check_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.is_active = not user.is_active
        db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/reset-password")
async def admin_reset_password(
    user_id: int,
    new_password: str = Form(...),
    db: Session = Depends(get_db),
    _admin: str = Depends(_check_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.password_hash = hash_password(new_password)
        db.commit()
    return RedirectResponse(url="/admin/users?message=Password+reset", status_code=303)


@router.post("/admin/users/{user_id}/delete")
async def admin_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: str = Depends(_check_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        db.delete(user)
        db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

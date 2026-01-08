"""
Database setup and session management for Lectionary Engines web app
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator

from .models import Base

# Database URL from environment or default to SQLite file
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./lectionary.db")

# Create engine
# For SQLite, we need check_same_thread=False to work with FastAPI
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False  # Set to True for SQL query logging during development
    )
else:
    engine = create_engine(DATABASE_URL, echo=False)

# Create session maker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """
    Initialize database - create all tables
    Call this when the application starts
    """
    Base.metadata.create_all(bind=engine)
    print(f"Database initialized at {DATABASE_URL}")


def close_db():
    """
    Close database connections
    Call this when the application shuts down
    """
    engine.dispose()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for database sessions

    Usage:
        with get_db_context() as db:
            study = db.query(Study).first()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI routes

    Usage:
        @app.get("/studies/{id}")
        def get_study(id: int, db: Session = Depends(get_db)):
            return db.query(Study).filter(Study.id == id).first()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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
    Initialize database - create all tables and add any missing columns.
    Call this when the application starts.
    """
    Base.metadata.create_all(bind=engine)

    # Add any missing columns that may not exist in older DB schemas
    if DATABASE_URL.startswith("sqlite"):
        import sqlite3
        db_path = DATABASE_URL.replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        def add_column_if_missing(table, column, col_type):
            cursor.execute(f"PRAGMA table_info({table})")
            cols = {row[1] for row in cursor.fetchall()}
            if column not in cols:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                print(f"  Migrated: added {table}.{column}")

        # Studies table migrations
        for col, typ in [
            ("news_integrated", "BOOLEAN DEFAULT 0"),
            ("news_context", "TEXT"),
            ("news_date", "VARCHAR(100)"),
            ("validation_score", "INTEGER"),
            ("validation_recommendation", "VARCHAR(50)"),
            ("validation_data", "TEXT"),
            ("profile_name", "VARCHAR(200)"),
            ("custom_preferences", "TEXT"),
            ("biblical_text", "TEXT"),
        ]:
            add_column_if_missing("studies", col, typ)

        conn.commit()
        conn.close()

        # Users table migrations (new columns only — table created by create_all above)
        cursor.execute("PRAGMA table_info(users)")
        if cursor.fetchall():  # table exists
            for col, typ in [
                ("is_active", "BOOLEAN DEFAULT 1"),
            ]:
                add_column_if_missing("users", col, typ)

        conn.commit()
        conn.close()

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

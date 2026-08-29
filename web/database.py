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
# Railway provides postgres:// URLs; SQLAlchemy 2.0 requires postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

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


# Columns that may be missing on older DB schemas (added after a table was
# first created). Applied on every startup for both SQLite (dev) and
# Postgres (Railway production) - see _migrate_missing_columns().
#
# sqlite_type / postgres_type differ only where boolean default literals
# differ (SQLite: 0/1, Postgres: FALSE/TRUE); everything else is identical
# DDL syntax on both backends.
COLUMN_MIGRATIONS = [
    # (table, column, sqlite_type, postgres_type)
    ("studies", "news_integrated", "BOOLEAN DEFAULT 0", "BOOLEAN DEFAULT FALSE"),
    ("studies", "news_context", "TEXT", "TEXT"),
    ("studies", "news_date", "VARCHAR(100)", "VARCHAR(100)"),
    ("studies", "validation_score", "INTEGER", "INTEGER"),
    ("studies", "validation_recommendation", "VARCHAR(50)", "VARCHAR(50)"),
    ("studies", "validation_data", "TEXT", "TEXT"),
    ("studies", "profile_name", "VARCHAR(200)", "VARCHAR(200)"),
    ("studies", "custom_preferences", "TEXT", "TEXT"),
    ("studies", "biblical_text", "TEXT", "TEXT"),
    ("user_profiles", "cultural_artifacts_level", "INTEGER DEFAULT 0", "INTEGER DEFAULT 0"),
    ("user_profiles", "auto_news_integration", "BOOLEAN DEFAULT 0", "BOOLEAN DEFAULT FALSE"),
    ("users", "is_active", "BOOLEAN DEFAULT 1", "BOOLEAN DEFAULT TRUE"),
    ("studies", "reading_date", "DATE", "DATE"),
    ("studies", "season", "VARCHAR(30)", "VARCHAR(30)"),
    ("workshop_preps", "reading_date", "DATE", "DATE"),
    ("workshop_preps", "season", "VARCHAR(30)", "VARCHAR(30)"),
]


def _migrate_missing_columns():
    """
    Add any columns listed in COLUMN_MIGRATIONS that don't exist yet.

    Base.metadata.create_all() only creates missing *tables* - it never
    alters a table that already exists, on either backend. Without this,
    a new model column only ever reaches a fresh SQLite file; an existing
    Railway/Postgres database would keep the old schema forever and error
    the first time the app touched the new column.

    Also creates indexes for newly-indexed columns on existing databases,
    since ALTER TABLE ADD COLUMN does not automatically create indexes.
    """
    if DATABASE_URL.startswith("sqlite"):
        import sqlite3
        db_path = DATABASE_URL.replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        tables = {t for t, _, _, _ in COLUMN_MIGRATIONS}
        existing_cols = {}
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            existing_cols[table] = {row[1] for row in cursor.fetchall()}

        for table, column, sqlite_type, _ in COLUMN_MIGRATIONS:
            if column not in existing_cols[table]:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sqlite_type}")
                print(f"  Migrated: added {table}.{column}")

        # Create indexes for newly-indexed columns on existing databases
        # (ALTER TABLE ADD COLUMN does not create indexes automatically)
        index_migrations = [
            ("idx_studies_reading_date", "studies", "reading_date"),
            ("idx_studies_season", "studies", "season"),
            ("idx_workshop_preps_reading_date", "workshop_preps", "reading_date"),
            ("idx_workshop_preps_season", "workshop_preps", "season"),
        ]
        for index_name, table, column in index_migrations:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table}({column})")

        conn.commit()
        conn.close()

    else:
        # Postgres supports IF NOT EXISTS on ADD COLUMN natively (9.6+),
        # so this is safe to run unconditionally on every startup.
        with engine.begin() as conn:
            for table, column, _, postgres_type in COLUMN_MIGRATIONS:
                conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {postgres_type}"
                )

            # Create indexes for newly-indexed columns on existing databases
            # (ALTER TABLE ADD COLUMN does not create indexes automatically)
            index_migrations = [
                ("idx_studies_reading_date", "studies", "reading_date"),
                ("idx_studies_season", "studies", "season"),
                ("idx_workshop_preps_reading_date", "workshop_preps", "reading_date"),
                ("idx_workshop_preps_season", "workshop_preps", "season"),
            ]
            for index_name, table, column in index_migrations:
                conn.exec_driver_sql(
                    f"CREATE INDEX IF NOT EXISTS {index_name} ON {table}({column})"
                )

        print("  Migrated: verified Postgres columns and indexes are up to date")


def init_db():
    """
    Initialize database - create all tables and add any missing columns.
    Call this when the application starts.
    """
    Base.metadata.create_all(bind=engine)
    _migrate_missing_columns()

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

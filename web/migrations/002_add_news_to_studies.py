"""
Migration 002: Add news integration columns to studies table
and create currents_analyses table.

Run: python -m web.migrations.002_add_news_to_studies
"""

import sqlite3
import os


def migrate():
    db_path = os.getenv("DATABASE_PATH", "./lectionary.db")

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}. Skipping migration (tables will be created on startup).")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check which columns already exist
    cursor.execute("PRAGMA table_info(studies)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    # Add news integration columns to studies
    new_columns = [
        ("news_integrated", "BOOLEAN DEFAULT 0"),
        ("news_context", "TEXT"),
        ("news_date", "VARCHAR(100)"),
    ]

    for col_name, col_type in new_columns:
        if col_name not in existing_columns:
            cursor.execute(f"ALTER TABLE studies ADD COLUMN {col_name} {col_type}")
            print(f"  Added column: studies.{col_name}")
        else:
            print(f"  Column already exists: studies.{col_name}")

    # Create currents_analyses table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS currents_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_date VARCHAR(100) NOT NULL,
            news_source VARCHAR(200),
            headline_summary VARCHAR(300),
            story_context TEXT,
            content TEXT NOT NULL,
            word_count INTEGER,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_currents_date ON currents_analyses (analysis_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_currents_created ON currents_analyses (created_at)")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()
    print("Migration 002 complete.")


if __name__ == "__main__":
    migrate()

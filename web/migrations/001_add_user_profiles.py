#!/usr/bin/env python3
"""
Database Migration: Add User Profiles

This migration adds the user_profiles table and profile tracking to studies table.

Run this migration: python3 web/migrations/001_add_user_profiles.py
"""

import sys
from pathlib import Path
import sqlite3
from datetime import datetime

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from web.config import WebConfig


def upgrade():
    """Apply the migration"""
    config = WebConfig.load()
    db_path = config.database_url.replace('sqlite:///', '')

    print(f"Applying migration 001_add_user_profiles to {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 1. Create user_profiles table
        print("Creating user_profiles table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL UNIQUE,
                description TEXT,
                study_length VARCHAR(20) DEFAULT 'medium' NOT NULL,
                tone_level INTEGER DEFAULT 5 NOT NULL,
                language_complexity VARCHAR(20) DEFAULT 'standard' NOT NULL,
                focus_areas TEXT,
                is_default BOOLEAN DEFAULT 0 NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create indexes for user_profiles
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_is_default ON user_profiles(is_default)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_profile_name ON user_profiles(name)')

        # 2. Add profile tracking columns to studies table
        print("Adding profile tracking columns to studies table...")

        # Check if columns already exist (in case migration is re-run)
        cursor.execute("PRAGMA table_info(studies)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'profile_name' not in columns:
            cursor.execute('ALTER TABLE studies ADD COLUMN profile_name VARCHAR(100)')
            print("  ✓ Added profile_name column")
        else:
            print("  - profile_name column already exists")

        if 'custom_preferences' not in columns:
            cursor.execute('ALTER TABLE studies ADD COLUMN custom_preferences TEXT')
            print("  ✓ Added custom_preferences column")
        else:
            print("  - custom_preferences column already exists")

        # 3. Insert default profiles
        print("Inserting default profiles...")

        default_profiles = [
            {
                'name': 'Default',
                'description': 'Balanced study with moderate depth',
                'study_length': 'medium',
                'tone_level': 5,
                'language_complexity': 'standard',
                'focus_areas': None,
                'is_default': True,
            },
            {
                'name': 'Seminary Student',
                'description': 'Academic depth with technical language',
                'study_length': 'long',
                'tone_level': 2,
                'language_complexity': 'advanced',
                'focus_areas': 'exegesis, historical context, theological implications',
                'is_default': False,
            },
            {
                'name': 'Daily Devotional',
                'description': 'Brief, personal, application-focused',
                'study_length': 'short',
                'tone_level': 7,
                'language_complexity': 'accessible',
                'focus_areas': 'personal growth, spiritual formation, daily application',
                'is_default': False,
            },
            {
                'name': 'Small Group Leader',
                'description': 'Balanced depth with discussion prompts',
                'study_length': 'medium',
                'tone_level': 6,
                'language_complexity': 'standard',
                'focus_areas': 'group discussion, practical application, community',
                'is_default': False,
            },
            {
                'name': 'Scholar',
                'description': 'Maximum depth, technical analysis',
                'study_length': 'long',
                'tone_level': 0,
                'language_complexity': 'advanced',
                'focus_areas': 'textual criticism, intertextuality, theological development',
                'is_default': False,
            },
        ]

        for profile in default_profiles:
            # Check if profile already exists
            cursor.execute('SELECT id FROM user_profiles WHERE name = ?', (profile['name'],))
            existing = cursor.fetchone()

            if existing:
                print(f"  - Profile '{profile['name']}' already exists")
            else:
                now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute('''
                    INSERT INTO user_profiles
                    (name, description, study_length, tone_level, language_complexity, focus_areas, is_default, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    profile['name'],
                    profile['description'],
                    profile['study_length'],
                    profile['tone_level'],
                    profile['language_complexity'],
                    profile['focus_areas'],
                    profile['is_default'],
                    now,
                    now,
                ))
                print(f"  ✓ Created profile '{profile['name']}'")

        # Commit changes
        conn.commit()
        print("\n✓ Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"\n✗ Migration failed: {e}")
        raise

    finally:
        conn.close()


def downgrade():
    """Reverse the migration"""
    config = WebConfig.load()
    db_path = config.database_url.replace('sqlite:///', '')

    print(f"Reversing migration 001_add_user_profiles from {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Drop user_profiles table
        print("Dropping user_profiles table...")
        cursor.execute('DROP TABLE IF EXISTS user_profiles')

        # Note: SQLite doesn't support DROP COLUMN, so we can't easily remove
        # the profile tracking columns from studies. They will remain but unused.
        print("Note: profile_name and custom_preferences columns remain in studies table")
        print("      (SQLite does not support DROP COLUMN)")

        conn.commit()
        print("\n✓ Migration reversed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"\n✗ Migration reversal failed: {e}")
        raise

    finally:
        conn.close()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='User Profiles Migration')
    parser.add_argument('--down', action='store_true', help='Reverse the migration')
    args = parser.parse_args()

    if args.down:
        downgrade()
    else:
        upgrade()

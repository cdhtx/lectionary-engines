"""
Database ORM models for Lectionary Engines web app
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Study(Base):
    """Study model - stores generated biblical interpretation studies"""

    __tablename__ = "studies"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Core study data
    engine = Column(String(50), nullable=False)  # 'threshold', 'palimpsest', 'collision'
    reference = Column(String(255), nullable=False)  # 'John 3:16-21'
    content = Column(Text, nullable=False)  # Full markdown content
    word_count = Column(Integer)

    # Metadata
    source = Column(String(50))  # 'paste', 'run', 'moravian', 'rcl'
    translation = Column(String(20))  # 'NRSVue', 'NIV', 'CEB', 'NLT', 'MSG'
    biblical_text = Column(Text)  # Original biblical text used

    # User preferences tracking
    profile_name = Column(String(100))  # Which profile was used (if any)
    custom_preferences = Column(Text)  # JSON blob of per-study overrides (if any)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # File sync (optional)
    file_path = Column(String(500))  # Path to markdown file if exists
    file_synced = Column(Boolean, default=False)

    # Search optimization
    reference_normalized = Column(String(255))  # Lowercase for search

    # Indexes
    __table_args__ = (
        Index('idx_engine', 'engine'),
        Index('idx_reference', 'reference'),
        Index('idx_created', 'created_at'),
        Index('idx_source', 'source'),
    )

    def __repr__(self):
        return f"<Study(id={self.id}, engine='{self.engine}', reference='{self.reference}')>"

    def to_dict(self):
        """Convert study to dictionary"""
        return {
            'id': self.id,
            'engine': self.engine,
            'reference': self.reference,
            'content': self.content,
            'word_count': self.word_count,
            'source': self.source,
            'translation': self.translation,
            'biblical_text': self.biblical_text,
            'profile_name': self.profile_name,
            'custom_preferences': self.custom_preferences,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'file_path': self.file_path,
            'file_synced': self.file_synced,
        }


class UserProfile(Base):
    """User Profile model - stores user preference profiles"""

    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Profile identity
    name = Column(String(100), nullable=False, unique=True)  # 'Default', 'Seminary Student', etc.
    description = Column(Text)  # User's description of the profile

    # Preferences
    study_length = Column(String(20), default='medium', nullable=False)  # 'short', 'medium', 'long'
    tone_level = Column(Integer, default=5, nullable=False)  # 0-8 scale (0=academic, 8=devotional)
    language_complexity = Column(String(20), default='standard', nullable=False)  # 'accessible', 'standard', 'advanced'
    focus_areas = Column(Text)  # Free text, user-specified (nullable)

    # Metadata
    is_default = Column(Boolean, default=False, nullable=False)  # Only one profile can be default

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index('idx_is_default', 'is_default'),
        Index('idx_profile_name', 'name'),
    )

    def __repr__(self):
        return f"<UserProfile(id={self.id}, name='{self.name}', length='{self.study_length}', tone={self.tone_level})>"

    def to_dict(self):
        """Convert profile to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'study_length': self.study_length,
            'tone_level': self.tone_level,
            'language_complexity': self.language_complexity,
            'focus_areas': self.focus_areas,
            'is_default': self.is_default,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_study_preferences(self):
        """Convert UserProfile to StudyPreferences dataclass"""
        from lectionary_engines.preferences import StudyPreferences
        return StudyPreferences(
            study_length=self.study_length,
            tone_level=self.tone_level,
            language_complexity=self.language_complexity,
            focus_areas=self.focus_areas,
        )

"""
Database ORM models for Lectionary Engines web app
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Index, Date, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class User(Base):
    """User model — controls who can access the app"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_user_email', 'email'),
    )

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', active={self.is_active})>"


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

    # News integration
    news_integrated = Column(Boolean, default=False)
    news_context = Column(Text)  # News story text if news was integrated
    news_date = Column(String(100))  # Date of news event

    # Validation results
    validation_score = Column(Integer)  # Overall score 0-100 (null if not validated)
    validation_recommendation = Column(String(20))  # 'approve', 'review', 'revise'
    validation_data = Column(Text)  # Full validation JSON (for detailed display)

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
            'news_integrated': self.news_integrated,
            'news_context': self.news_context,
            'news_date': self.news_date,
            'validation_score': self.validation_score,
            'validation_recommendation': self.validation_recommendation,
            'validation_data': self.validation_data,
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
    cultural_artifacts_level = Column(Integer, default=0, nullable=False)  # 0-10 scale (0=off, 10=maximum)
    auto_news_integration = Column(Boolean, default=False, nullable=False)  # auto-select a headline instead of requiring manual paste

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
            'cultural_artifacts_level': self.cultural_artifacts_level,
            'auto_news_integration': self.auto_news_integration,
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
            cultural_artifacts_level=self.cultural_artifacts_level,
        )


class WorkshopPrep(Base):
    """Workshop Prep model - stores sermon preparation scaffolding"""

    __tablename__ = "workshop_preps"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Core prep data
    lens = Column(String(50), nullable=False)  # 'apostolic_journalist', etc.
    lens_name = Column(String(100), nullable=False)  # 'The Apostolic Journalist'
    reference = Column(String(255), nullable=False)  # 'John 3:16-21'
    content = Column(Text, nullable=False)  # Full markdown content
    word_count = Column(Integer)

    # Metadata
    source = Column(String(50))  # 'paste', 'run', 'moravian', 'rcl'
    translation = Column(String(20))  # 'NRSVue', 'NIV', etc.
    biblical_text = Column(Text)  # Original biblical text used

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index('idx_workshop_lens', 'lens'),
        Index('idx_workshop_reference', 'reference'),
        Index('idx_workshop_created', 'created_at'),
    )

    def __repr__(self):
        return f"<WorkshopPrep(id={self.id}, lens='{self.lens}', reference='{self.reference}')>"

    def to_dict(self):
        """Convert prep to dictionary"""
        return {
            'id': self.id,
            'lens': self.lens,
            'lens_name': self.lens_name,
            'reference': self.reference,
            'content': self.content,
            'word_count': self.word_count,
            'source': self.source,
            'translation': self.translation,
            'biblical_text': self.biblical_text,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class CulturalSource(Base):
    """Cultural Source model - registry of sources for cultural artifacts"""

    __tablename__ = "cultural_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Source identity
    name = Column(String(100), nullable=False, unique=True)  # "Genius Lyrics API"
    description = Column(Text)  # What this source provides
    category = Column(String(50), nullable=False)  # music, film, tv, news, icon, tech, toy, fad
    source_type = Column(String(50), nullable=False)  # api, archive, feed, database, curated_list

    # Access configuration
    url = Column(String(500), nullable=False)  # Base URL or API endpoint
    query_method = Column(String(50), nullable=False)  # api_call, web_fetch, scrape, manual
    adapter_class = Column(String(100))  # Python class name for adapter
    output_format = Column(String(50))  # json, html, text

    # Era and theme coverage
    era_start = Column(Integer, default=1977)  # Start year
    era_end = Column(Integer, default=1999)  # End year
    themes_strength = Column(Text)  # JSON: what themes this source is good for

    # Authentication
    requires_auth = Column(Boolean, default=False)
    api_key_env_var = Column(String(100))  # Environment variable name for API key

    # Quality and status
    quality_rating = Column(Integer, default=3)  # 1-5
    usage_notes = Column(Text)  # How to best use this source
    active = Column(Boolean, default=True)
    last_verified = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index('idx_source_category', 'category'),
        Index('idx_source_active', 'active'),
    )

    def __repr__(self):
        return f"<CulturalSource(id={self.id}, name='{self.name}', category='{self.category}')>"

    def to_dict(self):
        import json
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'source_type': self.source_type,
            'url': self.url,
            'query_method': self.query_method,
            'adapter_class': self.adapter_class,
            'era_start': self.era_start,
            'era_end': self.era_end,
            'themes_strength': json.loads(self.themes_strength) if self.themes_strength else [],
            'quality_rating': self.quality_rating,
            'active': self.active,
        }


class CulturalResonance(Base):
    """Cultural Resonance model - stores generated cultural connections"""

    __tablename__ = "cultural_resonances"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Link to source study (optional)
    study_id = Column(Integer, nullable=True)  # FK to studies table
    workshop_id = Column(Integer, nullable=True)  # FK to workshop_preps table

    # Input
    themes = Column(Text, nullable=False)  # JSON array of themes searched
    reference = Column(String(255))  # Biblical reference if applicable

    # Output
    content = Column(Text, nullable=False)  # Generated resonance content (markdown)
    artifacts_found = Column(Integer)  # Number of artifacts surfaced
    sources_used = Column(Text)  # JSON array of source names used

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Indexes
    __table_args__ = (
        Index('idx_resonance_created', 'created_at'),
    )

    def __repr__(self):
        return f"<CulturalResonance(id={self.id}, themes='{self.themes[:50]}...')>"

    def to_dict(self):
        import json
        return {
            'id': self.id,
            'study_id': self.study_id,
            'workshop_id': self.workshop_id,
            'themes': json.loads(self.themes) if self.themes else [],
            'reference': self.reference,
            'content': self.content,
            'artifacts_found': self.artifacts_found,
            'sources_used': json.loads(self.sources_used) if self.sources_used else [],
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class CurrentsAnalysis(Base):
    """Currents Analysis model - stores theological news analyses"""

    __tablename__ = "currents_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Core data
    analysis_date = Column(String(100), nullable=False)
    news_source = Column(String(200))
    headline_summary = Column(String(300))
    story_context = Column(Text)
    content = Column(Text, nullable=False)
    word_count = Column(Integer)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Indexes
    __table_args__ = (
        Index('idx_currents_date', 'analysis_date'),
        Index('idx_currents_created', 'created_at'),
    )

    def __repr__(self):
        return f"<CurrentsAnalysis(id={self.id}, date='{self.analysis_date}')>"

    def to_dict(self):
        return {
            'id': self.id,
            'analysis_date': self.analysis_date,
            'news_source': self.news_source,
            'headline_summary': self.headline_summary,
            'story_context': self.story_context,
            'content': self.content,
            'word_count': self.word_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class CollisionVectorState(Base):
    """
    Persists the Collision engine's no-repeat vector sampler bags.

    Stored in the DB rather than local disk because the app filesystem is
    ephemeral on Railway/Render (wiped on every redeploy and container
    restart) - only the DB survives across those.
    """

    __tablename__ = "collision_vector_state"

    category = Column(String(50), primary_key=True)  # 'scientific', 'cultural', etc.
    remaining_bag = Column(Text, nullable=False)  # JSON list of not-yet-drawn vectors

    def __repr__(self):
        return f"<CollisionVectorState(category='{self.category}')>"


class LectionaryReadingCache(Base):
    """
    Caches the upcoming Sunday's RCL service readings so the Today
    homepage doesn't re-fetch from Vanderbilt's site on every page load.
    Keyed by the Sunday's date (the readings' effective date), not the
    date of the request - every day in the same week shares one row per
    reading type.
    """

    __tablename__ = "lectionary_reading_cache"

    id = Column(Integer, primary_key=True)
    reading_date = Column(Date, nullable=False, index=True)
    reading_type = Column(String(20), nullable=False)  # "gospel", "ot", "psalm", "epistle"
    reference = Column(String(500), nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("reading_date", "reading_type", name="uq_reading_date_type"),
    )

    def __repr__(self):
        return f"<LectionaryReadingCache(reading_date='{self.reading_date}', reading_type='{self.reading_type}')>"

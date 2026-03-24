"""
Base Adapter for Cultural Sources

All cultural source adapters inherit from this base class.
Provides common interface for querying sources and returning artifacts.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class CulturalArtifact:
    """
    A cultural artifact retrieved from a source.

    Represents a song, movie, TV show, news event, cultural moment, etc.
    that can be used as an illustration, analogy, or connection point.
    """
    # Identity
    title: str  # "Don't Stop Believin'"
    creator: str  # "Journey" or "Steven Spielberg"
    year: int  # 1981

    # Classification
    category: str  # music, film, tv, news, icon, tech, toy, fad
    source_name: str  # "Wikipedia" or "TMDB"

    # Content
    quote_or_description: str  # Actual lyrics, movie quote, or description
    context: str  # Why this matters, what was happening culturally

    # Thematic
    themes: List[str] = field(default_factory=list)  # ["hope", "perseverance", "journey"]
    theological_hooks: List[str] = field(default_factory=list)  # ["exodus", "pilgrimage"]

    # Usage
    sermon_angle: str = ""  # How a preacher might use this
    caution: str = ""  # Any caveats (controversial artist, etc.)

    # Metadata
    url: str = ""  # Link to source
    image_url: str = ""  # Poster, album art, etc.
    confidence: float = 1.0  # How confident we are in the match (0-1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'title': self.title,
            'creator': self.creator,
            'year': self.year,
            'category': self.category,
            'source_name': self.source_name,
            'quote_or_description': self.quote_or_description,
            'context': self.context,
            'themes': self.themes,
            'theological_hooks': self.theological_hooks,
            'sermon_angle': self.sermon_angle,
            'caution': self.caution,
            'url': self.url,
            'image_url': self.image_url,
            'confidence': self.confidence,
        }

    def to_markdown(self) -> str:
        """Format artifact for display in generated content"""
        md = f"### {self.title} ({self.year})\n"
        md += f"**{self.category.title()}** | {self.creator}\n\n"

        if self.quote_or_description:
            md += f"> {self.quote_or_description}\n\n"

        if self.context:
            md += f"**Context**: {self.context}\n\n"

        if self.themes:
            md += f"**Themes**: {', '.join(self.themes)}\n\n"

        if self.sermon_angle:
            md += f"**Sermon Connection**: {self.sermon_angle}\n\n"

        if self.caution:
            md += f"*Caution*: {self.caution}\n\n"

        if self.url:
            md += f"[Source]({self.url})\n"

        return md


class BaseAdapter(ABC):
    """
    Abstract base class for cultural source adapters.

    Each adapter knows how to query a specific source and return
    CulturalArtifact objects.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize adapter with optional configuration.

        Args:
            config: Optional config dict (API keys, settings, etc.)
        """
        self.config = config or {}
        self._cache: Dict[str, List[CulturalArtifact]] = {}

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this source"""
        pass

    @property
    @abstractmethod
    def category(self) -> str:
        """Primary category: music, film, tv, news, icon, tech, toy, fad"""
        pass

    @property
    def era_start(self) -> int:
        """Start year of era coverage"""
        return 1977

    @property
    def era_end(self) -> int:
        """End year of era coverage"""
        return 1999

    @abstractmethod
    async def search(
        self,
        themes: List[str],
        limit: int = 5,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None
    ) -> List[CulturalArtifact]:
        """
        Search this source for artifacts matching themes.

        Args:
            themes: List of theme keywords to search for
            limit: Maximum number of artifacts to return
            year_start: Optional start year filter
            year_end: Optional end year filter

        Returns:
            List of CulturalArtifact objects
        """
        pass

    @abstractmethod
    async def get_by_year(
        self,
        year: int,
        limit: int = 10
    ) -> List[CulturalArtifact]:
        """
        Get notable artifacts from a specific year.

        Args:
            year: The year to query
            limit: Maximum number of artifacts to return

        Returns:
            List of CulturalArtifact objects from that year
        """
        pass

    def is_in_era(self, year: int) -> bool:
        """Check if a year falls within our target era"""
        return self.era_start <= year <= self.era_end

    def clear_cache(self):
        """Clear the adapter's cache"""
        self._cache = {}

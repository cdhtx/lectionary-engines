"""
Cultural Resonance System

Sources and adapters for finding cultural artifacts that resonate
with biblical themes. Focused on 1977-1999 era for maximum ICP relevance.
"""

from .base_adapter import BaseAdapter, CulturalArtifact
from .wikipedia_adapter import WikipediaAdapter
from .tmdb_adapter import TMDBAdapter
from .resonance_engine import ResonanceEngine

__all__ = [
    'BaseAdapter',
    'CulturalArtifact',
    'WikipediaAdapter',
    'TMDBAdapter',
    'ResonanceEngine',
]

"""
Study Generator Service
Wraps existing engine classes for web application use
"""

import sys
from pathlib import Path
from typing import Optional, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lectionary_engines.claude_client import ClaudeClient
from lectionary_engines.engines.threshold import ThresholdEngine
from lectionary_engines.engines.palimpsest import PalimpsestEngine
from lectionary_engines.engines.collision import CollisionEngine
from lectionary_engines.text_fetcher import TextFetcher
from lectionary_engines.preferences import StudyPreferences


class StudyGeneratorService:
    """
    Service for generating biblical interpretation studies

    Wraps the existing CLI engine classes for use in web application.
    Provides a clean interface for study generation with all three engines.
    """

    def __init__(self, api_key: str, default_translation: str = "NRSVue"):
        """
        Initialize the study generator service

        Args:
            api_key: Anthropic API key
            default_translation: Default Bible translation to use
        """
        self.claude = ClaudeClient(api_key)
        self.fetcher = TextFetcher(default_translation)
        self.default_translation = default_translation

        # Initialize all three engines
        self.engines = {
            'threshold': ThresholdEngine(self.claude),
            'palimpsest': PalimpsestEngine(self.claude),
            'collision': CollisionEngine(self.claude)
        }

    def generate_study(
        self,
        engine_name: str,
        reference: str,
        text: Optional[str] = None,
        translation: Optional[str] = None,
        source: str = 'paste',
        preferences: Optional[StudyPreferences] = None
    ) -> Dict[str, Any]:
        """
        Generate a study using the specified engine

        Args:
            engine_name: Name of engine ('threshold', 'palimpsest', 'collision')
            reference: Biblical reference (e.g., "John 3:16-21")
            text: Biblical text (if None, will fetch from Bible Gateway)
            translation: Bible translation (if None, uses default)
            source: Source of text ('paste', 'run', 'moravian', 'rcl')
            preferences: Optional user preferences to customize the study

        Returns:
            dict with keys:
                - engine: Engine name
                - reference: Biblical reference
                - content: Generated study (markdown)
                - metadata: Additional metadata (word count, etc.)
                - biblical_text: Original biblical text
                - source: Source of text
                - translation: Translation used

        Raises:
            ValueError: If engine_name is invalid
            Exception: If study generation fails
        """
        # Validate engine name
        if engine_name not in self.engines:
            raise ValueError(
                f"Invalid engine: {engine_name}. "
                f"Must be one of: {', '.join(self.engines.keys())}"
            )

        # Fetch text if not provided
        if text is None:
            actual_translation = translation or self.default_translation
            text = self.fetcher.fetch(reference, actual_translation)
        else:
            actual_translation = translation or self.default_translation

        # Get the engine
        engine = self.engines[engine_name]

        # Generate the study (this is the core work - calls Claude API)
        # Use generate_with_preferences if preferences provided
        if preferences:
            study = engine.generate_with_preferences(text, reference, preferences)
        else:
            study = engine.generate(text, reference)

        # Add web-specific metadata
        study['biblical_text'] = text
        study['source'] = source
        study['translation'] = actual_translation

        # Ensure metadata dict exists
        if 'metadata' not in study:
            study['metadata'] = {}

        study['metadata']['source'] = source
        study['metadata']['translation'] = actual_translation

        return study

    def fetch_text(
        self,
        reference: str,
        translation: Optional[str] = None
    ) -> str:
        """
        Fetch biblical text from Bible Gateway

        Args:
            reference: Biblical reference
            translation: Translation to use (if None, uses default)

        Returns:
            Biblical text as string
        """
        actual_translation = translation or self.default_translation
        return self.fetcher.fetch(reference, actual_translation)

    def fetch_moravian(self) -> tuple[str, str]:
        """
        Fetch today's Moravian Daily Text

        Returns:
            tuple: (reference, text)
        """
        return self.fetcher.fetch_moravian()

    def fetch_rcl(
        self,
        reading_type: str = "gospel",
        translation: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Fetch today's RCL reading

        Args:
            reading_type: Type of reading ('ot', 'psalm', 'epistle', 'gospel')
            translation: Translation to use

        Returns:
            tuple: (reference, text)
        """
        return self.fetcher.fetch_rcl(reading_type)

    def list_engines(self) -> list[str]:
        """
        Get list of available engine names

        Returns:
            List of engine names
        """
        return list(self.engines.keys())

    def list_translations(self) -> dict:
        """
        Get list of supported translations

        Returns:
            Dictionary of translation codes and names
        """
        return TextFetcher.list_translations()

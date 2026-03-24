"""
Study Generator Service
Wraps existing engine classes for web application use

Includes validation pass for accuracy, helpfulness, and faithfulness checking.
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
from lectionary_engines.protocols import validation_protocol
from lectionary_engines.protocols import news_integration
from lectionary_engines.validation import ValidationResult


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
        preferences: Optional[StudyPreferences] = None,
        news_context: Optional[str] = None,
        news_date: Optional[str] = None,
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
            news_context: Optional news story text for news integration
            news_date: Optional date of news event

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

        # News integration: modify system prompt with injection fragment
        if news_context and news_context.strip():
            study = self._generate_with_news(
                engine=engine,
                engine_name=engine_name,
                text=text,
                reference=reference,
                preferences=preferences,
                news_context=news_context,
                news_date=news_date or "",
            )
        else:
            # Standard generation
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

        if news_context and news_context.strip():
            study['metadata']['news_integrated'] = True
            study['metadata']['news_date'] = news_date

        return study

    def _generate_with_news(
        self,
        engine,
        engine_name: str,
        text: str,
        reference: str,
        preferences: Optional[StudyPreferences],
        news_context: str,
        news_date: str,
    ) -> Dict[str, Any]:
        """
        Generate a study with news integration by appending injection to system prompt.

        Uses the engine's protocol system prompt + news injection fragment,
        then calls Claude directly.
        """
        from lectionary_engines.protocol_builder import build_system_prompt, build_output_constraints
        from lectionary_engines.protocols import collision_protocol

        # Get base system prompt from engine protocol
        base_system_prompt = engine.protocol['system_prompt']

        # If preferences, build customized prompt first
        if preferences:
            from lectionary_engines.preferences import DEFAULT_PREFERENCES
            preferences.validate()
            base_system_prompt = build_system_prompt(base_system_prompt, preferences)

        # Append news injection fragment
        injection = news_integration.get_news_injection(engine_name, news_context, news_date)
        modified_system_prompt = base_system_prompt + injection

        # Build the user message using the engine's normal input wrapping
        if engine_name == "collision":
            vectors = engine.generate_collision_vectors()
            user_message = collision_protocol.INPUT_WRAPPER(text, reference, vectors)
            max_tokens = 8000  # Extra tokens for news integration
        else:
            # Threshold and Palimpsest use simpler input
            from lectionary_engines.protocols import threshold_protocol, palimpsest_protocol
            protocol_module = threshold_protocol if engine_name == "threshold" else palimpsest_protocol
            if hasattr(protocol_module, 'INPUT_WRAPPER'):
                user_message = protocol_module.INPUT_WRAPPER(text, reference)
            else:
                user_message = f"Biblical Reference: {reference}\n\nBiblical Text:\n{text}"
            max_tokens = 7000  # Extra tokens for news integration

        # Call Claude directly with modified prompt
        content = self.claude.generate_study(
            text=user_message,
            reference=reference,
            system_prompt=modified_system_prompt,
            max_tokens=max_tokens,
        )

        result = {
            "engine": engine_name,
            "reference": reference,
            "content": content,
            "metadata": {
                "word_count": len(content.split()),
                "news_integrated": True,
                "news_date": news_date,
            },
        }

        if engine_name == "collision":
            result["metadata"]["collision_vectors"] = vectors

        return result

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

    def validate_study(
        self,
        biblical_text: str,
        reference: str,
        study_content: str
    ) -> ValidationResult:
        """
        Validate a generated study for accuracy, helpfulness, and faithfulness.

        Uses a lightweight Haiku model to review the study and flag potential issues.
        This is an optional second pass to catch problems before publishing.

        Args:
            biblical_text: The original biblical text that was studied
            reference: Biblical reference
            study_content: The generated study content (markdown)

        Returns:
            ValidationResult with scores, flags, and recommendations
        """
        try:
            # Call validation API
            json_response = self.claude.validate_study(
                biblical_text=biblical_text,
                reference=reference,
                study_content=study_content,
                system_prompt=validation_protocol.SYSTEM_PROMPT,
                validation_model=validation_protocol.VALIDATION_CONFIG['model'],
                max_tokens=validation_protocol.VALIDATION_CONFIG['max_tokens']
            )

            # Parse response into structured result
            return ValidationResult.from_json(json_response)

        except Exception as e:
            # Return a failed validation result if something goes wrong
            return ValidationResult.failed(f"Validation failed: {str(e)}")

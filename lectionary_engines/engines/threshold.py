"""
Threshold Engine Implementation

Simple wrapper that loads the protocol and calls Claude API.
Following mirror-loop pattern: minimal logic, protocol does the work.
"""

from datetime import datetime
from typing import Dict, Optional

from .base import BaseEngine
from ..protocols import threshold_protocol
from ..preferences import StudyPreferences
from ..protocol_builder import build_system_prompt, build_output_constraints


class ThresholdEngine(BaseEngine):
    """
    Threshold Engine: Four progressive thresholds of biblical engagement

    Sequence: Archaeological Dive → Theological Combustion → Present Friction →
              Embodied Practice → Tech Touchpoint

    Output: 20-30 minute integrated study (2500-3500 words) with one core insight
            developing across all movements
    """

    @property
    def name(self) -> str:
        return "threshold"

    @property
    def protocol(self) -> Dict:
        return {
            "system_prompt": threshold_protocol.SYSTEM_PROMPT,
            "constraints": threshold_protocol.OUTPUT_CONSTRAINTS,
        }

    def generate(self, text: str, reference: str) -> Dict:
        """
        Generate a Threshold study

        Args:
            text: Biblical text to analyze
            reference: Biblical reference (e.g., "John 3:16-21")

        Returns:
            dict with keys: engine, reference, content, metadata
        """
        # Wrap input according to protocol
        user_message = threshold_protocol.INPUT_WRAPPER(text, reference)

        # Call Claude API with system prompt from protocol
        output = self.claude.generate_study(
            text=user_message,
            reference=reference,
            system_prompt=threshold_protocol.SYSTEM_PROMPT,
            max_tokens=4000,  # ~3000 words output
        )

        # Package result
        return {
            "engine": self.name,
            "reference": reference,
            "content": output,
            "metadata": {
                "word_count": len(output.split()),
                "timestamp": datetime.now().isoformat(),
                "constraints": threshold_protocol.OUTPUT_CONSTRAINTS,
            },
        }

    def generate_with_preferences(
        self,
        text: str,
        reference: str,
        preferences: Optional[StudyPreferences] = None
    ) -> Dict:
        """
        Generate a Threshold study with user preferences applied

        Args:
            text: Biblical text to analyze
            reference: Biblical reference (e.g., "John 3:16-21")
            preferences: User preferences for customization

        Returns:
            dict with keys: engine, reference, content, metadata
        """
        from ..preferences import DEFAULT_PREFERENCES

        # Use default preferences if none provided
        if preferences is None:
            preferences = DEFAULT_PREFERENCES

        # Validate preferences
        preferences.validate()

        # Build customized system prompt
        custom_system_prompt = build_system_prompt(
            threshold_protocol.SYSTEM_PROMPT,
            preferences
        )

        # Build customized output constraints
        custom_constraints = build_output_constraints(
            threshold_protocol.OUTPUT_CONSTRAINTS,
            preferences
        )

        # Wrap input according to protocol
        user_message = threshold_protocol.INPUT_WRAPPER(text, reference)

        # Call Claude API with customized prompt and token limit
        output = self.claude.generate_study(
            text=user_message,
            reference=reference,
            system_prompt=custom_system_prompt,
            max_tokens=custom_constraints['max_tokens'],
        )

        # Package result with preference metadata
        return {
            "engine": self.name,
            "reference": reference,
            "content": output,
            "metadata": {
                "word_count": len(output.split()),
                "timestamp": datetime.now().isoformat(),
                "constraints": custom_constraints,
                "preferences": preferences.to_dict(),
            },
        }

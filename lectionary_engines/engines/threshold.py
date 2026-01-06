"""
Threshold Engine Implementation

Simple wrapper that loads the protocol and calls Claude API.
Following mirror-loop pattern: minimal logic, protocol does the work.
"""

from datetime import datetime
from typing import Dict

from .base import BaseEngine
from ..protocols import threshold_protocol


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

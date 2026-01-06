"""
Palimpsest Engine Implementation

Five progressive layers of biblical interpretation using the PaRDeS framework.
"""

from datetime import datetime
from typing import Dict

from .base import BaseEngine
from ..protocols import palimpsest_protocol


class PalimpsestEngine(BaseEngine):
    """
    Palimpsest Engine: Five hermeneutical layers (PaRDeS framework)

    Sequence: Peshat (literal) → Remez (allegory) → Derash (interpretation) →
              Sod (mystery) → Incarnation (contemporary embodiment)

    Output: 25-35 minute layered study (3000-4000 words) where each layer remains
            visible through the others like a palimpsest manuscript

    Special: Layer Four (Sod) requires a tonal shift to contemplative/poetic mode
    """

    @property
    def name(self) -> str:
        return "palimpsest"

    @property
    def protocol(self) -> Dict:
        return {
            "system_prompt": palimpsest_protocol.SYSTEM_PROMPT,
            "constraints": palimpsest_protocol.OUTPUT_CONSTRAINTS,
        }

    def generate(self, text: str, reference: str) -> Dict:
        """
        Generate a Palimpsest study

        Args:
            text: Biblical text to analyze
            reference: Biblical reference (e.g., "John 3:16-21")

        Returns:
            dict with keys: engine, reference, content, metadata
        """
        # Wrap input according to protocol
        user_message = palimpsest_protocol.INPUT_WRAPPER(text, reference)

        # Call Claude API with system prompt from protocol
        # Palimpsest studies are longer (3000-4000 words), so increase max_tokens
        output = self.claude.generate_study(
            text=user_message,
            reference=reference,
            system_prompt=palimpsest_protocol.SYSTEM_PROMPT,
            max_tokens=5000,  # ~4000 words output
        )

        # Package result
        return {
            "engine": self.name,
            "reference": reference,
            "content": output,
            "metadata": {
                "word_count": len(output.split()),
                "timestamp": datetime.now().isoformat(),
                "constraints": palimpsest_protocol.OUTPUT_CONSTRAINTS,
                "layers": ["peshat", "remez", "derash", "sod", "incarnation"],
            },
        }

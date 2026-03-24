"""
Workshop Engine

Sermon preparation engine using seven hermeneutical lenses.
Generates lighter output than study engines - focused sermon scaffolding.
"""

from typing import Dict, Optional

from ..claude_client import ClaudeClient
from ..protocols import workshop_protocol


class WorkshopEngine:
    """
    Sermon preparation engine using hermeneutical lenses

    Unlike the study engines, this produces sermon scaffolding:
    - Core question and key insight
    - Tension and suggested movement
    - Delivery notes and cautions
    """

    def __init__(self, claude_client: ClaudeClient):
        """
        Initialize workshop engine with Claude client

        Args:
            claude_client: ClaudeClient instance for API calls
        """
        self.claude = claude_client

    @property
    def name(self) -> str:
        return "workshop"

    @property
    def lenses(self) -> Dict:
        """Get available lenses"""
        return workshop_protocol.LENSES

    def list_lenses(self) -> list:
        """Get list of lens keys"""
        return list(workshop_protocol.LENSES.keys())

    def get_lens_info(self, lens_key: str) -> Dict:
        """Get info about a specific lens"""
        if lens_key not in workshop_protocol.LENSES:
            raise ValueError(f"Unknown lens: {lens_key}")
        return workshop_protocol.LENSES[lens_key]

    def generate(
        self,
        text: str,
        reference: str,
        lens: str = "apostolic_journalist"
    ) -> Dict:
        """
        Generate sermon scaffolding using the specified lens

        Args:
            text: Biblical text to analyze
            reference: Biblical reference (e.g., "John 3:16-21")
            lens: Lens key (default: apostolic_journalist)

        Returns:
            dict with keys:
                - engine: "workshop"
                - lens: Lens key used
                - lens_name: Human-readable lens name
                - reference: Biblical reference
                - content: Generated scaffolding (markdown)
                - metadata: Word count, etc.
        """
        # Validate lens
        if lens not in workshop_protocol.LENSES:
            raise ValueError(
                f"Invalid lens: {lens}. "
                f"Valid lenses: {', '.join(workshop_protocol.LENSES.keys())}"
            )

        lens_info = workshop_protocol.LENSES[lens]

        # Get system prompt for this lens
        system_prompt = workshop_protocol.get_system_prompt(lens)

        # Build user message
        user_message = workshop_protocol.INPUT_WRAPPER(text, reference, lens_info['name'])

        # Call Claude API (using lighter token limit for scaffolding)
        response = self.claude.generate_study(
            text=user_message,
            reference=reference,
            system_prompt=system_prompt,
            max_tokens=2000  # Lighter than full studies
        )

        # Calculate word count
        word_count = len(response.split())

        return {
            'engine': 'workshop',
            'lens': lens,
            'lens_name': lens_info['name'],
            'lens_tagline': lens_info['tagline'],
            'reference': reference,
            'content': response,
            'metadata': {
                'word_count': word_count,
                'lens': lens,
                'lens_name': lens_info['name']
            }
        }

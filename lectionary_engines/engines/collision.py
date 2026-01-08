"""
Collision Engine Implementation

Forces unexpected connections between ancient texts and contemporary realities
through randomized collision vectors. Maximum intensity, building to crescendo.
"""

import random
from datetime import datetime
from typing import Dict, Optional

from .base import BaseEngine
from ..protocols import collision_protocol
from ..preferences import StudyPreferences
from ..protocol_builder import build_system_prompt, build_output_constraints


class CollisionEngine(BaseEngine):
    """
    Collision Engine: Five-step collision process with randomizer

    Sequence: Anchor in Antiquity → Collide with Now → Navigate the Rupture →
              Crystallize the Insight (refrain) → Release into Future → Generative Outputs

    Output: 3000-5000 words of maximum intensity with randomized collision vectors
            forcing unprecedented connections

    Tone: Brueggemann meets Cormac McCarthy meets Radiohead
    """

    @property
    def name(self) -> str:
        return "collision"

    @property
    def protocol(self) -> Dict:
        return {
            "system_prompt": collision_protocol.SYSTEM_PROMPT,
            "constraints": collision_protocol.OUTPUT_CONSTRAINTS,
        }

    def generate_collision_vectors(self, custom_vector: Optional[str] = None) -> Dict[str, str]:
        """
        Generate randomized collision vectors from each category

        Args:
            custom_vector: Optional specific vector to use (will try to match category)

        Returns:
            dict with keys: scientific, cultural, philosophical, technological, personal
        """
        vectors = {}

        # If custom vector provided, try to use it for appropriate category
        # Otherwise random for all
        for category, options in collision_protocol.COLLISION_VECTORS.items():
            if custom_vector and custom_vector.lower() in [opt.lower() for opt in options]:
                # Use the custom vector for this category
                vectors[category] = custom_vector
            else:
                # Random selection
                vectors[category] = random.choice(options)

        return vectors

    def generate(
        self,
        text: str,
        reference: str,
        collision_vector: Optional[str] = None,
        custom_vectors: Optional[Dict[str, str]] = None,
    ) -> Dict:
        """
        Generate a Collision study

        Args:
            text: Biblical text to analyze
            reference: Biblical reference (e.g., "John 3:16-21")
            collision_vector: Optional specific vector to use
            custom_vectors: Optional dict of custom vectors for each category

        Returns:
            dict with keys: engine, reference, content, metadata
        """
        # Generate or use provided collision vectors
        if custom_vectors:
            vectors = custom_vectors
        else:
            vectors = self.generate_collision_vectors(collision_vector)

        # Wrap input according to protocol
        user_message = collision_protocol.INPUT_WRAPPER(text, reference, vectors)

        # Call Claude API with system prompt from protocol
        # Collision studies are long (3000-5000 words), so use higher max_tokens
        output = self.claude.generate_study(
            text=user_message,
            reference=reference,
            system_prompt=collision_protocol.SYSTEM_PROMPT,
            max_tokens=6000,  # ~5000 words output
        )

        # Package result
        return {
            "engine": self.name,
            "reference": reference,
            "content": output,
            "metadata": {
                "word_count": len(output.split()),
                "timestamp": datetime.now().isoformat(),
                "constraints": collision_protocol.OUTPUT_CONSTRAINTS,
                "collision_vectors": vectors,
                "steps": [
                    "anchor_in_antiquity",
                    "collide_with_now",
                    "navigate_rupture",
                    "crystallize_insight",
                    "release_into_future",
                    "generative_outputs",
                ],
            },
        }

    def list_collision_vectors(self, category: Optional[str] = None) -> Dict:
        """
        List available collision vectors

        Args:
            category: Optional specific category to list

        Returns:
            dict of vectors by category
        """
        if category:
            return {category: collision_protocol.COLLISION_VECTORS.get(category, [])}
        return collision_protocol.COLLISION_VECTORS

    def generate_with_preferences(
        self,
        text: str,
        reference: str,
        preferences: Optional[StudyPreferences] = None,
        collision_vector: Optional[str] = None,
        custom_vectors: Optional[Dict[str, str]] = None,
    ) -> Dict:
        """
        Generate a Collision study with user preferences applied

        Args:
            text: Biblical text to analyze
            reference: Biblical reference (e.g., "John 3:16-21")
            preferences: User preferences for customization
            collision_vector: Optional specific vector to use
            custom_vectors: Optional dict of custom vectors for each category

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
            collision_protocol.SYSTEM_PROMPT,
            preferences
        )

        # Build customized output constraints
        custom_constraints = build_output_constraints(
            collision_protocol.OUTPUT_CONSTRAINTS,
            preferences
        )

        # Generate or use provided collision vectors
        if custom_vectors:
            vectors = custom_vectors
        else:
            vectors = self.generate_collision_vectors(collision_vector)

        # Wrap input according to protocol
        user_message = collision_protocol.INPUT_WRAPPER(text, reference, vectors)

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
                "collision_vectors": vectors,
                "steps": [
                    "anchor_in_antiquity",
                    "collide_with_now",
                    "navigate_rupture",
                    "crystallize_insight",
                    "release_into_future",
                    "generative_outputs",
                ],
                "preferences": preferences.to_dict(),
            },
        }

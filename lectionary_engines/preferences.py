"""
User Preferences System for Lectionary Engines

Defines preference data structures for customizing study output based on user needs.
"""

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any


@dataclass
class StudyPreferences:
    """
    User preferences for study generation

    Attributes:
        study_length: 'short', 'medium', or 'long'
        tone_level: 0-8 scale (0=academic, 8=devotional)
        language_complexity: 'accessible', 'standard', or 'advanced'
        focus_areas: Free-text description of user interests (optional)
    """

    study_length: str = 'medium'  # 'short', 'medium', 'long'
    tone_level: int = 5  # 0-8 scale
    language_complexity: str = 'standard'  # 'accessible', 'standard', 'advanced'
    focus_areas: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert preferences to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StudyPreferences':
        """Create StudyPreferences from dictionary"""
        return cls(
            study_length=data.get('study_length', 'medium'),
            tone_level=data.get('tone_level', 5),
            language_complexity=data.get('language_complexity', 'standard'),
            focus_areas=data.get('focus_areas')
        )

    def get_tone_category(self) -> str:
        """
        Convert tone_level (0-8) to category name

        Returns:
            'academic' (0-2), 'balanced' (3-5), or 'devotional' (6-8)
        """
        if self.tone_level <= 2:
            return 'academic'
        elif self.tone_level <= 5:
            return 'balanced'
        else:
            return 'devotional'

    def get_length_constraints(self) -> Dict[str, int]:
        """
        Get word count and token constraints for study_length

        Returns:
            dict with min_words, max_words, max_tokens

        Note:
            Token limits are set generously (roughly 2x word count) to account for:
            - Markdown formatting (headers, bullets, bold, etc.)
            - Section structure overhead
            - Buffer to prevent mid-sentence cutoffs
        """
        length_map = {
            'short': {'min_words': 1000, 'max_words': 1500, 'max_tokens': 4000},
            'medium': {'min_words': 2500, 'max_words': 3500, 'max_tokens': 8000},
            'long': {'min_words': 5000, 'max_words': 7000, 'max_tokens': 16000},
        }
        return length_map.get(self.study_length, length_map['medium'])

    def validate(self) -> bool:
        """
        Validate preference values

        Returns:
            True if all values are valid

        Raises:
            ValueError: If any values are invalid
        """
        # Validate study_length
        valid_lengths = ['short', 'medium', 'long']
        if self.study_length not in valid_lengths:
            raise ValueError(
                f"Invalid study_length: {self.study_length}. "
                f"Must be one of: {', '.join(valid_lengths)}"
            )

        # Validate tone_level
        if not (0 <= self.tone_level <= 8):
            raise ValueError(
                f"Invalid tone_level: {self.tone_level}. "
                "Must be between 0 and 8"
            )

        # Validate language_complexity
        valid_complexities = ['accessible', 'standard', 'advanced']
        if self.language_complexity not in valid_complexities:
            raise ValueError(
                f"Invalid language_complexity: {self.language_complexity}. "
                f"Must be one of: {', '.join(valid_complexities)}"
            )

        return True

    def __repr__(self) -> str:
        """String representation for debugging"""
        tone_cat = self.get_tone_category()
        focus_display = self.focus_areas[:30] + '...' if self.focus_areas and len(self.focus_areas) > 30 else self.focus_areas or 'none'
        return (
            f"StudyPreferences("
            f"length={self.study_length}, "
            f"tone={tone_cat}({self.tone_level}), "
            f"language={self.language_complexity}, "
            f"focus='{focus_display}')"
        )


# Default profile (matches current behavior)
DEFAULT_PREFERENCES = StudyPreferences(
    study_length='medium',
    tone_level=5,
    language_complexity='standard',
    focus_areas=None
)

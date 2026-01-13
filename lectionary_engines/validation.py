"""
Validation System for Lectionary Engines

Provides structured validation of generated studies for accuracy,
helpfulness, and faithfulness. Uses a lightweight review pass with
a faster model to catch potential issues.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import json


@dataclass
class AccuracyIssue:
    """A specific accuracy concern in the study"""
    severity: str  # 'warning', 'caution', 'note'
    category: str  # 'linguistic', 'historical', 'citation', 'intertextual'
    claim: str
    concern: str
    suggestion: str


@dataclass
class TheologicalNote:
    """A theological observation for reader awareness"""
    type: str  # 'speculation', 'contested', 'boundary'
    location: str
    note: str


@dataclass
class Flag:
    """A user-facing flag about the study"""
    level: str  # 'critical', 'important', 'minor'
    message: str


@dataclass
class AccuracyResult:
    """Accuracy evaluation results"""
    score: int
    confidence: str  # 'high', 'medium', 'low'
    issues: List[AccuracyIssue] = field(default_factory=list)


@dataclass
class HelpfulnessResult:
    """Helpfulness evaluation results"""
    score: int
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)  # Where it pulls punches


@dataclass
class FaithfulnessNote:
    """A faithfulness observation"""
    type: str  # 'celebration', 'concern', 'question'
    observation: str


@dataclass
class FaithfulnessResult:
    """Faithfulness evaluation results"""
    score: int
    textual_honesty: str  # 'excellent', 'good', 'moderate', 'poor'
    prophetic_courage: str  # 'high', 'medium', 'low'
    notes: List[FaithfulnessNote] = field(default_factory=list)


@dataclass
class ValidationResult:
    """
    Complete validation result for a generated study.

    Attributes:
        overall_score: 0-100 score indicating overall quality
        recommendation: 'approve', 'review', or 'revise'
        vibe: One phrase capturing the study's spirit
        accuracy: Accuracy evaluation with issues
        helpfulness: Helpfulness evaluation with strengths/weaknesses
        faithfulness: Faithfulness evaluation with prophetic courage rating
        flags: User-facing flags to display
        summary: Brief overall assessment
        raw_response: Original JSON response from validator
        validation_error: Error message if validation failed
    """
    overall_score: int
    recommendation: str
    vibe: str
    accuracy: AccuracyResult
    helpfulness: HelpfulnessResult
    faithfulness: FaithfulnessResult
    flags: List[Flag]
    summary: str
    raw_response: Optional[Dict[str, Any]] = None
    validation_error: Optional[str] = None

    @classmethod
    def from_json(cls, json_str: str) -> 'ValidationResult':
        """
        Parse validation result from JSON response.

        Args:
            json_str: JSON string from validation API call

        Returns:
            ValidationResult instance

        Raises:
            ValueError: If JSON is invalid or missing required fields
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            # Return a failed validation result
            return cls.failed(f"Invalid JSON response: {e}")

        try:
            # Parse accuracy
            acc_data = data.get('accuracy', {})
            accuracy = AccuracyResult(
                score=acc_data.get('score', 0),
                confidence=acc_data.get('confidence', 'low'),
                issues=[
                    AccuracyIssue(
                        severity=issue.get('severity', 'note'),
                        category=issue.get('category', 'other'),
                        claim=issue.get('claim', ''),
                        concern=issue.get('concern', ''),
                        suggestion=issue.get('suggestion', '')
                    )
                    for issue in acc_data.get('issues', [])
                ]
            )

            # Parse helpfulness
            help_data = data.get('helpfulness', {})
            helpfulness = HelpfulnessResult(
                score=help_data.get('score', 0),
                strengths=help_data.get('strengths', []),
                weaknesses=help_data.get('weaknesses', [])
            )

            # Parse faithfulness
            faith_data = data.get('faithfulness', {})
            faithfulness = FaithfulnessResult(
                score=faith_data.get('score', 0),
                textual_honesty=faith_data.get('textual_honesty', 'moderate'),
                prophetic_courage=faith_data.get('prophetic_courage', 'medium'),
                notes=[
                    FaithfulnessNote(
                        type=note.get('type', 'note'),
                        observation=note.get('observation', '')
                    )
                    for note in faith_data.get('notes', [])
                ]
            )

            # Parse flags
            flags = [
                Flag(level=flag.get('level', 'minor'), message=flag.get('message', ''))
                for flag in data.get('flags', [])
            ]

            return cls(
                overall_score=data.get('overall_score', 0),
                recommendation=data.get('recommendation', 'review'),
                vibe=data.get('vibe', ''),
                accuracy=accuracy,
                helpfulness=helpfulness,
                faithfulness=faithfulness,
                flags=flags,
                summary=data.get('summary', 'Validation completed'),
                raw_response=data
            )

        except (KeyError, TypeError) as e:
            return cls.failed(f"Error parsing validation response: {e}")

    @classmethod
    def failed(cls, error_message: str) -> 'ValidationResult':
        """Create a failed validation result"""
        return cls(
            overall_score=0,
            recommendation='review',
            vibe='Validation failed',
            accuracy=AccuracyResult(score=0, confidence='low'),
            helpfulness=HelpfulnessResult(score=0),
            faithfulness=FaithfulnessResult(score=0, textual_honesty='moderate', prophetic_courage='medium'),
            flags=[Flag(level='important', message='Validation could not be completed')],
            summary=error_message,
            validation_error=error_message
        )

    @classmethod
    def skipped(cls) -> 'ValidationResult':
        """Create a skipped validation result (when validation is disabled)"""
        return cls(
            overall_score=100,
            recommendation='approve',
            vibe='Unvalidated',
            accuracy=AccuracyResult(score=100, confidence='low'),
            helpfulness=HelpfulnessResult(score=100),
            faithfulness=FaithfulnessResult(score=100, textual_honesty='moderate', prophetic_courage='medium'),
            flags=[],
            summary='Validation skipped',
            validation_error=None
        )

    def is_approved(self) -> bool:
        """Check if study is approved for use"""
        return self.recommendation == 'approve'

    def needs_review(self) -> bool:
        """Check if study needs human review"""
        return self.recommendation in ('review', 'revise')

    def has_critical_issues(self) -> bool:
        """Check if there are critical flags"""
        return any(f.level == 'critical' for f in self.flags)

    def get_display_flags(self) -> List[Dict[str, str]]:
        """Get flags formatted for UI display"""
        return [
            {'level': f.level, 'message': f.message}
            for f in self.flags
        ]

    def get_score_color(self) -> str:
        """Get color code for score display"""
        if self.overall_score >= 80:
            return 'green'
        elif self.overall_score >= 60:
            return 'yellow'
        else:
            return 'red'

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'overall_score': self.overall_score,
            'recommendation': self.recommendation,
            'vibe': self.vibe,
            'accuracy': {
                'score': self.accuracy.score,
                'confidence': self.accuracy.confidence,
                'issues': [
                    {
                        'severity': i.severity,
                        'category': i.category,
                        'claim': i.claim,
                        'concern': i.concern,
                        'suggestion': i.suggestion
                    }
                    for i in self.accuracy.issues
                ]
            },
            'helpfulness': {
                'score': self.helpfulness.score,
                'strengths': self.helpfulness.strengths,
                'weaknesses': self.helpfulness.weaknesses
            },
            'faithfulness': {
                'score': self.faithfulness.score,
                'textual_honesty': self.faithfulness.textual_honesty,
                'prophetic_courage': self.faithfulness.prophetic_courage,
                'notes': [
                    {
                        'type': n.type,
                        'observation': n.observation
                    }
                    for n in self.faithfulness.notes
                ]
            },
            'flags': [{'level': f.level, 'message': f.message} for f in self.flags],
            'summary': self.summary,
            'validation_error': self.validation_error
        }

    def __repr__(self) -> str:
        """String representation for debugging"""
        flag_count = len(self.flags)
        critical = sum(1 for f in self.flags if f.level == 'critical')
        return (
            f"ValidationResult("
            f"score={self.overall_score}, "
            f"recommendation={self.recommendation}, "
            f"flags={flag_count} ({critical} critical))"
        )

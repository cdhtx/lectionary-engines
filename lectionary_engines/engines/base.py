"""
Base Engine Class

Abstract base class for all interpretation engines.
Each engine is a thin wrapper that loads its protocol and calls Claude API.
"""

from abc import ABC, abstractmethod
from typing import Dict

from ..claude_client import ClaudeClient


class BaseEngine(ABC):
    """Abstract base class for all engines"""

    def __init__(self, claude_client: ClaudeClient):
        """
        Initialize engine with Claude client

        Args:
            claude_client: ClaudeClient instance for API calls
        """
        self.claude = claude_client

    @property
    @abstractmethod
    def name(self) -> str:
        """Engine name (e.g., 'threshold', 'palimpsest', 'collision')"""
        raise NotImplementedError

    @property
    @abstractmethod
    def protocol(self) -> Dict:
        """
        Returns system prompt and constraints from protocols/ directory

        Returns:
            dict with keys: 'system_prompt', 'constraints'
        """
        raise NotImplementedError

    @abstractmethod
    def generate(self, text: str, reference: str) -> Dict:
        """
        Generate study and return formatted output

        Args:
            text: Biblical text to analyze
            reference: Biblical reference (e.g., "John 3:16-21")

        Returns:
            dict with keys: engine, reference, content, metadata
        """
        raise NotImplementedError

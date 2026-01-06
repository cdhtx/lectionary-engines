"""
Lectionary Engines - Biblical interpretation CLI

Three hermeneutical frameworks for engaging scripture:
- Threshold: Four progressive thresholds
- Palimpsest: Five hermeneutical layers (PaRDeS)
- Collision: Five-step collision with randomizer
"""

__version__ = "0.1.0"

from .config import Config
from .claude_client import ClaudeClient
from .engines.threshold import ThresholdEngine
from .engines.palimpsest import PalimpsestEngine
from .engines.collision import CollisionEngine
from .text_fetcher import TextFetcher

__all__ = ["Config", "ClaudeClient", "ThresholdEngine", "PalimpsestEngine", "CollisionEngine", "TextFetcher"]

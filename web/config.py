"""
Web configuration for Lectionary Engines
Extends the base CLI configuration with web-specific settings
"""

import os
from pydantic import Field
from typing import Optional

# Import base config from CLI package
import sys
from pathlib import Path

# Add parent directory to path so we can import from lectionary_engines
sys.path.insert(0, str(Path(__file__).parent.parent))

from lectionary_engines.config import Config as BaseConfig


class WebConfig(BaseConfig):
    """Extended configuration for web application"""

    # Database
    database_url: str = Field(
        default="sqlite:///./lectionary.db",
        description="Database connection URL"
    )

    # File sync
    enable_file_sync: bool = Field(
        default=True,
        description="Also write markdown files when saving to database"
    )

    # Web server
    web_host: str = Field(
        default="0.0.0.0",
        description="Web server host"
    )

    web_port: int = Field(
        default=8000,
        description="Web server port"
    )

    # Pagination
    studies_per_page: int = Field(
        default=20,
        description="Number of studies to show per page in browse view"
    )

    @classmethod
    def load(cls, env_file: Optional[Path] = None) -> "WebConfig":
        """
        Load configuration from environment variables

        Args:
            env_file: Optional path to .env file

        Returns:
            WebConfig instance
        """
        # Load base config first
        base = super().load(env_file)

        # Create web config with base values + web-specific values
        return cls(
            # Base config values
            anthropic_api_key=base.anthropic_api_key,
            esv_api_key=base.esv_api_key,
            bible_api_key=base.bible_api_key,
            default_translation=base.default_translation,
            default_engine=base.default_engine,
            output_directory=base.output_directory,
            enable_lexicons=base.enable_lexicons,
            enable_morphology=base.enable_morphology,
            enable_cross_references=base.enable_cross_references,
            # Web-specific values
            database_url=os.getenv("DATABASE_URL", "sqlite:///./lectionary.db"),
            enable_file_sync=os.getenv("ENABLE_FILE_SYNC", "true").lower() == "true",
            web_host=os.getenv("WEB_HOST", "0.0.0.0"),
            web_port=int(os.getenv("WEB_PORT", "8000")),
            studies_per_page=int(os.getenv("STUDIES_PER_PAGE", "20")),
        )

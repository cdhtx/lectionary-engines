"""
Configuration management for Lectionary Engines

Uses Pydantic for type-safe config and python-dotenv for environment variables.
Mirrors the mirror-loop pattern of environment-based API key management.
"""

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from dotenv import load_dotenv


class Config(BaseModel):
    """Configuration for Lectionary Engines CLI"""

    # Required
    anthropic_api_key: str = Field(default="", description="Anthropic API key")

    # Optional - Bible APIs (Phase 2)
    esv_api_key: Optional[str] = Field(default=None, description="ESV API key")
    bible_api_key: Optional[str] = Field(default=None, description="Bible API key")

    # Preferences
    default_translation: str = Field(default="NRSVue", description="Default Bible translation")
    default_engine: str = Field(default="threshold", description="Default engine to use")
    output_directory: str = Field(default="outputs", description="Directory for generated studies")

    # Biblical Resources (Phase 3)
    enable_lexicons: bool = Field(default=False, description="Enable lexicon integration")
    enable_morphology: bool = Field(default=False, description="Enable morphology analysis")
    enable_cross_references: bool = Field(default=False, description="Enable cross-references")

    class Config:
        """Pydantic configuration"""
        env_file = ".env"
        env_file_encoding = "utf-8"

    @classmethod
    def load(cls, env_file: Optional[Path] = None) -> "Config":
        """
        Load configuration from environment variables

        Args:
            env_file: Optional path to .env file (defaults to .env in current directory)

        Returns:
            Config instance
        """
        # Load environment variables from .env file
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        # Create config from environment variables
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            esv_api_key=os.getenv("ESV_API_KEY"),
            bible_api_key=os.getenv("BIBLE_API_KEY"),
            default_translation=os.getenv("DEFAULT_TRANSLATION", "NRSVue"),
            default_engine=os.getenv("DEFAULT_ENGINE", "threshold"),
            output_directory=os.getenv("OUTPUT_DIRECTORY", "outputs"),
            enable_lexicons=os.getenv("ENABLE_LEXICONS", "false").lower() == "true",
            enable_morphology=os.getenv("ENABLE_MORPHOLOGY", "false").lower() == "true",
            enable_cross_references=os.getenv("ENABLE_CROSS_REFERENCES", "false").lower() == "true",
        )

    def validate_api_key(self) -> bool:
        """Check if Anthropic API key is set"""
        return bool(self.anthropic_api_key and self.anthropic_api_key != "")

    def get_output_path(self, filename: str) -> Path:
        """Get full path for output file"""
        return Path(self.output_directory) / filename

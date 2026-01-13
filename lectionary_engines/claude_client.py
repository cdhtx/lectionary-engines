"""
Claude API Client

Mirrors the getReflection() pattern from mirror-loop.
Simple wrapper around Anthropic SDK for generating biblical studies.

Implements prompt caching for cost optimization - the system prompt is cached
for 5 minutes, reducing input token costs by ~90% for cached portions.
"""

from typing import Optional
import anthropic


class ClaudeClient:
    """Client for interacting with Claude API"""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514", use_caching: bool = True):
        """
        Initialize Claude client

        Args:
            api_key: Anthropic API key
            model: Claude model to use (default: claude-sonnet-4-20250514)
            use_caching: Enable prompt caching for cost optimization (default: True)
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.use_caching = use_caching

    def _build_system_param(self, system_prompt: str):
        """
        Build the system parameter with optional caching

        When caching is enabled, the system prompt is marked for caching,
        reducing costs by ~90% for the cached portion on subsequent calls
        within the 5-minute cache window.

        Args:
            system_prompt: The system prompt text

        Returns:
            System parameter in the appropriate format
        """
        if self.use_caching:
            # Use structured format with cache_control for prompt caching
            return [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}
                }
            ]
        else:
            # Simple string format (no caching)
            return system_prompt

    def generate_study(
        self,
        text: str,
        reference: str,
        system_prompt: str,
        max_tokens: int = 4000,
    ) -> str:
        """
        Generate a biblical study using Claude

        Similar to mirror-loop's getReflection() but with configurable system prompts.
        The protocol documents define engine behavior via system prompts.

        Args:
            text: User message (biblical text + instructions)
            reference: Biblical reference for logging/debugging
            system_prompt: Engine-specific protocol prompt
            max_tokens: Maximum response length (default 4000 for ~3000 word outputs)

        Returns:
            str: Generated study content (markdown formatted)

        Raises:
            Exception: If Claude API returns an error
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=self._build_system_param(system_prompt),
                messages=[{"role": "user", "content": text}],
            )

            # Extract text content from response
            return response.content[0].text

        except anthropic.APIError as e:
            raise Exception(f"Claude API error for {reference}: {e}")
        except Exception as e:
            raise Exception(f"Unexpected error generating study for {reference}: {e}")

    def generate_study_streaming(
        self,
        text: str,
        reference: str,
        system_prompt: str,
        max_tokens: int = 4000,
    ):
        """
        Generate a biblical study with streaming (for long outputs like Collision)

        Yields text chunks as they're generated for progress display.
        Uses prompt caching when enabled for cost optimization.

        Args:
            text: User message (biblical text + instructions)
            reference: Biblical reference for logging/debugging
            system_prompt: Engine-specific protocol prompt
            max_tokens: Maximum response length

        Yields:
            str: Text chunks as they're generated

        Raises:
            Exception: If Claude API returns an error
        """
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                system=self._build_system_param(system_prompt),
                messages=[{"role": "user", "content": text}],
            ) as stream:
                for text_chunk in stream.text_stream:
                    yield text_chunk

        except anthropic.APIError as e:
            raise Exception(f"Claude API error for {reference}: {e}")
        except Exception as e:
            raise Exception(f"Unexpected error generating study for {reference}: {e}")

    def validate_study(
        self,
        biblical_text: str,
        reference: str,
        study_content: str,
        system_prompt: str,
        validation_model: str = "claude-3-5-haiku-20241022",
        max_tokens: int = 2000,
    ) -> str:
        """
        Validate a generated study for accuracy, helpfulness, and faithfulness.

        Uses a faster/cheaper model (Haiku) to review the study and return
        structured feedback. This is a second-pass review to catch issues.

        Args:
            biblical_text: The original biblical text that was studied
            reference: Biblical reference for logging
            study_content: The generated study to validate
            system_prompt: Validation protocol prompt
            validation_model: Model to use for validation (default: Haiku)
            max_tokens: Maximum response length

        Returns:
            str: JSON response with validation results

        Raises:
            Exception: If Claude API returns an error
        """
        try:
            response = self.client.messages.create(
                model=validation_model,
                max_tokens=max_tokens,
                system=self._build_system_param(system_prompt),
                messages=[{"role": "user", "content": f"""Biblical Reference: {reference}

Biblical Text:
{biblical_text}

---

Generated Study:
{study_content}

---

Evaluate this study and return your assessment as JSON."""}],
            )

            return response.content[0].text

        except anthropic.APIError as e:
            raise Exception(f"Validation API error for {reference}: {e}")
        except Exception as e:
            raise Exception(f"Unexpected error validating study for {reference}: {e}")

"""
Cultural Resonance Engine

Claude-first approach: Uses Claude's deep knowledge of 1977-1999 culture
as the primary source, with optional API enrichment.

This is a mining partner, not a search engine.
"""

import asyncio
from typing import List, Optional, Dict, Any
from .base_adapter import BaseAdapter, CulturalArtifact
from .wikipedia_adapter import WikipediaAdapter
from .tmdb_adapter import TMDBAdapter

# Import the new protocol
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from protocols import resonance_protocol


class ResonanceEngine:
    """
    Engine for finding and synthesizing cultural resonances.

    Coordinates multiple adapters, aggregates results, and uses Claude
    to generate meaningful connections for sermon illustrations.
    """

    def __init__(
        self,
        claude_client=None,
        adapters: Optional[List[BaseAdapter]] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the Resonance Engine.

        Args:
            claude_client: Optional ClaudeClient for synthesis
            adapters: Optional list of adapters (defaults to Wikipedia + TMDB)
            config: Optional configuration dict
        """
        self.claude = claude_client
        self.config = config or {}

        # Initialize default adapters if none provided
        if adapters is None:
            self.adapters = [
                WikipediaAdapter(config),
                TMDBAdapter(config),
            ]
        else:
            self.adapters = adapters

    async def find_resonances(
        self,
        themes: List[str],
        limit_per_source: int = 5,
        year_start: int = 1977,
        year_end: int = 1999,
        categories: Optional[List[str]] = None
    ) -> List[CulturalArtifact]:
        """
        Find cultural artifacts that resonate with given themes.

        Queries all adapters in parallel and aggregates results.

        Args:
            themes: List of theme keywords to search for
            limit_per_source: Max artifacts per source
            year_start: Start of era filter
            year_end: End of era filter
            categories: Optional filter for categories (music, film, etc.)

        Returns:
            List of CulturalArtifact objects sorted by confidence
        """
        # Filter adapters by category if specified
        active_adapters = self.adapters
        if categories:
            active_adapters = [
                a for a in self.adapters
                if a.category in categories
            ]

        # Query all adapters in parallel
        tasks = [
            adapter.search(themes, limit_per_source, year_start, year_end)
            for adapter in active_adapters
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        all_artifacts = []
        for result in results:
            if isinstance(result, list):
                all_artifacts.extend(result)
            elif isinstance(result, Exception):
                print(f"Adapter error: {result}")

        # Sort by confidence and deduplicate by title
        seen_titles = set()
        unique_artifacts = []
        for artifact in sorted(all_artifacts, key=lambda a: a.confidence, reverse=True):
            if artifact.title.lower() not in seen_titles:
                seen_titles.add(artifact.title.lower())
                unique_artifacts.append(artifact)

        return unique_artifacts

    async def get_era_context(
        self,
        year: int,
        categories: Optional[List[str]] = None
    ) -> Dict[str, List[CulturalArtifact]]:
        """
        Get cultural context for a specific year.

        Returns artifacts organized by category.

        Args:
            year: The year to get context for
            categories: Optional filter for categories

        Returns:
            Dict mapping category -> list of artifacts
        """
        active_adapters = self.adapters
        if categories:
            active_adapters = [
                a for a in self.adapters
                if a.category in categories
            ]

        # Query all adapters in parallel
        tasks = [
            adapter.get_by_year(year)
            for adapter in active_adapters
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Organize by category
        by_category: Dict[str, List[CulturalArtifact]] = {}
        for i, result in enumerate(results):
            if isinstance(result, list):
                adapter = active_adapters[i]
                if adapter.category not in by_category:
                    by_category[adapter.category] = []
                by_category[adapter.category].extend(result)

        return by_category

    def synthesize_connections(
        self,
        artifacts: List[CulturalArtifact],
        biblical_themes: List[str],
        reference: str = ""
    ) -> str:
        """
        Use Claude to synthesize meaningful connections.

        Takes raw artifacts and biblical themes, returns a synthesized
        markdown document with sermon-ready connections.

        Args:
            artifacts: List of cultural artifacts found
            biblical_themes: Themes from the biblical text
            reference: Biblical reference for context

        Returns:
            Markdown string with synthesized connections
        """
        if not self.claude:
            # Without Claude, just format the artifacts
            return self._format_artifacts_simple(artifacts)

        # Build artifact context for Claude
        artifact_context = self._build_artifact_context(artifacts)

        # Build synthesis prompt
        system_prompt = RESONANCE_SYNTHESIS_PROMPT
        user_message = f"""Biblical Reference: {reference}

Biblical Themes: {', '.join(biblical_themes)}

Cultural Artifacts Found (1977-1999):
{artifact_context}

Synthesize 5-7 of the most powerful connections between these cultural artifacts and the biblical themes. For each connection:
1. Name the artifact (title, year, creator)
2. Quote or describe the relevant moment
3. Explain the theological resonance
4. Suggest how a preacher might use it

Focus on artifacts that will land with audiences who grew up in the late 70s through 90s.
"""

        response = self.claude.generate_study(
            text=user_message,
            reference=reference or "Cultural Resonance",
            system_prompt=system_prompt,
            max_tokens=2000
        )

        return response

    def _build_artifact_context(self, artifacts: List[CulturalArtifact]) -> str:
        """Build context string from artifacts for Claude"""
        lines = []
        for i, artifact in enumerate(artifacts[:15], 1):  # Limit to 15
            lines.append(f"{i}. **{artifact.title}** ({artifact.year}) - {artifact.category}")
            lines.append(f"   Creator: {artifact.creator}")
            lines.append(f"   {artifact.quote_or_description[:200]}...")
            lines.append(f"   Themes: {', '.join(artifact.themes[:5])}")
            lines.append("")
        return "\n".join(lines)

    def _format_artifacts_simple(self, artifacts: List[CulturalArtifact]) -> str:
        """Simple formatting without Claude synthesis"""
        sections = []
        sections.append("# Cultural Resonances\n")

        for artifact in artifacts[:10]:
            sections.append(artifact.to_markdown())

        return "\n".join(sections)

    def mine_artifacts(
        self,
        themes: List[str],
        reference: str = "",
        context: str = ""
    ) -> str:
        """
        Claude-first artifact mining.

        Uses Claude's deep knowledge of 1977-1999 culture as the primary
        source. This is the partner approach - Claude mines its memory
        for the best illustrations.

        Args:
            themes: List of themes to mine for
            reference: Optional biblical reference
            context: Optional additional context

        Returns:
            Markdown string with mined artifacts
        """
        if not self.claude:
            return "Error: Claude client required for mining"

        # Build the mining prompt
        user_message = resonance_protocol.MINING_PROMPT.format(
            reference=reference or "General themes",
            themes=", ".join(themes),
            context=context or "Finding sermon illustrations"
        )

        response = self.claude.generate_study(
            text=user_message,
            reference=reference or "Cultural Mining",
            system_prompt=resonance_protocol.SYSTEM_PROMPT,
            max_tokens=3000
        )

        return response

    def mine_from_study(
        self,
        study_content: str,
        reference: str = ""
    ) -> str:
        """
        Mine cultural artifacts based on an existing study.

        Reads the study, extracts themes, and finds matching artifacts
        from Claude's knowledge of 1977-1999 culture.

        Args:
            study_content: The full study content
            reference: Biblical reference

        Returns:
            Markdown string with mined artifacts
        """
        if not self.claude:
            return "Error: Claude client required for mining"

        # Build the study mining prompt
        user_message = resonance_protocol.STUDY_MINING_PROMPT.format(
            study_content=study_content[:6000]  # Limit to avoid token issues
        )

        response = self.claude.generate_study(
            text=user_message,
            reference=reference or "Study Mining",
            system_prompt=resonance_protocol.SYSTEM_PROMPT,
            max_tokens=3000
        )

        return response


# Protocol prompt for synthesis
RESONANCE_SYNTHESIS_PROMPT = """You are a Cultural Resonance Synthesizer - a specialist in connecting biblical themes to cultural artifacts from 1977-1999.

Your audience: Pastors preparing sermons for congregations where many members grew up in the late 70s, 80s, and 90s. These cultural touchstones are their formative language.

## YOUR TASK

Take the cultural artifacts provided and synthesize POWERFUL, SPECIFIC connections to the biblical themes. You're not just listing - you're discovering the theological resonance.

## WHAT MAKES A GREAT CONNECTION

1. **Specificity**: Not "this movie is about redemption" but "the specific moment when Andy Dufresne emerges from the sewage pipe into the rain mirrors baptismal imagery"

2. **Surprise**: Find connections that make preachers say "I never thought of it that way"

3. **Quotability**: Include actual quotes, lyrics, or moments that can be used in a sermon

4. **Era Authenticity**: These references should feel native to the 1977-1999 era, not retrofitted

5. **Theological Depth**: Don't just match surface themes - find where the artifact touches something genuinely theological

## OUTPUT FORMAT

For each connection:

### [Artifact Title] (Year)
**The Moment**: [Specific scene, lyric, or element]
**The Resonance**: [How it connects to the biblical theme]
**Sermon Use**: [Practical suggestion for how to deploy it]

## CONSTRAINTS

- Focus on the 5-7 strongest connections, not all artifacts
- Be specific - name characters, quote lyrics, describe scenes
- Avoid cliché connections (Footprints in the Sand, etc.)
- Note any cautions (controversial artists, etc.)
- Make connections that LAND - emotionally resonant, not just intellectually clever

Begin immediately with the connections. No preamble.
"""

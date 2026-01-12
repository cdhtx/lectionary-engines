"""
Protocol Builder for Lectionary Engines

Dynamically constructs protocol prompts based on user preferences.
Injects customization instructions into base protocol prompts while preserving core methodology.
"""

from typing import Dict, Any
from .preferences import StudyPreferences


def build_system_prompt(base_prompt: str, preferences: StudyPreferences) -> str:
    """
    Build a customized system prompt by injecting user preferences

    Args:
        base_prompt: The base SYSTEM_PROMPT from a protocol file
        preferences: User's StudyPreferences

    Returns:
        Modified system prompt with preference instructions injected

    Example:
        >>> from lectionary_engines.protocols import threshold_protocol
        >>> prefs = StudyPreferences(study_length='short', tone_level=7)
        >>> custom_prompt = build_system_prompt(threshold_protocol.SYSTEM_PROMPT, prefs)
    """
    # Validate preferences
    preferences.validate()

    # Build customization instructions
    customization_parts = []

    # 1. Study Length/Depth
    length_instructions = {
        'short': {
            'word_count': '1000-1500 words',
            'guidance': 'Be concise and focus on core insights. Omit extended examples. Get to the heart of the matter quickly.'
        },
        'medium': {
            'word_count': '2500-3500 words',
            'guidance': 'Balanced depth with moderate examples and exploration. Develop insights thoroughly without excessive detail.'
        },
        'long': {
            'word_count': '5000-7000 words',
            'guidance': 'Maximum depth. Include extensive examples, multiple perspectives, deep exploration. Leave no stone unturned.'
        }
    }

    length_config = length_instructions[preferences.study_length]
    customization_parts.append(f"""**LENGTH**: Target {length_config['word_count']}
{length_config['guidance']}""")

    # 2. Tone (Academic vs Devotional)
    tone_category = preferences.get_tone_category()
    tone_instructions = {
        'academic': 'Use scholarly tone with objective analysis. Employ technical terminology where appropriate. Reference historical context and theological traditions. Maintain analytical distance while remaining engaging.',
        'balanced': 'Mix scholarly insight with personal application. Balance objective analysis with reflective engagement. Use moderate theological vocabulary with brief explanations.',
        'devotional': 'Use warm, personal tone that invites spiritual formation. Focus on how this text shapes our relationship with God and others. Make it intimate and inviting. Speak to the heart while honoring the mind.'
    }

    customization_parts.append(f"""**TONE**: {tone_category.title()} (level {preferences.tone_level}/8)
{tone_instructions[tone_category]}""")

    # 3. Language Complexity
    complexity_instructions = {
        'accessible': 'Use clear, simple language suitable for high school level readers. Define all technical or theological terms. Avoid unnecessary jargon. Make complex ideas accessible without dumbing them down.',
        'standard': 'Use moderate vocabulary and concepts suitable for college level readers. Provide brief definitions for specialized terms where helpful. Balance accessibility with intellectual rigor.',
        'advanced': 'Use technical terminology freely. Assume graduate-level theological and biblical studies knowledge. Engage with scholarly debates, textual criticism, and complex hermeneutical questions without extended explanations.'
    }

    customization_parts.append(f"""**LANGUAGE**: {preferences.language_complexity.title()}
{complexity_instructions[preferences.language_complexity]}""")

    # 4. Focus Areas (if specified)
    if preferences.focus_areas:
        customization_parts.append(f"""**FOCUS AREAS**: The user is particularly interested in themes related to: "{preferences.focus_areas}"

Pay special attention to how this text speaks to these interests. Let these themes shape your exploration and application. Look for connections even when not immediately obvious.""")

    # 5. Cultural Artifacts (if enabled)
    if preferences.cultural_artifacts_level > 0:
        level = preferences.cultural_artifacts_level
        # Determine density description based on level
        if level <= 3:
            density = "occasional"
            frequency = "Include 2-4 well-chosen cultural references throughout the study"
        elif level <= 6:
            density = "moderate"
            frequency = "Include 5-8 cultural references woven throughout the study"
        else:
            density = "rich"
            frequency = "Include 10+ cultural references woven densely throughout the study"

        customization_parts.append(f"""**CULTURAL ARTIFACTS**: Level {level}/10 ({density} density)
{frequency}, drawing from diverse sources that illuminate the scripture and make it immediately relevant to contemporary life.

**Source Categories** (mix recent and classic, weight for impact and relevance):
- **News & Current Events**: Headlines, recent stories, or ongoing cultural conversations that echo the text's themes
- **Music**: Lyrics, album themes, artist stories, music history that resonates with the passage
- **Film & Television**: Movie scenes, dialogue, character arcs, TV moments that illustrate the text's truths
- **Books**: Fiction and non-fiction themes, passages, author insights - both popular and literary
- **Podcasts & YouTube**: Notable episodes, creators, conversations that connect to the scripture
- **Social Media & Online Culture**: Reddit threads, viral posts, LinkedIn insights, online community wisdom
- **Interviews & Transcripts**: Quotes from interviews, speeches, or conversations that illuminate the text
- **Art & Visual Culture**: Paintings, photography, design, visual references that enhance understanding

**Integration Guidelines**:
- Weave references naturally into the study's flow - don't create a separate "cultural references" section
- Let artifacts illuminate scripture, not distract from it
- Mix high and popular culture - a Dylan lyric alongside a TikTok trend
- Include both timeless classics and current phenomena
- Reference specific works (titles, quotes, scenes) - not vague gestures
- Weight references by their power to illuminate, not just their relevance""")

    # Build the complete injection block
    injection = f"""
## USER CUSTOMIZATION

The user has requested the following customizations for this study:

{chr(10).join(customization_parts)}

**CRITICAL**: Honor these preferences while maintaining the core methodology of this engine. The structural approach remains unchanged; these preferences shape how you express the insights.

---
"""

    # Insert injection after the opening description but before main methodology
    # Strategy: Split on first occurrence of '##' after the initial description
    # This preserves the engine intro while injecting before the detailed protocol

    # Find the first '##' marker (usually "## THRESHOLD ENGINE PROTOCOL" or similar)
    first_section_marker = base_prompt.find('##')

    if first_section_marker != -1:
        # Split at the first ## marker
        intro = base_prompt[:first_section_marker]
        rest = base_prompt[first_section_marker:]
        return intro + injection + rest
    else:
        # If no ## markers, inject at the beginning (fallback)
        return injection + base_prompt


def build_output_constraints(base_constraints: Dict[str, Any], preferences: StudyPreferences) -> Dict[str, Any]:
    """
    Build output constraints adjusted for user preferences

    Args:
        base_constraints: Original OUTPUT_CONSTRAINTS from protocol
        preferences: User's StudyPreferences

    Returns:
        Modified constraints dictionary

    Example:
        >>> from lectionary_engines.protocols import threshold_protocol
        >>> prefs = StudyPreferences(study_length='long')
        >>> constraints = build_output_constraints(threshold_protocol.OUTPUT_CONSTRAINTS, prefs)
        >>> constraints['min_words']
        5000
    """
    # Get length-specific constraints
    length_constraints = preferences.get_length_constraints()

    # Merge with base constraints (preference constraints override)
    modified_constraints = base_constraints.copy()
    modified_constraints.update({
        'min_words': length_constraints['min_words'],
        'max_words': length_constraints['max_words'],
        'max_tokens': length_constraints['max_tokens'],
        # Preserve other base constraints
        'user_preferences': preferences.to_dict()  # Store for metadata
    })

    return modified_constraints

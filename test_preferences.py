#!/usr/bin/env python3
"""
Test script for user preferences system
"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from lectionary_engines.preferences import StudyPreferences
from lectionary_engines.protocol_builder import build_system_prompt, build_output_constraints
from lectionary_engines.protocols import threshold_protocol
from lectionary_engines.claude_client import ClaudeClient
from lectionary_engines.engines.threshold import ThresholdEngine
from lectionary_engines.config import Config


def test_preferences_creation():
    """Test creating StudyPreferences"""
    print("=" * 60)
    print("Test 1: Creating StudyPreferences")
    print("=" * 60)

    # Default preferences
    default_prefs = StudyPreferences()
    print(f"Default: {default_prefs}")

    # Short devotional study
    devotional_prefs = StudyPreferences(
        study_length='short',
        tone_level=7,
        language_complexity='accessible',
        focus_areas='personal spiritual formation'
    )
    print(f"Devotional: {devotional_prefs}")

    # Long academic study
    academic_prefs = StudyPreferences(
        study_length='long',
        tone_level=1,
        language_complexity='advanced',
        focus_areas='textual criticism, historical context'
    )
    print(f"Academic: {academic_prefs}")

    print("\n✓ Preferences created successfully\n")


def test_protocol_builder():
    """Test protocol builder injects preferences correctly"""
    print("=" * 60)
    print("Test 2: Protocol Builder")
    print("=" * 60)

    prefs = StudyPreferences(
        study_length='short',
        tone_level=7,
        language_complexity='accessible',
        focus_areas='social justice'
    )

    # Build custom prompt
    custom_prompt = build_system_prompt(threshold_protocol.SYSTEM_PROMPT, prefs)

    # Check that customization was injected
    assert "USER CUSTOMIZATION" in custom_prompt
    assert "1000-1500 words" in custom_prompt
    assert "devotional" in custom_prompt.lower()
    assert "accessible" in custom_prompt.lower()
    assert "social justice" in custom_prompt

    print("Custom prompt length:", len(custom_prompt))
    print("\nCustomization block preview:")
    print("-" * 60)

    # Extract and show customization block
    start = custom_prompt.find("## USER CUSTOMIZATION")
    end = custom_prompt.find("---", start)
    if start != -1 and end != -1:
        print(custom_prompt[start:end])

    print("\n✓ Protocol builder working correctly\n")


def test_output_constraints():
    """Test output constraints are modified based on preferences"""
    print("=" * 60)
    print("Test 3: Output Constraints")
    print("=" * 60)

    base_constraints = threshold_protocol.OUTPUT_CONSTRAINTS
    print(f"Base constraints: {base_constraints}")

    # Short study constraints
    short_prefs = StudyPreferences(study_length='short')
    short_constraints = build_output_constraints(base_constraints, short_prefs)
    print(f"Short constraints: {short_constraints}")
    assert short_constraints['min_words'] == 1000
    assert short_constraints['max_words'] == 1500

    # Long study constraints
    long_prefs = StudyPreferences(study_length='long')
    long_constraints = build_output_constraints(base_constraints, long_prefs)
    print(f"Long constraints: {long_constraints}")
    assert long_constraints['min_words'] == 5000
    assert long_constraints['max_words'] == 7000

    print("\n✓ Constraints adjusted correctly\n")


def test_threshold_with_preferences():
    """Test generating a study with preferences (actual Claude API call)"""
    print("=" * 60)
    print("Test 4: Generate Study with Preferences")
    print("=" * 60)

    # Load config
    config = Config.load()

    if not config.anthropic_api_key:
        print("⚠ Skipping API test - no API key configured")
        return

    # Create Claude client and engine
    claude = ClaudeClient(config.anthropic_api_key)
    engine = ThresholdEngine(claude)

    # Test text
    reference = "John 3:16"
    text = "For God so loved the world that he gave his only Son, so that everyone who believes in him may not perish but may have eternal life."

    # Create devotional preferences (short study for quick test)
    prefs = StudyPreferences(
        study_length='short',
        tone_level=7,
        language_complexity='accessible',
        focus_areas='God\'s love and grace'
    )

    print(f"Generating study with preferences: {prefs}")
    print(f"Reference: {reference}")
    print("\nCalling Claude API... (this will take 20-30 seconds)")

    try:
        # Generate study with preferences
        study = engine.generate_with_preferences(text, reference, prefs)

        print("\n✓ Study generated successfully!")
        print(f"  Engine: {study['engine']}")
        print(f"  Reference: {study['reference']}")
        print(f"  Word count: {study['metadata']['word_count']}")
        print(f"  Target: {prefs.get_length_constraints()['min_words']}-{prefs.get_length_constraints()['max_words']} words")
        print(f"  Preferences: {study['metadata'].get('preferences')}")

        # Show first 500 chars of study
        print("\nFirst 500 characters of study:")
        print("-" * 60)
        print(study['content'][:500])
        print("...")

        # Verify it's shorter than default
        if study['metadata']['word_count'] < 2000:
            print("\n✓ Study is appropriately short (< 2000 words)")
        else:
            print(f"\n⚠ Study is {study['metadata']['word_count']} words (expected < 2000)")

    except Exception as e:
        print(f"\n✗ Error generating study: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Run all tests"""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 10 + "PREFERENCE SYSTEM TEST SUITE" + " " * 20 + "║")
    print("╚" + "═" * 58 + "╝")
    print("\n")

    try:
        test_preferences_creation()
        test_protocol_builder()
        test_output_constraints()
        test_threshold_with_preferences()

        print("\n")
        print("=" * 60)
        print("ALL TESTS COMPLETED")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

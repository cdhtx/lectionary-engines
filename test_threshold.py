#!/usr/bin/env python3
"""
Test script to generate a Threshold study for Mark 5:1-5
"""

from lectionary_engines import Config, ClaudeClient, ThresholdEngine
from lectionary_engines.utils.terminal import display_study, display_success, display_error
from lectionary_engines.utils.storage import save_study

# Biblical text
reference = "Mark 5:1-5"
text = """They came to the other side of the sea, to the region of the Gerasenes. And when he had stepped out of the boat, immediately a man from the tombs with an unclean spirit met him. He lived among the tombs, and no one could restrain him any more, even with a chain, for he had often been restrained with shackles and chains, but the chains he wrenched apart, and the shackles he broke in pieces, and no one had the strength to subdue him. Night and day among the tombs and on the mountains he was always howling and bruising himself with stones."""

print("\n" + "="*80)
print("THRESHOLD ENGINE TEST: Mark 5:1-5 (NRSVue)")
print("="*80 + "\n")

try:
    # Load config
    config = Config.load()

    if not config.validate_api_key():
        display_error("API key not found or invalid")
        exit(1)

    print("✓ Config loaded")
    print("✓ API key validated")
    print("\nGenerating Threshold study...")
    print("(This may take 30-60 seconds...)\n")

    # Initialize Claude client and engine
    claude = ClaudeClient(config.anthropic_api_key)
    threshold = ThresholdEngine(claude)

    # Generate study
    study = threshold.generate(text, reference)

    # Display study
    print("\n" + "="*80)
    display_study(study["content"], engine="threshold")

    # Save study
    output_path = save_study(study, config.output_directory)
    display_success(f"Study saved to: {output_path}")

    print("\n" + "="*80)
    print(f"Word count: {study['metadata']['word_count']}")
    print("="*80 + "\n")

except Exception as e:
    display_error(f"Failed to generate study: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

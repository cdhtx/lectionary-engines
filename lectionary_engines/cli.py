"""
Lectionary Engines CLI

Command-line interface for running biblical interpretation engines.
"""

import sys
import click
from pathlib import Path

from .config import Config
from .claude_client import ClaudeClient
from .engines.threshold import ThresholdEngine
from .engines.palimpsest import PalimpsestEngine
from .engines.collision import CollisionEngine
from .text_fetcher import TextFetcher, SUPPORTED_TRANSLATIONS
from .utils.terminal import (
    console,
    display_study,
    display_error,
    display_success,
    display_info,
    display_warning,
)
from .utils.storage import save_study, list_studies, read_study


@click.group()
@click.version_option(version="0.1.0")
def main():
    """
    Lectionary Engines - Biblical interpretation CLI

    Three hermeneutical frameworks for engaging scripture:
    - Threshold: Four progressive thresholds of engagement
    - Palimpsest: Five hermeneutical layers (PaRDeS framework)
    - Collision: Five-step collision with randomizer
    """
    pass


@main.command()
@click.argument("engine", type=click.Choice(["threshold", "palimpsest", "collision"]))
def paste(engine: str):
    """
    Run an engine with manually pasted text

    Examples:
        lectionary paste threshold
        lectionary paste palimpsest
        lectionary paste collision
    """
    console.print(f"\n[bold cyan]═══ Lectionary Engines: {engine.upper()} ═══[/bold cyan]\n")

    # Load configuration
    try:
        config = Config.load()
    except Exception as e:
        display_error(f"Failed to load configuration: {e}")
        sys.exit(1)

    # Validate API key
    if not config.validate_api_key():
        display_error("ANTHROPIC_API_KEY not found in environment")
        display_info("Please set ANTHROPIC_API_KEY in your .env file or environment")
        display_info("Copy .env.example to .env and add your API key")
        sys.exit(1)

    # Prompt for reference
    reference = click.prompt("\n[cyan]Biblical reference[/cyan] (e.g., 'John 3:16-21')", type=str)

    # Prompt for text
    console.print("\n[yellow]Paste your biblical text below.[/yellow]")
    console.print("[dim]Press Enter twice (blank line) when done, or Ctrl+D (Unix) / Ctrl+Z (Windows):[/dim]\n")

    text_lines = []
    try:
        while True:
            try:
                line = input()
                # If we get a blank line after some input, check if user wants to finish
                if not line and text_lines:
                    # Give them another chance - if next line is also blank, we're done
                    break
                text_lines.append(line)
            except EOFError:
                # Ctrl+D or Ctrl+Z pressed
                break
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Cancelled[/yellow]\n")
        sys.exit(0)

    text = "\n".join(text_lines).strip()

    if not text:
        display_error("No text provided")
        sys.exit(1)

    # Initialize Claude client
    try:
        claude = ClaudeClient(config.anthropic_api_key)
    except Exception as e:
        display_error(f"Failed to initialize Claude client: {e}")
        sys.exit(1)

    # Select and initialize engine
    if engine == "threshold":
        engine_instance = ThresholdEngine(claude)
    elif engine == "palimpsest":
        engine_instance = PalimpsestEngine(claude)
    elif engine == "collision":
        engine_instance = CollisionEngine(claude)
    else:
        display_error(f"Engine '{engine}' not yet implemented")
        sys.exit(1)

    # Generate study
    console.print("\n[bold green]Generating study...[/bold green]")
    console.print("[dim]This may take 30-60 seconds...[/dim]\n")

    try:
        study = engine_instance.generate(text, reference)
    except Exception as e:
        display_error(f"Failed to generate study: {e}")
        sys.exit(1)

    # Display study
    display_study(study["content"], engine=engine)

    # Save study
    try:
        output_path = save_study(study, config.output_directory)
        display_success(f"Study saved to: {output_path}")
    except Exception as e:
        display_warning(f"Failed to save study: {e}")

    console.print("")


@main.command()
@click.argument("engine", type=click.Choice(["threshold", "palimpsest", "collision"]))
@click.argument("reference")
@click.option("--translation", "-t",
              type=click.Choice(["NRSVue", "NIV", "CEB", "NLT", "MSG"]),
              default="NRSVue",
              help="Bible translation (default: NRSVue)")
def run(engine: str, reference: str, translation: str):
    """
    Run an engine with automatically fetched text from Bible Gateway

    Examples:
        lectionary run threshold "Mark 5:1-5"
        lectionary run palimpsest "John 3:16-21" --translation NIV
        lectionary run collision "Romans 8:18-30" -t MSG
    """
    console.print(f"\n[bold cyan]═══ Lectionary Engines: {engine.upper()} ═══[/bold cyan]\n")

    # Load configuration
    try:
        config = Config.load()
    except Exception as e:
        display_error(f"Failed to load configuration: {e}")
        sys.exit(1)

    # Validate API key
    if not config.validate_api_key():
        display_error("ANTHROPIC_API_KEY not found in environment")
        display_info("Please set ANTHROPIC_API_KEY in your .env file or environment")
        display_info("Copy .env.example to .env and add your API key")
        sys.exit(1)

    # Initialize text fetcher
    fetcher = TextFetcher(default_translation=translation)

    # Validate reference format
    if not fetcher.validate_reference(reference):
        display_warning(f"Reference format may be invalid: '{reference}'")
        display_info("Expected format: 'Book Chapter:Verse' or 'Book Chapter:Verse-Verse'")
        display_info("Example: 'John 3:16-21' or 'Mark 5:1-5'")

    # Fetch text
    console.print(f"[yellow]Fetching {reference} ({translation})...[/yellow]\n")
    try:
        text = fetcher.fetch(reference, translation)
    except Exception as e:
        display_error(f"Failed to fetch text: {e}")
        sys.exit(1)

    console.print(f"[green]✓[/green] Fetched {len(text.split())} words\n")

    # Initialize Claude client
    try:
        claude = ClaudeClient(config.anthropic_api_key)
    except Exception as e:
        display_error(f"Failed to initialize Claude client: {e}")
        sys.exit(1)

    # Select and initialize engine
    if engine == "threshold":
        engine_instance = ThresholdEngine(claude)
        time_estimate = "30-60 seconds"
    elif engine == "palimpsest":
        engine_instance = PalimpsestEngine(claude)
        time_estimate = "60-90 seconds"
    elif engine == "collision":
        engine_instance = CollisionEngine(claude)
        time_estimate = "90-120 seconds"
    else:
        display_error(f"Engine '{engine}' not yet implemented")
        sys.exit(1)

    # Generate study
    console.print(f"[bold green]Generating {engine} study...[/bold green]")
    console.print(f"[dim]This may take {time_estimate}...[/dim]\n")

    try:
        study = engine_instance.generate(text, reference)
    except Exception as e:
        display_error(f"Failed to generate study: {e}")
        sys.exit(1)

    # Display study
    display_study(study["content"], engine=engine)

    # Save study
    try:
        output_path = save_study(study, config.output_directory)
        display_success(f"Study saved to: {output_path}")
    except Exception as e:
        display_warning(f"Failed to save study: {e}")

    console.print("")


@main.command()
def config():
    """Show current configuration"""
    try:
        cfg = Config.load()
    except Exception as e:
        display_error(f"Failed to load configuration: {e}")
        sys.exit(1)

    console.print("\n[bold cyan]Current Configuration[/bold cyan]\n")
    console.print(f"API Key: {'[green]✓ Set[/green]' if cfg.validate_api_key() else '[red]✗ Not set[/red]'}")
    console.print(f"Default Translation: {cfg.default_translation}")
    console.print(f"Default Engine: {cfg.default_engine}")
    console.print(f"Output Directory: {cfg.output_directory}")
    console.print("")


@main.command()
def list():
    """List saved studies"""
    try:
        studies = list_studies()
    except Exception as e:
        display_error(f"Failed to list studies: {e}")
        sys.exit(1)

    if not studies:
        display_info("No saved studies found")
        return

    console.print("\n[bold cyan]Saved Studies[/bold cyan]\n")

    for i, study in enumerate(studies, 1):
        console.print(f"{i}. [{study['engine']}] {study['reference']}")
        console.print(f"   Date: {study.get('timestamp', 'Unknown')[:10]}")
        console.print(f"   Words: {study.get('word_count', 'Unknown')}")
        console.print(f"   File: {study.get('filepath', 'Unknown')}")
        console.print("")


@main.command()
@click.argument("filepath", type=click.Path(exists=True))
def show(filepath: str):
    """Display a saved study"""
    try:
        content = read_study(filepath)
    except Exception as e:
        display_error(f"Failed to read study: {e}")
        sys.exit(1)

    display_study(content)


@main.command()
@click.argument("engine", type=click.Choice(["threshold", "palimpsest", "collision"]))
@click.option("--translation",
              type=click.Choice(["NRSVue", "NIV", "CEB", "NLT", "MSG"]),
              default="NRSVue",
              help="Bible translation (default: NRSVue)")
def moravian(engine: str, translation: str):
    """
    Run an engine with today's Moravian Daily Text

    Fetches ALL biblical passages from moravian.org including:
    - Daily Psalm, OT Reading, and NT Reading
    - Watchword (OT verse) and Daily Text (NT verse)

    All passages are used together as a frame for interpretation.

    Examples:
        lectionary moravian threshold
        lectionary moravian palimpsest --translation NIV
        lectionary moravian collision
    """
    console.print(f"\n[bold cyan]═══ Moravian Daily Text: {engine.upper()} ═══[/bold cyan]\n")

    # Load configuration
    try:
        config = Config.load()
    except Exception as e:
        display_error(f"Failed to load configuration: {e}")
        sys.exit(1)

    # Validate API key
    if not config.validate_api_key():
        display_error("ANTHROPIC_API_KEY not found in environment")
        display_info("Please set ANTHROPIC_API_KEY in your .env file")
        sys.exit(1)

    # Initialize text fetcher
    fetcher = TextFetcher(default_translation=translation)

    # Fetch today's complete Moravian text (all passages)
    console.print(f"[yellow]Fetching today's Moravian Daily Text (all passages)...[/yellow]\n")
    try:
        reference, biblical_text = fetcher.fetch_moravian()
    except Exception as e:
        display_error(f"Failed to fetch Moravian text: {e}")
        sys.exit(1)

    console.print(f"[green]✓[/green] {reference}")
    console.print(f"[green]✓[/green] Fetched {len(biblical_text.split())} words\n")

    # Initialize Claude client
    try:
        claude = ClaudeClient(config.anthropic_api_key)
    except Exception as e:
        display_error(f"Failed to initialize Claude client: {e}")
        sys.exit(1)

    # Select and initialize engine
    if engine == "threshold":
        engine_instance = ThresholdEngine(claude)
        time_estimate = "30-60 seconds"
    elif engine == "palimpsest":
        engine_instance = PalimpsestEngine(claude)
        time_estimate = "60-90 seconds"
    elif engine == "collision":
        engine_instance = CollisionEngine(claude)
        time_estimate = "90-120 seconds"
    else:
        display_error(f"Engine '{engine}' not implemented")
        sys.exit(1)

    # Generate study
    console.print(f"[bold green]Generating {engine} study...[/bold green]")
    console.print(f"[dim]This may take {time_estimate}...[/dim]\n")

    try:
        study = engine_instance.generate(biblical_text, reference)
    except Exception as e:
        display_error(f"Failed to generate study: {e}")
        sys.exit(1)

    # Display study
    display_study(study["content"], engine=engine)

    # Save study
    try:
        output_path = save_study(study, config.output_directory)
        display_success(f"Study saved to: {output_path}")
    except Exception as e:
        display_warning(f"Failed to save study: {e}")

    console.print("")


@main.command()
@click.argument("engine", type=click.Choice(["threshold", "palimpsest", "collision"]))
@click.option("--reading", "-r",
              type=click.Choice(["ot", "psalm", "epistle", "gospel"]),
              default="gospel",
              help="Which reading to use (default: gospel)")
@click.option("--translation",
              type=click.Choice(["NRSVue", "NIV", "CEB", "NLT", "MSG"]),
              default="NRSVue",
              help="Bible translation (default: NRSVue)")
def rcl(engine: str, reading: str, translation: str):
    """
    Run an engine with today's Revised Common Lectionary reading

    Automatically fetches from Vanderbilt Divinity Library

    Examples:
        lectionary rcl threshold
        lectionary rcl palimpsest --reading ot
        lectionary rcl collision -r epistle --translation NIV

    Note: RCL readings are primarily for Sundays and major feast days.
    """
    console.print(f"\n[bold cyan]═══ Revised Common Lectionary: {engine.upper()} ═══[/bold cyan]\n")

    # Load configuration
    try:
        config = Config.load()
    except Exception as e:
        display_error(f"Failed to load configuration: {e}")
        sys.exit(1)

    # Validate API key
    if not config.validate_api_key():
        display_error("ANTHROPIC_API_KEY not found in environment")
        display_info("Please set ANTHROPIC_API_KEY in your .env file")
        sys.exit(1)

    # Initialize text fetcher
    fetcher = TextFetcher(default_translation=translation)

    # Fetch today's RCL reading
    console.print(f"[yellow]Fetching today's RCL reading ({reading})...[/yellow]\n")
    try:
        reference, biblical_text = fetcher.fetch_rcl(reading_type=reading)
    except Exception as e:
        display_error(f"Failed to fetch RCL reading: {e}")
        display_info("RCL readings are typically for Sundays. For weekdays, use 'run' command with a specific reference.")
        sys.exit(1)

    console.print(f"[green]✓[/green] {reference}")
    console.print(f"[green]✓[/green] Fetched {len(biblical_text.split())} words\n")

    # Initialize Claude client
    try:
        claude = ClaudeClient(config.anthropic_api_key)
    except Exception as e:
        display_error(f"Failed to initialize Claude client: {e}")
        sys.exit(1)

    # Select and initialize engine
    if engine == "threshold":
        engine_instance = ThresholdEngine(claude)
        time_estimate = "30-60 seconds"
    elif engine == "palimpsest":
        engine_instance = PalimpsestEngine(claude)
        time_estimate = "60-90 seconds"
    elif engine == "collision":
        engine_instance = CollisionEngine(claude)
        time_estimate = "90-120 seconds"
    else:
        display_error(f"Engine '{engine}' not implemented")
        sys.exit(1)

    # Generate study
    console.print(f"[bold green]Generating {engine} study...[/bold green]")
    console.print(f"[dim]This may take {time_estimate}...[/dim]\n")

    try:
        study = engine_instance.generate(biblical_text, reference)
    except Exception as e:
        display_error(f"Failed to generate study: {e}")
        sys.exit(1)

    # Display study
    display_study(study["content"], engine=engine)

    # Save study
    try:
        output_path = save_study(study, config.output_directory)
        display_success(f"Study saved to: {output_path}")
    except Exception as e:
        display_warning(f"Failed to save study: {e}")

    console.print("")


if __name__ == "__main__":
    main()

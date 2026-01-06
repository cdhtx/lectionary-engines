"""
Terminal formatting utilities using Rich

Provides beautiful terminal output for displaying generated studies.
"""

import re
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.table import Table


console = Console()


def display_study(content: str, engine: str = ""):
    """
    Display a generated study in the terminal with Rich formatting

    Args:
        content: Markdown-formatted study content
        engine: Engine name (for header display)
    """
    # Route to engine-specific display
    if engine == "threshold":
        _display_threshold_study(content)
    elif engine == "collision":
        _display_collision_study(content)
    elif engine == "palimpsest":
        _display_palimpsest_study(content)
    else:
        # Default display
        if engine:
            header = Text(f"\n{engine.upper()} ENGINE STUDY\n", style="bold cyan")
            console.print(Panel(header, border_style="cyan"))
        md = Markdown(content)
        console.print(md)
        console.print("\n" + "─" * 80 + "\n", style="dim")


def _display_threshold_study(content: str):
    """Display Threshold study with archaeological excavation aesthetic"""

    # Extract title
    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    title = title_match.group(1) if title_match else "Threshold Study"

    # Header
    console.print("\n")
    console.print("╔" + "═" * 78 + "╗", style="bold yellow")
    console.print("║" + f"{'THRESHOLD ENGINE STUDY':^78}" + "║", style="bold yellow")
    console.print("║" + f"{title:^78}" + "║", style="bold yellow")
    console.print("╚" + "═" * 78 + "╝", style="bold yellow")
    console.print()

    # Parse content by thresholds
    thresholds = [
        ("Threshold One", "PRIMA LECTIO", "Archaeological Dive", "I", 10),
        ("Threshold Two", "SECUNDA LECTIO", "Theological Combustion", "II", 25),
        ("Threshold Three", "TERTIA LECTIO", "Present Friction", "III", 40),
        ("Threshold Four", "QUARTA LECTIO", "Embodied Practice", "IV", 60),
    ]

    # Split content into intro and thresholds
    parts = re.split(r'#+\s*Threshold (One|Two|Three|Four)', content, flags=re.IGNORECASE)

    # Display intro (before first threshold)
    if len(parts) > 0 and parts[0].strip():
        intro = parts[0].strip()
        # Remove title from intro if present
        intro = re.sub(r'^#\s+.+$', '', intro, flags=re.MULTILINE).strip()
        if intro:
            md = Markdown(intro)
            console.print(md)
            console.print()

    # Display each threshold
    for i, (threshold_name, latin_name, subtitle, stratum, depth) in enumerate(thresholds):
        # Find threshold content
        threshold_num = threshold_name.split()[1]  # "One", "Two", etc.

        # Search for this threshold in parts
        threshold_content = None
        for j in range(1, len(parts), 2):  # Odd indices have threshold names
            if parts[j].lower() == threshold_num.lower() and j + 1 < len(parts):
                threshold_content = parts[j + 1].strip()
                break

        if not threshold_content:
            continue

        # Clean up the content
        threshold_content = re.sub(r'^:.*$', '', threshold_content, flags=re.MULTILINE).strip()

        # Depth marker
        progress = "▓" * (depth // 5) + "░" * (20 - depth // 5)
        console.print("┌" + "─" * 78 + "┐", style="dim yellow")
        console.print(f"│ EXCAVATION DEPTH: -{depth}m  {progress}{'STRATUM ' + stratum:>30} │", style="yellow")
        console.print("└" + "─" * 78 + "┘", style="dim yellow")
        console.print()

        # Threshold header
        console.print("═" * 80, style="bold yellow")
        console.print(f"  ◆ {latin_name} ◆", style="bold cyan")
        console.print(f"  {threshold_name}: {subtitle}", style="cyan")
        console.print("═" * 80, style="bold yellow")
        console.print()

        # Process content for special boxes
        threshold_content = _add_threshold_boxes(threshold_content)

        # Display content
        md = Markdown(threshold_content)
        console.print(md)
        console.print()

    # Tech touchpoint section
    if "Tech Touchpoint" in content or "tech touchpoint" in content.lower():
        tech_match = re.search(r'#+\s*Tech Touchpoint(.+?)(?=─{3,}|$)', content, re.DOTALL | re.IGNORECASE)
        if tech_match:
            console.print("─" * 80, style="dim cyan")
            console.print("  ⚙ INSTRUMENTUM TECHNOLOGIAE ⚙", style="bold cyan")
            console.print("  Tech Touchpoint", style="cyan")
            console.print("─" * 80, style="dim cyan")
            console.print()

            tech_content = tech_match.group(1).strip()
            md = Markdown(tech_content)
            console.print(md)
            console.print()

    # Through-line footer
    if "Through-Line" in content or "through-line" in content.lower():
        through_line_match = re.search(r'(?:The )?Through-Line.*?:(.+?)(?=─{3,}|$)', content, re.DOTALL | re.IGNORECASE)
        if through_line_match:
            console.print("═" * 80, style="bold yellow")
            console.print("  THE THROUGH-LINE", style="bold cyan")
            console.print("═" * 80, style="bold yellow")
            through_text = through_line_match.group(1).strip()
            console.print(through_text, style="dim")
            console.print("═" * 80, style="bold yellow")
            console.print()


def _add_threshold_boxes(content: str) -> str:
    """Add visual boxes for artifacts, marginalia, etc."""
    # This would parse content for special markers and add boxes
    # For now, return as-is since we'd need to update the protocol to add markers
    return content


def _display_collision_study(content: str):
    """Display Collision study with futuristic console aesthetic (existing style)"""
    # Keep existing collision display logic
    md = Markdown(content)
    console.print(md)


def _display_palimpsest_study(content: str):
    """Display Palimpsest study (existing style for now)"""
    # Keep existing palimpsest display logic
    md = Markdown(content)
    console.print(md)


def display_error(message: str):
    """
    Display an error message

    Args:
        message: Error message to display
    """
    console.print(f"\n[bold red]Error:[/bold red] {message}\n")


def display_success(message: str):
    """
    Display a success message

    Args:
        message: Success message to display
    """
    console.print(f"\n[bold green]✓[/bold green] {message}\n")


def display_info(message: str):
    """
    Display an info message

    Args:
        message: Info message to display
    """
    console.print(f"\n[cyan]ℹ[/cyan] {message}\n")


def display_warning(message: str):
    """
    Display a warning message

    Args:
        message: Warning message to display
    """
    console.print(f"\n[yellow]⚠[/yellow] {message}\n")

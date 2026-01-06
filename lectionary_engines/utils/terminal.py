"""
Terminal formatting utilities using Rich

Provides beautiful terminal output for displaying generated studies.
"""

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text


console = Console()


def display_study(content: str, engine: str = ""):
    """
    Display a generated study in the terminal with Rich formatting

    Args:
        content: Markdown-formatted study content
        engine: Engine name (for header display)
    """
    # Display header
    if engine:
        header = Text(f"\n{engine.upper()} ENGINE STUDY\n", style="bold cyan")
        console.print(Panel(header, border_style="cyan"))

    # Render markdown content
    md = Markdown(content)
    console.print(md)

    # Display footer
    console.print("\n" + "─" * 80 + "\n", style="dim")


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

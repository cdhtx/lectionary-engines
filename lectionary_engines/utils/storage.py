"""
Storage utilities for saving generated studies

Handles saving studies to markdown files and metadata to JSON.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict


def sanitize_filename(reference: str) -> str:
    """
    Convert a biblical reference to a safe filename

    Args:
        reference: Biblical reference (e.g., "John 3:16-21")

    Returns:
        Sanitized filename (e.g., "john-3-16-21")
    """
    # Convert to lowercase
    safe = reference.lower()
    # Replace spaces and colons with hyphens
    safe = re.sub(r"[\s:]+", "-", safe)
    # Remove any other non-alphanumeric characters except hyphens
    safe = re.sub(r"[^a-z0-9\-]", "", safe)
    # Remove duplicate hyphens
    safe = re.sub(r"-+", "-", safe)
    # Remove leading/trailing hyphens
    safe = safe.strip("-")
    return safe


def save_study(study: Dict, output_dir: str = "outputs") -> str:
    """
    Save a generated study to markdown file with metadata

    Args:
        study: Study dict with keys: engine, reference, content, metadata
        output_dir: Directory to save outputs (default: "outputs")

    Returns:
        str: Path to saved file
    """
    # Create output directory if it doesn't exist
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Create metadata directory
    metadata_path = output_path / ".metadata"
    metadata_path.mkdir(exist_ok=True)

    # Generate filename
    safe_ref = sanitize_filename(study["reference"])
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"{study['engine']}_{safe_ref}_{date_str}.md"
    filepath = output_path / filename

    # Prepare markdown content with frontmatter
    frontmatter = f"""---
engine: {study['engine']}
reference: {study['reference']}
date: {datetime.now().strftime('%Y-%m-%d')}
word_count: {study['metadata'].get('word_count', 0)}
---

"""

    # Write markdown file
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter)
        f.write(study["content"])

    # Save metadata as JSON
    metadata_file = metadata_path / f"{study['engine']}_{safe_ref}_{date_str}.json"
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "engine": study["engine"],
                "reference": study["reference"],
                "timestamp": study["metadata"]["timestamp"],
                "word_count": study["metadata"].get("word_count", 0),
                "constraints": study["metadata"].get("constraints", {}),
                "filepath": str(filepath),
            },
            f,
            indent=2,
        )

    return str(filepath)


def list_studies(output_dir: str = "outputs") -> list[Dict]:
    """
    List all saved studies

    Args:
        output_dir: Directory containing outputs

    Returns:
        List of study metadata dicts
    """
    output_path = Path(output_dir)
    metadata_path = output_path / ".metadata"

    if not metadata_path.exists():
        return []

    studies = []
    for json_file in metadata_path.glob("*.json"):
        with open(json_file, "r", encoding="utf-8") as f:
            studies.append(json.load(f))

    # Sort by timestamp (most recent first)
    studies.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return studies


def read_study(filepath: str) -> str:
    """
    Read a saved study file

    Args:
        filepath: Path to study markdown file

    Returns:
        Study content
    """
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()

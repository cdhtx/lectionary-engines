# Lectionary Engines

Biblical interpretation CLI using three hermeneutical frameworks powered by Claude AI.

## Overview

Lectionary Engines provides three sophisticated frameworks for engaging with biblical texts:

- **Threshold** (✓ Available): Four progressive thresholds of engagement (Archaeological → Theological → Present → Practice)
- **Palimpsest** (Coming in Phase 2): Five hermeneutical layers (PaRDeS framework)
- **Collision** (Coming in Phase 2): Five-step collision process with randomizer

## Quick Start

### Prerequisites

- Python 3.10 or higher
- Anthropic API key ([get one here](https://console.anthropic.com/))

### Installation

```bash
# Clone or download this repository
cd lectionary-engines

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Or install in development mode
pip install -e .
```

### Configuration

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and add your Anthropic API key
# ANTHROPIC_API_KEY=your_key_here
```

### Usage

```bash
# Run the Threshold engine with manual paste
lectionary paste threshold

# Or use as a Python module
python -m lectionary_engines paste threshold
```

When prompted:
1. Enter your biblical reference (e.g., "John 3:16-21")
2. Paste your biblical text
3. Press Enter twice (or Ctrl+D on Mac/Linux, Ctrl+Z on Windows)

The tool will generate a complete study (2500-3500 words, ~20-30 minutes reading) and save it to the `outputs/` directory.

## The Threshold Engine

The Threshold methodology guides you through four progressive levels of engagement with scripture:

### 1. Archaeological Dive (5-7 min)
Ground the text in its ancient reality. Explore historical context, original language, cultural background, and what the original audience would have understood and felt.

### 2. Theological Combustion (5-7 min)
Let the archaeological discovery challenge traditional theological assumptions. Explore what the text reveals about God, humanity, and salvation.

### 3. Present Friction (5-7 min)
Identify where the theological disruption collides with contemporary life. Create productive tension between ancient text and modern reality.

### 4. Embodied Practice (ongoing)
Receive concrete, actionable practices for living out the insight: breath prayer, coaching questions, and specific daily practices.

### Tech Touchpoint
Get a specific technology recommendation (phone reminders, calendar blocks, etc.) to help you re-encounter the insight throughout your day.

**One Core Insight**: Unlike disconnected devotional thoughts, each Threshold study develops a single insight progressively across all four movements.

## CLI Commands

### `lectionary paste <engine>`

Run an engine with manually pasted text.

```bash
lectionary paste threshold
```

### `lectionary config`

Show current configuration (API key status, preferences).

```bash
lectionary config
```

### `lectionary list`

List all saved studies.

```bash
lectionary list
```

### `lectionary show <filepath>`

Display a previously saved study.

```bash
lectionary show outputs/threshold_john-3-16-21_20250131.md
```

## Project Structure

```
lectionary-engines/
├── lectionary_engines/
│   ├── cli.py                    # CLI interface
│   ├── config.py                 # Configuration management
│   ├── claude_client.py          # Claude API wrapper
│   ├── engines/
│   │   ├── base.py               # Base engine class
│   │   └── threshold.py          # Threshold engine
│   ├── protocols/
│   │   └── threshold_protocol.py # Threshold system prompt
│   └── utils/
│       ├── terminal.py           # Rich terminal formatting
│       └── storage.py            # File storage utilities
├── outputs/                      # Generated studies
├── pyproject.toml                # Project configuration
├── requirements.txt              # Dependencies
└── .env                          # Your API keys (git-ignored)
```

## Architecture Philosophy

Following the "mirror-loop" pattern:

- **Protocols define behavior**: Engine logic lives in protocol documents (system prompts), not code
- **Simple, focused code**: Minimal abstraction, clear separation of concerns
- **Environment-based config**: API keys in `.env` files, not hardcoded
- **Thin wrappers**: Engines are simple wrappers around protocols + Claude API

The protocol IS the engine. The code is just plumbing.

## Output Format

Studies are saved as markdown files with frontmatter:

```markdown
---
engine: threshold
reference: John 3:16-21
date: 2025-01-31
word_count: 2847
---

# Threshold Study: John 3:16-21

[Study content...]
```

Metadata is also saved to `outputs/.metadata/` as JSON for future features (search, comparison, etc.).

## Roadmap

### Phase 1: MVP (Current)
- ✓ Threshold engine
- ✓ Manual paste input
- ✓ Beautiful terminal output
- ✓ Markdown file storage

### Phase 2: Full Engine Suite (Coming Soon)
- Palimpsest engine (5-layer PaRDeS framework)
- Collision engine (with randomizer)
- Bible API integration (ESV API)
- `lectionary run <engine> "<reference>"` command

### Phase 3: Biblical Resources (Future)
- Hebrew/Greek lexicon integration
- Morphological analysis
- Cross-references
- `--resources` flags for enhanced output

## Troubleshooting

### "ANTHROPIC_API_KEY not found"

Make sure you've created a `.env` file (copy from `.env.example`) and added your API key:

```bash
cp .env.example .env
# Edit .env and add: ANTHROPIC_API_KEY=your_key_here
```

### "ModuleNotFoundError"

Make sure you've installed dependencies:

```bash
pip install -r requirements.txt
```

### "Command not found: lectionary"

If installed with `pip install -e .`, make sure your virtual environment is activated:

```bash
source venv/bin/activate
```

Or run directly as a module:

```bash
python -m lectionary_engines paste threshold
```

## Development

### Running Tests

```bash
pip install -e ".[dev]"
pytest
```

### Code Formatting

```bash
black lectionary_engines/
ruff check lectionary_engines/
```

## Contributing

This project is in active development. Phase 1 (MVP) is complete. Phases 2 and 3 are planned.

## License

MIT License - see LICENSE file for details.

## Acknowledgments

Inspired by:
- Walter Brueggemann's prophetic imagination
- N.T. Wright's historical-critical synthesis
- Ancient Jewish PaRDeS hermeneutic
- The "mirror-loop" architecture pattern for AI-driven applications

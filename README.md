# Lectionary Engines

Biblical interpretation CLI using three hermeneutical frameworks powered by Claude AI.

## Overview

Lectionary Engines provides three sophisticated frameworks for engaging with biblical texts:

- **Threshold**: Four progressive thresholds of engagement (Archaeological → Theological → Present → Practice)
- **Palimpsest**: Five hermeneutical layers using the PaRDeS framework (Peshat → Remez → Derash → Sod → Incarnation)
- **Collision**: Five-step collision process with randomizer forcing unexpected connections

Each engine has a unique visual identity in the terminal with beautiful typography.

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
# Quick start - Today's Moravian Daily Text
python3 -m lectionary_engines moravian threshold

# Or use a specific Bible passage
python3 -m lectionary_engines run threshold "John 3:16-21"

# Today's Revised Common Lectionary
python3 -m lectionary_engines rcl palimpsest

# Try different engines
python3 -m lectionary_engines moravian palimpsest
python3 -m lectionary_engines run collision "Romans 8:28-39"

# Manual paste (if you have text from another source)
python3 -m lectionary_engines paste threshold
```

The tool will generate a complete study (2500-5000 words depending on engine) and save it to the `outputs/` directory.

**Supported translations**: NRSVue (default), NIV, CEB, NLT, MSG

## For Testers / Beta Users

Want to try this out? Here's the fastest path:

1. **Get an Anthropic API key** (free tier available): https://console.anthropic.com/
2. **Clone this repo**: `git clone https://github.com/cdhtx/lectionary-engines.git`
3. **Install**: `cd lectionary-engines && pip3 install -r requirements.txt`
4. **Configure**: `cp .env.example .env` then add your API key to `.env`
5. **Run**: `python3 -m lectionary_engines moravian threshold`

That's it! You'll get today's Moravian Daily Text interpreted through the Threshold engine.

**What to test:**
- Try all three engines: `threshold`, `palimpsest`, `collision`
- Try different commands: `moravian`, `rcl`, `run`
- Check the visual formatting - each engine has a unique aesthetic
- Notice Layer 4 in Palimpsest - the tone should shift to contemplative/mystical

**Feedback welcome on:**
- Theological depth and accuracy
- Practical usefulness of the practices
- Visual presentation and readability
- Any bugs or rough edges

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

## The Three Engines

### Threshold Engine - Archaeological Excavation 🏛️
Four progressive thresholds (2500-3500 words):
1. **Archaeological Dive** - Historical context, original languages, ancient world
2. **Theological Combustion** - Challenge traditional assumptions
3. **Present Friction** - Collision with contemporary life
4. **Embodied Practice** - Concrete daily practices
5. **Tech Touchpoint** - Digital tool to sustain the insight

*Visual style*: Depth markers, Latin threshold names, earth-tone colors

### Palimpsest Engine - Sacred Manuscript 📜
Five hermeneutical layers (3000-4000 words):
1. **פ Peshat** - Plain sense (scholarly-economical)
2. **ר Remez** - Hints & allusions (connective-exploratory)
3. **ד Derash** - Interpretation & inquiry (survey-engaged)
4. **ס Sod** - Mystery (mystical-poetic-spacious) *[tone shifts here]*
5. **י Incarnation** - Embodied practice (practical-empowering)

*Visual style*: Hebrew letters, ornamental borders, purple/magenta colors

### Collision Engine - Futuristic Console 🔮
Five-step collision process (3000-5000 words):
1. **Anchor in Antiquity** - Deep exegesis
2. **Collide with Now** - 5 random collision vectors (scientific, cultural, philosophical, technological, personal)
3. **Navigate the Rupture** - Hold contradictions
4. **Crystallize the Insight** - Poetic refrain emerges
5. **Release into Future** - Generative outputs

*Visual style*: Console aesthetic, futuristic formatting

## CLI Commands

### Main Commands

```bash
# Moravian Daily Text (fetches all 5 daily passages)
python3 -m lectionary_engines moravian <engine>

# Revised Common Lectionary
python3 -m lectionary_engines rcl <engine> [--reading ot|psalm|epistle|gospel]

# Specific Bible passage
python3 -m lectionary_engines run <engine> "Reference" [--translation NRSVue|NIV|CEB|NLT|MSG]

# Manual paste
python3 -m lectionary_engines paste <engine>
```

### Utility Commands

```bash
# Show configuration
python3 -m lectionary_engines config

# List all saved studies
python3 -m lectionary_engines list

# Display a saved study
python3 -m lectionary_engines show outputs/threshold_john-3-16-21.md
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

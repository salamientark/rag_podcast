# RAG Podcast Project

A RAG (Retrieval-Augmented Generation) system for podcast content analysis, featuring automated episode ingestion, transcription, and AI-powered processing.

## Overview

This project provides tools to:
- **Sync podcast episodes** from RSS feeds to a local database
- **Download audio files** from podcast episodes
- **Transcribe audio** with speaker identification
- **Process transcripts** using LLM services for analysis and Q&A

## Project Structure

```
rag_podcast/
├── src/
│   ├── db/              # Database models and connection management
│   ├── ingestion/       # RSS feed sync and audio download tools
│   ├── transcription/   # Audio transcription with speaker mapping
│   ├── llm/             # LLM integration (OpenAI, etc.)
│   └── utils/           # Shared utilities (logging, etc.)
├── alembic/             # Database migrations
├── data/                # Data storage (audio, transcripts, database)
├── logs/                # Application logs
└── examples/            # Usage examples
```

## Requirements

- Python >= 3.13
- `uv` package manager (recommended)

## Setup

1. **Install dependencies**:
   ```bash
   uv sync
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Setup database**:
   ```bash
   uv run alembic upgrade head
   ```

## Usage

### Episode Ingestion

#### Sync RSS Feed to Database

Fetch episodes from the podcast RSS feed and store metadata in the database:

```bash
# Sync last 30 days (default)
uv run -m src.ingestion.sync_episodes

# Sync all episodes (full history)
uv run -m src.ingestion.sync_episodes --full-sync

# Sync last 60 days
uv run -m src.ingestion.sync_episodes --days 60

# Sync only 5 most recent episodes
uv run -m src.ingestion.sync_episodes --limit 5

# Dry run (preview without saving)
uv run -m src.ingestion.sync_episodes --dry-run --limit 5

# Verbose output with debug logging
uv run -m src.ingestion.sync_episodes --verbose
```

#### Download Audio Files

Download MP3 audio files for episodes in the database:

```bash
# Download all missing episodes
uv run -m src.ingestion.audio_scrap

# Download 5 most recent missing episodes
uv run -m src.ingestion.audio_scrap --limit 5

# Dry run (show what would be downloaded)
uv run -m src.ingestion.audio_scrap --dry-run

# Verbose output with detailed logging
uv run -m src.ingestion.audio_scrap --verbose

# Custom audio directory
uv run -m src.ingestion.audio_scrap --audio-dir /path/to/audio
```

### Transcription

Transcribe audio files with speaker identification:

```bash
# Transcribe audio files
uv run -m src.transcription

# Additional options (see src/transcription/ for details)
uv run -m src.transcription --help
```

### Database Management

#### Apply Migrations

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Rollback one migration
uv run alembic downgrade -1

# View migration history
uv run alembic history
```

#### Create New Migrations

```bash
# Auto-generate migration from model changes
uv run alembic revision --autogenerate -m "description of changes"

# Create empty migration template
uv run alembic revision -m "description"
```

### Code Quality

#### Linting

```bash
# Check for issues
uv run ruff check

# Auto-fix issues
uv run ruff check --fix
```

#### Formatting

```bash
# Format code
uv run ruff format
```

## Development

### Logging

This project uses a centralized logging system with flexible decorators. See [src/logger/README.md](src/logger/README.md) for detailed documentation on:
- Setting up loggers
- Using logging decorators
- Customizing log output
- Examples and best practices

Quick example:
```python
from src.logger import setup_logging, log_function

logger = setup_logging("my_module", "logs/my_module.log")

@log_function(logger_name="my_module", log_execution_time=True)
def my_function():
    logger.info("Processing...")
```

### Adding New Features

1. Create your module in the appropriate `src/` subdirectory
2. Use the centralized logging utilities from `src.utils`
3. Follow the code style guidelines in `AGENTS.md`
4. Update database models if needed and create migrations
5. Add examples and documentation

## Common Workflows

### Complete Setup for New Episodes

```bash
# 1. Sync latest episodes from RSS feed
uv run -m src.ingestion.sync_episodes --days 30

# 2. Download missing audio files
uv run -m src.ingestion.audio_scrap --limit 10

# 3. Transcribe new audio
uv run -m src.transcription
```

### Testing Before Production Run

```bash
# Preview what would be synced/downloaded without making changes
uv run -m src.ingestion.sync_episodes --dry-run --limit 5
uv run -m src.ingestion.audio_scrap --dry-run --limit 5
```

### Monitoring and Logs

Check logs in the `logs/` directory:
- `logs/sync_episodes.log` - RSS feed sync operations
- `logs/audio_download.log` - Audio download operations
- `logs/database.log` - Database operations
- Custom log files for specific modules

## Troubleshooting

### Database Issues

```bash
# Check current migration status
uv run alembic current

# Reset to a specific version
uv run alembic downgrade <revision>
uv run alembic upgrade head
```

### Audio Download Issues

- Check network connectivity
- Verify episode URLs in database
- Check `logs/audio_download.log` for detailed error messages
- Try with `--verbose` flag for more information

### Import Errors

Make sure you're using `uv run` prefix for all commands to ensure proper environment activation.

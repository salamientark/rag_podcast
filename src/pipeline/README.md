# Pipeline Module

Backend pipeline for orchestrating the complete podcast processing workflow.

## Overview

The pipeline module coordinates all stages from RSS feed to vector embeddings:
1. **Sync** - Fetch episode metadata from RSS feed
2. **Download** - Download audio files
3. **Transcribe** - Transcribe audio with speaker diarization
4. **Chunk** - Split transcripts for RAG
5. **Embed** - Generate and store embeddings in Qdrant

## Usage

### Basic Usage (Required: --podcast or --feed-url)

```bash
# Using podcast name (from database)
uv run -m src.pipeline --podcast "Le rendez-vous Tech" --full
uv run -m src.pipeline --podcast "Le rendez-vous Tech" --limit 5

# Using custom RSS feed URL (auto-detects podcast name)
uv run -m src.pipeline --feed-url "https://feeds.example.com/podcast.xml" --full
uv run -m src.pipeline --feed-url "https://feeds.example.com/podcast.xml" --limit 5

# Process specific episodes (by episode_id within podcast)
uv run -m src.pipeline --podcast "Le rendez-vous Tech" --episode-id 672 680
```

### Advanced Options

```bash
# Run specific stages only
uv run -m src.pipeline --podcast "Le rendez-vous Tech" --stages transcribe,embed --limit 10

# Force reprocessing
uv run -m src.pipeline --podcast "Le rendez-vous Tech" --episode-id 672 --force

# Dry run (preview)
uv run -m src.pipeline --feed-url "https://feeds.example.com/podcast.xml" --dry-run --verbose
```

## Available Stages

| Stage | Description |
|-------|-------------|
| `synced` | Episode metadata in database |
| `audio_downloaded` | Audio file downloaded |
| `raw_transcript` | Initial transcription complete |
| `formatted_transcript` | Speaker-identified transcript ready |
| `embedded` | Chunks embedded in Qdrant |

## CLI Options

### Required (choose one)
- `--podcast NAME` - Process episodes from specific podcast (case-insensitive)
- `--feed-url URL` - Use custom RSS feed (auto-detects podcast name, always syncs)

Note: --podcast and --feed-url are mutually exclusive

### Processing Modes (choose one)
- `--full` - Process all episodes from podcast
- `--episode-id ID [ID ...]` - Process specific episode(s) by episode_id (not UUID)
- `--limit N` - Process up to N episodes needing work (default: 5)

### Options
- `--stages STAGE,...` - Run only specific stages (comma-separated)
- `--force` - Force reprocessing of already completed stages
- `--dry-run` - Show what would be processed without executing
- `-v, --verbose` - Enable verbose logging output

## Features

### Features
- **Multi-episode Processing** - Handle single episodes or batches
- **Stage Selection** - Run specific stages or complete pipeline
- **Smart Resumption** - Skip already completed stages automatically
- **Force Reprocessing** - Override completion status when needed
- **Comprehensive Logging** - Detailed progress and error reporting
- **Dry Run Mode** - Preview operations without execution
- **Database Integration** - Automatic status tracking and updates

### Status
- ✅ **CLI Interface** - Complete argument parsing and validation
- ✅ **Orchestration Logic** - Core pipeline coordination implemented
- ✅ **Stage Wrappers** - Individual stage execution functions
- ✅ **Progress Tracking** - Detailed logging and status reporting
- ✅ **Error Handling** - Graceful failure handling and recovery
- ✅ **Force Reprocessing** - Skip completion checks when needed

## Architecture

```
src/pipeline/
├── __init__.py          # Module exports
├── __main__.py          # CLI entry point ✓
├── orchestrator.py      # Core pipeline logic (TODO)
└── stages.py            # Stage wrappers (TODO)
```

## Key Concepts

- **uuid**: Unique identifier for each episode (UUID7 format, primary key)
- **episode_id**: Sequential episode number within a podcast (not globally unique)
- **podcast**: Podcast name/identifier (groups episodes together)

Note: When using --episode-id, you specify the episode_id (e.g., 672), not the UUID.

## Error Handling

By default, the pipeline continues processing on errors:
```bash
# Continue on error (default behavior)
uv run -m src.pipeline --limit 10
```

## Logging

Logs are written to `logs/pipeline.log` with configurable verbosity:
```bash
# Standard logging
uv run -m src.pipeline --limit 5

# Verbose logging
uv run -m src.pipeline --limit 5 --verbose
```

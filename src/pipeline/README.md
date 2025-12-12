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

### Process All Episodes
```bash
uv run -m src.pipeline --full
```

### Process Specific Episode(s)
```bash
# Single episode
uv run -m src.pipeline --episode-id 672

# Multiple episodes
uv run -m src.pipeline --episode-id 672 680 685 690
```

### Process Limited Episodes
```bash
# Process last 5 episodes needing work
uv run -m src.pipeline --limit 5
```

### Stage Control

#### Run Specific Stages Only
```bash
uv run -m src.pipeline --stages raw_transcript,formatted_transcript,embedded --limit 10
```

### Options

#### Force Reprocessing
```bash
uv run -m src.pipeline --episode-id 672 --force
```

#### Dry Run (Preview)
```bash
uv run -m src.pipeline --dry-run --limit 10 --verbose
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

### Processing Modes (choose one)
- `--full` - Process all episodes in database
- `--episode-id ID [ID ...]` - Process specific episode(s) by ID
- `--limit N` - Process up to N episodes needing work

### Stage Control
- `--stages STAGE,...` - Run only specific stages (comma-separated)

### Options
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

## Examples

### Development Workflow
```bash
# Test argument parsing
uv run -m src.pipeline --help

# Preview what would be processed
uv run -m src.pipeline --dry-run --limit 5 --verbose

# Process single episode (when implemented)
uv run -m src.pipeline --episode-id 672

# Process multiple episodes
uv run -m src.pipeline --episode-id 672 673 680 --verbose

# Incremental processing
uv run -m src.pipeline --limit 10
```

### Production Workflow
```bash
# Daily incremental run
uv run -m src.pipeline --limit 50

# Full reprocessing with force
uv run -m src.pipeline --full --force

# Only embed new transcripts
uv run -m src.pipeline --stages embedded --limit 20
```

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

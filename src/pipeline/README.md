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

### Implemented (v0.1.0)
- ✓ Comprehensive argument parsing with validation
- ✓ Multiple episode ID support
- ✓ Stage validation against ProcessingStage enum
- ✓ Database connectivity check
- ✓ Episode ID validation
- ✓ Dry-run mode with detailed preview
- ✓ Mutually exclusive argument validation
- ✓ Database status reporting
- ✓ Logging infrastructure

### To Be Implemented
- Pipeline orchestration logic (`orchestrator.py`)
- Stage wrapper functions (`stages.py`)
- Progress tracking and reporting
- Error handling and recovery
- Stage skipping based on completion status
- Force reprocessing logic

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

## Next Steps

1. Implement `orchestrator.run_pipeline()` function
2. Implement stage wrappers in `stages.py`
3. Add progress tracking and reporting
4. Integrate with existing modules (ingestion, transcription, embedder)
5. Add comprehensive error handling
6. Implement force reprocessing logic
7. Add unit tests

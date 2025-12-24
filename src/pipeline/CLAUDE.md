# Pipeline Module

## Overview

The pipeline module orchestrates the complete podcast processing workflow, from RSS feed ingestion to vector embedding storage. It coordinates five distinct processing stages in sequence.

**Core workflow:**

1. RSS feed sync (metadata to SQL database)
2. Audio download (from podcast feeds)
3. Transcription (with speaker diarization)
4. Speaker mapping & formatting (LLM-based identification)
5. Embedding generation (chunking + vector storage in Qdrant)

## Key Files

### `orchestrator.py`

Central control logic for the pipeline.

**Key functions:**

- `run_pipeline()`: Main entry point, orchestrates all stages
- `fetch_db_episodes()`: Retrieves episodes ordered by published date
- `filter_episode()`: Filters by ID, limit, processing stage, or podcast name

### `stages.py`

Wrapper functions for each pipeline stage with standardized error handling, logging, and database updates.

**Stage functions:**

- `run_sync_stage()`: Fetches RSS feed, syncs to database
- `run_download_stage()`: Downloads audio files
- `run_raw_transcript_stage()`: Generates raw transcripts with diarization
- `run_speaker_mapping_stage()`: Uses LLM to identify speakers
- `run_formatted_transcript_stage()`: Creates readable transcripts
- `run_embedding_stage()`: Chunks transcripts and generates embeddings

### `__main__.py`

CLI interface with comprehensive argument parsing.

## Stage Mapping (CLI → ProcessingStage)

```python
"sync" → ProcessingStage.SYNCED
"download" → ProcessingStage.AUDIO_DOWNLOADED
"raw_transcript" → ProcessingStage.RAW_TRANSCRIPT
"format_transcript" → ProcessingStage.FORMATTED_TRANSCRIPT
"embed" → ProcessingStage.EMBEDDED
```

## Critical Contracts (for reviews)

### Episode identity

- SQL primary key is `Episode.uuid`
- `episode_id` is per-podcast and not globally unique
- Pipeline filtering by `--episode-id` is scoped to the selected podcast

### Stage monotonicity

- Pipeline stages must only move forward.
- Downgrades are only allowed in reconciliation workflows.

### File layout expectations

Pipeline stage wrappers currently assume a per-podcast workspace layout:

- Audio: `data/{podcast}/audio/`
- Transcripts: `data/{podcast}/transcripts/episode_{episode_id:03d}/`
- Embeddings: `data/{podcast}/embeddings/`

If you change these conventions, you must update:

- stage wrappers
- reconciliation logic
- documentation contracts

### Qdrant payload requirements

Embedding stage must store payload fields required by query:

- `db_uuid`, `podcast`, `episode_id`, `title`, `chunk_index`, `total_chunks`, `text`

## Gotchas

1. **Case sensitivity**: Podcast filtering is case-insensitive, but DB stores canonical names.
2. **Feed URL vs Podcast**: Mutually exclusive. `feed_url` always triggers sync.
3. **Stage dependencies**: Stages must run in order. Can't skip prerequisites.
4. **Dictionary conversion**: Episodes converted from SQLAlchemy models to dicts via `to_dict()`.

## Usage Examples

```bash
uv run -m src.pipeline --podcast "Le rendez-vous Tech" --limit 5
uv run -m src.pipeline --feed-url "https://example.com/feed.xml" --episode-id 672 680
uv run -m src.pipeline --podcast "Le rendez-vous Tech" --stages embed --full
uv run -m src.pipeline --feed-url "https://example.com/feed.xml" --dry-run --verbose
```

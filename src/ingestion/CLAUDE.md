# Ingestion Module

## Overview

The ingestion module handles the complete pipeline for fetching, downloading, and reconciling podcast episode data from RSS feeds. It manages the initial stages of the RAG podcast system.

## Key Scripts

### sync_episodes.py

**Purpose**: Fetch episode metadata from RSS feeds and sync to database

**Key Functions:**

- `fetch_podcast_episodes(feed_url)` - Parses RSS XML, extracts episode metadata, auto-generates UUID7
- `filter_episodes(episodes, full_sync, days_back, limit)` - Date-based filtering, sorts chronologically (oldest first)
- `sync_to_database(episodes, dry_run)` - Upserts episodes, skips existing by `(podcast, audio_url)`

**Usage:**

```bash
uv run -m src.ingestion.sync_episodes --full-sync
uv run -m src.ingestion.sync_episodes --days 30
uv run -m src.ingestion.sync_episodes --limit 5 --dry-run
```

### audio_scrap.py

**Purpose**: Download audio files from RSS feed URLs

**Key Functions:**

- `download_episode(episode_number, title, url, workspace)` - Downloads with browser headers, validates >100KB
- `download_missing_episodes(audio_dir, limit, dry_run)` - Main orchestrator

**Filename Convention:** `episode_{id:03d}_{sanitized_title}.mp3`

### reconcile.py

**Purpose**: Ensure database records match filesystem and Qdrant state

**Key Functions:**

- `reconcile_filesystem(episodes, audio_dir, transcript_dir, dry_run)` - Syncs DB with files
- `reconcile_qdrant(episodes, collection_name, dry_run)` - Verifies embedding status
- `extract_transcript_metadata(raw_transcript_path)` - Parses AssemblyAI JSON for duration/confidence

**Usage:**

```bash
uv run -m src.ingestion.reconcile --all
uv run -m src.ingestion.reconcile --episodes 670 671
uv run -m src.ingestion.reconcile --days 7 --skip-qdrant
```

## Processing Stages

1. **SYNCED** - Episode metadata in database
2. **AUDIO_DOWNLOADED** - Audio file downloaded
3. **RAW_TRANSCRIPT** - AssemblyAI raw JSON exists
4. **FORMATTED_TRANSCRIPT** - Speaker-labeled text exists
5. **EMBEDDED** - Embeddings stored in Qdrant

## Gotchas

1. **Episode ID Assignment**: IDs assigned sequentially by RSS order (oldest first). Immutable once assigned.

2. **Feedpress.me Redirects**: Audio URLs require browser headers to avoid 403 errors. Handled automatically.

3. **Filename Sanitization**: Removes ALL punctuation, converts to lowercase, truncates at 100 chars.

4. **Duplicate Detection**: Uses `(podcast, audio_url)` tuple, NOT episode title or GUID.

5. **Processing Stage Progression**: Stages only move forward (except EMBEDDED verification).

6. **Database Session Management**: Uses `get_db_session()` context manager. Critical for avoiding "DetachedInstanceError".

7. **AssemblyAI Metadata**: Expected at `data/transcripts/episode_{id:03d}/raw_episode_{id}.json`.

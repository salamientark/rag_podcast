# Ingestion Module

Downloads podcast episodes from RSS feeds and saves audio files.

## Quick Start

```bash
# Sync episodes from RSS feed and download audio
uv run -m src.ingestion.sync_episodes --full-sync
uv run -m src.ingestion.audio_scrap
```

## Scripts

### `sync_episodes.py` - Fetch Episode Metadata

```bash
# Basic usage (last 30 days)
uv run -m src.ingestion.sync_episodes

# Sync all episodes
uv run -m src.ingestion.sync_episodes --full-sync

# Sync specific number
uv run -m src.ingestion.sync_episodes --limit 5
```

**Options:**
- `--full-sync` - Sync all episodes
- `--days N` - Sync last N days (default: 30)
- `--limit N` - Process only N episodes
- `--dry-run` - Preview without saving
- `--verbose` - Show detailed output

**What it does:**
- Fetches episode metadata from RSS feed
- Stores title, date, audio URL, description in database
- Skips duplicates automatically
- Log: `logs/sync_episodes.log`

### `reconcile.py` - Database Reconciliation

```bash
# Reconcile all episodes
uv run -m src.ingestion.reconcile --all

# Reconcile specific episodes
uv run -m src.ingestion.reconcile --episodes 670 671 672

# Reconcile recent episodes
uv run -m src.ingestion.reconcile --days 7

# Preview changes without saving
uv run -m src.ingestion.reconcile --all --dry-run

# Skip Qdrant verification (filesystem only)
uv run -m src.ingestion.reconcile --all --skip-qdrant
```

**Options:**
- `--all` - Reconcile ALL episodes (required flag for safety)
- `--episodes ID [ID ...]` - Specific episode IDs to reconcile
- `--days N` - Reconcile episodes from last N days
- `--dry-run` - Preview changes without committing to database
- `--skip-qdrant` - Skip Qdrant verification (filesystem only)
- `--verbose` - Show detailed output

**What it does:**
- Scans filesystem for episode files (audio, transcripts, speaker mappings)
- Extracts metadata from transcript JSON files (duration, confidence)
- Updates database fields to match filesystem reality:
  - `audio_file_path`
  - `raw_transcript_path`
  - `formatted_transcript_path`
  - `speaker_mapping_path` ✨
  - `transcript_duration` ✨
  - `transcript_confidence` ✨
  - `processing_stage`
- Verifies embeddings in Qdrant vector database
- Upgrades stage to `EMBEDDED` if found in Qdrant
- Downgrades stage if marked `EMBEDDED` but not in Qdrant
- Log: `logs/reconcile.log`

**When to use:**
- After manual file operations (moving/copying episodes)
- Database got out of sync with filesystem
- After recovering from errors or crashes
- Verify which episodes are fully processed
- Check Qdrant embedding status

### `audio_scrap.py` - Download Audio Files

```bash
# Download all missing episodes
uv run -m src.ingestion.audio_scrap

# Download specific number
uv run -m src.ingestion.audio_scrap --limit 5

# Preview downloads
uv run -m src.ingestion.audio_scrap --dry-run
```

**Options:**
- `--limit N` - Download only N episodes
- `--audio-dir PATH` - Custom save directory (default: `data/audio`)
- `--dry-run` - Preview without downloading
- `--verbose` - Show detailed output

**What it does:**
- Downloads MP3 files for episodes in database
- Saves as `episode_001_Title.mp3` (zero-padded ID)
- Skips existing files automatically
- Retries failed downloads (3 attempts)
- Log: `logs/audio_download.log`

## Processing Stages

Episodes move through these stages:
1. `synced` - Metadata in database
2. `audio_downloaded` - Audio file downloaded
3. `raw_transcript` - Transcribed
4. `formatted_transcript` - Formatted
5. `embedded` - In vector database

## Common Tasks

**Initial setup:**
```bash
uv run -m src.ingestion.sync_episodes --full-sync
uv run -m src.ingestion.audio_scrap
```

**Daily updates:**
```bash
uv run -m src.ingestion.sync_episodes --days 7
uv run -m src.ingestion.audio_scrap
```

**Verify database consistency:**
```bash
# Check all episodes are in sync
uv run -m src.ingestion.reconcile --all

# Fix specific episodes
uv run -m src.ingestion.reconcile --episodes 670 671 672

# Check what would change (safe preview)
uv run -m src.ingestion.reconcile --all --dry-run
```

**Testing:**
```bash
uv run -m src.ingestion.sync_episodes --limit 3 --dry-run
uv run -m src.ingestion.audio_scrap --limit 3
```

**Fix database after manual changes:**
```bash
# Reconcile all episodes with filesystem and Qdrant
uv run -m src.ingestion.reconcile --all
```

## Environment Setup

Required in `.env`:
```env
FEED_URL=https://feeds.feedpress.me/your-podcast-feed
DATABASE_URL=sqlite:///data/podcast.db
```

## Troubleshooting

**No episodes found:**
- Check `FEED_URL` in `.env`
- Try `--full-sync` flag
- Verify feed: `curl $FEED_URL`

**Downloads fail:**
- Check logs: `tail -f logs/audio_download.log`
- Verify disk space: `df -h`
- Re-run (skips successful downloads)

**Database errors:**
- Run migrations: `uv run alembic upgrade head`
- Check file exists: `ls -lh data/podcast.db`

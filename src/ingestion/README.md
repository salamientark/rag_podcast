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

# Fix database status from files
uv run -m src.ingestion.sync_episodes --reconcile --full-sync
```

**Options:**
- `--full-sync` - Sync all episodes
- `--days N` - Sync last N days (default: 30)
- `--limit N` - Process only N episodes
- `--reconcile` - Update database status from filesystem
- `--dry-run` - Preview without saving
- `--verbose` - Show detailed output

**What it does:**
- Fetches episode metadata from RSS feed
- Stores title, date, audio URL, description in database
- Skips duplicates automatically
- Log: `logs/sync_episodes.log`

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

**Testing:**
```bash
uv run -m src.ingestion.sync_episodes --limit 3 --dry-run
uv run -m src.ingestion.audio_scrap --limit 3
```

**Fix database after manual changes:**
```bash
uv run -m src.ingestion.sync_episodes --reconcile --full-sync
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

"""
Ingestion package for podcast RAG system.

This package contains scripts for ingesting podcast episodes from RSS feeds
and downloading audio files. The ingestion pipeline consists of:

1. RSS Feed Sync (sync_episodes.py):
   - Fetches episode metadata from RSS feed
   - Stores episodes in database
   - Reconciles episode status from filesystem

2. Audio Download (audio_scrap.py):
   - Downloads audio files from RSS URLs
   - Handles feedpress.me redirects
   - Stores files with consistent naming convention

Modules:
    sync_episodes: RSS feed synchronization and status reconciliation
    audio_scrap: Audio file download and management

Usage:
    # Sync episodes from RSS
    uv run -m src.ingestion.sync_episodes --full-sync

    # Download missing audio files
    uv run -m src.ingestion.audio_scrap --limit 5

    # Reconcile episode status from filesystem
    uv run -m src.ingestion.sync_episodes --reconcile --limit 10
"""

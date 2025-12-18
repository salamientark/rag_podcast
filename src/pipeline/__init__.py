"""
Podcast processing pipeline module.

This module orchestrates the complete podcast processing workflow:
    1. RSS feed sync (src.ingestion.sync_episodes)
    2. Audio download (src.ingestion.audio_scrap)
    3. Transcription (src.transcription)
    4. Chunking (src.chunker)
    5. Embedding (src.embedder)

Usage:
    # CLI interface
    uv run -m src.pipeline --full
    uv run -m src.pipeline --episode-id 672
    uv run -m src.pipeline --limit 5

    # Programmatic interface (to be implemented)
    from src.pipeline import run_pipeline
    result = run_pipeline(mode="full", dry_run=False)
"""

__version__ = "0.1.0"

# Main pipeline functions
from .orchestrator import (
    run_pipeline,
    fetch_db_episodes,
    get_last_requested_stage,
    filter_episode,
)
from .stages import (
    run_sync_stage,
    run_download_stage,
    run_raw_trancript_stage,
    run_speaker_mapping_stage,
    run_formatted_trancript_stage,
    run_embedding_stage,
    update_episode_in_db,
)

__all__ = [
    # Main pipeline orchestration
    "run_pipeline",
    "fetch_db_episodes",
    "get_last_requested_stage",
    "filter_episode",
    # Stage functions
    "run_sync_stage",
    "run_download_stage",
    "run_raw_trancript_stage",
    "run_speaker_mapping_stage",
    "run_formatted_trancript_stage",
    "run_embedding_stage",
    "update_episode_in_db",
]

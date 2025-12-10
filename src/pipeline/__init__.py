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

# TODO: Import and export main pipeline functions once implemented
# from .orchestrator import run_pipeline, get_episode_stage
# from .stages import (
#     run_sync_stage,
#     run_download_stage,
#     run_transcription_stage,
#     run_chunking_stage,
#     run_embedding_stage,
# )

__all__ = [
    # Main exports will be added here
    # "run_pipeline",
    # "get_episode_stage",
]

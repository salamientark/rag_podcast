import logging

from typing import Optional, Dict, Any

from src.logger import log_function
from src.db import ProcessingStage, get_db_session, Episode
from .stages import (
    run_sync_stage,
    run_download_stage,
    run_transcription_stage,
    run_summarization_stage,
    run_embedding_stage,
)

DEFAULT_LIMIT_NBR = 5

ARG_TO_PROCESSING_STAGE = {
    "sync": ProcessingStage.SYNCED,
    "download": ProcessingStage.AUDIO_DOWNLOADED,
    "raw_transcript": ProcessingStage.RAW_TRANSCRIPT,
    "format_transcript": ProcessingStage.FORMATTED_TRANSCRIPT,
    "embed": ProcessingStage.EMBEDDED,
}


def get_last_requested_stage(stages: list[str]) -> ProcessingStage:
    """
    Get the last requested stage from the list of stages.

    Used in pipeline process to filter episodes to process.

    Args:
        stages (list[str]): List of stage names.

    Returns:
        ProcessingStage: The last requested processing stage.
    """
    stage_order = list(ProcessingStage)
    last_stage = None
    for stage in stages:
        converted_stage = ARG_TO_PROCESSING_STAGE.get(stage)
        if converted_stage is None:
            continue
        if last_stage is None:
            last_stage = converted_stage
            continue
        converted_stage_index = stage_order.index(converted_stage)
        target_stage_index = stage_order.index(last_stage)
        if converted_stage_index > target_stage_index:
            last_stage = converted_stage
    return last_stage


def filter_episode(
    podcast_id: int,
    episodes_id: Optional[list[int]] = None,
    limit: Optional[int] = None,
    force: bool = False,
) -> list[Dict[str, Any]]:
    """
    Query episodes from the database by podcast ID, specific episode IDs, or maximum count.

    Parameters:
        podcast_id (int): Include only episodes belonging to this podcast.
        episodes_id (Optional[list[int]]): If provided, include only episodes with these IDs.
        limit (Optional[int]): If provided and `episodes_id` is not, include up to this many non-EMBEDDED episodes (defaults to 5).
        force (bool): If True, include all episodes regardless of processing stage.

    Returns:
        list[Dict[str, Any]]: Episodes that match the provided filters.
    """
    if limit is None and episodes_id is None:
        limit = DEFAULT_LIMIT_NBR

    with get_db_session() as session:
        if limit is not None:
            if not force:
                episodes = (
                    session.query(Episode)
                    .filter(
                        Episode.podcast_id == podcast_id,
                        Episode.processing_stage.not_in(
                            [ProcessingStage.EMBEDDED, ProcessingStage.ERROR]
                        ),
                    )
                    .order_by(Episode.published_date.desc())
                    .limit(limit)
                    .all()
                )
            else:
                episodes = (
                    session.query(Episode)
                    .filter(
                        Episode.podcast_id == podcast_id,
                    )
                    .order_by(Episode.published_date.desc())
                    .limit(limit)
                    .all()
                )
        else:
            if not force:
                episodes = (
                    session.query(Episode)
                    .filter(
                        Episode.podcast_id == podcast_id,
                        Episode.episode_id.in_(episodes_id),
                        Episode.processing_stage.not_in(
                            [ProcessingStage.EMBEDDED, ProcessingStage.ERROR]
                        ),
                    )
                    .all()
                )
            else:
                episodes = (
                    session.query(Episode)
                    .filter(
                        Episode.podcast_id == podcast_id,
                        Episode.episode_id.in_(episodes_id),
                    )
                    .all()
                )
        filtered_episodes = [ep.to_dict() for ep in episodes]

    return filtered_episodes


@log_function(logger_name="pipeline", log_execution_time=True)
async def run_pipeline(
    episodes_id: Optional[list[int]] = None,
    limit: Optional[int] = None,
    stages: Optional[list[str]] = None,
    dry_run: bool = False,
    verbose: bool = False,
    use_cloud_storage: bool = False,
    podcast_id: Optional[int] = None,
    podcast_name: Optional[str] = None,
    feed_url: Optional[str] = None,
    force: bool = False,
):
    """
    Orchestrates the end-to-end podcast processing pipeline across configurable stages.

    Runs sync, download, transcription, formatting (including speaker mapping), and embedding stages as requested.

    Parameters:
        episodes_id (list[int] | None): Specific episode_id values to process within the selected podcast; when provided the pipeline restricts processing to these episodes.
        limit (int | None): Maximum number of episodes to process when `episodes_id` is not provided.
        stages (list[str] | None): Ordered list of stage names to run (None runs all stages).
        dry_run (bool): If true, run in preview mode without making persistent changes.
        verbose (bool): If true, enable more detailed logging.
        use_cloud_storage (bool): If true, use cloud storage paths and uploads where supported.
        podcast_id (int | None): Podcast ID to filter episodes.
        podcast_name (str | None): Podcast name for display/logging purposes.
        feed_url (str | None): RSS feed URL to sync from.
        force (bool): If true, force reprocessing of already completed stages.
    """
    logger = logging.getLogger("pipeline")
    all_failures = []

    try:
        # Run sync Stage
        logger.info("=== PIPELINE STARTED ===")

        if podcast_id is None:
            logger.error("podcast_id must be provided")
            raise ValueError("podcast_id must be provided")

        logger.info(f"Processing podcast: {podcast_name} (id={podcast_id})")

        # Run sync stage if requested
        if stages is None or "sync" in stages:
            if feed_url:
                run_sync_stage(podcast_id=podcast_id, feed_url=feed_url)
            else:
                logger.info("Skipping sync stage (no feed_url provided)")

        # Filter episodes to process
        episodes_to_process = filter_episode(podcast_id, episodes_id, limit, force)
        if len(episodes_to_process) == 0:
            logger.info("No episodes found to process. Exiting pipeline.")
            logger.info("=== PIPELINE COMPLETED SUCCESSFULLY ===")
            return []

        # Run download audio stage
        if force or stages is None or "download" in stages:
            episodes_to_process, failed = run_download_stage(
                episodes_to_process, use_cloud_storage
            )
            all_failures.extend(failed)

        # Run transcription stage (Gemini: transcription + speaker identification)
        # Accepts both "raw_transcript" and "format_transcript" for backward compatibility
        if (
            force
            or stages is None
            or "raw_transcript" in stages
            or "format_transcript" in stages
        ):
            episodes_to_process, failed = run_transcription_stage(
                episodes_to_process, use_cloud_storage, force
            )
            all_failures.extend(failed)
            episodes_to_process, failed_summaries = await run_summarization_stage(
                episodes_to_process, force
            )
            all_failures.extend(failed_summaries)

        # Run embedding stage
        if force or stages is None or "embed" in stages:
            episodes_to_process, failed = run_embedding_stage(episodes_to_process)
            all_failures.extend(failed)

        logger.info("=== PIPELINE COMPLETED SUCCESSFULLY ===")
        return all_failures

    except Exception:
        logger.error("=== PIPELINE FAILED WITH EXCEPTION ===", exc_info=True)
        raise

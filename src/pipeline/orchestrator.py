import logging

from typing import Optional, Dict, Any

from src.logger import log_function
from src.db import ProcessingStage, get_db_session, Episode
from .stages import (
    run_sync_stage,
    run_download_stage,
    run_raw_transcript_stage,
    run_speaker_mapping_stage,
    run_formatted_transcript_stage,
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
    podcast: str,
    episodes_id: Optional[list[int]] = None,
    limit: Optional[int] = None,
    force: bool = False,
) -> list[Dict[str, Any]]:
    """
    Query episodes from the database by podcast name, specific episode IDs, or maximum count.

    Podcast filtering is case-insensitive. If `episodes_id` is provided, returns only episodes whose `episode_id` is in that list. If `limit` is provided (or defaults to 5), returns up to `limit` non-EMBEDDED episodes ordered by publication date descending.

    Parameters:
        podcast (str): Include only episodes whose podcast name matches this value (case-insensitive).
        episodes_id (Optional[list[int]]): If provided, include only episodes with these IDs.
        limit (Optional[int]): If provided and `episodes_id` is not, include up to this many non-EMBEDDED episodes (defaults to 5).

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
                        Episode.podcast.ilike(podcast),
                        Episode.processing_stage != ProcessingStage.EMBEDDED,
                    )
                    .order_by(Episode.published_date.desc())
                    .limit(limit)
                    .all()
                )
            else:
                episodes = (
                    session.query(Episode)
                    .filter(
                        Episode.podcast.ilike(podcast),
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
                        Episode.podcast.ilike(podcast),
                        Episode.episode_id.in_(episodes_id),
                        Episode.processing_stage != ProcessingStage.EMBEDDED,
                    )
                    .all()
                )
            else:
                episodes = (
                    session.query(Episode)
                    .filter(
                        Episode.podcast.ilike(podcast),
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
    podcast: Optional[str] = None,
    feed_url: Optional[str] = None,
    force: bool = False,
):
    """
    Orchestrates the end-to-end podcast processing pipeline across configurable stages.

    Runs sync, download, transcription, formatting (including speaker mapping), and embedding stages as requested; when `feed_url` is provided the sync stage is always run and the podcast name is extracted and used for filtering, when only `podcast` is provided sync runs only if requested, and a ValueError is raised if neither `feed_url` nor `podcast` is supplied.

    Parameters:
        episodes_id (list[int] | None): Specific episode_id values to process within the selected podcast; when provided the pipeline restricts processing to these episodes.
        limit (int | None): Maximum number of episodes to process when `episodes_id` is not provided.
        stages (list[str] | None): Ordered list of stage names to run (None runs all stages).
        dry_run (bool): If true, run in preview mode without making persistent changes.
        verbose (bool): If true, enable more detailed logging.
        use_cloud_storage (bool): If true, use cloud storage paths and uploads where supported.
        podcast (str | None): Podcast name to filter episodes; used when `feed_url` is not provided. If both `feed_url` and `podcast` are given, `feed_url` takes precedence.
        feed_url (str | None): RSS feed URL to sync from; when provided the function runs the sync stage to extract the podcast name and uses it for filtering.
    """
    logger = logging.getLogger("pipeline")

    try:
        # Run sync Stage
        logger.info("=== PIPELINE STARTED ===")

        # Handle feed_url vs podcast
        if feed_url:
            # Always run sync stage when feed_url is provided
            logger.info(f"Using custom feed URL: {feed_url}")
            extracted_podcast = run_sync_stage(feed_url=feed_url)
            logger.info(f"Extracted podcast name from feed: {extracted_podcast}")
            podcast = extracted_podcast
        elif podcast:
            logger.info(f"Filtering by podcast: {podcast}")
            # Only run sync if stage is requested
            if stages is None or "sync" in stages:
                run_sync_stage()
        else:
            logger.error("Either feed_url or podcast must be provided")
            raise ValueError("Either feed_url or podcast must be provided")

        # Filter episodes to process
        episodes_to_process = filter_episode(podcast, episodes_id, limit, force)
        if len(episodes_to_process) == 0:
            logger.info("No episodes found to process. Exiting pipeline.")
            logger.info("=== PIPELINE COMPLETED SUCCESSFULLY ===")
            return

        # Run download audio stage
        if force or stages is None or "download" in stages:
            episodes_to_process = run_download_stage(
                episodes_to_process, use_cloud_storage
            )

        # Run raw transcript stage
        if force or stages is None or "raw_transcript" in stages:
            episodes_to_process = run_raw_transcript_stage(episodes_to_process)

        # Run formatted transcript stage (Speaker mapping included)
        if force or stages is None or "format_transcript" in stages:
            episodes_to_process = run_speaker_mapping_stage(episodes_to_process, force)
            episodes_to_process = run_formatted_transcript_stage(
                episodes_to_process, use_cloud_storage, force
            )
            await run_summarization_stage(episodes_to_process, force)

        # Run embedding stage
        if force or stages is None or "embed" in stages:
            run_embedding_stage(episodes_to_process)

        logger.info("=== PIPELINE COMPLETED SUCCESSFULLY ===")

    except Exception:
        raise

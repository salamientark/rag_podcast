import logging

from typing import Optional, Dict, Any

from src.logger import log_function
from src.db import ProcessingStage, fetch_db_episodes
from .stages import (
    run_sync_stage,
    run_download_stage,
    run_raw_transcript_stage,
    run_speaker_mapping_stage,
    run_formatted_transcript_stage,
    run_embedding_stage,
)


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
    episodes: list[Dict[str, Any]],
    episodes_id: Optional[list[int]] = None,
    limit: Optional[int] = None,
    stage: Optional[ProcessingStage] = ProcessingStage.EMBEDDED,
    podcast: Optional[str] = None,
) -> list[Dict[str, Any]]:
    """
    Filter a list of Episode Dictionnaries by podcast name, specific episode IDs, a maximum count, and target processing stage.

    Podcast filtering is applied first and is case-insensitive. If `episodes_id` is provided, returns only episodes whose `episode_id` is in that list. If `episodes_id` is not provided and `limit` is provided, returns up to `limit` episodes whose current processing stage is earlier than the specified `stage`, preserving the input order. If neither `episodes_id` nor `limit` is provided, returns the (optionally podcast-filtered) input list.

    Parameters:
        episodes (list[Dict[str, Any]]): Episodes to filter.
        episodes_id (Optional[list[int]]): If provided, include only episodes with these IDs.
        limit (Optional[int]): If provided and `episodes_id` is not, include up to this many episodes that are before `stage`.
        stage (Optional[ProcessingStage]): Target processing stage used when applying `limit`.
        podcast (Optional[str]): If provided, include only episodes whose podcast name matches this value (case-insensitive).

    Returns:
        list[Dict[str, Any]]: Episodes that match the provided filters.
    """
    logger = logging.getLogger("pipeline")

    # Filter by podcast first (case-insensitive)
    if podcast is not None:
        episodes = [ep for ep in episodes if ep["podcast"].lower() == podcast.lower()]
        logger.info(f"Filtered to {len(episodes)} episodes from podcast: {podcast}")

    filtered_episodes = []
    stage_order = list(ProcessingStage)

    # Select by IDs
    if episodes_id is not None:
        filtered_episodes = [ep for ep in episodes if ep.episode_id in episodes_id]
    # Select by limit
    elif limit is not None:
        episode_left = limit
        for ep in episodes:
            if episode_left <= 0:
                break
            current_stage_index = stage_order.index(ep["processing_stage"])
            target_stage_index = stage_order.index(stage)
            if current_stage_index < target_stage_index:
                filtered_episodes.append(ep)
                episode_left -= 1
    else:
        # Full mode - return all episodes
        filtered_episodes = episodes

    return filtered_episodes


@log_function(logger_name="pipeline", log_execution_time=True)
def run_pipeline(
    episodes_id: Optional[list[int]] = None,
    limit: Optional[int] = None,
    stages: Optional[list[str]] = None,
    dry_run: bool = False,
    verbose: bool = False,
    use_cloud_storage: bool = False,
    podcast: Optional[str] = None,
    feed_url: Optional[str] = None,
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
        # Get last requested stage if exist
        last_stage = ProcessingStage.EMBEDDED
        if stages is not None:
            last_stage = get_last_requested_stage(stages)

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
        episodes_to_process = filter_episode(
            fetch_db_episodes(),
            episodes_id=episodes_id,
            limit=limit,
            stage=last_stage,
            podcast=podcast,
        )

        # Run download audio stage
        if stages is None or "download" in stages:
            episodes_to_process = run_download_stage(
                episodes_to_process, use_cloud_storage
            )

        # Run raw transcript stage
        if stages is None or "raw_transcript" in stages:
            episodes_to_process = run_raw_transcript_stage(episodes_to_process)

        # Run formatted transcript stage (Speaker mapping included)
        if stages is None or "format_transcript" in stages:
            episodes_to_process = run_speaker_mapping_stage(episodes_to_process)
            episodes_to_process = run_formatted_transcript_stage(
                episodes_to_process, use_cloud_storage
            )

        # Run embedding stage
        if stages is None or "embed" in stages:
            run_embedding_stage(episodes_to_process)

        logger.info("=== PIPELINE COMPLETED SUCCESSFULLY ===")

    except Exception:
        raise

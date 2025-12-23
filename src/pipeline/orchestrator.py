import logging

from typing import Optional

from src.logger import log_function
from src.db import get_db_session, Episode, ProcessingStage
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


@log_function(logger_name="pipeline", log_execution_time=True)
def fetch_db_episodes() -> list[Episode]:
    """Fetch all episodes from the database.

    Returns:
        List of Episode objects from the database, sorted by published date descending.
    """
    logger = logging.getLogger("pipeline")
    logger.info("Fetching episodes from database...")
    with get_db_session() as session:
        episodes = session.query(Episode).order_by(Episode.published_date.desc()).all()
    logger.info(f"Fetched {len(episodes)} episodes from database.")
    return episodes


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
    episodes: list[Episode],
    episodes_id: Optional[list[int]] = None,
    limit: Optional[int] = None,
    stage: Optional[ProcessingStage] = ProcessingStage.EMBEDDED,
    podcast: Optional[str] = None,
) -> list[Episode]:
    """
    Filter episodes based on provided IDs, limit, stage, and podcast.

    Args:
        episodes (list[Episode]): List of Episode objects to filter.
        episodes_id (Optional[list[int]]): List of episode IDs to include. If None, include all.
        limit (Optional[int]): Maximum number of episodes to return. If None, no limit.
        stage (Optional[ProcessingStage]): Processing stage to filter by. If None, defaults to EMBEDDED.
        podcast (Optional[str]): Podcast name to filter by (case-insensitive). If None, include all podcasts.

    Returns:
        list[Episode]: Filtered list of Episode objects.
    """
    logger = logging.getLogger("pipeline")

    # Filter by podcast first (case-insensitive)
    if podcast is not None:
        episodes = [ep for ep in episodes if ep.podcast.lower() == podcast.lower()]
        logger.info(f"Filtered to {len(episodes)} episodes from podcast: {podcast}")

    filetered_episodes = []
    stage_order = list(ProcessingStage)

    # Select by IDs
    if episodes_id is not None:
        filetered_episodes = [ep for ep in episodes if ep.episode_id in episodes_id]
    # Select by limit
    elif limit is not None:
        episode_left = limit
        for ep in episodes:
            if episode_left <= 0:
                break
            current_stage_index = stage_order.index(ep.processing_stage)
            target_stage_index = stage_order.index(stage)
            if current_stage_index < target_stage_index:
                filetered_episodes.append(ep)
                episode_left -= 1
    else:
        # Full mode - return all episodes
        filetered_episodes = episodes

    return filetered_episodes


@log_function(logger_name="pipeline", log_execution_time=True)
def run_pipeline(
    episodes_id: Optional[list[int]] = None,
    limit: Optional[int] = None,
    stages: Optional[list[str]] = None,
    dry_run: bool = False,
    verbose: bool = False,
    use_cloud_storage: bool = False,
    podcast: Optional[str] = None,
):
    logger = logging.getLogger("pipeline")

    try:
        # Get last requested stage if exist
        last_stage = ProcessingStage.EMBEDDED
        if stages is not None:
            last_stage = get_last_requested_stage(stages)

        # Run sync Stage
        logger.info("=== PIPELINE STARTED ===")
        if podcast:
            logger.info(f"Filtering by podcast: {podcast}")

        if stages is None or "sync" in stages:
            run_sync_stage()

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
            audio_path = run_download_stage(episodes_to_process, use_cloud_storage)
        else:
            audio_path = [ep.audio_file_path for ep in episodes_to_process]

        # Run raw transcript stage
        if stages is None or "raw_transcript" in stages:
            raw_transcript_path = run_raw_transcript_stage(audio_path)
        else:
            raw_transcript_path = [ep.raw_transcript_path for ep in episodes_to_process]

        # Run formatted transcript stage (Speaker mapping included)
        if stages is None or "format_transcript" in stages:
            speaker_mapping_paths = run_speaker_mapping_stage(raw_transcript_path)

            transcript_with_mapping = [
                {"transcript": rt, "speaker_mapping": sm}
                for rt, sm in zip(raw_transcript_path, speaker_mapping_paths)
            ]
            formatted_transcript_paths = run_formatted_transcript_stage(
                transcript_with_mapping, use_cloud_storage
            )
        else:
            formatted_transcript_paths = [
                ep.formatted_transcript_path for ep in episodes_to_process
            ]

        # Run embedding stage
        if stages is None or "embed" in stages:
            run_embedding_stage(formatted_transcript_paths)

        logger.info("=== PIPELINE COMPLETED SUCCESSFULLY ===")

    except Exception:
        raise

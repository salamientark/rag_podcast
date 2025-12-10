"""
Pipeline stage wrapper functions.

Each function wraps existing module logic and provides:
- Standardized error handling
- Database updates
- Progress tracking
- Logging

To be implemented:
- run_sync_stage()
- run_download_stage()
- run_transcription_stage()
- run_chunking_stage()
- run_embedding_stage()
"""

# TODO: Implement stage wrappers
import logging
import os

from typing import Any

from src.logger import log_function
from src.db import Episode
from src.ingestion.sync_episodes import fetch_podcast_episodes, sync_to_database
from src.ingestion.audio_scrap import get_existing_files, generate_filename, download_episode


AUDIO_DIR = "data/audio"


@log_function(logger_name="pipeline", log_execution_time=True)
def run_sync_stage():
    """
    Sync RSS feed to SQL database.
    """
    logger = logging.getLogger("pipeline")
    episodes = []  # Placeholder for actual sync logic
    try:
        logger.info("Starting sync stage...")
        logger.info("Fetching podcast episodes from RSS feed...")
        episodes = fetch_podcast_episodes()
        if not episodes:
            logger.error("No episodes fetched during sync stage.")
            raise ValueError("No episodes fetched during sync stage.")

        logger.info(f"Fetched {len(episodes)} episodes. Syncing to database...")
        stats = sync_to_database(episodes)
        logger.info(
                f"\nSync stage completed: {stats['processed']} processed, {stats['added']} added, "
                f"{stats['skipped']} skipped, {stats['errors']} errors"
        )

    except Exception as e:
        logger.error(f"Sync stage failed: {e}")
        raise e



@log_function(logger_name="pipeline", log_execution_time=True)
def run_download_stage(episodes: list[Episode]) -> list[str]:
    """
    Download episode audio files.

    all_episode should be selected episode list from sync stage, only keeping those to be processed.

    Args:
        episodes (list[Episode]): List of episodes that will be proccessed

    Returns:
        list[str]: List of episode file names.
    """
    logger = logging.getLogger("pipeline")
    try:
        logger.info("Starting download stage...")
        # Get existing audio file
        existing_files = get_existing_files(AUDIO_DIR)
    
        # Find missing episodes and add path of existing episodes to list
        missing_episodes = []
        episodes_path_list = []
        for episode in episodes:
            print(f"DEBUG: episode: {episode}")
            ep_number = episode.id
            ep_title = episode.title
            expected_filename = generate_filename(
                ep_number, ep_title
            )
            if expected_filename not in existing_files:
                missing_episodes.append(episode)
            else:
                filename = generate_filename(ep_number, ep_title)
                filepath = os.path.join(AUDIO_DIR, filename)
                episodes_path_list.append(filepath)

        if not missing_episodes:
            logger.info("No missing episodes to download.")
            return episodes_path_list
        logger.info(f"Found {len(missing_episodes)} missing episodes to download.")
        
        for episode in missing_episodes:
            success, filepath = download_episode(
                episode.id,
                episode.title,
                episode.audio_url,
                AUDIO_DIR
            )

            if success:
                episodes_path_list.append(filepath)
            else:
                logger.warning(f"Failed to download episode {episode['id']}: {episode['title']}")


        logger.info("Download stage completed successfully.")
        return episodes_path_list

    except Exception as e:
        logger.error(f"Download stage failed: {e}")
        raise e


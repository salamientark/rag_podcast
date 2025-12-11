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
import json

from pathlib import Path
from typing import Any, Optional
from datetime import datetime

from src.logger import log_function
from src.db import Episode, get_db_session, ProcessingStage
from src.ingestion.sync_episodes import fetch_podcast_episodes, sync_to_database
from src.ingestion.audio_scrap import get_existing_files, generate_filename, download_episode
from src.transcription import get_episode_id_from_path, check_formatted_transcript_exists, transcribe_local_file
from src.transcription.transcript import transcribe_with_diarization


AUDIO_DIR = "data/audio"
TRANSCRIPT_DIR = "data/transcripts"


@log_function(logger_name="pipeline", log_execution_time=True)
def update_episode_in_db(
    episode_id: int,
    guid: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    published_date: Optional[datetime] = None,
    audio_url: Optional[str] = None,
    processing_stage: Optional[ProcessingStage] = None,
    audio_file_path: Optional[str] = None,
    raw_transcript_path: Optional[str] = None,
    speaker_mapping_path: Optional[str] = None,
    formatted_transcript_path: Optional[str] = None,
    transcript_duration: Optional[int] = None,
    transcript_confidence: Optional[float] = None,
):
    """
    Update episode record in the database.

    Update episode by episode ID.
    Only update field with an argument. None argument = No update

    Args:
        episode_id (int): ID of the episode to update.
        guid (Optional[str]): New GUID.
        title (Optional[str]): New title.
        description (Optional[str]): New description.
        published_date (Optional[datetime]): New published date.
        audio_url (Optional[str]): New audio URL.
        processing_stage (Optional[ProcessingStage]): New processing stage.
        audio_file_path (Optional[str]): New audio file
        raw_transcript_path (Optional[str]): New raw transcript file path.
        speaker_mapping_path (Optional[str]): New speaker mapping file path.
        formatted_transcript_path (Optional[str]): New formatted transcript file path.
        transcript_duration (Optional[int]): New transcript duration in seconds.
        transcript_confidence (Optional[float]): New transcript confidence score.
    """
    logger = logging.getLogger("pipeline")

    try:
        logger.info(f"Updating episode ID {episode_id} in database...")
        # Create update dictionary
        update_data: dict[str, Any] = {}
        if guid is not None:
            update_data["guid"] = guid
        if title is not None:
            update_data["title"] = title
        if description is not None:
            update_data["description"] = description
        if published_date is not None:
            update_data["published_date"] = published_date
        if audio_url is not None:
            update_data["audio_url"] = audio_url
        if processing_stage is not None:
            update_data["processing_stage"] = processing_stage
        if audio_file_path is not None:
            update_data["audio_file_path"] = audio_file_path
        if raw_transcript_path is not None:
            update_data["raw_transcript_path"] = raw_transcript_path
        if speaker_mapping_path is not None:
            update_data["speaker_mapping_path"] = speaker_mapping_path
        if formatted_transcript_path is not None:
            update_data["formatted_transcript_path"] = formatted_transcript_path
        if transcript_duration is not None:
            update_data["transcript_duration"] = transcript_duration
        if transcript_confidence is not None:
            update_data["transcript_confidence"] = transcript_confidence

        # Update the episode in the database
        with get_db_session() as session:
            session.query(Episode).filter(Episode.id == episode_id).update(
                update_data,
            )
    except Exception as e:
        raise e


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


@log_function(logger_name="pipeline", log_execution_time=True)
def run_raw_trancript_stage(audio_path: list[str]) -> list[str]:
    """
    Generate raw transcript from audio files.

    Args:
        audio_path (list[str]): List of episode audio file paths.

    Returns:
        list[str]: List of raw transcript file paths.
    """
    logger = logging.getLogger("pipeline")

    try:
        logger.info("Starting raw transcription stage...")
        raw_transcript_paths = []
        for path in audio_path:
            # Get episode ID
            episode_id = int(get_episode_id_from_path(path))

            # Create output directory
            output_dir = Path(TRANSCRIPT_DIR) / f"episode_{episode_id:03d}/"
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.error(f"Failed to create output directory {output_dir}: {e}")
                continue

            # Check if transcript already exist
            raw_file_path = Path(output_dir) / f"raw_episode_{episode_id:03d}.json"
            if raw_file_path.exists():
                # Add to list
                raw_transcript_paths.append(str(raw_file_path))
                logger.info(f"Formatted transcript already exists for episode ID {episode_id}, skipping transcription.")
            else:
                # Call transcription function here
                logger.info(f"Transcribing episode ID {episode_id} from file {path}...")
                raw_trancript = transcribe_with_diarization(Path(path), language="fr")
                try:
                    with open(raw_file_path, "w", encoding="utf-8") as f:
                        json.dump(raw_trancript, f, indent=4)
                except OSError as e:
                    logger.error(f"Failed to save raw transcript for episode ID {episode_id}: {e}")
                    continue
                logger.info(f"Saved raw transcription to {raw_file_path}")
            # Update db
            update_episode_in_db(
                episode_id=episode_id,
                raw_transcript_path=str(raw_file_path),
                processing_stage=ProcessingStage.RAW_TRANSCRIPT,
            )
        # Placeholder for actual transcription logic
        logger.info("Raw transcription stage completed successfully.")
        return raw_transcript_paths

    except Exception as e:
        logger.error(f"Failed to complete raw transcript pipeline : {e}")
        raise

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
from typing import Any, Optional, Dict
from datetime import datetime

from dotenv import load_dotenv

from src.logger import log_function
from src.db import (
    Episode,
    get_db_session,
    ProcessingStage,
    get_qdrant_client,
    create_collection,
)
from src.ingestion.sync_episodes import (
    fetch_podcast_episodes,
    sync_to_database,
    filter_episodes,
)
from src.ingestion.audio_scrap import (
    get_existing_files,
    generate_filename,
    download_episode,
)
from src.transcription import (
    get_episode_id_from_path,
    format_transcript,
    map_speakers_with_llm,
)
from src.transcription.transcript import transcribe_with_diarization
from src.embedder.embed import process_episode_embedding


AUDIO_DIR = "data/audio"
TRANSCRIPT_DIR = "data/transcripts"
EMBEDDING_DIR = "data/embeddings"


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
            session.commit()
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

        episodes = filter_episodes(episodes, full_sync=True)

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
            expected_filename = generate_filename(ep_number, ep_title)
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
                episode.id, episode.title, episode.audio_url, AUDIO_DIR
            )

            if success:
                episodes_path_list.append(filepath)
            else:
                logger.warning(
                    f"Failed to download episode {episode['id']}: {episode['title']}"
                )

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
            transcript_duration = None
            transcript_confidence = None

            if raw_file_path.exists():
                # Load existing transcript to extract metadata
                logger.info(
                    f"Raw transcript already exists for episode ID {episode_id}, loading metadata."
                )
            else:
                # Call transcription function here
                logger.info(f"Transcribing episode ID {episode_id} from file {path}...")
                raw_trancript = transcribe_with_diarization(Path(path), language="fr")

                # Extract metadata from new transcription
                transcript_duration = raw_trancript.get("transcript", {}).get(
                    "audio_duration"
                )
                transcript_confidence = raw_trancript.get("transcript", {}).get(
                    "confidence"
                )

                # Convert duration to int if it exists (database expects Integer)
                if transcript_duration is not None:
                    transcript_duration = int(transcript_duration)

                logger.info(
                    f"Transcription metadata: duration={transcript_duration}s, confidence={transcript_confidence}"
                )

                try:
                    with open(raw_file_path, "w", encoding="utf-8") as f:
                        json.dump(raw_trancript, f, indent=4)
                    logger.info(f"Saved raw transcription to {raw_file_path}")
                except OSError as e:
                    logger.error(
                        f"Failed to save raw transcript for episode ID {episode_id}: {e}"
                    )
                    continue

            # Update db with transcript path and metadata
            raw_transcript_paths.append(str(raw_file_path))
            update_episode_in_db(
                episode_id=episode_id,
                raw_transcript_path=str(raw_file_path),
                processing_stage=ProcessingStage.RAW_TRANSCRIPT,
                transcript_duration=transcript_duration,
                transcript_confidence=transcript_confidence,
            )

        logger.info("Raw transcription stage completed successfully.")
        return raw_transcript_paths

    except Exception as e:
        logger.error(f"Failed to complete raw transcript pipeline : {e}")
        raise


@log_function(logger_name="pipeline", log_execution_time=True)
def run_speaker_mapping_stage(raw_transcript_path: list[str]) -> list[str]:
    """
    Generate speaker mapping from raw transcript files.

    Args:
        raw_transcript_path (list[str]): List of raw transcript file paths.

    Returns:
        list[str]: List of speaker mapping file paths.
    """
    logger = logging.getLogger("pipeline")

    try:
        logger.info("Starting speaker mapping stage...")
        speaker_mapping_paths = []

        for path in raw_transcript_path:
            episode_id = int(get_episode_id_from_path(path))
            output_dir = Path(TRANSCRIPT_DIR) / f"episode_{episode_id:03d}/"

            # Take mapping from cache if exists
            mapping_file_path = Path(
                output_dir / f"speakers_episode_{episode_id:03d}.json"
            )
            mapping_result = {}
            if mapping_file_path.exists():
                logger.info(
                    f"Speaker mapping already exists for episode ID {episode_id}, loading from cache."
                )
            else:
                logger.info(
                    f"Generating speaker mapping for episode ID {episode_id} from file {path}..."
                )
                raw_formatted_text = format_transcript(path, max_tokens=10000)
                mapping_result = map_speakers_with_llm(raw_formatted_text)
                try:
                    with open(mapping_file_path, "w", encoding="utf-8") as f:
                        json.dump(mapping_result, f, indent=4)
                    logger.info(f"Saved mapping result to {mapping_file_path}")
                except OSError as e:
                    logger.error(
                        f"Failed to write mapping result to {mapping_file_path}: {e}"
                    )
                    continue
            speaker_mapping_paths.append(str(mapping_file_path))

            # Save to db
            update_episode_in_db(
                episode_id=episode_id,
                speaker_mapping_path=str(path),
                processing_stage=ProcessingStage.RAW_TRANSCRIPT,
            )
        logger.info("Speaker mapping stage completed successfully.")
        return speaker_mapping_paths

    except Exception as e:
        logger.error(f"Failed to complete speaker mapping pipeline : {e}")
        raise


@log_function(logger_name="pipeline", log_execution_time=True)
def run_formatted_trancript_stage(
    transcript_with_mapping: list[Dict[str, str]],
) -> list[str]:
    """
    Generate formatted transcript  + speaker mapping from raw transcript files.

    Args:
        raw_transcript_path (list[Dict[str,str]]): List of raw transcript file + speaker mapping file

    Returns:
        list[str]: List of formatted transcript file paths.
    """
    logger = logging.getLogger("pipeline")

    try:
        logger.info("Starting formatted transcription stage...")
        formatted_transcript_paths = []

        for item in transcript_with_mapping:
            transcript_path = item["transcript"]
            speaker_map_path = item["speaker_mapping"]

            episode_id = int(get_episode_id_from_path(transcript_path))
            output_dir = Path(TRANSCRIPT_DIR) / f"episode_{episode_id:03d}/"
            formatted_file_path = (
                Path(output_dir) / f"formatted_episode_{episode_id:03d}.txt"
            )
            if formatted_file_path.exists():
                # Add to list
                logger.info(
                    f"Formatted transcript already exists for episode ID {episode_id}, skipping transcription."
                )
            else:
                # Call transcription function here
                logger.info(
                    f"Transcribing episode ID {episode_id} from file {transcript_path}..."
                )
                formatted_trancript = format_transcript(
                    transcript_path, speaker_mapping=speaker_map_path
                )
                try:
                    with open(formatted_file_path, "w", encoding="utf-8") as f:
                        json.dump(formatted_trancript, f, indent=4)
                    logger.info(
                        f"Saved formatted transcript transcription to {formatted_file_path}"
                    )
                except OSError as e:
                    logger.error(
                        f"Failed to save formatted transcript for episode ID {episode_id}: {e}"
                    )
                    continue
            formatted_transcript_paths.append(str(formatted_file_path))

            # Update db
            update_episode_in_db(
                episode_id=episode_id,
                formatted_transcript_path=str(formatted_file_path),
                processing_stage=ProcessingStage.FORMATTED_TRANSCRIPT,
            )

        logger.info("Format transcription stage completed successfully.")
        return formatted_transcript_paths

    except Exception as e:
        logger.error(f"Failed to complete formatted transcript pipeline : {e}")
        raise


@log_function(logger_name="pipeline", log_execution_time=True)
def run_embedding_stage(transcript_path: list[str]):
    """
    Generate embeddings from formatted transcript files with 3-tier caching:
    1. Check Qdrant DB → save to local file if missing + update SQL
    2. Check local file → upload to Qdrant + update SQL
    3. Embed fresh → save to both + update SQL

    Args:
        transcript_path (list[str]): List of formatted transcript file paths.

    Returns:
        list[str]: List of embedding file paths.
    """
    logger = logging.getLogger("pipeline")

    try:
        load_dotenv()
        logger.info("Starting embedding stage...")

        # Create collection if not exist
        collection_name = os.getenv("QDRANT_COLLECTION_NAME")
        if collection_name is None:
            raise ValueError("QDRANT_COLLECTION_NAME not set in environment variables.")

        with get_qdrant_client() as qdrant_client:
            create_collection(
                qdrant_client,
                collection_name,
            )

        # Create output directory if not exists
        output_dir = Path(EMBEDDING_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        embedding_paths = []
        # Process each transcript with 3-tier caching
        for path in transcript_path:
            episode_id = int(get_episode_id_from_path(path))
            logger.info(
                f"Processing embedding for episode ID {episode_id} from file {path}..."
            )

            # Use new 3-tier caching function
            result = process_episode_embedding(
                input_file=path,
                episode_id=episode_id,
                collection_name=collection_name,
                dimensions=1024,
            )

            if result["success"]:
                action = result["action"]
                embedding_path = result["embedding_path"]
                embedding_paths.append(embedding_path)

                if action == "retrieved_from_qdrant":
                    logger.info(
                        f"Episode {episode_id}: Retrieved from Qdrant, saved to local cache"
                    )
                elif action == "loaded_from_file":
                    logger.info(
                        f"Episode {episode_id}: Loaded from local file, uploaded to Qdrant"
                    )
                elif action == "embedded_fresh":
                    logger.info(
                        f"Episode {episode_id}: Embedded fresh, saved to both locations"
                    )
            else:
                logger.error(
                    f"Failed to process embedding for episode {episode_id}: {result.get('error')}"
                )

        logger.info(
            f"Embedding stage completed successfully. Processed {len(embedding_paths)} episodes."
        )
        return embedding_paths

    except Exception as e:
        logger.error(f"Failed to complete embedding pipeline: {e}")
        raise

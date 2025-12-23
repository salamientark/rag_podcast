"""
Pipeline stage wrapper functions.

Each function wraps existing module logic and provides:
- Standardized error handling
- Database updates
- Progress tracking
- Logging
"""

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
from src.storage import CloudStorage, LocalStorage


AUDIO_DIR = "data/audio"
TRANSCRIPT_DIR = "data/transcripts"
EMBEDDING_DIR = "data/embeddings"


@log_function(logger_name="pipeline", log_execution_time=True)
def update_episode_in_db(
    uuid: str,
    podcast: Optional[str] = None,
    episode_id: Optional[int] = None,
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
        uuid (str): UUID of the episode to update.
        podcast (Optional[str]): New podcast name.
        episode_id (Optional[int]): New episode id.
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
        # Create update dictionary
        update_data: dict[str, Any] = {}
        if podcast is not None:
            update_data["podcast"] = podcast
        if episode_id is not None:
            update_data["episode_id"] = episode_id
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
            session.query(Episode).filter(Episode.uuid == uuid).update(
                update_data,
            )
            session.commit()
    except Exception as e:
        raise e


@log_function(logger_name="pipeline", log_execution_time=True)
def run_sync_stage(feed_url: Optional[str] = None) -> str:
    """
    Sync RSS feed to SQL database.

    Args:
        feed_url: Optional custom RSS feed URL. If None, uses FEED_URL from .env

    Returns:
        str: Podcast name extracted from the feed
    """
    logger = logging.getLogger("pipeline")
    episodes = []
    try:
        if feed_url:
            logger.info(f"Starting sync stage with custom feed URL: {feed_url}")
        else:
            logger.info("Starting sync stage with default feed URL from .env")

        logger.info("Fetching podcast episodes from RSS feed...")
        episodes = fetch_podcast_episodes(feed_url=feed_url)
        if not episodes:
            logger.error("No episodes fetched during sync stage.")
            raise ValueError("No episodes fetched during sync stage.")

        # Extract podcast name from first episode
        podcast_name = episodes[0]["podcast"]
        logger.info(f"Detected podcast from feed: {podcast_name}")

        episodes = filter_episodes(episodes, full_sync=True)
        logger.info(f"Fetched {len(episodes)} episodes. Syncing to database...")

        stats = sync_to_database(episodes)
        logger.info(
            f"Sync stage completed: {stats['processed']} processed, {stats['added']} added, "
            f"{stats['skipped']} skipped, {stats['errors']} errors"
        )

        return podcast_name

    except Exception as e:
        logger.error(f"Sync stage failed: {e}")
        raise e


@log_function(logger_name="pipeline", log_execution_time=True)
def run_download_stage(
    episodes: list[Episode],
    cloud_save: bool = False,
) -> list[Dict[str, Any]]:
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

        # Get workspace directory
        podcast = episodes[0].podcast
        workspace = f"{podcast}/audio/"
        if not cloud_save:
            workspace = f"data/{workspace}"

        # Get existing audio file
        existing_files = get_existing_files(workspace)

        # Find missing episodes and add path of existing episodes to list
        missing_episodes = []
        episodes_list = []
        for episode in episodes:
            ep_number = episode.episode_id
            ep_title = episode.title
            episode_data = {
                    'uuid': episode.uuid,
                    'podcast': episode.podcast,
                    'episode_id': episode.episode_id,
                    'title': episode.title,
            }
            filename = generate_filename(ep_number, ep_title)
            if filename not in existing_files:
                missing_episodes.append(episode)
            else:
                filepath = os.path.join(workspace, filename)
                episode_data['audio_path'] = filepath
                episodes_list.append(episode_data)

        if not missing_episodes:
            logger.info("No missing episodes to download.")
            if cloud_save:
                storage = CloudStorage()
                for i, episode in enumerate(episodes):
                    filename = os.path.basename(episodes_list[i]['audio_path'])
                    if storage.file_exist(workspace, filename):
                        logger.info(
                            f"Episode {episode.episode_id} already exists in cloud storage, skipping upload."
                        )
                    else:
                        storage.client.upload_file(
                            episodes_list[i]['audio_path'],
                            storage.bucket_name,
                            f"{workspace}{filename}",
                        )
                        logger.info(
                            f"Uploaded episode {episode.episode_id} to cloud storage."
                        )
                    update_episode_in_db(
                        uuid=episode.uuid,
                        episode_id=episode.episode_id,
                        audio_file_path=storage._get_absolute_filename(
                            workspace, filename
                        ),
                        processing_stage=ProcessingStage.AUDIO_DOWNLOADED,
                    )
            return episodes_list
        logger.info(f"Found {len(missing_episodes)} missing episodes to download.")

        for episode in missing_episodes:
            workspace = f"data/{podcast}/audio/"
            success, filepath = download_episode(
                episode.episode_id, episode.title, episode.audio_url, workspace
            )

            if success:
                update_episode_in_db(
                    uuid=episode.uuid,
                    episode_id=episode.episode_id,
                    audio_file_path=filepath,
                    processing_stage=ProcessingStage.AUDIO_DOWNLOADED,
                )
                episode_data = {
                        'uuid': episode.uuid,
                        'podcast': episode.podcast,
                        'episode_id': episode.episode_id,
                        'title': episode.title,
                        'audio_path': filepath,
                }
                episodes_list.append(episode_data)
                if cloud_save:
                    storage = CloudStorage()
                    workspace = "{podcast}/audio/"
                    filename = os.path.basename(filepath)
                    if storage.file_exist(workspace, filename):
                        logger.info(
                            f"Episode {episode.episode_id} already exists in cloud storage, skipping upload."
                        )
                    else:
                        storage.client.upload_file(
                            filepath, storage.bucket_name, f"{workspace}{filename}"
                        )
                        logger.info(
                            f"Uploaded episode {episode.episode_id} to cloud storage."
                        )
                    update_episode_in_db(
                        uuid=episode.uuid,
                        episode_id=episode.episode_id,
                        audio_file_path=storage._get_absolute_filename(
                            workspace, filename
                        ),
                        processing_stage=ProcessingStage.AUDIO_DOWNLOADED,
                    )
            else:
                logger.warning(
                    f"Failed to download episode {episode.episode_id}: {episode['title']}"
                )

        logger.info("Download stage completed successfully.")
        return episodes_list

    except Exception as e:
        logger.error(f"Download stage failed: {e}")
        raise e


@log_function(logger_name="pipeline", log_execution_time=True)
def run_raw_transcript_stage(episodes: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
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
        transcripted_episodes = []
        workspace = f"data/{episodes[0]['podcast']}/transcripts/"
        for episode in episodes:
            # Get episode ID
            episode_id = episode["episode_id"]

            # Create output directory
            output_dir = Path(f'{workspace}/episode_{episode_id:03d}/')
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
                logger.info(f"Transcribing episode ID {episode_id} from file {episode['audio_path']}...")
                raw_transcript = transcribe_with_diarization(Path(episode['audio_path']), language="fr")

                # Extract metadata from new transcription
                transcript_duration = raw_transcript.get("transcript", {}).get(
                    "audio_duration"
                )
                transcript_confidence = raw_transcript.get("transcript", {}).get(
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
                        json.dump(raw_transcript, f, indent=4)
                    logger.info(f"Saved raw transcription to {raw_file_path}")
                except OSError as e:
                    logger.error(
                        f"Failed to save raw transcript for episode ID {episode_id}: {e}"
                    )
                    continue

            # Update db with transcript path and metadata
            episode['raw_transcript_path'] = str(raw_file_path)
            update_episode_in_db(
                uuid=episode['uuid'],
                raw_transcript_path=str(raw_file_path),
                processing_stage=ProcessingStage.RAW_TRANSCRIPT,
                transcript_duration=transcript_duration,
                transcript_confidence=transcript_confidence,
            )
            transcripted_episodes.append(episode)

        logger.info("Raw transcription stage completed successfully.")
        return transcripted_episodes

    except Exception as e:
        logger.error(f"Failed to complete raw transcript pipeline : {e}")
        raise


@log_function(logger_name="pipeline", log_execution_time=True)
def run_speaker_mapping_stage(episodes: list[Dict[str, Any]]) -> list[str]:
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
        episodes_with_mapping = []
        workspace = f"data/{episodes[0]['podcast']}/transcripts"

        for episode in episodes:
            episode_id = episode["episode_id"]
            output_dir = Path(f"{workspace}/episode_{episode_id:03d}/")

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
                    f"Generating speaker mapping for episode ID {episode_id} from file {episode['raw_transcript_path']}..."
                )
                raw_formatted_text = format_transcript(Path(episode['raw_transcript_path']), max_tokens=10000)
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
            episode['mapping_path'] = str(mapping_file_path)
            episodes_with_mapping.append(episode)

            # Save to db
            update_episode_in_db(
                uuid=episode['uuid'],
                speaker_mapping_path=str(mapping_file_path),
                processing_stage=ProcessingStage.RAW_TRANSCRIPT,
            )
        logger.info("Speaker mapping stage completed successfully.")
        return episodes_with_mapping

    except Exception as e:
        logger.error(f"Failed to complete speaker mapping pipeline : {e}")
        raise


@log_function(logger_name="pipeline", log_execution_time=True)
def run_formatted_transcript_stage(
    transcript_with_mapping: list[Dict[str, str]],
    cloud_storage: bool = False,
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
        local_formatted_path = []
        local_storage = LocalStorage()

        for item in transcript_with_mapping:
            transcript_path = item["transcript"]
            speaker_map_path = item["speaker_mapping"]

            # Create filename
            episode_id = int(get_episode_id_from_path(transcript_path))
            filename = f"formatted_episode_{episode_id:03d}.txt"

            # Local save
            local_workspace = local_storage.create_episode_workspace(episode_id)
            logger.info(
                f"transcribing episode id {episode_id} from file {transcript_path}..."
            )

            # Load speaker mapping from JSON file
            speaker_mapping_dict = {}
            if os.path.exists(speaker_map_path):
                try:
                    with open(speaker_map_path, "r", encoding="utf-8") as f:
                        speaker_mapping_dict = json.load(f)
                    logger.info(f"Loaded speaker mapping: {speaker_mapping_dict}")
                except (FileNotFoundError, json.JSONDecodeError) as e:
                    logger.warning(
                        f"Could not load speaker mapping from {speaker_map_path}: {e}"
                    )
                    speaker_mapping_dict = {}
            else:
                logger.warning(f"Speaker mapping file not found: {speaker_map_path}")

            formatted_transcript = format_transcript(
                Path(transcript_path), speaker_mapping=speaker_mapping_dict
            )
            formatted_file_path = local_storage.save_file(
                local_workspace, filename, formatted_transcript
            )
            local_formatted_path.append(str(formatted_file_path))

            # Cloud save
            if cloud_storage:
                storage = CloudStorage()
                workspace = storage.create_episode_workspace(episode_id)
                if storage.file_exist(workspace, filename):
                    logger.info(
                        f"Formatted transcript already exists for episode ID {episode_id}, skipping transcription."
                    )
                    formatted_file_path = storage._get_absolute_filename(
                        workspace, filename
                    )
                else:
                    formatted_file_path = storage.save_file(
                        workspace, filename, formatted_transcript
                    )

            # Update db
            update_episode_in_db(
                episode_id=episode_id,
                formatted_transcript_path=str(formatted_file_path),
                processing_stage=ProcessingStage.FORMATTED_TRANSCRIPT,
            )

        logger.info("Format transcription stage completed successfully.")
        return local_formatted_path

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
        raise e

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

from dotenv import load_dotenv

from src.logger import log_function
from src.db import (
    ProcessingStage,
    get_qdrant_client,
    create_collection,
    update_episode_in_db,
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
    format_transcript,
    map_speakers_with_llm,
)
from src.transcription.transcript import transcribe_with_diarization
from src.embedder.embed import process_episode_embedding
from src.storage import get_cloud_storage, LocalStorage
from src.transcription.summarize import summarize, save_summary_to_cloud


AUDIO_DIR = "data/audio"
TRANSCRIPT_DIR = "data/transcripts"
EMBEDDING_DIR = "data/embeddings"


@log_function(logger_name="pipeline", log_execution_time=True)
def run_sync_stage(feed_url: Optional[str] = None) -> str:
    """
    Sync podcast RSS feed into the SQL database and return the podcast name.

    Parameters:
        feed_url (Optional[str]): Custom RSS feed URL; if None, uses FEED_URL from environment.

    Returns:
        str: Podcast name extracted from the fetched feed.

    Raises:
        ValueError: If no episodes are fetched from the feed.
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
    episodes: list[Dict[str, Any]],
    cloud_save: bool = False,
) -> list[Dict[str, Any]]:
    """
    Download audio files for the provided episodes, optionally upload them to cloud storage, and update episode records.

    Processes the given list of episode dictionaries, reusing existing local audio files when present, downloading missing files, and updating the database processing stage and audio file path for each processed episode. If cloud_save is True, uploads audio files to cloud storage (skipping files that already exist there) and updates the database with the cloud absolute path.

    Parameters:
        episodes (list[Dict[str, Any]]): Episodes to process; each dict must include keys uuid, podcast, episode_id, title, and audio_url.
        cloud_save (bool): If True, upload audio files to cloud storage and store cloud paths in the database.

    Returns:
        list[Dict[str, Any]]: List of episode dictionaries with keys `uuid`, `podcast`, `episode_id`, `title`, and `audio_path` (local or cloud path as stored in the DB).
    """
    logger = logging.getLogger("pipeline")
    try:
        logger.info("Starting download stage...")

        # Get workspace directory
        podcast = episodes[0]["podcast"]
        workspace = f"{podcast}/audio/"
        if not cloud_save:
            workspace = f"data/{workspace}"

        # Get existing audio file
        existing_files = get_existing_files(workspace)

        # Find missing episodes and add path of existing episodes to list
        missing_episodes = []
        episodes_list = []
        for episode in episodes:
            ep_number = episode["episode_id"]
            ep_title = episode["title"]
            episode_data = {
                "uuid": episode["uuid"],
                "podcast": episode["podcast"],
                "episode_id": episode["episode_id"],
                "title": episode["title"],
            }
            filename = generate_filename(ep_number, ep_title)
            if filename not in existing_files:
                missing_episodes.append(episode)
            else:
                filepath = os.path.join(workspace, filename)
                episode_data["audio_path"] = filepath
                episodes_list.append(episode_data)

        if not missing_episodes:
            logger.info("No missing episodes to download.")
            if cloud_save:
                storage = get_cloud_storage()
                for episode in episodes_list:
                    # for i, episode in enumerate(episodes):
                    filename = os.path.basename(episode["audio_path"])
                    if storage.file_exist(workspace, filename):
                        logger.info(
                            f"Episode {episode['episode_id']} already exists in cloud storage, skipping upload."
                        )
                    else:
                        storage.client.upload_file(
                            episode["audio_path"],
                            storage.bucket_name,
                            f"{workspace}{filename}",
                        )
                        logger.info(
                            f"Uploaded episode {episode['episode_id']} to cloud storage."
                        )
                    update_episode_in_db(
                        uuid=episode["uuid"],
                        episode_id=episode["episode_id"],
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
                episode["episode_id"], episode["title"], episode["audio_url"], workspace
            )

            if success:
                update_episode_in_db(
                    uuid=episode["uuid"],
                    episode_id=episode["episode_id"],
                    audio_file_path=filepath,
                    processing_stage=ProcessingStage.AUDIO_DOWNLOADED,
                )
                episode_data = {
                    "uuid": episode["uuid"],
                    "podcast": episode["podcast"],
                    "episode_id": episode["episode_id"],
                    "title": episode["title"],
                    "audio_path": filepath,
                }
                episodes_list.append(episode_data)
                if cloud_save:
                    storage = get_cloud_storage()
                    workspace = f"{podcast}/audio/"
                    filename = os.path.basename(filepath)
                    if storage.file_exist(workspace, filename):
                        logger.info(
                            f"Episode {episode['episode_id']} already exists in cloud storage, skipping upload."
                        )
                    else:
                        storage.client.upload_file(
                            filepath, storage.bucket_name, f"{workspace}{filename}"
                        )
                        logger.info(
                            f"Uploaded episode {episode['episode_id']} to cloud storage."
                        )
                    update_episode_in_db(
                        uuid=episode["uuid"],
                        episode_id=episode["episode_id"],
                        audio_file_path=storage._get_absolute_filename(
                            workspace, filename
                        ),
                        processing_stage=ProcessingStage.AUDIO_DOWNLOADED,
                    )
            else:
                logger.warning(
                    f"Failed to download episode {episode['episode_id']}: {episode['title']}"
                )

        logger.info("Download stage completed successfully.")
        return episodes_list

    except Exception as e:
        logger.error(f"Download stage failed: {e}")
        raise e


@log_function(logger_name="pipeline", log_execution_time=True)
def run_raw_transcript_stage(episodes: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """
    Generate raw transcripts for the provided episodes and persist them to disk.

    Parameters:
        episodes (list[Dict[str, Any]]): List of episode dictionaries. Each dictionary must include
            the keys `uuid`, `podcast`, `episode_id`, and `audio_path`. `title` is optional but may be present.

    Returns:
        list[Dict[str, Any]]: The input episode dictionaries augmented with `raw_transcript_path`.
            Episodes may also include `transcript_duration` (int seconds) and `transcript_confidence` when available.

    Side effects:
        - Writes raw transcript JSON files to a per-episode workspace on disk.
        - Updates the episode record in the database with `raw_transcript_path`, `processing_stage` set to
          RAW_TRANSCRIPT, and any available `transcript_duration` and `transcript_confidence`.
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
            output_dir = Path(f"{workspace}/episode_{episode_id:03d}/")
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
                logger.info(
                    f"Transcribing episode ID {episode_id} from file {episode['audio_path']}..."
                )
                raw_transcript = transcribe_with_diarization(
                    Path(episode["audio_path"]), language="fr"
                )

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
            episode["raw_transcript_path"] = str(raw_file_path)
            update_episode_in_db(
                uuid=episode["uuid"],
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
def run_speaker_mapping_stage(episodes: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """
    Generate per-episode speaker mappings from raw transcript files and attach mapping paths to each episode.

    Parameters:
        episodes (list[Dict[str, Any]]): List of episode dictionaries. Each dictionary must include the keys
            'uuid', 'podcast', 'episode_id', and 'raw_transcript_path'.

    Returns:
        list[Dict[str, Any]]: The same list of episode dictionaries with a new 'mapping_path' key for each episode
        pointing to the JSON file containing the speaker mapping.
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
                raw_formatted_text = format_transcript(
                    Path(episode["raw_transcript_path"]), max_tokens=10000
                )
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
            episode["mapping_path"] = str(mapping_file_path)
            episodes_with_mapping.append(episode)

            # Save to db
            update_episode_in_db(
                uuid=episode["uuid"],
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
    episodes: list[Dict[str, str]],
    cloud_storage: bool = False,
) -> list[Dict[str, Any]]:
    """
    Create speaker-attributed, human-readable transcripts from raw transcripts and attach their paths to each episode.

    Parameters:
        episodes (list[dict]): List of episode dictionaries. Each dictionary must include the keys
            `uuid`, `podcast`, `episode_id`, `title`, `raw_transcript_path`, and `mapping_path`.
        cloud_storage (bool): If True, upload the formatted transcript to configured cloud storage.

    Returns:
        list[dict]: The same episode dictionaries with a `formatted_transcript_path` key added (path to the saved formatted transcript).
    """
    logger = logging.getLogger("pipeline")

    try:
        logger.info("Starting formatted transcription stage...")
        updated_episodes = []
        local_storage = LocalStorage()

        for episode in episodes:
            transcript_path = episode["raw_transcript_path"]
            speaker_map_path = episode["mapping_path"]

            # Create filename
            episode_id = episode["episode_id"]
            filename = f"formatted_episode_{episode_id:03d}.txt"

            # Local save
            local_workspace = (
                f"data/{episodes[0]['podcast']}/transcripts/episode_{episode_id:03d}/"
            )
            # local_workspace = local_storage.create_episode_workspace(episode_id)
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
            episode["formatted_transcript_path"] = str(formatted_file_path)
            updated_episodes.append(episode)
            # local_formatted_path.append(str(formatted_file_path))

            # Cloud save
            if cloud_storage:
                storage = get_cloud_storage()
                workspace = (
                    f"{episodes[0]['podcast']}/transcripts/episode_{episode_id:03d}/"
                )
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
                uuid=episode["uuid"],
                formatted_transcript_path=str(formatted_file_path),
                processing_stage=ProcessingStage.FORMATTED_TRANSCRIPT,
            )

        logger.info("Format transcription stage completed successfully.")
        return updated_episodes

    except Exception as e:
        logger.error(f"Failed to complete formatted transcript pipeline : {e}")
        raise


@log_function(logger_name="pipeline", log_execution_time=True)
async def run_summarization_stage(
    episodes: list[Dict[str, Any]],
    ) -> None:
    """
    Create summaries for each episode's formatted transcript and attach their paths to each episode.

    Parameters:
        episodes (list[dict]): List of episode dictionaries. Each dictionary must include the
                keys `podcast`, `episode_id`, `transcript_path`
    """
    try:
        logger = logging.getLogger("pipeline")
        logger.info("Starting summarization stage...")

        storage_engine = get_cloud_storage()
        client = storage_engine.get_client()
        for episode in episodes:
            podcast = episode["podcast"]
            episode_id = episode["episode_id"]
            transcript_path = episode["formatted_transcript_path"]
            bucket_name = storage_engine.bucket_name
            key = f"{podcast}/summaries/episode_{episode_id}_summary.txt"

            # Generate summary
            logger.info(
                f"Generating summary for episode ID {episode_id} from file {transcript_path}..."
            )

            response = client.get_object(Bucket=bucket_name, Key=transcript_path)
            transcript_content = response["Body"].read().decode('utf-8')
            summary = await summarize(transcript_content, language="fr")
            link = save_summary_to_cloud(bucket_name, key, summary)
            update_episode_in_db(
                episode["uuid"],
                podcast=podcast,
                episode_id=episode_id,
                summary_path=link,
            )

    except Exception as e:
        logger.error(f"Failed to complete summarization pipeline : {e}")
        raise


@log_function(logger_name="pipeline", log_execution_time=True)
def run_embedding_stage(episodes: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """
    Generate embeddings for each episode's formatted transcript using a three-tier cache (Qdrant → local file → fresh embedding) and attach resulting embedding paths to episode dictionaries.

    Parameters:
        episodes (list[dict]): List of episode dictionaries. Each dictionary must include keys: `uuid`, `podcast`, `episode_id`, `title`, and `formatted_transcript_path`. The function will add or update the `embedding_path` key on successful processing.

    Returns:
        list[dict]: The subset of input episode dictionaries that were successfully processed, each augmented with an `embedding_path` pointing to the local embedding file.
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
        workspace = f"data/{episodes[0]['podcast']}/embeddings/"
        output_dir = Path(workspace)
        output_dir.mkdir(parents=True, exist_ok=True)

        updated_episodes = []
        # Process each transcript with 3-tier caching
        for episode in episodes:
            episode_id = episode["episode_id"]
            logger.info(
                f"Processing embedding for episode ID {episode_id} from file {episode['formatted_transcript_path']}..."
            )

            # Use new 3-tier caching function
            result = process_episode_embedding(
                input_file=episode["formatted_transcript_path"],
                episode_uuid=episode["uuid"],
                collection_name=collection_name,
                dimensions=1024,
            )

            if result["success"]:
                action = result["action"]
                episode["embedding_path"] = result["embedding_path"]
                updated_episodes.append(episode)

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
            f"Embedding stage completed successfully. Processed {len(episodes)} episodes."
        )
        return updated_episodes

    except Exception as e:
        logger.error(f"Failed to complete embedding pipeline: {e}")
        raise e

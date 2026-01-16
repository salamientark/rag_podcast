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
from src.transcription.gemini_transcript import transcribe_with_gemini
from src.embedder.embed import process_episode_embedding
from src.storage import get_cloud_storage, LocalStorage
from src.transcription.summarize import summarize, save_summary_to_cloud, make_file_url


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
        list[Dict[str, Any]]: List of episode dictionaries with keys `uuid`, `podcast`, `episode_id`, `title`, and `audio_file_path` (local or cloud path as stored in the DB).
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
            episode_data = episode.copy()
            filename = generate_filename(ep_number, ep_title)
            if filename not in existing_files:
                missing_episodes.append(episode)
            else:
                filepath = os.path.join(workspace, filename)
                episode_data["audio_file_path"] = filepath
                episodes_list.append(episode_data)

        if not missing_episodes:
            logger.info("No missing episodes to download.")
            if cloud_save:
                storage = get_cloud_storage()
                for episode in episodes_list:
                    filename = os.path.basename(episode["audio_file_path"])
                    if storage.file_exist(workspace, filename):
                        logger.info(
                            f"Episode {episode['episode_id']} already exists in cloud storage, skipping upload."
                        )
                    else:
                        storage.client.upload_file(
                            episode["audio_file_path"],
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
                episode_data = episode.copy()
                episode_data["audio_file_path"] = filepath
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
def run_transcription_stage(
    episodes: list[Dict[str, Any]],
    cloud_storage: bool = False,
    force: bool = False,
) -> list[Dict[str, Any]]:
    """
    Transcribe audio files using Gemini and save formatted transcripts.

    Uses Gemini to transcribe audio with speaker identification in a single call.
    Episode description is passed to Gemini for speaker name context.

    Parameters:
        episodes (list[Dict[str, Any]]): List of episode dictionaries. Each must include:
            `uuid`, `podcast`, `episode_id`, `audio_file_path`, `description`.
        cloud_storage (bool): If True, upload transcripts to cloud storage.
        force (bool): If True, re-transcribe even if transcript exists.

    Returns:
        list[Dict[str, Any]]: Episodes with `formatted_transcript_path` added.
    """
    logger = logging.getLogger("pipeline")

    try:
        logger.info("Starting Gemini transcription stage...")
        updated_episodes = []
        local_storage = LocalStorage()
        podcast = episodes[0]["podcast"]

        for episode in episodes:
            episode_id = episode["episode_id"]
            audio_path = Path(episode["audio_file_path"])
            description = episode.get("description", "")

            # Ensure we have a valid local path for transcription
            if not audio_path.exists():
                # Try local path format (handles cloud-style paths)
                local_audio_path = Path(f"data/{podcast}/audio/") / audio_path.name
                if local_audio_path.exists():
                    audio_path = local_audio_path
                else:
                    logger.error(
                        f"Audio file not found for episode {episode_id}: {episode['audio_file_path']}"
                    )
                    continue

            # Create output directory
            local_workspace = f"data/{podcast}/transcripts/episode_{episode_id:03d}/"
            Path(local_workspace).mkdir(parents=True, exist_ok=True)

            filename = f"formatted_episode_{episode_id:03d}.txt"
            local_path = Path(local_workspace) / filename

            # Check if transcript already exists locally
            if local_path.exists() and not force:
                logger.info(
                    f"Transcript already exists for episode {episode_id:03d}, skipping transcription."
                )
                episode["formatted_transcript_path"] = str(local_path.resolve())
                formatted_text = None  # Will read from file if needed for cloud upload
            else:
                # Transcribe with Gemini
                logger.info(
                    f"Transcribing episode {episode_id:03d} with Gemini from {audio_path.name}..."
                )
                result = transcribe_with_gemini(audio_path, description)
                formatted_text = result["formatted_text"]

                # Save locally
                formatted_file_path = local_storage.save_file(
                    local_workspace, filename, formatted_text
                )
                episode["formatted_transcript_path"] = str(formatted_file_path)

            updated_episodes.append(episode)

            # Cloud save
            formatted_file_path = episode["formatted_transcript_path"]
            if cloud_storage:
                storage = get_cloud_storage()
                cloud_workspace = f"{podcast}/transcripts/episode_{episode_id:03d}/"
                if storage.file_exist(cloud_workspace, filename) and not force:
                    logger.info(
                        f"Transcript already exists in cloud for episode {episode_id:03d}."
                    )
                    formatted_file_path = storage._get_absolute_filename(
                        cloud_workspace, filename
                    )
                else:
                    # Read from local file if we didn't transcribe (reused existing)
                    if formatted_text is None:
                        formatted_text = local_path.read_text(encoding="utf-8")
                    formatted_file_path = storage.save_file(
                        cloud_workspace, filename, formatted_text
                    )

            # Update database
            update_episode_in_db(
                uuid=episode["uuid"],
                formatted_transcript_path=str(formatted_file_path),
                processing_stage=ProcessingStage.FORMATTED_TRANSCRIPT,
            )

            logger.info(f"Episode {episode_id:03d} transcription completed.")

        logger.info("Gemini transcription stage completed successfully.")
        return updated_episodes

    except Exception as e:
        logger.error(f"Failed to complete transcription stage: {e}")
        raise


async def run_summarization_stage(
    episodes: list[Dict[str, Any]],
    force: bool = False,
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
            if episode["summary_path"] and not force:
                continue
            podcast = episode["podcast"]
            episode_id = episode["episode_id"]
            transcript_path = episode["formatted_transcript_path"]
            bucket_name = storage_engine.bucket_name
            transcript_key = f"{podcast}/" + transcript_path.split(f"{podcast}/")[1]
            summary_key = f"{podcast}/summaries/episode_{episode_id:03d}_summary.txt"

            link = make_file_url(bucket_name, summary_key)
            if storage_engine.file_exist(bucket_name, summary_key) and not force:
                logger.info(
                    f"Summary already exists for episode ID {episode_id:03d}, skipping summarization."
                )
                continue

            # Generate summary
            logger.info(
                f"Generating summary for episode ID {episode_id:03d} from file {transcript_path}..."
            )

            response = client.get_object(Bucket=bucket_name, Key=transcript_key)
            transcript_content = response["Body"].read().decode("utf-8")
            summary = await summarize(transcript_content, language="fr")
            link = save_summary_to_cloud(bucket_name, summary_key, summary)
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
                f"Processing embedding for episode ID {episode_id:03d} from file {episode['formatted_transcript_path']}..."
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
                        f"Episode {episode_id:03d}: Retrieved from Qdrant, saved to local cache"
                    )
                elif action == "loaded_from_file":
                    logger.info(
                        f"Episode {episode_id:03d}: Loaded from local file, uploaded to Qdrant"
                    )
                elif action == "embedded_fresh":
                    logger.info(
                        f"Episode {episode_id:03d}: Embedded fresh, saved to both locations"
                    )
            else:
                logger.error(
                    f"Failed to process embedding for episode {episode_id:03d}: {result.get('error')}"
                )

        logger.info(
            f"Embedding stage completed successfully. Processed {len(episodes)} episodes."
        )
        return updated_episodes

    except Exception as e:
        logger.error(f"Failed to complete embedding pipeline: {e}")
        raise e

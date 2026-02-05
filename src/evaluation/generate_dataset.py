from pathlib import Path
from typing import List, Union, Optional, Dict, Any
from llama_index.core import Document
from src.chunker import chunk_long_text



from src.logger import setup_logging
from src.db import get_db_session, get_podcast_by_name_or_slug, Episode
from src.storage.cloud import get_cloud_storage

logger = setup_logging(
    logger_name="reprocess_failed",
    log_file="logs/reprocess_failed.log",
    verbose=True,
)


def filter_episodes(
    podcast_name: str, limit: int = 10
) -> Optional[List[Dict[str, Any]]]:
    """
    Retrieve the latest episodes for a given podcast that have a formatted transcript.

    Args:
        podcast_name:(str) The name or slug of the podcast.
        limit(int): The maximum number of episodes to return. Defaults to 10.

    Returns:
        A list of episode dictionaries if successful, or None if the podcast
        is not found or an error occurs.
    """
    try:
        # Check for podcast existence
        podcast = get_podcast_by_name_or_slug(podcast_name)
        if not podcast:
            raise ValueError(f"Podcast '{podcast_name}' not found.")
        # Get the lasts episode from podcast
        episode_as_dicts = []
        with get_db_session() as session:
            episodes_to_process = (
                session.query(Episode)
                .filter(
                    Episode.podcast_id == podcast.id,
                    Episode.formatted_transcript_path.isnot(None),
                )
                .order_by(Episode.published_date.desc())
                .limit(limit)
                .all()
            )
            episode_as_dicts = [ep.to_dict() for ep in episodes_to_process]
        return episode_as_dicts
    except Exception as e:
        logger.error(f"Error fetching podcast '{podcast_name}': {e}")
        return None


def download_transcript(url: str, output_path: Path) -> bool:
    try:
        storage_engine = get_cloud_storage()
        client = storage_engine.get_client()
    


def load_documents_from_files(file_paths: List[Union[str, Path]]) -> List[Document]:
    """
    Load and chunk documents from a list of file paths.

    Args:
        file_paths: List of paths to transcript files.

    Returns:
        List of LlamaIndex Document objects with chunked content and metadata.
    """
    documents = []

    # We use a smaller chunk size for evaluation dataset generation
    # to create more specific questions.
    EVAL_CHUNK_SIZE = 1024
    EVAL_OVERLAP = 0.1

    for file_path in file_paths:
        path = Path(file_path)
        filename = path.name
        if not path.exists():
            logger.warning(f"File not found: {path}")
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()

            if not text.strip():
                logger.warning(f"Empty file skipped: {path}")
                continue

            # Create chunks
            chunks = chunk_long_text(
                text, max_tokens=EVAL_CHUNK_SIZE, overlap_percent=EVAL_OVERLAP
            )

            # Convert chunks to LlamaIndex Documents
            for i, chunk_text in enumerate(chunks):
                # Extract some basic metadata from filename if possible
                filename = path.name
                metadata = {"source": str(path), "filename": filename, "chunk_index": i}

                doc = Document(text=chunk_text, metadata=metadata)
                documents.append(doc)

            logger.info(f"Loaded {len(chunks)} chunks from {filename}")

        except Exception as e:
            logger.error(f"Error loading {path}: {e}")

    return documents


def __main__():
    """ """
    PODCAST_NAME = "le rendez-vous jeux"
    LIMIT = 5

    try:
        # Get the last episodes with formatted transcripts for the specified podcast
        logger.info(
            f"Fetching episodes for podcast: {PODCAST_NAME} with limit: {LIMIT}"
        )
        episodes_as_dict = filter_episodes(PODCAST_NAME, LIMIT)
        if episodes_as_dict is None:
            logger.error("Failed to fetch episodes.")
            return

        logger.info(
            f"Fetched {len(episodes_as_dict)} episodes for podcast: {PODCAST_NAME}"
        )
        logger.info(f"Episodes IDS: {[ep['episode_id'] for ep in episodes_as_dict]}")

        transcripts_path = [ep["formatted_transcript_path"] for ep in episodes_as_dict]

        print(f"Transcripts paths: {transcripts_path}")

        # Downloads transcripts in tmp dir
    except Exception as e:
        logger.error(f"Error in main: {e}")
        exit(1)


if __name__ == "__main__":
    __main__()

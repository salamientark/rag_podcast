import logging
import numpy as np
from typing import Any, Optional, Dict
from datetime import datetime, timezone
from dotenv import load_dotenv
from pathlib import Path
import voyageai

from src.logger import log_function
from src.db.database import get_db_session, update_episode_in_db
from src.db.qdrant_client import (
    get_qdrant_client,
    insert_one_point,
    get_episode_vectors,
)
from src.db.models import Episode, ProcessingStage
from src.chunker.token_counter import check_voyage_limits, count_tokens
from src.chunker import chunk_long_text


DEFAULT_EMBEDDING_OUTPUT_DIR = Path("data/embeddings")


def format_publication_date(dt: datetime) -> str:
    """
    Convert datetime to ISO 8601 format with UTC timezone.

    Treats naive datetimes as UTC (assumes podcast times are in UTC).

    Args:
        dt: datetime object (naive or timezone-aware)

    Returns:
        str: ISO 8601 formatted string with timezone (e.g., "2009-01-25T19:19:22+00:00")
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


@log_function(logger_name="embedder", log_args=False, log_execution_time=True)
def embed_text(text: str | list[str], dimensions: int = 1024) -> Any:
    """Generate embeddings for the given text using VoyageAI's embedding model.

    Args:
        text (str | list[str]): The input text to be embedded.
        dimensions (int): Output dimensions for the embedding.
                         Valid values: 256, 512, 1024, 2048. Default: 1024.

    Returns:
        Any: VoyageAI embedding result object containing embeddings and metadata.

    Raises:
        ValueError: If dimensions parameter is not one of [256, 512, 1024, 2048].
        Exception: If embedding generation fails.
    """
    logger = logging.getLogger("embedder")
    load_dotenv()

    # Validate dimensions parameter
    valid_dimensions = [256, 512, 1024, 2048]
    if dimensions not in valid_dimensions:
        raise ValueError(
            f"Invalid dimensions: {dimensions}. Must be one of {valid_dimensions}"
        )

    # Automatically look for VOYAGE_API_KEY env variable
    try:
        # Create embedding client
        vo = voyageai.Client()  # type: ignore

        # Ensure text is a list for API compatibility
        texts_to_embed = [text] if isinstance(text, str) else text

        # Check token limits before making API call
        model_name = "voyage-3"
        limit_check = check_voyage_limits(texts_to_embed, model=model_name)

        if not limit_check["fits"]:
            error_msg = f"Text exceeds Voyage AI limits: {limit_check['issues']}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(
            f"Generating embeddings with {dimensions} dimensions "
            f"({limit_check['total_tokens']} tokens, "
            f"{limit_check['total_tokens'] / limit_check['model_limits']['context_length'] * 100:.1f}% of limit)"
        )

        result = vo.embed(
            texts_to_embed,
            model=model_name,
            input_type="document",
            output_dimension=dimensions,
        )
        logger.info(
            f"Embeddings generated successfully. "
            f"API reported {result.total_tokens} tokens"
        )
        return result
    except Exception as e:
        logger.error(f"Error generating embeddings: {e}")
        raise


@log_function(logger_name="embedder", log_args=True, log_execution_time=True)
def update_episode_processing_stage(
    uuid: str,
) -> bool:
    """
    Update episode database record with EMBEDDED processing stage.

    Args:
        episode_id: Database ID of the episode
        processing_stage: New processing stage to set

    Returns:
        bool: True if update successful, False otherwise
    """
    logger = logging.getLogger("embedder")
    try:
        with get_db_session() as session:
            episode = session.query(Episode).filter_by(uuid=uuid).first()

            if not episode:
                logger.error(f"Episode {uuid} not found in database")
                return False

            # Update db fields
            stage_order = list(ProcessingStage)
            current_stage_index = stage_order.index(episode.processing_stage)
            target_stage_index = stage_order.index(ProcessingStage.EMBEDDED)
            if current_stage_index < target_stage_index:
                episode.processing_stage = ProcessingStage.EMBEDDED

            session.commit()
            logger.info(f"Updated episode ID {uuid} with EMBEDDED processing stage")
            return True
    except Exception as e:
        logger.error(f"Failed to update episode ID {uuid}: {e}")
        return False


def save_embedding_to_file(output_path: Path, embed: list[float] | np.ndarray) -> Path:
    """Save embeddings to the specified output path as .npy file.

    Args:
        output_path (Path): Full path where the embedding file should be saved.
        embed (list[float] | np.ndarray): The embedding vector to save.

    Returns:
        Path: The path where the file was saved.

    Raises:
        OSError: If file cannot be written.
    """
    # Create parent directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure .npy extension
    if output_path.suffix != ".npy":
        output_path = output_path.with_suffix(".npy")

    # Convert to numpy array if needed
    if not isinstance(embed, np.ndarray):
        embed = np.array(embed)

    # Save as numpy file
    with open(output_path, "wb") as f:
        np.save(f, embed)
    return output_path


def load_embedding_from_file(file_path: Path) -> Optional[np.ndarray]:
    """
    Load an embedding array from a .npy file.
    
    Returns:
        Optional[np.ndarray]: The loaded embedding array, or `None` if the file does not exist.
    
    Raises:
        Exception: If the file exists but cannot be loaded.
    """
    if not file_path.exists():
        return None

    try:
        with open(file_path, "rb") as f:
            embedding = np.load(f)
        return embedding
    except Exception as e:
        logger = logging.getLogger("embedder")
        logger.error(f"Failed to load embedding from {file_path}: {e}")
        raise


@log_function(logger_name="embedder", log_args=True, log_execution_time=True)
def embed_file_to_db(
    input_file: str | Path,
    episode_uuid: str,
    episode_id: int,
    collection_name: str,
    dimensions: int = 1024,
    save_to_file: bool = False,
):
    """
    High-level function to embed text from a file and store in database.

    Args:
        input_file (str | Path): Path to the input transcript file.
        episode_uuid (str): Episode UUID in Database
        collection_name (str): Name of the collection to store embeddings.
        dimensions (int): Output vector dimensions (default: 1024).
        output_path (Optional[str | Path]): Optional path to save embeddings as .npy file.
        save_to_file (bool): Whether to save embeddings to file.
    """
    logger = logging.getLogger("embedder")
    input_path = Path(input_file)
    try:
        # Load transcript text from file
        with input_path.open("r", encoding="utf-8") as f:
            transcript_text = f.read()
        # Generate embeddings
        embedding_result = embed_text(transcript_text, dimensions=dimensions)
        embeddings = embedding_result.embeddings[0]

        # Optionally save to file
        if save_to_file:
            filename = (
                DEFAULT_EMBEDDING_OUTPUT_DIR
                / f"episode_{episode_id:03d}_d{dimensions}.npy"
            )
            saved_path = save_embedding_to_file(Path(filename), embeddings)
            logger.info(f"Embeddings saved to file: {saved_path}")

        # Get episode info from database
        with get_db_session() as session:
            episode = session.query(Episode).filter_by(uuid=episode_uuid).first()
            if not episode:
                raise ValueError(f"Episode ID {episode_id} not found in database")

        # Create payload metadata
        payload = {
            "episode_id": episode_id,
            "title": episode.title,
            "db_guid": str(episode.uuid),
            "publication_date": format_publication_date(episode.published_date),
        }

        logger.info(
            f"Storing embeddings for episode ID {episode_id} in collection '{collection_name}'"
        )
        # Insert embeddings into Qdrant
        with get_qdrant_client() as client:
            insert_one_point(
                client=client,
                collection_name=collection_name,
                vector=embeddings,
                payload=payload,
            )
        logger.info(f"Embeddings stored in database for episode ID {episode_id}")

        # Update episode processing stage
        update_episode_processing_stage(episode_uuid)
    except Exception as e:
        logger.error(f"Failed to embed file {input_file}: {e}")
        raise


@log_function(logger_name="embedder", log_args=True, log_execution_time=True)
def process_episode_embedding(
    input_file: str | Path,
    episode_uuid: str,
    collection_name: str,
    dimensions: int = 1024,
) -> Dict[str, Any]:
    """
    Process an episode's transcript into embeddings using a three-tier caching strategy and upload results to Qdrant.
    
    Checks Qdrant for existing vectors, falls back to a local .npy cache, and if neither exists splits the transcript into chunks, generates embeddings, saves them locally, and uploads per-chunk points to Qdrant. In all successful cases the episode's processing stage is updated to EMBEDDED.
    
    Parameters:
        input_file (str | Path): Path to the transcript file to read.
        episode_uuid (str): Database UUID of the episode to process and tag in metadata.
        collection_name (str): Qdrant collection name to query/upload vectors.
        dimensions (int): Embedding vector dimensionality to request and persist.
    
    Returns:
        dict: Status dictionary containing:
            - action (str | None): One of "retrieved_from_qdrant", "loaded_from_file", or "embedded_fresh" indicating what was done.
            - embedding_path (str | None): Path to the local .npy file where embeddings are stored (if available).
            - success (bool): `true` when the operation completed successfully, `false` on error.
            - error (str | None): Error message when `success` is `false`.
    """
    logger = logging.getLogger("embedder")
    input_path = Path(input_file)

    result = {
        "action": None,
        "embedding_path": None,
        "success": False,
        "error": None,
    }

    try:
        # Get episode info from database
        with get_db_session() as session:
            episode = session.query(Episode).filter_by(uuid=episode_uuid).first()
            if not episode:
                raise ValueError(f"Episode UUID {episode_uuid} not found in database")

        # Get paths
        workspace = f"data/{episode.podcast}/embeddings/"
        local_file_path = Path(
            f"{workspace}/episode_{episode.episode_id:03d}_d{dimensions}.npy"
        )

        # Create base payload metadata
        base_payload = {
            "podcast": episode.podcast,
            "episode_id": episode.episode_id,
            "title": episode.title,
            "db_uuid": str(episode_uuid),
            "dimensions": dimensions,
            "publication_date": format_publication_date(episode.published_date),
        }

        # TIER 1: Check if vectors exist in Qdrant
        logger.info(
            f"Checking if episode {episode_uuid} exists in Qdrant collection '{collection_name}'"
        )
        with get_qdrant_client() as client:
            vectors = get_episode_vectors(
                client=client,
                collection_name=collection_name,
                episode_uuid=episode_uuid,
            )

        if vectors is not None:
            num_chunks = len(vectors)
            logger.info(
                f"Episode {episode_uuid} found in Qdrant ({num_chunks} chunk(s)), saving to local cache"
            )
            # Save to local file if it doesn't exist
            if not local_file_path.exists():
                embeddings_array = np.array(vectors)  # Shape: (num_chunks, dimensions)
                saved_path = save_embedding_to_file(local_file_path, embeddings_array)
                logger.info(
                    f"Saved {num_chunks} chunk embedding(s) from Qdrant to local file: {saved_path}"
                )

            # Update SQL database
            update_episode_in_db(
                episode_uuid, processing_stage=ProcessingStage.EMBEDDED
            )

            result["action"] = "retrieved_from_qdrant"
            result["embedding_path"] = str(local_file_path)
            result["success"] = True
            return result

        # TIER 2: Check if local file exists
        logger.info(f"Episode {episode_uuid} not in Qdrant, checking local file")
        local_embedding = load_embedding_from_file(local_file_path)

        if local_embedding is not None:
            # Check if it's multi-chunk (2D array) or single chunk (1D array)
            if local_embedding.ndim == 1:
                # Legacy format: single embedding vector
                embeddings_list = [local_embedding]
            else:
                # New format: multiple chunks
                embeddings_list = [
                    local_embedding[i] for i in range(local_embedding.shape[0])
                ]

            logger.info(
                f"Episode {episode_uuid} found in local file ({len(embeddings_list)} chunk(s)), uploading to Qdrant"
            )

            # We need to get the original text to include in metadata
            # Load transcript text to re-chunk for text metadata
            with input_path.open("r", encoding="utf-8") as f:
                transcript_text = f.read()

            # Re-chunk the text to get chunk texts for metadata
            chunk_texts = chunk_long_text(
                transcript_text, max_tokens=30000, overlap_percent=0.1
            )

            # Ensure we have the same number of chunks as embeddings
            if len(chunk_texts) != len(embeddings_list):
                logger.warning(
                    f"Mismatch: {len(chunk_texts)} text chunks vs {len(embeddings_list)} embeddings. "
                    "Using available chunks."
                )
                # Use the minimum to avoid index errors
                min_chunks = min(len(chunk_texts), len(embeddings_list))
                chunk_texts = chunk_texts[:min_chunks]
                embeddings_list = embeddings_list[:min_chunks]

            # Upload all chunks to Qdrant with text metadata
            with get_qdrant_client() as client:
                for i, (embedding, chunk_text) in enumerate(
                    zip(embeddings_list, chunk_texts)
                ):
                    chunk_payload = {
                        **base_payload,
                        "chunk_index": i,
                        "total_chunks": len(embeddings_list),
                        "token_count": count_tokens(chunk_text),
                        "text": chunk_text,  # ✅ NOW INCLUDES TEXT!
                    }
                    insert_one_point(
                        client=client,
                        collection_name=collection_name,
                        vector=embedding.tolist()
                        if hasattr(embedding, "tolist")
                        else embedding,
                        payload=chunk_payload,
                    )
            logger.info(f"Uploaded {len(embeddings_list)} chunk embedding(s) to Qdrant")

            # Update SQL database
            update_episode_in_db(
                episode_uuid, processing_stage=ProcessingStage.EMBEDDED
            )
            # update_episode_processing_stage(str(episode_id))

            result["action"] = "loaded_from_file"
            result["embedding_path"] = str(local_file_path)
            result["success"] = True
            return result

        # TIER 3: Embed fresh from transcript with chunking
        logger.info(
            f"Episode {episode_uuid} not found locally, generating fresh embedding"
        )

        # Load transcript text
        with input_path.open("r", encoding="utf-8") as f:
            transcript_text = f.read()

        # Chunk text if needed (max 30K tokens per chunk, 10% overlap)
        chunk_texts = chunk_long_text(
            transcript_text, max_tokens=30000, overlap_percent=0.1
        )

        # Embed all chunks in single API call
        embedding_result = embed_text(chunk_texts, dimensions=dimensions)
        embeddings_list = embedding_result.embeddings  # List of embeddings

        # Save all chunks to single local file
        embeddings_array = np.array(embeddings_list)  # Shape: (num_chunks, dimensions)
        saved_path = save_embedding_to_file(local_file_path, embeddings_array)
        logger.info(
            f"Saved {len(chunk_texts)} chunk embedding(s) to local file: {saved_path}"
        )

        # Upload each chunk to Qdrant with metadata
        with get_qdrant_client() as client:
            for i, (embedding, chunk_text) in enumerate(
                zip(embeddings_list, chunk_texts)
            ):
                chunk_payload = {
                    **base_payload,
                    "chunk_index": i,
                    "total_chunks": len(chunk_texts),
                    "token_count": count_tokens(chunk_text),
                    "text": chunk_text,
                }
                insert_one_point(
                    client=client,
                    collection_name=collection_name,
                    vector=embedding,
                    payload=chunk_payload,
                )
        logger.info(
            f"Uploaded {len(embeddings_list)} chunk embedding(s) to Qdrant collection '{collection_name}'"
        )

        # Update SQL database
        # update_episode_processing_stage(str(episode_id))
        update_episode_in_db(episode_uuid, processing_stage=ProcessingStage.EMBEDDED)

        result["action"] = "embedded_fresh"
        result["embedding_path"] = str(saved_path)
        result["success"] = True
        return result

    except Exception as e:
        logger.error(f"Failed to process embedding for episode {episode_uuid}: {e}")
        result["error"] = str(e)
        return result
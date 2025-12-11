import logging
import numpy as np
from typing import Any, Optional
from dotenv import load_dotenv
from pathlib import Path
import voyageai

from src.logger import log_function
from src.db.database import get_db_session
from src.db.qdrant_client import get_qdrant_client, insert_one_point
from src.db.models import Episode, ProcessingStage
from src.embedder.token_counter import check_voyage_limits


DEFAULT_EMBEDDING_OUTPUT_DIR = Path("data/embeddings")


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


def chunks_to_text(chunks: list[Any]) -> list[str]:
    """Convert list of Chunks to list of text strings.

    Args:
        chunks (list[Chunks]): List of Chunks objects.
    Returns:
        list[str]: List of text strings extracted from chunks.
    """
    text_list = [chunk.text.strip() for chunk in chunks]
    return text_list

@log_function(logger_name="embedder", log_args=True, log_execution_time=True)
def update_episode_processing_stage(
    episode_id: str,
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
            episode = session.query(Episode).filter_by(id=episode_id).first()

            if not episode:
                logger.error(f"Episode {episode_id} not found in database")
                return False

            # Update db fields
            stage_order = list(ProcessingStage)
            current_stage_index = stage_order.index(episode.processing_stage)
            target_stage_index = stage_order.index(ProcessingStage.EMBEDDED)
            if current_stage_index < target_stage_index:
                episode.processing_stage = ProcessingStage.EMBEDDED

            session.commit()
            logger.info(f"Updated episode ID {episode_id} with EMBEDDED processing stage")
            return True
    except Exception as e:
        logger.error(f"Failed to update episode ID {episode_id}: {e}")
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


@log_function(logger_name="embedder", log_args=True, log_execution_time=True)
def embed_file_to_db(
    input_file: str | Path,
    episode_id: int,
    collection_name: str,
    dimensions: int = 1024,
    save_to_file: bool = False,
):
    """
    High-level function to embed text from a file and store in database.

    Args:
        input_file (str | Path): Path to the input transcript file.
        episode_id (int): Database ID of the episode.
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
        print(f"DEBUG: save_to_file={save_to_file}")
        if save_to_file:
            filename = DEFAULT_EMBEDDING_OUTPUT_DIR / f"episode_{episode_id:03d}_d{dimensions}.npy"
            print(f"DEBUG: Saving embeddings to file: {filename}")
            saved_path = save_embedding_to_file(Path(filename), embeddings)
            print(f"DEBUG: Saved path: {saved_path}")
            logger.info(f"Embeddings saved to file: {saved_path}")

        # Get episode info from database
        with get_db_session() as session:
            episode = session.query(Episode).filter_by(id=episode_id).first()
            if not episode:
                raise ValueError(f"Episode ID {episode_id} not found in database")

        # Create payload metadata
        payload = {
            "episode_id": episode_id,
            "title": episode.title,
            "db_guid": str(episode.guid)
        }

        logger.info(f"Storing embeddings for episode ID {episode_id} in collection '{collection_name}'")
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
        update_episode_processing_stage(str(episode_id))
    except Exception as e:
        logger.error(f"Failed to embed file {input_file}: {e}")
        raise

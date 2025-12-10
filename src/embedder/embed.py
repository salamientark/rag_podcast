import logging
import numpy as np
from typing import Any
from dotenv import load_dotenv
from pathlib import Path
import voyageai

from src.logger import log_function


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

        logger.info(f"Generating embeddings with {dimensions} dimensions")
        result = vo.embed(
            texts_to_embed,
            model="voyage-3",
            input_type="document",
            output_dimension=dimensions,
        )
        logger.info("Embeddings generated successfully")
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
    np.save(output_path, embed)
    return output_path

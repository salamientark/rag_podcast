import voyageai
import logging
import numpy as np
from typing import Any
from dotenv import load_dotenv
from pathlib import Path
from chonkie import Chunk
from src.transcription import get_mapped_transcript
from src.logger import setup_logging, log_function


@log_function(logger_name="embedder", log_args=True, log_execution_time=True)
def embed_text(text: str | list[str]) -> Any:
    """Generate embeddings for the given text using VoyageAI's embedding model.

    Args:
        text (str | list[str]): The input text to be embedded.

    Returns:
        list[float]: A list of floats representing the text embedding.
    """
    logger = logging.getLogger("embedder")
    env = load_dotenv()
    if not env:
        logger.error("Failed to load environment variables from .env file.")
        raise
    # Automatically look for VOYAGE_API_KEY env variable
    try:
        # Create embedding client
        vo = voyageai.Client()

        logger.info("Generating embeddings")
        result = vo.embed(text, model="voyage-3.5", input_type="document")
        logger.info("Embeddings generated successfully")
        return result
    except Exception as e:
        logger.error(f"Error generating embeddings: {e}")


ABSOLUTE_EPISODE_PATH = Path(
    "/home/madlab/Code/rag_podcast/data/transcript/episode_672_universal.json"
)


def chunks_to_text(chunks: list[Chunk]) -> list[str]:
    """Convert list of Chunks to list of text strings.

    Args:
        chunks (list[Chunks]): List of Chunks objects.
    Returns:
        list[str]: List of text strings extracted from chunks.
    """
    text_list = [chunk.text.strip() for chunk in chunks]
    return text_list


def save_embedding_to_file(filename: str, embed: list[float] | np.ndarray) -> Path:
    """Save the requested file to data/embeddings/<filename>.npy

    Args:
        filename (str): The name of the file to save.
        embed (list[float] | numpy.array): The embedding vector to save.
    Returns:
        Saved file path.
    """
    base_path = Path("data/embeddings/")
    file_path = base_path / f"{filename}.npy"
    with open(file_path, "w", encoding="utf-8") as f:
        if isinstance(embed, np.ndarray):
            np.save(f, embed)
        else:
            np_embed = np.array(embed)
            np.save(f, np_embed)
        return Path(f"data/embeddings/{filename}.npy")


if __name__ == "__main__":
    # Setup logging
    logger = setup_logging(
        logger_name="embedder",
        log_file="logs/embedder.log",
        verbose=False,
    )

    print(f"Transcripting text of {ABSOLUTE_EPISODE_PATH}... ", end="", flush=True)
    raw_transcript = get_mapped_transcript(ABSOLUTE_EPISODE_PATH)
    print(f"First 5000 char of transcripted text: {raw_transcript[:5000]}")

    # chunks = chunk_text(raw_transcript, chunk_size=1000)
    # text_chunks = chunks_to_text(chunks)
    # print(f"Done: {len(text_chunks)} chunks created.")
    # print(f"Embedding text chunks... ", end="", flush=True)
    # print(f"First chunk preview:\n{text_chunks[0][:5000]}")
    # print(f"Type of text_chunks: {type(text_chunks)}")
    # print(f"Length of text_chunks: {len(text_chunks)}")

    embed = embed_text(raw_transcript)
    print("Done.")
    print(f"Embedding total tokens: {embed.total_tokens}")
    print(f"Embedding result: {embed.embeddings}")
    saved_path = save_embedding_to_file("episode_672", embed)
    print(f"Saved embedding to {saved_path}")

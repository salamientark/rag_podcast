import logging
import tiktoken

from typing import Any
from .token_counter import count_tokens
from chonkie.chunker.token import TokenChunker


def chunks_to_text(chunks: list[Any]) -> list[str]:
    """
    Convert a list of chunk-like objects into their stripped text strings.

    Parameters:
        chunks (list[Any]): Objects that expose a `text` attribute; each `text` value will be stripped of leading and trailing whitespace.

    Returns:
        list[str]: Extracted and stripped text strings.
    """
    text_list = [chunk.text.strip() for chunk in chunks]
    return text_list


def chunk_long_text(
    text: str, max_tokens: int = 30000, overlap_percent: float = 0.1
) -> list[str]:
    """
    Chunk input text into token-sized segments with configurable overlap.

    Parameters:
        text (str): Text to be chunked.
        max_tokens (int): Maximum tokens per chunk. Defaults to 30000.
        overlap_percent (float): Fraction of max_tokens to overlap between consecutive chunks (e.g., 0.1 for 10%). Defaults to 0.1.

    Returns:
        list[str]: List of chunked text segments; a single-item list containing the original text if it fits within max_tokens.
    """
    logger = logging.getLogger("embedder")

    # Check total token count
    token_count = count_tokens(text)

    if token_count <= max_tokens:
        logger.info(
            f"Text fits within limit ({token_count} tokens), no chunking needed"
        )
        return [text]

    # Calculate overlap in tokens
    overlap_tokens = int(max_tokens * overlap_percent)

    logger.info(
        f"Text has {token_count} tokens, chunking with "
        f"{max_tokens} tokens per chunk and {overlap_tokens} token overlap"
    )

    # Use TokenChunker from chonkie with tiktoken encoder
    encoding = tiktoken.get_encoding("cl100k_base")
    chunker = TokenChunker(
        tokenizer=encoding, chunk_size=max_tokens, chunk_overlap=overlap_tokens
    )

    chunks = chunker.chunk(text)
    chunk_texts = [chunk.text for chunk in chunks]

    logger.info(f"Created {len(chunk_texts)} chunks from text")
    return chunk_texts

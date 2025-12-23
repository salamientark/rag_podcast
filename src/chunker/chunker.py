import logging
import tiktoken

from typing import Any
from .token_counter import count_tokens
from chonkie.chunker.token import TokenChunker


def chunks_to_text(chunks: list[Any]) -> list[str]:
    """Convert list of Chunks to list of text strings.

    Args:
        chunks (list[Chunks]): List of Chunks objects.
    Returns:
        list[str]: List of text strings extracted from chunks.
    """
    text_list = [chunk.text.strip() for chunk in chunks]
    return text_list


def chunk_long_text(
    text: str, max_tokens: int = 30000, overlap_percent: float = 0.1
) -> list[str]:
    """
    Chunk text if it exceeds token limit, with overlap between chunks.

    Args:
        text: Input text to chunk
        max_tokens: Maximum tokens per chunk (default 30000)
        overlap_percent: Overlap between chunks as percentage (default 0.1 = 10%)

    Returns:
        List of text chunks (single item if text fits within limit)
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

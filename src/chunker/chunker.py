import json
from pathlib import Path
from chonkie import SemanticChunker, Chunk
from src.transcription import get_mapped_transcript


def chunk_text(text: str, chunk_size: int = 8192) -> list[Chunk]:
    """Chunk text using SemanticChunker from chonkie.
    Args:
        text: Text to chunk
        chunk_size: Maximum chunk size in tokens
    Returns:
        List of text chunks
    """
    chunker = SemanticChunker(
        chunk_size=chunk_size,
    )
    chunks = chunker.chunk(text)
    return chunks


ABSOLUTE_EPISODE_PATH = Path(
    "/home/madlab/Code/rag_podcast/data/transcript/episode_672_universal.json"
)


if __name__ == "__main__":
    # Format transcript with speaker names
    print("Formatting full transcript with speaker names... ", end="", flush=True)
    text = get_mapped_transcript(ABSOLUTE_EPISODE_PATH)
    print("Done")

    # Chunk the text
    print("Chunking text... ", end="", flush=True)
    chunks = chunk_text(text)
    print("Done")
    print(f"Number of chunks: {len(chunks)}")
    print(f"First chunk preview:\n{chunks[0][:5000]}")

    print("========== ANALYSIS ==========")
    word_count = 0
    word_count_squared = 0
    for chunk in chunks:
        wc = len(chunk.text.split())
        word_count += wc
        word_count_squared += wc * wc

    # Compute statistics
    input_wc = len(text.split())
    average_wc = word_count / len(chunks)
    variance_wc = (word_count_squared / len(chunks)) - (average_wc * average_wc)
    total_wc = word_count

    print(f"Total input word count: {input_wc}")
    print(f"Total output word count: {total_wc}")
    print(f"Average word count per chunk: {average_wc:.2f}")
    print(f"Variance of word count per chunk: {variance_wc:.2f}")

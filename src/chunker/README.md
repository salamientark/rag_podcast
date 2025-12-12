# Chunker Module

Semantic text chunking for RAG applications using the Chonkie library. Splits podcast transcripts into meaningful chunks optimized for vector search and retrieval.

## Quick Start

```python
from src.chunker.chunker import chunk_text

# Chunk transcript text
chunks = chunk_text(transcript_text, chunk_size=8192)
print(f"Created {len(chunks)} chunks")
```

## Features

- **Semantic Chunking** - Preserves meaning by splitting at natural boundaries
- **Configurable Size** - Adjustable chunk size (default: 8192 tokens)
- **Speaker Awareness** - Integrates with transcript formatting to maintain speaker context
- **RAG Optimized** - Chunks sized for effective vector search and LLM context windows

## Core Function

### `chunk_text(text: str, chunk_size: int = 8192) -> list[Chunk]`

Splits text into semantic chunks using the SemanticChunker from Chonkie.

**Parameters:**
- `text` - Input text to chunk (formatted transcript)
- `chunk_size` - Maximum chunk size in tokens (default: 8192)

**Returns:**
- List of Chunk objects with text content and metadata

**Example:**
```python
transcript = "Speaker A: Welcome to the show... Speaker B: Thanks for having me..."
chunks = chunk_text(transcript, chunk_size=4096)

for i, chunk in enumerate(chunks):
    print(f"Chunk {i+1}: {len(chunk.text)} chars")
    print(f"Content: {chunk.text[:100]}...")
```

## Integration

The chunker integrates with the embedding pipeline:

```bash
# Chunking happens automatically during embedding
uv run -m src.embedder.main "data/transcripts/*/formatted_*.txt"

# Or through the complete pipeline
uv run -m src.pipeline --stages embedded --limit 5
```

## Chunk Size Guidelines

**Recommended chunk sizes by use case:**
- **4096 tokens** - Fine-grained search, detailed Q&A
- **8192 tokens** - Balanced approach (default)
- **16384 tokens** - Broader context, episode summaries

**Token estimation:** ~4 characters per token for English text

## Dependencies

- **Chonkie** - Semantic chunking library
- **src.transcription** - Integration with transcript formatting

## Technical Notes

- Uses SemanticChunker which respects sentence boundaries and speaker turns
- Optimized for podcast transcript structure (speaker labels, dialogue flow)
- Chunk size is approximate - actual chunks may be slightly larger to preserve sentence boundaries
- Integrates with the formatted transcript output from the transcription module
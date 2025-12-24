# Embedder Module

## Overview

The embedder module generates vector embeddings from podcast transcripts using VoyageAI's API and stores them in Qdrant vector database. It supports batch processing, automatic chunking for long texts, and a 3-tier caching strategy.

## Key Files

### `embed.py` - Core Embedding Logic

**Key Functions:**

- `embed_text(text, dimensions=1024)` - Generate embeddings using VoyageAI's voyage-3 model
  - Accepts string or list of strings
  - Validates dimensions (256, 512, 1024, 2048)
  - Pre-checks token limits before API call
  - Returns VoyageAI result object with embeddings

- `process_episode_embedding(input_file, episode_uuid, collection_name, dimensions)` - Main processing function
  - **3-Tier Caching Strategy:**
    1. Check Qdrant DB first → if found, save to local file
    2. Check local .npy file → if found, upload to Qdrant
    3. Generate fresh embeddings → save to both Qdrant and local file
  - Handles automatic chunking for long transcripts (max 30K tokens/chunk, 10% overlap)
  - Returns status dict with action taken

- `save_embedding_to_file(output_path, embed)` / `load_embedding_from_file(file_path)` - Local storage helpers
  - Saves/loads embeddings as numpy .npy files
  - Supports both 1D (single chunk) and 2D (multi-chunk) arrays

### `__main__.py` - CLI Batch Processor

**CLI Usage:**

```bash
uv run -m src.embedder file.txt
uv run -m src.embedder "data/transcripts/**/*.txt"
uv run -m src.embedder *.txt --dimensions 512 --collection my_collection
uv run -m src.embedder *.txt --skip-existing  # default
uv run -m src.embedder *.txt --no-skip-existing  # force reprocess
uv run -m src.embedder *.txt --dry-run --verbose
```

## Important Patterns

### Multi-Chunk Embedding Architecture

Long transcripts are automatically chunked to fit VoyageAI's 32K token limit:

- Each chunk is embedded separately
- All chunks stored as separate Qdrant points with shared metadata
- Local storage saves all chunks in single .npy file as 2D array

### Payload Metadata Structure

Every Qdrant point includes:

```python
{
    "podcast": str,
    "episode_id": int,
    "title": str,
    "db_uuid": str,
    "dimensions": int,
    "publication_date": str,  # ISO 8601 with timezone
    "chunk_index": int,
    "total_chunks": int,
    "token_count": int,
    "text": str
}
```

## Gotchas

1. **Token Limits**: VoyageAI voyage-3 model has 32K token limit. Pre-validation via `check_voyage_limits()` prevents API errors.

2. **Caching Behavior**: Re-chunking happens when loading from local file. Chunk boundaries must be deterministic!

3. **Dimension Mismatch**: Changing dimensions requires re-embedding everything. Local files are named with dimension suffix: `episode_001_d1024.npy`.

4. **Skip Logic**: `--skip-existing` checks Qdrant only, not local files. Uses `check_episode_exists_in_qdrant()`.

5. **Array Shape Handling**: Local .npy files can be 1D (legacy single chunk) or 2D (multi-chunk). Code must handle both.

6. **Episode ID vs UUID**: `episode_id` is int, `episode_uuid` is string. Functions use different parameter names.

7. **VoyageAI Result Object**: `embed_text()` returns a result object, extract with `result.embeddings[0]`.

## Dependencies

- `voyageai` - VoyageAI API client
- `numpy` - Embedding array storage
- `qdrant-client` - Vector database
- `tiktoken` - Token counting (via src.chunker.token_counter)
- `src.db.qdrant_client` - Qdrant helper functions
- `src.chunker` - Text chunking logic

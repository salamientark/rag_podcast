# Embedder Module

## Overview

The embedder module generates vector embeddings from podcast transcripts using VoyageAI's API and stores them in Qdrant vector database. It supports automatic chunking for long texts and a 3-tier caching strategy.

This documentation is review-oriented: it defines the payload and caching contracts that other modules depend on.

## Key Files

### `embed.py` - Core Embedding Logic

**Key Functions:**

- `embed_text(text, dimensions=1024)`  
  Generate embeddings using VoyageAI. Accepts a string or list of strings. Validates dimensions and checks token limits before calling the API.

  **Important (current code reality):**
  - The embedder currently uses `model_name = "voyage-3"` inside `embed_text()`.
  - If the rest of the system expects `voyage-3.5`, this mismatch should be resolved (either update code or config), otherwise retrieval quality and compatibility assumptions can drift.

- `process_episode_embedding(input_file, episode_uuid, collection_name, dimensions)`  
  Main processing function implementing **3-tier caching**:
  1. Check Qdrant DB first → if found, save to local file (if missing) + update SQL stage
  2. Check local `.npy` file → if found, upload to Qdrant + update SQL stage
  3. Generate fresh embeddings (with chunking) → save to both Qdrant and local file + update SQL stage

- `save_embedding_to_file(output_path, embed)` / `load_embedding_from_file(file_path)`  
  Local storage helpers. Local `.npy` files can be:
  - 1D array: legacy single-chunk embedding
  - 2D array: multi-chunk embeddings (shape: `(num_chunks, dimensions)`)

### `__main__.py` - CLI Batch Processor

Provides batch embedding for transcript files. Note: some DB lookups in this CLI are currently inconsistent with the SQLAlchemy model (see “Known Broken”).

## Chunking Contract

Long transcripts are chunked to fit VoyageAI limits:

- Max tokens per chunk: 30,000
- Overlap: 10%

Chunking must be deterministic enough that re-chunking (e.g., when uploading from local cache) does not produce wildly different chunk counts. If chunking parameters change, cached embeddings may no longer align with chunk texts.

## Qdrant Payload Contract (REQUIRED)

Every Qdrant point inserted for an episode must include at least:

```python
{
  "podcast": str,
  "episode_id": int,
  "title": str,
  "db_uuid": str,          # MUST match Episode.uuid
  "dimensions": int,
  "publication_date": str, # ISO 8601
  "chunk_index": int,
  "total_chunks": int,
  "token_count": int,
  "text": str              # REQUIRED for RAG responses
}
```

If `text` is missing, the query system may return empty/low-quality answers because it cannot synthesize responses from retrieved nodes.

## Qdrant Indexes (REQUIRED)

Before filtering/scrolling by payload fields, the collection must have payload indexes:

- `episode_id`: INTEGER
- `db_uuid`: KEYWORD

The helper `ensure_payload_indexes()` exists for this purpose.

## Gotchas / Review Rules

1. **UUID vs episode_id**: Qdrant linking must use `db_uuid` (Episode.uuid). `episode_id` is not globally unique.
2. **Dimension changes**: changing `dimensions` requires re-embedding; local cache filenames include dimension suffix.
3. **Multi-chunk support**: code must handle both 1D and 2D `.npy` formats.
4. **Model naming drift**: keep embedder model name aligned with query embedding model configuration.

## Known Broken (current code reality)

- The embedder CLI (`src/embedder/__main__.py`) contains DB lookups using fields like `Episode.id` / `Episode.guid` that do not match the current SQLAlchemy model (`Episode.uuid` and `Episode.episode_id`). This can fail at runtime.

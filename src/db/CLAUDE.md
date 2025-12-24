# Database Module (src/db)

## Overview

This module provides dual-database support for the podcast RAG system:

- **SQLite** (via SQLAlchemy): Stores episode metadata and processing state
- **Qdrant**: Vector database for semantic search over episode embeddings

The module uses context managers for safe, session-per-operation database access with comprehensive logging and error handling.

## Key Components

### models.py

**Episode Model**

- Primary table storing podcast episode metadata and processing state
- Uses UUID7 as primary key (not auto-increment)
- Tracks processing pipeline through `ProcessingStage` enum
- File paths populated as processing progresses (audio, transcripts)

**ProcessingStage Enum**

- Sequential processing stages: `SYNCED → AUDIO_DOWNLOADED → RAW_TRANSCRIPT → FORMATTED_TRANSCRIPT → EMBEDDED`
- Each stage implies all previous stages are complete
- Used by reconciliation logic to determine status from filesystem

**TimestampMixin**

- Adds automatic `created_at` and `updated_at` timestamps
- Uses database-level defaults (`func.now()`) for consistency

### database.py

**Core Functions**

- `get_db_session()`: Context manager for session-per-operation pattern
- `init_database()`: Creates all tables (not migrations)
- `update_episode_in_db()`: Updates episode by UUID (only updates non-None fields)
- `get_podcasts()`: Returns list of unique podcast names

**SQLite Optimizations**

- NullPool connection pooling (avoids SQLite locking issues)
- WAL mode for better concurrent access
- 30-second busy timeout
- Foreign key constraints enabled

### qdrant_client.py

**Core Functions**

- `get_qdrant_client()`: Context manager for Qdrant connections
- `create_collection()`: Creates collection if not exists
- `insert_one_point()`: Inserts single vector with auto-generated UUID
- `check_episode_exists_in_qdrant()`: Checks if episode is already embedded
- `get_episode_vectors()`: Retrieves all vectors for an episode (supports multi-chunk)
- `ensure_payload_indexes()`: Creates indexes for `episode_id` and `db_uuid` fields

**Configuration**

- Embedding dimension: 1024 (VoyageAI voyage-3.5)
- Distance metric: Cosine similarity
- Supports both API key and local deployment

## Important Patterns

### Session-Per-Operation

```python
# SQLite
with get_db_session() as session:
    episode = session.query(Episode).filter_by(uuid=uuid).first()
    episode.processing_stage = ProcessingStage.EMBEDDED
    session.commit()

# Qdrant
with get_qdrant_client() as client:
    client.upsert(collection_name="...", points=[...])
```

### Selective Updates

```python
# Only updates non-None fields
update_episode_in_db(
    uuid="abc-123",
    processing_stage=ProcessingStage.AUDIO_DOWNLOADED,
    audio_file_path="/path/to/audio.mp3"
)
```

### Multi-Chunk Episodes

- Episodes can have multiple embeddings (chunks)
- Vectors stored with `chunk_index` in payload
- `get_episode_vectors()` retrieves all chunks sorted by index
- Legacy single-chunk episodes supported (chunk_index defaults to 0)

## Environment Variables

Required in `.env`:

```bash
DATABASE_URL=sqlite:///path/to/database.db
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION_NAME=podcast_episodes
QDRANT_API_KEY=xxx  # Optional for local deployment
```

## Gotchas

1. **Episode IDs vs UUIDs**: `episode_id` is NOT unique across podcasts (only within a podcast). Always use `uuid` for lookups.

2. **Processing Stage Transitions**: Stages are sequential and implied - don't skip stages, reconciliation logic depends on this order.

3. **SQLite Thread Safety**: Uses NullPool and `check_same_thread=False` but still subject to locking under heavy writes.

4. **Qdrant Payload Indexes**: Must call `ensure_payload_indexes()` before filtering on `episode_id` or `db_uuid`. Filtering without indexes will be slow or fail.

5. **Database Migrations**: `init_database()` creates tables but doesn't run Alembic migrations - use `alembic upgrade head`.

6. **Error Handling**: Database errors trigger automatic rollback. Qdrant errors use fail-open approach (returns False, not exception).

7. **Multi-Chunk Limit**: `get_episode_vectors()` assumes max 100 chunks per episode. Increase `limit` parameter if episodes exceed this.

# Database Module

SQLAlchemy-based database layer for the RAG podcast system, providing models, connections, and Qdrant vector database integration.

## Quick Start

```python
from src.db import get_db_session, Episode, ProcessingStage

# Database operations
with get_db_session() as session:
    episodes = session.query(Episode).filter(Episode.processing_stage == ProcessingStage.EMBEDDED).all()
    print(f"Found {len(episodes)} embedded episodes")
```

## Components

### Models (`models.py`)
- **`Episode`** - Core podcast episode model with metadata and processing status
- **`ProcessingStage`** - Enum tracking pipeline stages (SYNCED → AUDIO_DOWNLOADED → RAW_TRANSCRIPT → FORMATTED_TRANSCRIPT → EMBEDDED)
- **`TimestampMixin`** - Automatic created_at/updated_at timestamps

### Database Connection (`database.py`)
- **`get_db_session()`** - Context manager for database sessions
- **Database URL** - SQLite by default, configurable via environment

### Vector Database (`qdrant_client.py`)
- **Qdrant integration** - Vector storage and retrieval operations
- **Episode management** - Link relational data with vector embeddings

## Episode Model

```python
# Key fields
class Episode:
    uuid: str                        # Primary key (UUID7 format)
    podcast: str                     # Podcast name/identifier
    episode_id: int                  # Episode number within podcast (not globally unique)
    title: str                       # Episode title
    published_date: datetime         # Publication date
    audio_url: str                   # Original audio URL
    
    # File paths
    audio_file_path: str             # Local audio file
    raw_transcript_path: str         # Initial transcript JSON  
    speaker_mapping_path: str        # Speaker identification
    formatted_transcript_path: str   # Final formatted transcript
    
    # Processing metadata
    processing_stage: ProcessingStage # Current pipeline stage
    transcript_duration: int         # Duration in seconds
    transcript_confidence: float     # Transcription confidence
    
    # Timestamps (automatic)
    created_at: datetime
    updated_at: datetime
```

## Processing Stages

Episodes progress through these stages:

```python
class ProcessingStage(Enum):
    SYNCED = "synced"                     # Metadata in database
    AUDIO_DOWNLOADED = "audio_downloaded" # Audio file downloaded
    RAW_TRANSCRIPT = "raw_transcript"     # Transcribed with AssemblyAI
    FORMATTED_TRANSCRIPT = "formatted_transcript" # Speaker-identified
    EMBEDDED = "embedded"                 # Chunked and in Qdrant
```

## Usage Examples

### Query Episodes by Stage
```python
with get_db_session() as session:
    # Episodes ready for transcription
    pending = session.query(Episode).filter(
        Episode.processing_stage == ProcessingStage.AUDIO_DOWNLOADED
    ).all()
    
    # Episodes by podcast
    podcast_episodes = session.query(Episode).filter(
        Episode.podcast == "Le rendez-vous Tech"
    ).all()
```

### Update Episode Status
```python
with get_db_session() as session:
    episode = session.query(Episode).filter(
        Episode.podcast == "Le rendez-vous Tech",
        Episode.episode_id == 672
    ).first()
    episode.processing_stage = ProcessingStage.RAW_TRANSCRIPT
    episode.raw_transcript_path = "/path/to/transcript.json"
    # Session automatically commits on context exit
```

### Get Available Podcasts
```python
from src.db import get_podcasts

podcasts = get_podcasts()
print(f"Available podcasts: {podcasts}")
```

## Database Migrations

Using Alembic for schema management:

```bash
# Apply migrations
uv run alembic upgrade head

# Create new migration
uv run alembic revision --autogenerate -m "description"

# Migration history
uv run alembic history
```

## Environment Configuration

```bash
# Database URL (SQLite by default)
DATABASE_URL=sqlite:///data/podcast.db

# Qdrant vector database
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION_NAME=podcasts
```

## Qdrant Integration

The `qdrant_client.py` module provides:

- **Vector storage** - Store episode embeddings with metadata
- **Similarity search** - Find relevant content for RAG queries
- **Episode linking** - Connect relational Episode records with vector data
- **Collection management** - Create and manage Qdrant collections

## Best Practices

1. **Use context managers** - Always use `get_db_session()` for automatic cleanup
2. **Batch operations** - Group multiple database operations in single sessions  
3. **Stage progression** - Episodes should advance through stages in order
4. **Unique constraints** - GUID field ensures no duplicate episodes
5. **Migration safety** - Always backup database before applying migrations

## Integration

The database module integrates throughout the pipeline:

- **Ingestion** - Stores episode metadata and tracks download status
- **Transcription** - Updates paths and processing stages
- **Embedding** - Links episodes with Qdrant vector data
- **Query** - Provides metadata for RAG responses
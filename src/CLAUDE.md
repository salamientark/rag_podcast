# RAG Podcast - Source Code Documentation

## Project Overview

This is a French-language podcast RAG (Retrieval Augmented Generation) system for notpatrick's podcasts. It provides end-to-end processing from RSS feed ingestion to semantic search via an MCP server.

This documentation is intended to be a **source of truth for automated code reviews** (e.g., CodeRabbit) and for humans. When in doubt, prefer the **Contracts / Invariants** section below.

## Architecture

```
src/
├── chunker/       # Token counting and text chunking
├── db/            # SQLite + Qdrant database layer
├── embedder/      # VoyageAI embedding generation
├── ingestion/     # RSS sync, audio download, reconciliation
├── llm/           # OpenAI integration
├── logger/        # Centralized logging utilities
├── mcp/           # MCP server for Claude Desktop integration
├── pipeline/      # Processing orchestrator
├── query/         # RAG query engine with French support
├── storage/       # Local/cloud storage abstraction
└── transcription/ # Gemini transcription with speaker identification
```

## Processing Pipeline (High Level)

Episodes flow through these stages tracked in the database:

1. **SYNCED** → `ingestion/sync_episodes.py` - RSS metadata to database
2. **AUDIO_DOWNLOADED** → `ingestion/audio_scrap.py` - Download audio files
3. **FORMATTED_TRANSCRIPT** → `transcription/gemini_transcript.py` - Gemini transcription + speaker identification
4. **EMBEDDED** → `embedder/embed.py` - VoyageAI embeddings to Qdrant

Note: `RAW_TRANSCRIPT` stage exists in the enum for backward compatibility but is skipped in the current pipeline.

Run the full pipeline:

```bash
uv run -m src.pipeline --podcast "Le rendez-vous Tech" --limit 5
```

---

## Contracts / Invariants (Review-Grade)

These are the rules that other modules rely on. Code reviews should treat violations as bugs.

### Identity & Keys (SQL + Qdrant)

- **`Episode.uuid` is the SQL primary key** (string UUID7). It is the only globally unique identifier.
- **`Episode.episode_id` is NOT globally unique**. It is a sequential integer **within a podcast**.
- Any cross-podcast lookup must use `uuid` (or `(podcast, episode_id)` if explicitly scoped).
- Qdrant points must be linkable back to SQL via payload field:
  - **`db_uuid`** (string) == `Episode.uuid`

### ProcessingStage monotonicity

- Stages are ordered: `SYNCED → AUDIO_DOWNLOADED → RAW_TRANSCRIPT → FORMATTED_TRANSCRIPT → EMBEDDED`.
- Normal pipeline execution must only move stages **forward**.
- The only allowed downgrade is during **reconciliation** when an episode is marked `EMBEDDED` but is not found in Qdrant.

### Filesystem layout (canonical)

Local filesystem layout is expected to be consistent across modules:

- Audio:
  - `data/{podcast}/audio/episode_{episode_id:03d}_*.mp3` (pipeline)
  - Some legacy scripts also use `data/audio/episode_{episode_id:03d}_*.mp3` (ingestion)
- Transcripts:
  - `data/{podcast}/transcripts/episode_{episode_id:03d}/formatted_episode_{episode_id:03d}.txt`
- Embeddings (local cache):
  - `data/{podcast}/embeddings/episode_{episode_id:03d}_d{dimensions}.npy`
  - File may contain 1D (legacy single chunk) or 2D (multi-chunk) arrays.

If a module introduces a new path convention, it must update:

- pipeline stage wrappers
- reconciliation logic
- documentation (this file + module CLAUDE.md)

### Qdrant payload contract (required fields)

Every Qdrant point inserted for an episode must include at least:

- `db_uuid` (string) — required for episode-level filtering
- `podcast` (string)
- `episode_id` (int) — per-podcast id, used for display and some filters
- `title` (string)
- `dimensions` (int)
- `publication_date` (ISO 8601 string)
- `chunk_index` (int, default 0)
- `total_chunks` (int, default 1)
- `text` (string) — required for RAG responses

### Qdrant indexes (required)

Before filtering/scrolling by payload fields, the collection must have payload indexes:

- `episode_id`: INTEGER
- `db_uuid`: KEYWORD

The helper `ensure_payload_indexes()` exists for this purpose.

---

## Review Guidelines (for CodeRabbit / humans)

When reviewing changes:

1. **Do not introduce new DB lookups by `Episode.id`**. The model does not have an `id` column; use `uuid` or `(podcast, episode_id)`.
2. **Any Qdrant filter must ensure payload indexes exist** (or call helper).
3. **Avoid global side effects** in import time (e.g., `load_dotenv()` inside dataclass body, global `Settings.*` in LlamaIndex) unless explicitly justified.
4. **Storage abstraction**: new file writes should go through `BaseStorage` where possible; do not hardcode cloud URLs/paths in business logic.
5. **Stage transitions** must respect monotonicity rules.

---

## Known Broken / Tech Debt (current code reality)

These are not "gotchas"; they are known runtime issues or inconsistencies that should be fixed.

1. **LocalStorage.\_get_absolute_filename is incorrect**: it references cloud attributes (`endpoint`, `bucket_name`) that do not exist in LocalStorage.
2. **Model naming drift**: query config defaults to `voyage-3.5` but embedder currently uses `voyage-3`. This can cause retrieval/embedding mismatch if not aligned.
3. **Global Settings conflicts**: query modules set `llama_index.core.Settings.*` globally; multiple instances can conflict.

---

## Core Technologies

| Component     | Technology                                       |
| ------------- | ------------------------------------------------ |
| Transcription | Google Gemini (gemini-3-flash-preview)           |
| Embeddings    | VoyageAI (currently `voyage-3` in embedder code) |
| Vector Store  | Qdrant                                           |
| SQL Database  | SQLite with SQLAlchemy                           |
| LLM           | Claude (query) + OpenAI (misc)                   |
| Reranking     | BGE-M3 multilingual                              |
| Framework     | LlamaIndex                                       |

## Environment Variables

```bash
# Database
DATABASE_URL=sqlite:///path/to/database.db
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION_NAME=podcast_episodes
QDRANT_API_KEY=xxx  # Optional for local

# API Keys
ANTHROPIC_API_KEY=xxx
VOYAGE_API_KEY=xxx
OPENAI_API_KEY=xxx
GEMINI_API_KEY=xxx

# Cloud Storage (optional)
BUCKET_ENDPOINT=https://...
BUCKET_KEY_ID=xxx
BUCKET_ACCESS_KEY=xxx
BUCKET_NAME=xxx

# Podcast Feed
FEED_URL=https://...
```

## Code Quality

```bash
uv run ruff format
uv run ruff check
```

## Module Documentation

Each module has its own `CLAUDE.md` with detailed documentation:

- [chunker/CLAUDE.md](chunker/CLAUDE.md) - Token counting, text chunking
- [db/CLAUDE.md](db/CLAUDE.md) - SQLite + Qdrant dual-database
- [embedder/CLAUDE.md](embedder/CLAUDE.md) - VoyageAI embedding generation
- [ingestion/CLAUDE.md](ingestion/CLAUDE.md) - RSS sync, audio download
- [llm/CLAUDE.md](llm/CLAUDE.md) - OpenAI speaker identification
- [logger/CLAUDE.md](logger/CLAUDE.md) - Centralized logging
- [mcp/CLAUDE.md](mcp/CLAUDE.md) - MCP server for Claude Desktop integration
- [pipeline/CLAUDE.md](pipeline/CLAUDE.md) - 5-stage orchestrator
- [query/CLAUDE.md](query/CLAUDE.md) - RAG query engine
- [storage/CLAUDE.md](storage/CLAUDE.md) - Local/cloud abstraction
- [transcription/CLAUDE.md](transcription/CLAUDE.md) - Gemini transcription

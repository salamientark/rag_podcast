# RAG Podcast - Source Code Documentation

## Project Overview

This is a French-language podcast RAG (Retrieval Augmented Generation) system for notpatrick's podcasts. It provides end-to-end processing from RSS feed ingestion to semantic search via MCP server.

## Architecture

```
src/
├── chunker/       # Token counting and text chunking
├── db/            # SQLite + Qdrant database layer
├── embedder/      # VoyageAI embedding generation
├── ingestion/     # RSS sync, audio download, reconciliation
├── llm/           # OpenAI integration for speaker identification
├── logger/        # Centralized logging utilities
├── mcp/           # MCP server for Claude Desktop integration
├── pipeline/      # 5-stage processing orchestrator
├── query/         # RAG query engine with French support
├── storage/       # Local/cloud storage abstraction
└── transcription/ # AssemblyAI transcription with diarization
```

## Processing Pipeline

Episodes flow through 5 sequential stages tracked in the database:

1. **SYNCED** → `ingestion/sync_episodes.py` - RSS metadata to database
2. **AUDIO_DOWNLOADED** → `ingestion/audio_scrap.py` - Download audio files
3. **RAW_TRANSCRIPT** → `transcription/transcript.py` - AssemblyAI transcription
4. **FORMATTED_TRANSCRIPT** → `transcription/speaker_mapper.py` - LLM speaker identification
5. **EMBEDDED** → `embedder/embed.py` - VoyageAI embeddings to Qdrant

Run the full pipeline:

```bash
uv run -m src.pipeline --podcast "Le rendez-vous Tech" --limit 5
```

## Key Entry Points

### MCP Server (for Claude Desktop)

```bash
python -m src.mcp.server --host 127.0.0.1 --port 9000
```

### Interactive Query CLI

```bash
uv run -m src.query --enable-reranking
```

### Individual Module CLIs

```bash
uv run -m src.ingestion.sync_episodes --full-sync
uv run -m src.ingestion.audio_scrap --limit 5
uv run -m src.transcription audio1.mp3 audio2.mp3
uv run -m src.embedder "data/transcripts/**/*.txt"
```

## Core Technologies

| Component     | Technology                                       |
| ------------- | ------------------------------------------------ |
| Transcription | AssemblyAI Universal-2 with diarization          |
| Embeddings    | VoyageAI voyage-3.5 (1024 dims)                  |
| Vector Store  | Qdrant                                           |
| SQL Database  | SQLite with SQLAlchemy                           |
| LLM           | Claude (query) + OpenAI (speaker identification) |
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
ASSEMBLYAI_API_KEY=xxx

# Cloud Storage (optional)
BUCKET_ENDPOINT=https://...
BUCKET_KEY_ID=xxx
BUCKET_ACCESS_KEY=xxx
BUCKET_NAME=xxx

# Podcast Feed
PODCAST_FEED_URL=https://...
```

## Code Quality

```bash
uv run ruff format
uv run ruff check
```

## Critical Gotchas

### Episode IDs vs UUIDs

- `episode_id` is NOT globally unique - only unique within a podcast
- Always use `uuid` for cross-podcast lookups
- Episode IDs assigned sequentially by RSS order (oldest first)

### Caching Strategy

The system uses aggressive caching at multiple levels:

- Transcription: Reuses existing JSON files
- Embeddings: 3-tier cache (Qdrant → local .npy → fresh generation)
- Always use `--force` to bypass caches

### French-First Design

- System prompts are in French
- BGE-M3 reranker optimized for multilingual/French
- Error messages in CLI are French

### Processing Stage Ordering

Stages are sequential and implied:

- EMBEDDED implies all previous stages complete
- Don't skip stages - reconciliation depends on this
- Use `uv run -m src.ingestion.reconcile --all` to fix inconsistencies

### Async Patterns

Query module methods are async-only. Must use:

```python
await service.query("question")
# or
asyncio.run(service.query("question"))
```

## Module Documentation

Each module has its own `CLAUDE.md` with detailed documentation:

- [chunker/CLAUDE.md](chunker/CLAUDE.md) - Token counting, text chunking
- [db/CLAUDE.md](db/CLAUDE.md) - SQLite + Qdrant dual-database
- [embedder/CLAUDE.md](embedder/CLAUDE.md) - VoyageAI embedding generation
- [ingestion/CLAUDE.md](ingestion/CLAUDE.md) - RSS sync, audio download
- [llm/CLAUDE.md](llm/CLAUDE.md) - OpenAI speaker identification
- [logger/CLAUDE.md](logger/CLAUDE.md) - Centralized logging
- [mcp/CLAUDE.md](mcp/CLAUDE.md) - MCP server for Claude Desktop
- [pipeline/CLAUDE.md](pipeline/CLAUDE.md) - 5-stage orchestrator
- [query/CLAUDE.md](query/CLAUDE.md) - RAG query engine
- [storage/CLAUDE.md](storage/CLAUDE.md) - Local/cloud abstraction
- [transcription/CLAUDE.md](transcription/CLAUDE.md) - AssemblyAI + speaker mapping

## Known Issues

1. **Import bug in transcription**: `__main__.py` imports from `src.transcript` instead of `src.transcription`
2. **LocalStorage.\_get_absolute_filename**: References undefined cloud attributes
3. **Hardcoded host name**: Speaker identification assumes "Patrick" is the host
4. **Token estimation**: Uses `word_count * 0.75` heuristic

# Query Module

## Purpose

The `query` module provides French-language RAG (Retrieval Augmented Generation) for podcast content. It supports two operational modes:

1. **Stateless service mode** (`service.py`) - Single-shot queries for MCP server integration
2. **Interactive chat mode** (`__main__.py`) - Rich CLI with conversation memory

Both modes use VoyageAI embeddings with Qdrant vector store and Claude LLM for generation.

## Key Classes

### PodcastQueryService (`service.py`)

**Stateless RAG service** - Core querying logic without conversation memory.

- Retrieves relevant podcast chunks using vector similarity
- Applies optional BGE-M3 reranking for better French results
- Handles temporal sorting for queries about "recent episodes"

### PodcastQueryAgent (`__main__.py`)

**Stateful chat agent** - Interactive CLI with conversation memory.

- Extends with `ChatMemoryBuffer` (3000 token limit)
- Uses `CondensePlusContextChatEngine` for multi-turn conversations
- Provides Rich terminal UI with French help/welcome messages

## Configuration (QueryConfig)

**Models:**

- `llm_model`: Claude Sonnet 4 (default: "claude-sonnet-4-20250514")
- `embedding_model`: VoyageAI (default: "voyage-3.5" in config)
- `rerank_model`: BGE-M3 multilingual reranker

**Retrieval settings:**

- `similarity_top_k=5`: Initial retrieval count
- `rerank_top_n=3`: Final chunks after reranking
- `use_reranking=True`: Enable/disable reranking

## Postprocessors

### sort_nodes_temporally()

Sorts retrieved nodes by episode ID (descending) for temporal queries. Detects keywords: "derniers", "dernier", "récent", "recent", "nouveau", "nouvelles"

### get_reranker()

Creates `SentenceTransformerRerank` instance using BGE-M3 model.

## Critical Contracts (for reviews)

### Qdrant payload must include text

The query system expects retrieved nodes to contain the original chunk text. This is typically stored in Qdrant payload as `text` and then surfaced by the vector store.

If embeddings were inserted without `text`, the system may retrieve metadata-only nodes and produce poor/empty answers.

### Global Settings side effects (LlamaIndex)

Both `service.py` and `__main__.py` set:

- `llama_index.core.Settings.embed_model`
- `llama_index.core.Settings.llm`

These are **global**. Multiple instances (or tests) can conflict. Reviews should be cautious about introducing additional global Settings mutations or relying on Settings state across modules.

### Episode identity

Episode identity in Qdrant must be linked via payload field:

- `db_uuid` == SQL `Episode.uuid`

Do not assume `episode_id` is globally unique.

## Gotchas

1. **Temporal sorting assumption**: assumes higher `episode_id` = more recent. This is only valid if episode_id assignment is chronological and stable per podcast.
2. **Reranking performance**: BGE-M3 is slower but more accurate.
3. **Async-only query**: must be called with `await` or `asyncio.run()`.

## CLI Entry Points

```bash
uv run -m src.query
uv run -m src.query --enable-reranking
uv run -m src.query --mcp-server-url http://localhost:9000
```

## Known Gaps (not necessarily broken)

- `process_nodes_with_metadata()` exists but is not consistently applied in the query flow. If you want guaranteed citations, ensure metadata injection is part of the retrieval/synthesis pipeline.

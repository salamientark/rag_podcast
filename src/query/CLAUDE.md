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
- `embedding_model`: VoyageAI (default: "voyage-3.5" @ 1024 dims)
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

## CLI Entry Points

```bash
uv run -m src.query
uv run -m src.query --enable-reranking
uv run -m src.query --mcp-server-url http://localhost:9000
```

## Gotchas

1. **Global Settings**: LLM and embedding models configured globally via `Settings`. Conflicts possible with multiple instances.

2. **Temporal Sorting Logic**: Assumes higher `episode_id` = more recent.

3. **Reranking Performance**: BGE-M3 is slower but more accurate. Default enabled.

4. **Memory Token Limit**: 3000 tokens (~8-12 exchanges). Older messages auto-dropped.

5. **API Key Validation**: Missing keys raise `ValueError` immediately at initialization.

6. **Async-Only Query**: Must be called with `await` or `asyncio.run()`.

7. **Response Type**: Returns `str`, not response objects. Metadata lost.

8. **Error Messages in French**: User-facing CLI errors are in French.

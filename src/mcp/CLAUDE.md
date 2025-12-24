# MCP Module

## Overview

This module implements an MCP (Model Context Protocol) server for the RAG Podcast system. It exposes the podcast query functionality as an MCP tool that can be used by MCP clients like Claude Desktop.

## Purpose

- Provides a standardized interface to the RAG podcast database via MCP
- Enables stateless RAG queries (no conversation memory at the server level)
- Client-side agentic behavior handled by MCP clients
- French-language podcast content querying

## Key Files

### `server.py`

Entry point for running the MCP server.

- Disables tokenizer parallelism to avoid fork issues with FastMCP
- Supports HTTP transport with configurable host/port (default: 127.0.0.1:9000)

### `config.py`

Core configuration and dependency injection.

- **`mcp`**: Global FastMCP instance named "Rag Podcast Server"
- **`config`**: Global QueryConfig instance
- **`get_query_service()`**: Lazy-initializes singleton PodcastQueryService

### `prompts.py`

French-language system prompt for the MCP server.

- Instructs AI to use `query_podcast` tool for all podcast-related queries

### `tools/query_db.py`

The core MCP tool implementation.

- **`@mcp.tool() async def query_db(question: str) -> str`**
  - Stateless RAG query - each call is independent
  - Delegates to `PodcastQueryService.query()`

## Architecture Patterns

### Stateless Design

The server maintains NO conversation history. Each `query_db()` call is independent. The MCP client handles:

- Conversation context
- Query reformulation
- Multi-turn reasoning

### Singleton Service Pattern

Single `PodcastQueryService` instance shared across all requests via lazy initialization.

## Gotchas

1. **Tokenizer Parallelism**: Must set `TOKENIZERS_PARALLELISM=false` before importing transformers.

2. **Service Initialization**: Lazy-loaded on first query, not at server startup. First query may be slower.

3. **Language**: System designed for French queries and responses.

4. **Transport**: Currently configured for HTTP. Update `mcp.run()` for stdio.

5. **Import Order**: `tools/query_db.py` imported at end of `config.py` after `mcp` is defined.

## Running the Server

```bash
python -m src.mcp.server
python -m src.mcp.server --host 0.0.0.0 --port 8080
```

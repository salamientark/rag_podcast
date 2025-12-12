# Query Agent

Interactive CLI for querying podcast content using RAG (Retrieval-Augmented Generation) with LlamaIndex, VoyageAI, and Qdrant.

## Quick Start

```bash
# Start interactive query session
uv run -m src.query

# With reranking enabled (slower but higher quality)
uv run -m src.query --enable-rerank
```

## Features

- **Natural Language Queries** - Ask questions about podcast episodes in plain English
- **Vector Similarity Search** - Find relevant content using VoyageAI embeddings
- **Conversational Memory** - Maintains context across questions (3000 token limit)
- **BGE-M3 Reranking** - Optional reranking for improved relevance (local, free)
- **Episode Metadata** - Answers include episode titles, IDs, and dates
- **Rich CLI Interface** - Clean formatting with Rich library

## Configuration

Required environment variables:
```bash
OPENAI_API_KEY=your_openai_key          # For chat completions
VOYAGE_API_KEY=your_voyage_key          # For embeddings
QDRANT_URL=http://localhost:6333        # Vector database
QDRANT_COLLECTION_NAME=podcasts         # Collection name
```

## Usage Examples

### Interactive Session
```bash
uv run -m src.query

🎧 Podcast Query Agent
Ask questions about your episodes!

You: What did they discuss about AI developments?
Agent: In episodes 671-673, they covered Google's new AI models, 
       including Gemini improvements and competitive responses...

You: Tell me more about episode 672 specifically
Agent: Episode 672 "Google takes the AI pole position" focused on...

You: /quit
👋 Goodbye!
```

### Available Commands
- **Regular questions** - Natural language queries about podcast content
- **`/help`** - Show help information  
- **`/quit`** - Exit the application

## Architecture

- **LlamaIndex** - RAG framework with query engine
- **VoyageAI** - Text embeddings (voyage-3, 1024 dimensions)
- **Qdrant** - Vector database for similarity search
- **OpenAI GPT-4** - Chat completions and response generation
- **BGE-M3** - Optional reranking model (local inference)

## Performance Settings

**Default Configuration:**
- Top-K retrieval: 10 chunks initially → 5 after reranking
- Memory limit: 3000 tokens (~8-12 conversation exchanges)
- Reranking: Disabled (enable with `--enable-rerank`)
- Response language: English interface

**Memory Management:**
The agent maintains conversation history up to 3000 tokens. Older exchanges are automatically pruned when the limit is reached.

## Requirements

Your Qdrant collection must contain:
- **Vector embeddings** (1024-dimensional VoyageAI)
- **Metadata** with episode_id, title, chunk_index
- **Original text content** in payload (required for RAG)

If text content is missing from your Qdrant payloads, see the embedder module documentation for re-embedding with text included.

## Troubleshooting

**Connection Issues:**
```bash
# Verify Qdrant is running
curl http://localhost:6333/health

# Check collection exists
curl http://localhost:6333/collections
```

**Empty Responses:**
- Ensure episodes are embedded in Qdrant with text content
- Try broader queries if being too specific
- Check logs for embedding or retrieval errors

**Performance Issues:**
- Enable reranking for better relevance: `--enable-rerank`
- Reduce conversation history by restarting the session
- Verify adequate system memory for BGE-M3 model
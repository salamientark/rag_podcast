# Chunker Module

## Purpose

This module handles text tokenization and chunking for the RAG podcast system. It provides utilities to:

- Count tokens in text using tiktoken encoding
- Split long texts into overlapping chunks for processing
- Validate text against API provider limits (Voyage AI)
- Convert chunk objects to plain text lists

## Key Components

### token_counter.py

**Core Functions:**

- `count_tokens(text, encoding_name="cl100k_base")` - Count tokens using tiktoken encoder
- `truncate_to_tokens(text, max_tokens, encoding_name="cl100k_base")` - Truncate text to fit token limit
- `check_voyage_limits(texts, model="voyage-3.5", encoding_name="cl100k_base")` - Validate against Voyage AI API limits

**Constants:**

- `VOYAGE_LIMITS` - Dictionary of token limits for Voyage AI embedding models (context_length, batch_total, batch_size)

### chunker.py

**Core Functions:**

- `chunk_long_text(text, max_tokens=30000, overlap_percent=0.1)` - Main chunking function with overlap
- `chunks_to_text(chunks)` - Extract text strings from Chunk objects

**Dependencies:**

- Uses `chonkie.chunker.token.TokenChunker` for actual chunking logic
- Uses tiktoken's "cl100k_base" encoding (GPT-4/3.5-turbo compatible)

## Important Patterns

### Token Counting

All token counting uses tiktoken with "cl100k_base" encoding by default. This provides accurate counts for OpenAI models and approximate counts for Voyage AI embeddings.

### Chunking Strategy

- Chunks overlap by default (10% overlap_percent)
- Only chunks if text exceeds max_tokens threshold
- Returns list with single item if no chunking needed
- Uses TokenChunker from chonkie library, not custom implementation

### Logging

Both modules use Python's logging module:

- `token_counter.py` uses `__name__` logger
- `chunker.py` uses "embedder" logger (note: not "chunker")

## Gotchas

1. **Encoding Mismatch**: The module uses "cl100k_base" encoding throughout. If you need different encoding for specific models, you must pass `encoding_name` parameter explicitly.

2. **Logger Name**: chunker.py logs to "embedder" logger, not "chunker" - this is intentional for pipeline integration but can be confusing.

3. **Chunk Objects**: `chunk_long_text()` returns list of strings, but internally works with Chunk objects from chonkie. Use `chunks_to_text()` if you need to convert Chunk objects elsewhere.

4. **Overlap Calculation**: Overlap is specified as percentage (0.1 = 10%), not absolute tokens. The overlap_tokens is calculated as `int(max_tokens * overlap_percent)`.

5. **Voyage AI Limits**: The VOYAGE_LIMITS dictionary is as of Dec 2025. These limits may change - check Voyage AI docs if you see unexpected validation failures.

6. **No Return on Fit**: `chunk_long_text()` doesn't tell you whether chunking occurred - check returned list length (1 = no chunking, >1 = chunked).

7. **External Dependency**: Core chunking logic lives in the `chonkie` library, not this module. This module is essentially a wrapper around chonkie's TokenChunker.

## Usage Example

```python
from src.chunker import count_tokens, chunk_long_text, chunks_to_text, check_voyage_limits

# Count tokens
text = "Your long transcript here..."
token_count = count_tokens(text)

# Chunk if needed (with 10% overlap)
chunks = chunk_long_text(text, max_tokens=8000, overlap_percent=0.1)
print(f"Created {len(chunks)} chunks")

# Validate before API call
result = check_voyage_limits(chunks, model="voyage-3.5")
if not result["fits"]:
    print(f"Limit violations: {result['issues']}")
```

## Module Exports

From `__init__.py`:

- `count_tokens` - Token counting function
- `chunk_long_text` - Main chunking function
- `chunks_to_text` - Chunk object conversion utility

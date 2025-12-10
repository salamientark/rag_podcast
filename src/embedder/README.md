# Embedder Module

Generate text embeddings from podcast transcripts using VoyageAI's embedding models with automatic token validation.

## Overview

The embedder module provides:
- **CLI tool** for generating embeddings from transcript files
- **Token counter** for validating text length before API calls
- **Automatic validation** against Voyage AI token limits

## CLI Usage

### Basic Command

```bash
uv run -m src.embedder <input_file> [options]
```

### Options

| Option | Short | Type | Description |
|--------|-------|------|-------------|
| `input_file` | - | Path | **Required.** Path to input transcript file (JSON or TXT) |
| `--dimensions` | `-d` | int | Output vector dimensions: 256, 512, 1024, 2048 (default: 1024) |
| `--outfile` | `-o` | Path | Custom output path (default: `data/embeddings/<input>.npy`) |
| `--verbose` | `-v` | flag | Enable detailed logging output |

### Examples

```bash
# Basic usage with default 1024 dimensions
uv run -m src.embedder data/transcript/episode_672.json
```

**Output:**
```
Loading transcript from episode_672.json...
Generating embeddings with 1024 dimensions...
✓ Successfully saved embeddings to: data/embeddings/episode_672.npy
```

```bash
# Custom dimensions
uv run -m src.embedder episode.json --dimensions 512
```

**Output:**
```
Loading transcript from episode.json...
Generating embeddings with 512 dimensions...
✓ Successfully saved embeddings to: data/embeddings/episode.npy
```

```bash
# Verbose mode - shows token counts and detailed progress
uv run -m src.embedder episode.json --verbose
```

**Output:**
```
Loading transcript from episode.json...
Transcript preview (first 500 chars):
Speaker A: Today we're discussing...

Generating embeddings with 1024 dimensions...
Total tokens processed: 22,171
Embedding shape: 1024 dimensions
Saving embeddings to data/embeddings/episode.npy...
✓ Successfully saved embeddings to: data/embeddings/episode.npy
```

```bash
# Custom output location
uv run -m src.embedder episode.json -o custom/path/output.npy
```

**Output:**
```
Loading transcript from episode.json...
Generating embeddings with 1024 dimensions...
✓ Successfully saved embeddings to: custom/path/output.npy
```

```bash
# Combined options
uv run -m src.embedder episode.json -d 256 -o output.npy --verbose
```

**Output:**
```
Loading transcript from episode.json...
Transcript preview (first 500 chars):
...

Generating embeddings with 256 dimensions...
Total tokens processed: 22,171
Embedding shape: 256 dimensions
Saving embeddings to output.npy...
✓ Successfully saved embeddings to: output.npy
```

## Token Counter Utility

The token counter validates text length against Voyage AI limits **before** making API calls. This prevents errors, saves API costs, and helps you decide whether to send whole text or chunk it.

### What It Does

- **Counts tokens** in your text using tiktoken (OpenAI's tokenizer)
- **Validates** against Voyage AI model limits (context length, batch size, etc.)
- **Prevents errors** by catching oversized texts before API calls
- **Helps chunking decisions** - tells you if text needs to be split

### Quick Usage

```python
from src.embedder.token_counter import count_tokens, check_voyage_limits

# Count tokens
tokens = count_tokens("Your transcript text...")
print(f"Token count: {tokens:,}")

# Check if it fits Voyage AI limits
result = check_voyage_limits(text, model="voyage-3")
if result["fits"]:
    print(f"✓ Safe to embed ({result['total_tokens']:,} tokens)")
else:
    print(f"✗ Too large: {result['issues']}")
```

### Voyage AI Model Limits

| Model | Context Length | When to Use |
|-------|----------------|-------------|
| `voyage-3` | 32,000 tokens | Default choice (currently used by embedder) |
| `voyage-3.5` | 32,000 tokens | Latest model with improved quality |
| `voyage-3.5-lite` | 32,000 tokens | Faster/cheaper option |
| `voyage-3-large` | 32,000 tokens | Best quality |

### When to Chunk vs. Send Whole

**✓ Send whole text when:**
- Token count < 32,000 (within context limit)
- Processing single podcast episodes (~20K tokens typical)

**⚠ Chunk text when:**
- Token count > 32,000 (exceeds context length)
- Building RAG systems (smaller chunks = better retrieval)

**Example:** Episode 672 has 22,171 tokens (69% of limit) → send whole text at once!

### Available Functions

#### `count_tokens(text: str) -> int`
Count tokens in text.

```python
from src.embedder.token_counter import count_tokens
tokens = count_tokens("Hello, world!")  # Returns: 4
```

#### `check_voyage_limits(texts: str | list[str], model: str = "voyage-3.5") -> dict`
Validate text against Voyage AI limits.

```python
from src.embedder.token_counter import check_voyage_limits

result = check_voyage_limits(transcript, model="voyage-3")
# Returns: {
#   "fits": True/False,
#   "total_tokens": 22171,
#   "issues": [],  # List of problems if any
#   "model_limits": {...}
# }
```

#### `truncate_to_tokens(text: str, max_tokens: int) -> str`
Truncate text to fit within token limit.

```python
from src.embedder.token_counter import truncate_to_tokens
short_text = truncate_to_tokens(long_text, max_tokens=1000)
```

For detailed documentation, see `TOKEN_COUNTER_README.md` in this directory.

## Performance Notes

- **Token counting:** <1ms for typical transcripts
- **Embedding generation:** ~2-5s depending on text length and API latency
- **Storage:** 
  - 256 dims: ~1KB per document
  - 1024 dims: ~4KB per document
  - 2048 dims: ~8KB per document

## Environment Variables

- `VOYAGE_API_KEY` - **Required.** Your Voyage AI API key
- Get your API key at: https://www.voyageai.com/

## Related Documentation

- **Voyage AI API Docs:** https://docs.voyageai.com/docs/embeddings

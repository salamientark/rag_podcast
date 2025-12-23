# Embedder Module

Generate text embeddings from podcast transcripts using VoyageAI and store them in Qdrant vector database for RAG applications.

## Quick Start

```bash
# Embed single transcript file
uv run -m src.embedder data/transcripts/formatted_episode.txt

# Batch process multiple files
uv run -m src.embedder "data/transcripts/*/formatted_*.txt"

# With custom dimensions
uv run -m src.embedder *.txt --dimensions 512
```

## CLI Tools

### Batch Processing (Recommended)
```bash
# Process all formatted transcripts
uv run -m src.embedder "data/transcripts/*/formatted_*.txt"

# Custom collection and dimensions
uv run -m src.embedder *.txt --collection my_podcasts --dimensions 512

# Preview without processing
uv run -m src.embedder "**/*.txt" --dry-run --verbose
```

**Options:**
- `--dimensions` (`-d`) - Vector dimensions: 256, 512, 1024, 2048 (default: 1024)
- `--collection` - Qdrant collection name (default: from environment)
- `--save-local` - Save embeddings as .npy files locally
- `--episode-id` - Override episode UUID for database lookup
- `--dry-run` - Validate files without processing
- `--verbose` (`-v`) - Detailed logging output

### Single File Processing
```bash
# Generate embeddings for one file
uv run -m src.embedder transcript.json

# Custom output location
uv run -m src.embedder transcript.json -o custom/path/output.npy

# Verbose mode with token counting
uv run -m src.embedder transcript.json --verbose
```

## Features

- **VoyageAI Integration** - Uses voyage-3 model (1024-dim embeddings)
- **Qdrant Storage** - Direct integration with vector database
- **Batch Processing** - Handle multiple files with glob patterns
- **Token Validation** - Pre-validates text against VoyageAI limits
- **Auto Episode ID** - Extracts episode numbers from filenames
- **Progress Tracking** - Real-time progress with success/failure reporting
- **Local Backup** - Optional .npy file storage for embeddings

## Token Counter

Validates text against VoyageAI model limits before API calls:

```python
from src.embedder.token_counter import count_tokens, check_voyage_limits

# Count tokens in text
tokens = count_tokens("Your transcript text...")
print(f"Token count: {tokens:,}")

# Validate against model limits
result = check_voyage_limits(text, model="voyage-3")
if result["fits"]:
    print(f"✓ Safe to embed ({result['total_tokens']:,} tokens)")
else:
    print(f"✗ Too large: {result['issues']}")
```

**VoyageAI Model Limits:**
- **voyage-3**: 32,000 tokens (current default)
- **voyage-3.5**: 32,000 tokens (latest model)
- **voyage-3-large**: 32,000 tokens (best quality)

## Output Examples

**Batch Processing:**
```
Processing 3 file(s)...
------------------------------------------------------------

[1/3] Processing: formatted_episode_671.txt
  ✓ Successfully processed formatted_episode_671.txt

[2/3] Processing: formatted_episode_672.txt
  ✓ Successfully processed formatted_episode_672.txt
    Local file: data/embeddings/episode_672_d1024.npy

[3/3] Processing: formatted_episode_673.txt
  ✓ Successfully processed formatted_episode_673.txt

============================================================
PROCESSING SUMMARY
============================================================
Total files:    3
Successful:     3
Failed:         0
Collection:     podcasts
Dimensions:     1024

✓ Batch processing complete!
```

**Single File:**
```
Loading transcript from episode_672.json...
Generating embeddings with 1024 dimensions...
Total tokens processed: 22,171
✓ Successfully saved embeddings to: data/embeddings/episode_672.npy
```

## Environment Variables

```bash
# Required
VOYAGE_API_KEY=your_voyage_ai_key_here

# Optional (defaults)
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION_NAME=podcasts
```

## Integration with Pipeline

The embedder integrates with the main pipeline system:

```bash
# Embed through pipeline (recommended)
uv run -m src.pipeline --podcast "Le rendez-vous Tech" --stages embed --limit 5
```

## Troubleshooting

**Token Limit Errors:**
```bash
# Check token count first
uv run python -c "from src.embedder.token_counter import count_tokens; print(count_tokens(open('file.txt').read()))"

# Use smaller chunks if over 32,000 tokens
```

**API Key Issues:**
```bash
# Verify API key is set
echo $VOYAGE_API_KEY

# Test API connectivity
uv run python -c "import voyageai; print('VoyageAI key valid')"
```

**Qdrant Connection:**
```bash
# Check Qdrant health
curl http://localhost:6333/health

# Verify collection exists
curl http://localhost:6333/collections
```

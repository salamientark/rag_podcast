# RAG Podcast Project

A complete RAG (Retrieval-Augmented Generation) system for podcast content analysis and querying. This project provides an end-to-end pipeline from RSS feeds to AI-powered conversations about podcast content.

## 🎯 Overview

Transform podcast episodes into a searchable, queryable knowledge base:
- **📡 Automated ingestion** from RSS feeds with metadata extraction
- **📁 Audio file management** with organized download and storage
- **🎙️ Advanced transcription** using Google Gemini with speaker identification  
- **📝 Intelligent text processing** with semantic chunking for RAG
- **🔍 Vector embeddings** using VoyageAI stored in Qdrant database
- **🤖 AI query agent** for natural language conversations about episodes

## 🏗️ Architecture

```
rag_podcast/
├── src/
│   ├── db/              # SQLAlchemy models, database connections, migrations
│   ├── ingestion/       # RSS sync, audio downloads, reconciliation
│   ├── transcription/   # Gemini transcription with speaker identification
│   ├── chunker/         # Semantic text chunking for RAG
│   ├── embedder/        # VoyageAI embeddings with Qdrant storage
│   ├── query/           # RAG query agent with LlamaIndex
│   ├── pipeline/        # End-to-end orchestration system
│   ├── llm/             # OpenAI integration and LLM abstractions
│   └── logger/          # Centralized logging infrastructure
├── alembic/             # Database schema migrations
├── data/                # Episode storage (audio, transcripts, embeddings)
└── logs/                # Application logs by module
```

## 🔄 Processing Pipeline

Episodes flow through these automated stages:
1. **`SYNCED`** → Metadata fetched from RSS feed
2. **`AUDIO_DOWNLOADED`** → MP3 files downloaded locally  
3. **`FORMATTED_TRANSCRIPT`** → Transcribed with Gemini (speaker identification included)
5. **`EMBEDDED`** → Chunked and embedded in Qdrant vector database

## 🚀 Key Features

- **🎯 Complete automation** - One command processes entire pipeline
- **🔍 Advanced search** - Vector similarity + keyword search + reranking
- **🎭 Speaker identification** - AI-powered speaker name mapping
- **📊 Progress tracking** - Detailed logging and status monitoring  
- **🔧 Flexible configuration** - Granular control over each stage
- **💾 Incremental processing** - Smart resumption and duplicate handling

## ⚙️ Requirements

- **Python** >= 3.13
- **Package Manager**: [`uv`](https://docs.astral.sh/uv/) (fast Python package manager)
- **Vector Database**: [Qdrant](https://qdrant.tech/) (local or cloud instance)
- **API Keys**: OpenAI, VoyageAI, Gemini

## 🛠️ Setup

### 1. Install Dependencies
```bash
# Clone repository
git clone <repository-url>
cd rag_podcast

# Install with uv (recommended)
uv sync

# Alternative: pip install
pip install -e .
```

### 2. Environment Configuration
```bash
# Copy example environment file
cp .env.example .env

# Required API keys (.env):
OPENAI_API_KEY=your_openai_key_here
VOYAGE_API_KEY=your_voyage_ai_key_here  
GEMINI_API_KEY=your_gemini_key_here

# Database configuration
DATABASE_URL=sqlite:///data/podcast.db
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION_NAME=podcasts

# RSS feed URL
FEED_URL=https://feeds.example.com/your-podcast-feed
```

### 3. Database Setup
```bash
# Apply database migrations
uv run alembic upgrade head

# Verify database creation
ls -la data/podcast.db
```

### 4. Start Qdrant (Vector Database)
```bash
# Option 1: Docker (recommended)
docker compose up -d qdrant

# Option 2: Local installation
# Follow instructions at https://qdrant.tech/documentation/quick-start/
```

## 🎯 Quick Start

### Complete Pipeline (Recommended)
```bash
# Process everything: sync → download → transcribe → embed
uv run -m src.pipeline --limit 5

# Process specific episodes
uv run -m src.pipeline --episode-id 672 673 674

# Preview what would be processed (dry run)
uv run -m src.pipeline --dry-run --limit 3
```

### Query Your Podcast Content
```bash
# Start the interactive query agent
uv run -m src.query

# Example conversation:
# You: What did they discuss about AI in recent episodes?
# Agent: Based on episodes 672-674, they covered Google's new AI models...
```

## 📋 Detailed Usage

### 1. Episode Ingestion

**Sync RSS Feed to Database:**
```bash
# Basic sync (last 30 days)
uv run -m src.ingestion.sync_episodes

# Full history sync
uv run -m src.ingestion.sync_episodes --full-sync

# Limited sync with preview
uv run -m src.ingestion.sync_episodes --limit 10 --dry-run --verbose

# Use custom RSS feed
uv run -m src.ingestion.sync_episodes --feed-url https://feeds.example.com/podcast.xml
```

**Download Audio Files:**
```bash
# Download all missing episodes
uv run -m src.ingestion.audio_scrap

# Targeted download
uv run -m src.ingestion.audio_scrap --limit 5 --verbose
```

### 2. Transcription & Processing

**Transcribe Audio:**
```bash
# Transcribe all pending audio files
uv run -m src.transcription

# Force re-transcription
uv run -m src.transcription --force

# Preview transcription queue
uv run -m src.transcription --dry-run
```

**Generate Embeddings:**
```bash
# Embed formatted transcripts into Qdrant
uv run -m src.embedder "data/transcripts/*/formatted_*.txt"

# Custom embedding dimensions
uv run -m src.embedder transcript.txt --dimensions 512
```

### 3. End-to-End Pipeline

**Automated Processing:**
```bash
# Process all episodes through complete pipeline
uv run -m src.pipeline --full

# Process specific stages only
uv run -m src.pipeline --stages raw_transcript,embedded --limit 5

# Force reprocessing
uv run -m src.pipeline --episode-id 672 --force
```

### 4. UI

**History database**
```bash
# Start the postrgesql server
pg_ctl -D ./data/db_data -l logfile start
```

### Database Management

#### Apply Migrations

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Rollback one migration
uv run alembic downgrade -1

# View migration history
uv run alembic history
```

#### Create New Migrations

```bash
# Auto-generate migration from model changes
uv run alembic revision --autogenerate -m "description of changes"

# Create empty migration template
uv run alembic revision -m "description"
```

### Code Quality

#### Linting

```bash
# Check for issues
uv run ruff check

# Auto-fix issues
uv run ruff check --fix
```

#### Formatting

```bash
# Format code
uv run ruff format
```

## Development

### Logging

This project uses a centralized logging system with flexible decorators. See [src/logger/README.md](src/logger/README.md) for detailed documentation on:
- Setting up loggers
- Using logging decorators
- Customizing log output
- Examples and best practices

Quick example:
```python
from src.logger import setup_logging, log_function

logger = setup_logging("my_module", "logs/my_module.log")

@log_function(logger_name="my_module", log_execution_time=True)
def my_function():
    logger.info("Processing...")
```

### Adding New Features

1. Create your module in the appropriate `src/` subdirectory
2. Use the centralized logging utilities from `src.utils`
3. Follow the code style guidelines in `AGENTS.md`
4. Update database models if needed and create migrations
5. Add examples and documentation

## 🔄 Common Workflows

### Initial Setup (New Installation)
```bash
# 1. Complete setup for first 10 episodes
uv run -m src.pipeline --limit 10

# 2. Start querying your content
uv run -m src.query
```

### Daily Updates
```bash
# Process new episodes from last 7 days
uv run -m src.ingestion.sync_episodes --days 7
uv run -m src.pipeline --limit 5
```

### Maintenance & Recovery
```bash
# Verify database consistency with filesystem
uv run -m src.ingestion.reconcile --all --dry-run

# Fix sync issues
uv run -m src.ingestion.reconcile --all

# Reprocess failed episodes
uv run -m src.pipeline --episode-id 672 673 --force
```

### Development & Testing
```bash
# Safe preview mode (no changes)
uv run -m src.ingestion.sync_episodes --dry-run --limit 3
uv run -m src.pipeline --dry-run --limit 3

# Process single episode end-to-end
uv run -m src.pipeline --episode-id 672 --verbose
```

### Monitoring & Logs

Log files in `logs/` directory:
- `pipeline.log` - End-to-end pipeline operations
- `sync_episodes.log` - RSS feed sync operations  
- `audio_download.log` - Audio download operations
- `transcript.log` - Transcription operations
- `database.log` - Database operations

## 🔧 Troubleshooting

### Common Issues

**Pipeline Failures:**
```bash
# Check pipeline status and logs
uv run -m src.pipeline --dry-run --verbose

# Verify database consistency
uv run -m src.ingestion.reconcile --all --dry-run
```

**Database Issues:**
```bash
# Check migration status
uv run alembic current
uv run alembic history

# Reset database (caution!)
rm data/podcast.db
uv run alembic upgrade head
```

**API Key Errors:**
```bash
# Verify environment variables
grep -E "(OPENAI|VOYAGE|GEMINI)" .env

# Test API connectivity
uv run python -c "import openai; print('OpenAI key valid')"
```

**Qdrant Connection Issues:**
```bash
# Check Qdrant status
curl http://localhost:6333/health

# Restart Qdrant
docker restart $(docker ps -q --filter ancestor=qdrant/qdrant)
```

**Performance Issues:**
- Large episodes: Use `--limit` flags to process in batches
- Slow queries: Enable reranking with `--enable-rerank` 
- Memory usage: Monitor with `uv run -m src.pipeline --verbose`

### Getting Help

1. **Check logs** in `logs/` directory for detailed error messages
2. **Use verbose mode** with `--verbose` flag for debugging
3. **Dry run mode** with `--dry-run` to preview operations safely
4. **Run reconciliation** to fix database inconsistencies

**Environment Setup:**
Always use `uv run` prefix to ensure proper Python environment activation.

# Transcription Module

Audio transcription with speaker diarization using AssemblyAI Universal-2, including intelligent speaker identification and transcript formatting.

## Quick Start

```bash
# Transcribe all pending audio files
uv run -m src.transcription

# Force re-transcription of specific files
uv run -m src.transcription --force

# Preview transcription queue
uv run -m src.transcription --dry-run --verbose
```

## Features

- **AssemblyAI Integration** - Universal-2 model with speaker diarization
- **Speaker Identification** - AI-powered mapping of speaker labels to real names
- **Batch Processing** - Handle multiple audio files automatically
- **Smart Resumption** - Skip already transcribed files unless forced
- **Database Integration** - Automatic status tracking and metadata storage
- **Progress Tracking** - Real-time progress with detailed logging

## CLI Options

- `--force` - Re-transcribe files that already have transcripts
- `--no-db-update` - Skip database status updates (file operations only)
- `--dry-run` - Preview what would be processed without execution
- `--verbose` (`-v`) - Enable detailed logging output
- `--help` - Show complete usage information

## Processing Pipeline

### 1. Audio Detection
Automatically finds audio files ready for transcription:
- Scans database for episodes with `AUDIO_DOWNLOADED` stage
- Verifies audio files exist on filesystem
- Skips episodes that already have formatted transcripts

### 2. Raw Transcription
Uses AssemblyAI Universal-2 with speaker diarization:
- Uploads audio to AssemblyAI
- Processes with speaker separation
- Downloads raw transcript with speaker labels
- Saves as `raw_episode_XXX.json`

### 3. Speaker Identification
AI-powered speaker name mapping:
- Analyzes conversation context and patterns
- Identifies real names from dialogue content
- Creates speaker mapping (e.g., "Speaker A" → "Patrick")
- Saves mapping as `speakers_episode_XXX.json`

### 4. Transcript Formatting
Combines transcription with speaker identification:
- Applies speaker mappings to raw transcript
- Formats with real speaker names
- Creates formatted transcript for RAG embedding
- Saves as `formatted_episode_XXX.txt`

## Output Files

For episode 672, the module generates:
```
data/transcript/episode_672/
├── raw_episode_672_universal.json       # Raw AssemblyAI transcript
├── speakers_episode_672.json            # Speaker name mappings  
└── formatted_episode_672.txt            # Final formatted transcript
```

## Usage Examples

### Basic Transcription
```bash
# Process all pending episodes
uv run -m src.transcription

# Example output:
# [1/3] Processing: episode_672.mp3
#   Episode ID: 672
#   ⟳ Transcribing...
#   ✓ Transcription completed successfully
```

### Force Reprocessing
```bash
# Re-transcribe specific episodes
uv run -m src.transcription --force

# Useful when:
# - Improving speaker identification
# - Fixing transcript formatting
# - Testing new transcription settings
```

### Dry Run Preview
```bash
uv run -m src.transcription --dry-run --verbose

# Shows:
# - Which files would be processed
# - Current episode processing status
# - Database update actions
# - File existence checks
```

## Configuration

Environment variables:
```bash
# Required
ASSEMBLYAI_API_KEY=your_assemblyai_key
OPENAI_API_KEY=your_openai_key      # For speaker identification

# Optional
DATABASE_URL=sqlite:///data/podcast.db
TRANSCRIPT_OUTPUT_DIR=data/transcript  # Custom output directory
```

## Integration

### With Pipeline System
```bash
# Transcribe through main pipeline (recommended)
uv run -m src.pipeline --stages raw_transcript,formatted_transcript --limit 5

# Direct transcription (advanced usage)
uv run -m src.transcription --verbose
```

### With Database
The module automatically:
- Updates episode `processing_stage` to `FORMATTED_TRANSCRIPT`
- Sets file path fields (`raw_transcript_path`, `formatted_transcript_path`, etc.)
- Records transcript duration and confidence scores
- Links episodes for downstream embedding process

## Speaker Identification

The AI speaker identification process:

1. **Context Analysis** - Examines conversation patterns and content
2. **Name Extraction** - Identifies explicit name mentions in dialogue
3. **Role Detection** - Determines host vs. guest relationships
4. **Mapping Creation** - Creates reliable speaker label mappings

**Example transformation:**
```
Input:  "Speaker A: Welcome back to the show..."
        "Speaker B: Thanks for having me, Patrick..."

Output: {"Speaker A": "Patrick", "Speaker B": "Guest"}
```

## Error Handling

Common issues and solutions:

**API Errors:**
- Rate limiting: Automatic retry with exponential backoff
- Authentication: Verify API keys in environment
- File upload issues: Check audio file format and size

**Processing Failures:**
- Speaker ID failures: Falls back to generic labels
- Network issues: Saves partial progress and resumes
- Database errors: Files are saved even if DB update fails

## Best Practices

1. **Batch Processing** - Process multiple files together for efficiency
2. **Monitor Logs** - Check `logs/transcript.log` for detailed status
3. **Verify Output** - Review speaker identification accuracy
4. **Resource Management** - AssemblyAI processes files asynchronously
5. **Cost Optimization** - Use `--dry-run` to preview before processing large batches

## Output Format

**Formatted Transcript Example:**
```
Patrick: Welcome back to Tech Talk, I'm Patrick and today we're discussing...

Guest: Thanks for having me Patrick. I'm excited to talk about the new AI developments...

Patrick: Let's dive right in. What's the most significant change you've seen?
```

This formatted output is optimized for:
- RAG embedding and chunking
- Natural language processing
- Human readability
- Conversation flow preservation
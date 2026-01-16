# Transcription Module

## Purpose

Converts audio podcast files into formatted transcripts with speaker identification using Google Gemini.

This module is part of the pipeline stage:

`AUDIO_DOWNLOADED → FORMATTED_TRANSCRIPT`

## Key Components

### gemini_transcript.py

Core transcription functionality using Google Gemini API.

**Key Functions:**

- `transcribe_with_gemini(file_path, description)` - Main transcription with speaker identification
- `get_gemini_client()` - Returns configured Gemini client

**How it works:**

1. Uploads audio file to Gemini
2. Sends transcription prompt with episode description for speaker context
3. Gemini returns formatted transcript with timestamps and speaker names
4. No intermediate steps needed (no raw JSON, no separate speaker mapping)

**Output:**

```python
{
    "transcript": {"text": str},
    "formatted_text": str,  # Ready-to-use formatted transcript
    "_metadata": {
        "transcriber": "gemini",
        "model": "gemini-3-flash-preview",
        "processing_time_seconds": float,
        "prompt_tokens": int,
        "response_tokens": int,
        ...
    }
}
```

## File Naming Convention

Outputs are organized in: `{output_dir}/episode_{episode_id:03d}/`

- Formatted: `formatted_episode_{episode_id:03d}.txt`

## CLI

The CLI is implemented in `src/transcription/__main__.py`:

```bash
uv run -m src.transcription --podcast "Podcast Name" episode_001.mp3
uv run -m src.transcription --podcast "Podcast Name" *.mp3 --force
uv run -m src.transcription --podcast "Podcast Name" *.mp3 --dry-run
```

Options:
- `--force` - Re-transcribe even if transcript exists
- `--no-db-update` - Skip database updates
- `--dry-run` - Preview without processing
- `--verbose` - Enable detailed logging

## Environment Variables

```bash
GEMINI_API_KEY=your_gemini_api_key
```

## Cost

Gemini 3 Flash: ~$0.16/hour of audio (32 tokens/second, $1/1M audio tokens)

## Gotchas

1. **Episode identity**: SQL primary key is `Episode.uuid`. The integer `episode_id` is per-podcast and not globally unique.
2. **Description context**: Episode description is passed to Gemini for better speaker identification. If not available, generic labels (Speaker A, Speaker B) are used.
3. **No intermediate files**: Unlike the previous AssemblyAI flow, there's no raw JSON or speaker mapping JSON. Gemini produces the final formatted transcript directly.

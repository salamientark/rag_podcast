# Transcription Module

## Purpose

Converts audio podcast files into formatted transcripts with speaker diarization (AssemblyAI Universal-2) and optional speaker identification (OpenAI LLM).

This module is part of the pipeline stages:

`AUDIO_DOWNLOADED → RAW_TRANSCRIPT → FORMATTED_TRANSCRIPT`

## Key Components

### transcript.py

Core transcription functionality using AssemblyAI.

**Key Functions:**

- `transcribe_with_diarization(file_path, language)` - Main transcription with speaker diarization
- `check_formatted_transcript_exists(output_dir, episode_id)` - Cache check
- `get_episode_id_from_path(file_path)` - Extracts episode number from filename

**Output Structure (raw JSON):**

```python
{
  "transcript": {"text": str, "confidence": float, "audio_duration": int},
  "speakers": [{"speaker": str, "segments": [...]}],
  "words": [{"text": str, "start": float, "end": float, "speaker": str}],
  "_metadata": {...}
}
```

### speaker_mapper.py

Transforms raw transcripts and identifies real speaker names.

**Key Functions:**

- `format_transcript(json_path, max_tokens, speaker_mapping)`  
  Converts word-level JSON to readable text. If `speaker_mapping` is provided, it replaces generic labels with real names.
- `map_speakers_with_llm(formatted_text)`  
  Uses OpenAI to identify real speaker names from a formatted transcript excerpt.
- `get_mapped_transcript(raw_transcript_path)`  
  Convenience function: format → map → re-format.

## Speaker Mapping Contract (IMPORTANT)

Speaker mapping is a JSON object where keys are **generic labels**:

- Keys: `"Speaker A"`, `"Speaker B"`, ...
- Values: real names (string) or `"Unknown"` (case-insensitive accepted)

Example:

```json
{
  "Speaker A": "Patrick",
  "Speaker B": "Cédric",
  "Speaker C": "Unknown"
}
```

Any other format (e.g., `{"A": "Patrick"}`) must be converted before being passed to `format_transcript()`.

## File Naming Convention (canonical)

Outputs are organized in: `{output_dir}/episode_{episode_id:03d}/`

- Raw: `raw_episode_{episode_id:03d}.json`
- Mapping: `speakers_episode_{episode_id:03d}.json`
- Formatted: `formatted_episode_{episode_id:03d}.txt`

## CLI

The CLI is implemented in `src/transcription/__main__.py` and is intended to support:

- `--force` - Re-transcribe even if formatted transcript exists
- `--no-db-update` - Skip database updates
- `--dry-run` - Preview without processing
- `--verbose` - Enable detailed logging

## Gotchas / Review Rules

1. **Episode identity**: SQL primary key is `Episode.uuid`. The integer `episode_id` is per-podcast and not globally unique.
2. **Do not query `Episode.id`**: the model does not have an `id` column.
3. **Mapping format must match the contract** above.
4. **AssemblyAI time units**: raw data is in milliseconds; code converts to seconds in output.

## Known Broken (current code reality)

1. **Hard runtime break**: `src/transcription/__main__.py` imports `from src.transcript.speaker_mapper ...` but the package is `src.transcription`. This will fail immediately when running the CLI.
2. **DB queries in CLI use wrong fields**: the CLI currently queries `Episode.id` in multiple places; the model uses `uuid` (PK) and `episode_id` (int).

These should be fixed before relying on the transcription CLI in production.

# Transcription Module

## Purpose

Converts audio podcast files into formatted transcripts with speaker identification using AssemblyAI Universal-2 and OpenAI LLM.

## Key Components

### transcript.py

Core transcription functionality using AssemblyAI.

**Key Functions:**

- `transcribe_with_diarization(file_path, language)` - Main transcription with speaker diarization
- `check_formatted_transcript_exists(output_dir, episode_id)` - Cache check
- `get_episode_id_from_path(file_path)` - Extracts episode number from filename

**Output Structure:**

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

- `format_transcript(json_path, max_tokens, speaker_mapping)` - Converts word-level JSON to readable text
- `map_speakers_with_llm(formatted_text)` - Uses OpenAI to identify real speaker names
- `get_mapped_transcript(raw_transcript_path)` - Convenience function for full pipeline

### **main**.py

CLI interface for batch transcription with database integration.

**CLI Flags:**

- `--force` - Re-transcribe even if formatted transcript exists
- `--no-db-update` - Skip database updates
- `--dry-run` - Preview without processing
- `--verbose` - Enable detailed logging

## Processing Pipeline

1. **Raw Transcription** - AssemblyAI transcribes audio → `raw_episode_XXX.json`
2. **Speaker Identification** - LLM identifies speakers → `speakers_episode_XXX.json`
3. **Formatting** - Creates readable transcript → `formatted_episode_XXX.txt`
4. **Database Update** - Records paths and advances processing stage

## File Naming Convention

- Raw: `raw_episode_001.json`
- Mapping: `speakers_episode_001.json`
- Formatted: `formatted_episode_001.txt`

Outputs organized in: `{output_dir}/episode_{id:03d}/`

## Gotchas

1. **Import Bug**: `__main__.py` line 44 imports from `src.transcript.speaker_mapper` but should be `src.transcription`.

2. **Hardcoded Model**: `speaker_mapper.py` uses `gpt-5` with no fallback.

3. **Silent Mapping Failures**: `map_speakers_with_llm()` returns empty dict `{}` on errors without warning.

4. **Token Estimation**: Uses `word_count * 0.75` heuristic, may not be accurate.

5. **AssemblyAI Time Units**: Raw data in milliseconds, converted to seconds in output.

6. **Missing Validation**: No validation that episode IDs in filenames match database.

7. **Language Default**: Defaults to French (`language="fr"`). Not auto-detected.

8. **Database Coupling**: Code queries DB even with `--no-db-update` for dry-run analysis.

## Environment Dependencies

- `ASSEMBLYAI_API_KEY` - Required for transcription
- `OPENAI_API_KEY` - Required for speaker identification
- Database connection - Required even with `--no-db-update`

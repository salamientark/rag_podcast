# LLM Module

## Purpose

This module provides LLM integration for the RAG podcast system. Currently focused on speaker identification from podcast transcripts using OpenAI's API.

## Key Files

### `openai.py`

- **`init_llm_openai()`** - Factory function that initializes the OpenAI client
  - Loads environment variables via dotenv
  - Returns `OpenAI` client or `None` on failure
  - Handles missing API keys gracefully

### `prompts.py`

- **`_speaker_identification_prompt()`** - Returns the system prompt for speaker identification
  - Identifies real speaker names from generic labels (Speaker A, B, etc.)
  - Assumes host is named "Patrick" and has the most dialogue
  - Expects JSON output: `{"Speaker A": "Name1", "Speaker B": "Name2"}`
  - Falls back to "Unknown" for unidentifiable speakers

## Important Patterns

### Initialization Pattern

```python
client = init_llm_openai()  # Returns None on failure
if client:
    # Use client
else:
    # Handle gracefully
```

### Environment Configuration

Requires `OPENAI_API_KEY` in environment variables. Uses `dotenv` to load from `.env` file.

## Gotchas

1. **Silent Failures**: `init_llm_openai()` prints errors but returns `None`. Always check for `None` before use.

2. **Hardcoded Host Name**: Speaker identification prompt assumes host is named "Patrick". Modify for different podcasts.

3. **No Retry Logic**: No retry on transient errors. Network issues result in `None`.

4. **Missing Base Classes**: README references non-existent `base.py` and `LLMProvider` abstract class.

5. **No Model Configuration**: Model must be specified at call time.

6. **Environment Loading**: `load_dotenv()` called every time `init_llm_openai()` is invoked.

## Usage Example

```python
from src.llm import init_llm_openai, _speaker_identification_prompt

client = init_llm_openai()
if not client:
    print("Failed to initialize LLM")
    return

prompt = _speaker_identification_prompt()
response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": prompt},
        {"role": "user", "content": transcript_text}
    ],
    temperature=0.1
)
```

"""Gemini-based audio transcription with speaker identification.

This module provides transcription using Google's Gemini API, which handles
both speech-to-text and speaker identification in a single call.
"""

import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.logger import log_function


# GEMINI_MODEL = "gemini-3-pro-preview"
GEMINI_MODEL = "gemini-3-flash-preview"

GEMINI_SYSTEM_INSTRUCTION = """You are an expert audio transcriber. Transcribe the following podcast audio.

## Instructions
- **Direct Output Only:** Start your response immediately with the Speakers header. Do not include introductory text like "Here is the transcription" or "Sure, I can do that." No extra at the end either.
- **Speaker Identification:** Identify speakers by name when possible using the episode context provided by the user.
- **Header:** Begin with a bulleted list of speakers detected in the audio (Name: Role/Location).
- **Timestamps:** Include timestamps in [MM:SS] or [HH:MM:SS] format at the start of each speaker turn.
- **Cleaned Verbatim:** Transcribe the spoken words accurately, but remove filler words (e.g., "um", "uh", "like" when used as a filler), stammers, and immediate repetitions/false starts. **Do not** rephrase sentences or change the speaker's vocabulary; simply prune the noise.

## Output Format
**Speakers:**
* **Name:** Role (Location)
* **Name:** Role (Location)

---

[00:00:00] **Speaker Name:** Their dialogue here...

[00:01:23] **Another Speaker:** Their response...
"""


def get_gemini_client() -> genai.Client:
    """Get configured Gemini client.

    Returns:
        Configured Gemini client

    Raises:
        ValueError: If GEMINI_API_KEY not found
    """
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment variables")
    return genai.Client(api_key=api_key)


@log_function(logger_name="transcript", log_args=True, log_execution_time=True)
def transcribe_with_gemini(
    file_path: Path,
    description: str,
    model: str = GEMINI_MODEL,
) -> dict:
    """Transcribe audio using Gemini with speaker identification.

    Transcribes in the original spoken language (no translation).
    Uses episode description to help identify speakers by name.

    Args:
        file_path: Path to audio file
        description: Episode description for speaker context
        model: Gemini model to use (see GEMINI_MODEL constant)

    Returns:
        Dict with transcript text, formatted output, and metadata

    Raises:
        FileNotFoundError: If audio file not found
        ValueError: If API key missing
        Exception: If transcription fails
    """
    logger = logging.getLogger("transcript")

    if not file_path.exists():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    logger.info(f"Starting Gemini transcription of {file_path.name}")
    print(f"Transcribing: {file_path.name}...")
    start_time = time.time()

    client = get_gemini_client()

    try:
        # Upload audio file to Gemini
        logger.info("Uploading audio file to Gemini...")
        audio_file = client.files.upload(file=str(file_path))

        # Build user message with episode context
        user_message = (
            f"## Episode Context\n{description or 'No description available'}"
        )

        # Generate transcription
        logger.info(f"Requesting transcription with model {model}...")
        response = client.models.generate_content(
            model=model,
            contents=[user_message, audio_file],
            config=types.GenerateContentConfig(
                system_instruction=GEMINI_SYSTEM_INSTRUCTION,
            ),
        )

        processing_time = time.time() - start_time

        # Validate response has text content
        if not response.text or not response.text.strip():
            # Log diagnostic info to understand why
            logger.error(f"Gemini returned empty response for {file_path.name}")
            if response.candidates:
                for i, candidate in enumerate(response.candidates):
                    logger.error(
                        f"Candidate {i}: finish_reason={candidate.finish_reason}"
                    )
                    if candidate.safety_ratings:
                        for rating in candidate.safety_ratings:
                            logger.error(
                                f"  Safety: {rating.category}={rating.probability}"
                            )
            else:
                logger.error("No candidates in response")
            raise ValueError(
                f"Gemini returned no text for {file_path.name}. "
                "Check logs for safety ratings or finish reason."
            )

        # Extract token usage for logging
        usage_info = {}
        if response.usage_metadata:
            usage = response.usage_metadata
            prompt_tokens = usage.prompt_token_count
            response_tokens = usage.candidates_token_count
            total_tokens = usage.total_token_count
            usage_info = {
                "prompt_tokens": prompt_tokens,
                "response_tokens": response_tokens,
                "total_tokens": total_tokens,
            }
            if prompt_tokens is not None and response_tokens is not None:
                logger.info(
                    f"Token usage - prompt: {prompt_tokens:,}, "
                    f"response: {response_tokens:,}, "
                    f"total: {total_tokens:,}"
                )

        result = {
            "transcript": {
                "text": response.text,
            },
            "formatted_text": response.text,
            "_metadata": {
                "transcriber": "gemini",
                "model": model,
                "processing_time_seconds": processing_time,
                "audio_file": str(file_path),
                **usage_info,
            },
        }

        logger.info(f"Gemini transcription completed in {processing_time:.2f}s")
        print(f"Transcription completed in {processing_time:.1f}s")

        return result

    except Exception as e:
        logger.error(f"Gemini transcription failed: {e}")
        raise Exception(f"Gemini transcription failed: {e}")
    finally:
        client.close()

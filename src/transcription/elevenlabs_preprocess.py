"""Utilities for formatting ElevenLabs speech-to-text transcripts.

ElevenLabs can return a verbose transcript JSON structure with word-level timing,
spacing tokens, diarization labels, and audio events. This module transforms that
raw structure into a more readable, timestamped transcript.

The formatter is designed for the JSON returned by `ElevenLabs.speech_to_text`.
In practice this is the output of `transcription.model_dump()`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Mapping


logger = logging.getLogger(__name__)


def _format_timestamp_hh_mm_ss(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _ensure_parenthesized(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("(") and stripped.endswith(")"):
        return stripped
    return f"({stripped})"


def preprocess_elevenlabs_transcript_data(data: Mapping[str, Any]) -> str:
    """Convert ElevenLabs transcript JSON data to readable text.

    Args:
        data: Transcript JSON dict (e.g. from `model_dump()`).

    Returns:
        Formatted transcript with timestamped speaker turns and audio events.

    Raises:
        ValueError: If required fields are missing or invalid.
    """

    words = data.get("words")
    if not isinstance(words, list):
        raise ValueError("Invalid ElevenLabs transcript: missing 'words' list")

    speaker_to_label: dict[str, str] = {}
    next_speaker_index = 0

    def get_speaker_label(speaker_id: str) -> str:
        nonlocal next_speaker_index
        if speaker_id not in speaker_to_label:
            if next_speaker_index >= 26:
                speaker_to_label[speaker_id] = f"Speaker {next_speaker_index + 1}"
            else:
                letter = chr(ord("A") + next_speaker_index)
                speaker_to_label[speaker_id] = f"Speaker {letter}"
            next_speaker_index += 1
        return speaker_to_label[speaker_id]

    output_lines: list[str] = []

    current_speaker_id: str | None = None
    current_start: float | None = None
    current_text_parts: list[str] = []

    def flush_speaker_block() -> None:
        nonlocal current_speaker_id, current_start, current_text_parts
        if current_speaker_id is None:
            return

        text = "".join(current_text_parts).strip()
        if not text:
            current_speaker_id = None
            current_start = None
            current_text_parts = []
            return

        timestamp = _format_timestamp_hh_mm_ss(current_start or 0.0)
        speaker_label = get_speaker_label(current_speaker_id)
        output_lines.append(f"[{timestamp}] {speaker_label}: {text}")
        output_lines.append("")

        current_speaker_id = None
        current_start = None
        current_text_parts = []

    for token in words:
        if not isinstance(token, Mapping):
            continue

        token_type = str(token.get("type", ""))

        if token_type == "audio_event":
            flush_speaker_block()
            start = float(token.get("start", 0.0))
            timestamp = _format_timestamp_hh_mm_ss(start)
            event_text = str(token.get("text", "")).strip()
            if event_text:
                output_lines.append(
                    f"[{timestamp}] {_ensure_parenthesized(event_text)}"
                )
                output_lines.append("")
            continue

        speaker_id = token.get("speaker_id")
        if not isinstance(speaker_id, str) or not speaker_id:
            continue

        if token_type == "spacing":
            if current_speaker_id == speaker_id:
                current_text_parts.append(str(token.get("text", "")))
            continue

        start = token.get("start")
        try:
            token_start = float(start) if start is not None else None
        except (TypeError, ValueError):
            token_start = None

        if current_speaker_id != speaker_id:
            flush_speaker_block()
            current_speaker_id = speaker_id
            current_start = token_start
            current_text_parts = [str(token.get("text", ""))]
        else:
            if current_start is None and token_start is not None:
                current_start = token_start
            current_text_parts.append(str(token.get("text", "")))

    flush_speaker_block()

    while output_lines and output_lines[-1] == "":
        output_lines.pop()

    return "\n".join(output_lines)


def preprocess_elevenlabs_transcript_file(input_path: Path) -> str:
    """Load an ElevenLabs transcript JSON file and format it.

    Args:
        input_path: Path to a JSON file from ElevenLabs `model_dump()`.

    Returns:
        Formatted transcript.

    Raises:
        FileNotFoundError: If `input_path` does not exist.
        ValueError: If the JSON is invalid or has unexpected structure.
    """

    with open(input_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, Mapping):
        raise ValueError(
            "Invalid ElevenLabs transcript: top-level JSON is not an object"
        )

    return preprocess_elevenlabs_transcript_data(data)

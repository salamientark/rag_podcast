# Transcription module - Main API for transcribing audio files and URLs

# Import the main transcription functions

from src.transcription.transcript import (
    check_formatted_transcript_exists,
    get_episode_id_from_path,
    transcribe_with_diarization,
)
from src.transcription.speaker_mapper import (
    map_speakers_with_llm,
    format_transcript,
    get_mapped_transcript,
)

# Main public API - these are the functions other modules should use
__all__ = [
    "check_formatted_transcript_exists",
    "get_episode_id_from_path",
    "transcribe_with_diarization",
    "get_mapped_transcript",
    "map_speakers_with_llm",
    "format_transcript",
]

# Transcription module - Main API for transcribing audio files and URLs

# Import the main transcription functions
from src.transcription.transcript import (
    transcribe_audio,
    transcribe_with_diarization,
)

# Main public API - these are the functions other modules should use
__all__ = ["transcribe_audio", "transcribe_with_diarization"]

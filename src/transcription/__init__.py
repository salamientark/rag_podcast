# Transcription module - Main API for transcribing audio files and URLs

# Import the main transcription functions
from src.transcription.transcript import (
    transcribe_audio,
    transcribe_with_diarization,
    download_from_url,
    is_url,
    setup_logging,
    cleanup_temp_files,
)

# Main public API - these are the functions other modules should use
__all__ = ["transcribe_audio", "transcribe_with_diarization"]

#!/usr/bin/env python3
"""
Core transcription functionality using AssemblyAI Universal-2 with diarization.
This module provides the core functions for transcribing audio files and URLs.
"""

import re
import logging
import os
import time
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv
import assemblyai as aai

from src.logger import log_function


@log_function(logger_name="transcript", log_args=True, log_execution_time=True)
def transcribe_with_diarization(file_path: Path, language: str = "fr") -> Dict:
    """
    Transcribe audio file using AssemblyAI Universal-2 with full diarization.

    Args:
        file_path: Path to audio file
        language: Language code (default: fr)

    Returns:
        Dict with comprehensive transcription and speaker data

    Raises:
        Exception: If transcription fails
    """
    logger = logging.getLogger("transcript")

    if not file_path.exists():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    # Load API key
    load_dotenv()
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        raise ValueError("ASSEMBLYAI_API_KEY not found in environment variables")

    aai.settings.api_key = api_key

    # Configure transcription with diarization
    config = aai.TranscriptionConfig(
        language_code=language,
        speech_models=["universal"],
        speaker_labels=True,  # Enable diarization
        punctuate=True,
        format_text=True,
    )

    logger.info(
        f"Starting transcription of {file_path.name} with AssemblyAI Universal-2"
    )
    print(f"Transcribing: {file_path.name}...")
    start_time = time.time()

    try:
        # Create transcriber and start transcription
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(str(file_path))

        # Check for errors
        if transcript.status == aai.TranscriptStatus.error:
            raise Exception(f"AssemblyAI transcription failed: {transcript.error}")

        # Build comprehensive result with diarization
        result = {
            "transcript": {
                "text": transcript.text,
                "language": language,
                "confidence": transcript.confidence,
                "audio_duration": transcript.audio_duration,
            },
            "speakers": [],
            "words": [],
            "_metadata": {
                "transcriber": "assemblyai",
                "model": "universal-2",
                "processing_time_seconds": time.time() - start_time,
                "audio_file": str(file_path),
                "diarization_enabled": True,
                "language": language,
            },
        }

        # Extract speaker information from utterances
        if transcript.utterances:
            speakers_dict = {}

            for utterance in transcript.utterances:
                speaker_id = utterance.speaker

                if speaker_id not in speakers_dict:
                    speakers_dict[speaker_id] = {"speaker": speaker_id, "segments": []}

                speakers_dict[speaker_id]["segments"].append(
                    {
                        "text": utterance.text,
                        "start": utterance.start / 1000.0,  # Convert to seconds
                        "end": utterance.end / 1000.0,  # Convert to seconds
                        "confidence": utterance.confidence,
                    }
                )

            result["speakers"] = list(speakers_dict.values())

        # Add word-level data with speaker attribution
        if transcript.words:
            for word in transcript.words:
                word_data = {
                    "text": word.text,
                    "start": word.start / 1000.0,  # Convert to seconds
                    "end": word.end / 1000.0,  # Convert to seconds
                    "confidence": word.confidence,
                }

                # Add speaker if available
                if hasattr(word, "speaker") and word.speaker:
                    word_data["speaker"] = word.speaker

                result["words"].append(word_data)

        processing_time = time.time() - start_time
        logger.info(f"AssemblyAI transcription completed in {processing_time:.2f}s")
        print(f"✓ Transcription completed in {processing_time:.1f}s")

        return result

    except Exception as e:
        logger.error(f"AssemblyAI transcription failed: {e}")
        raise Exception(f"AssemblyAI transcription failed: {e}")


def check_formatted_transcript_exists(output_dir: Path, episode_id: int) -> bool:
    """
    Check if formatted transcript file already exists.

    Args:
        output_dir: Base output directory
        episode_id: Episode ID number

    Returns:
        True if formatted transcript exists, False otherwise
    """
    formatted_path = (
        output_dir
        / f"episode_{episode_id:03d}"
        / f"formatted_episode_{episode_id:03d}.txt"
    )
    return formatted_path.exists()


def get_episode_id_from_path(file_path: str | Path) -> str:
    """Get episode number from file path.

    Used in automatic audio to transcript naming.

    Args:
        file_path: Path to audio file

    Returns:
        Episode ID as string if found else random UUID
    """
    pattern = re.compile(r"episode_(\d{3})")
    match = pattern.search(str(file_path))
    if match:
        episode_num = match.group(1)  # '001'
        return episode_num
    return "000"  # Fallback to UUID if not found

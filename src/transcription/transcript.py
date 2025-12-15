#!/usr/bin/env python3
"""
Core transcription functionality using AssemblyAI Universal-2 with diarization.
This module provides the core functions for transcribing audio files and URLs.
"""

import re
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, Optional, Union

from dotenv import load_dotenv
import assemblyai as aai

from src.transcription.speaker_mapper import format_transcript, map_speakers_with_llm
from src.db.database import get_db_session
from src.db.models import Episode, ProcessingStage
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


@log_function(logger_name="transcript", log_execution_time=True)
def update_episode_transcription_paths(
    episode_id: int,
    raw_transcript_path: str,
    speaker_mapping_path: str,
    formatted_transcript_path: str,
    transcript_duration: Optional[int] = None,
    transcript_confidence: Optional[float] = None,
) -> bool:
    """
    Update episode database record with transcription file paths.

    Args:
        episode_id: Database ID of the episode
        raw_transcript_path: Path to raw transcription JSON
        speaker_mapping_path: Path to speaker mapping JSON
        formatted_transcript_path: Path to formatted transcript text
        transcript_duration: Duration of the transcript audio in seconds
        transcript_confidence: Confidence score of the transcription

    Returns:
        bool: True if update successful, False otherwise
    """
    logger = logging.getLogger("audio_scraper")
    try:
        with get_db_session() as session:
            episode = session.query(Episode).filter_by(id=episode_id).first()

            if not episode:
                logger.error(f"Episode {episode_id} not found in database")
                return False

            # Update db fields
            stage_order = list(ProcessingStage)
            current_stage_index = stage_order.index(episode.processing_stage)
            target_stage_index = stage_order.index(ProcessingStage.FORMATTED_TRANSCRIPT)
            if current_stage_index < target_stage_index:
                episode.processing_stage = ProcessingStage.FORMATTED_TRANSCRIPT
            episode.raw_transcript_path = raw_transcript_path
            episode.speaker_mapping_path = speaker_mapping_path
            episode.formatted_transcript_path = formatted_transcript_path
            episode.transcript_duration = transcript_duration
            episode.transcript_confidence = transcript_confidence

            session.commit()
            logger.info(f"Updated episode ID {episode_id} with audio file path")
            return True
    except Exception as e:
        logger.error(f"Failed to update episode ID {episode_id}: {e}")
        return False


@log_function(logger_name="transcript", log_execution_time=True)
def transcribe_local_file(
    input_file: Union[str, Path],
    language: str = "fr",
    output_dir: Optional[Union[str, Path]] = "data/transcripts/",
    episode_id: Optional[int] = None,
):
    """High level function to transcribe a local audio file.

    Transcribe a local audio file and save the following files:
        - The raw transcription JSON with diarization
        - The speaker mapping JSON
        - The formatted transcript text file

    BEWARE: The files will be saved in a subdirectory of output_dir

    Transcribe using AssemblyAI Universal-2 with diarization.

    Args:
        input_path: Path to local audio file
        language: Language code for transcription (default: fr)
        output_dir: Directory to save output files (default: data/transcripts/)
        episode_id: Optional episode ID for naming else try to found it file name

    Raises:
        FileNotFoundError: If local file doesn't exist
        ValueError: If API key is missing
        Exception: If transcription or download fails
    """
    logger = logging.getLogger("transcript")

    try:
        # Find episode id for naming if not provided
        input_path = Path(input_file)
        episode_nbr = int(
            episode_id
            if episode_id is not None
            else get_episode_id_from_path(input_path)
        )

        # Create output directory if not exists
        out_dir_path = Path(output_dir / f"episode_{episode_nbr:03d}/")
        try:
            out_dir_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create output directory {out_dir_path}: {e}")
            raise

        # Raw transcription
        raw_file_path = Path(out_dir_path / f"raw_episode_{episode_nbr:03d}.json")
        # Take transcription from cache if exists
        if raw_file_path.exists():
            raw_result = json.loads(raw_file_path.read_text(encoding="utf-8"))
        else:
            raw_result = transcribe_with_diarization(input_path, language)
            try:
                with open(raw_file_path, "w", encoding="utf-8") as f:
                    json.dump(raw_result, f, indent=4)
                    logger.info(f"Saved raw transcription to {raw_file_path}")
            except OSError as e:
                logger.error(f"Failed to write raw transcript to {raw_file_path}: {e}")
                raise

        # Speaker mapping
        mapping_file_path = Path(
            out_dir_path / f"speakers_episode_{episode_nbr:03d}.json"
        )
        # Take mapping from cache if exists
        mapping_result = {}
        if mapping_file_path.exists():
            raw_formatted_text = format_transcript(raw_file_path, max_tokens=10000)
        else:
            raw_formatted_text = format_transcript(raw_file_path, max_tokens=10000)
            mapping_result = map_speakers_with_llm(raw_formatted_text)
            try:
                with open(mapping_file_path, "w", encoding="utf-8") as f:
                    json.dump(mapping_result, f, indent=4)
                    logger.info(f"Saved mapping result to {mapping_file_path}")
            except OSError as e:
                logger.error(
                    f"Failed to write mapping result to {mapping_file_path}: {e}"
                )
                raise

        # Formatted transcript
        formatted_transcript_path = Path(
            out_dir_path / f"formatted_episode_{episode_nbr:03d}.txt"
        )
        formatted_text = format_transcript(
            raw_file_path, speaker_mapping=mapping_result
        )
        try:
            with open(formatted_transcript_path, "w", encoding="utf-8") as f:
                f.write(formatted_text)
                logger.info(f"Saved mapping result to {formatted_transcript_path}")
        except OSError as e:
            logger.error(
                f"Failed to write mapping result to {formatted_transcript_path}: {e}"
            )
            raise

        # Update database record
        try:
            transcript_duration = raw_result["transcript"].get("audio_duration")
            transcript_confidence = raw_result["transcript"].get("confidence")
            update_episode_transcription_paths(
                episode_nbr,
                str(raw_file_path),
                str(mapping_file_path),
                str(formatted_transcript_path),
                transcript_duration=transcript_duration,
                transcript_confidence=transcript_confidence,
            )
            logger.info("Database updated successfully")
        except Exception as db_error:
            logger.error(f"DB update failed but files saved: {db_error}")
            # Files exist but DB not updated - manual intervention needed
        # Return path to formatted transcript
        return formatted_transcript_path

    except Exception:
        raise

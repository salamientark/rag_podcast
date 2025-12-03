#!/usr/bin/env python3
"""
Simple transcript script using AssemblyAI Universal-2 with diarization.
Handles both file paths and URLs, outputs structured JSON with speaker information.

Usage:
    uv run -m src.transcription <input> [output.json]
    uv run -m src.transcription <input> --language en
    uv run -m src.transcription <input> --keep-temp --verbose

Examples:
    uv run -m src.transcription https://example.com/podcast.mp3
    uv run -m src.transcription audio.mp3 results.json
    uv run -m src.transcription audio.mp3 --language en --verbose
"""

import argparse
import json
import logging
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional
import requests

from dotenv import load_dotenv
import assemblyai as aai
from src.ingestion.audio_scrap import sanitize_filename


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Set up logging for the transcript script."""
    logger = logging.getLogger("transcript")

    # Avoid adding multiple handlers
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_formatter = logging.Formatter("%(levelname)s: %(message)s")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger


def is_url(input_str: str) -> bool:
    """Check if input string is a URL."""
    return input_str.startswith(("http://", "https://"))


def download_from_url(url: str, temp_dir: Path, max_retries: int = 3) -> Path:
    """
    Download audio from URL using proven audio_scrap.py logic.

    Args:
        url: Audio URL to download
        temp_dir: Directory for temporary files
        max_retries: Maximum download attempts

    Returns:
        Path to downloaded file

    Raises:
        Exception: If download fails after all retries
    """
    logger = logging.getLogger("transcript")

    # Generate filename from URL
    url_title = url.split("/")[-1].split("?")[0].replace(".mp3", "")
    safe_title = sanitize_filename(url_title or "downloaded_audio")
    filename = f"{safe_title}.mp3"
    filepath = temp_dir / filename

    # Browser headers from audio_scrap.py to handle feedpress.me redirects
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "audio/mpeg, audio/*, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    }

    temp_dir.mkdir(parents=True, exist_ok=True)

    for attempt in range(max_retries):
        try:
            logger.info(f"Downloading {filename} (attempt {attempt + 1}/{max_retries})")
            print(f"  Downloading: {url[:60]}...")

            # Download with browser headers and redirects
            response = requests.get(url, stream=True, headers=headers, timeout=120)
            response.raise_for_status()

            # Write file in chunks
            with open(filepath, "wb") as f:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

            # Verify file size
            file_size = filepath.stat().st_size
            if file_size < 100 * 1024:  # Less than 100KB is suspicious
                logger.warning(
                    f"File {filename} is suspiciously small: {file_size} bytes"
                )
                filepath.unlink()
                raise Exception(f"Downloaded file too small: {file_size} bytes")

            logger.info(f"Successfully downloaded {filename} ({file_size:,} bytes)")
            print(f"  ✓ Downloaded {filename} ({file_size:,} bytes)")
            return filepath

        except requests.exceptions.RequestException as e:
            logger.warning(f"Download attempt {attempt + 1} failed for {filename}: {e}")
            print(f"  ✗ Attempt {attempt + 1} failed: {e}")

            # Clean up partial file
            if filepath.exists():
                filepath.unlink()

        except Exception as e:
            logger.error(f"Unexpected error downloading {filename}: {e}")
            print(f"  ✗ Unexpected error: {e}")

            # Clean up partial file
            if filepath.exists():
                filepath.unlink()

        # Wait before retry
        if attempt < max_retries - 1:
            wait_time = 2**attempt  # 1s, 2s, 4s
            logger.info(f"Waiting {wait_time}s before retry...")
            time.sleep(wait_time)

    raise Exception(f"Failed to download {filename} after {max_retries} attempts")


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


def cleanup_temp_files(temp_dir: Path, keep_files: bool = False) -> None:
    """
    Clean up temporary files.

    Args:
        temp_dir: Directory containing temporary files
        keep_files: If True, preserve files for debugging
    """
    logger = logging.getLogger("transcript")

    if keep_files:
        logger.info(f"Keeping temporary files in: {temp_dir}")
        print(f"Temporary files preserved in: {temp_dir}")
        return

    try:
        if temp_dir.exists() and temp_dir.is_dir():
            import shutil

            shutil.rmtree(temp_dir)
            logger.debug(f"Cleaned up temporary directory: {temp_dir}")
    except Exception as e:
        logger.warning(f"Failed to cleanup temporary files: {e}")


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Transcribe audio files or URLs using AssemblyAI with diarization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run -m src.transcription https://example.com/podcast.mp3
  uv run -m src.transcription audio.mp3 results.json
  uv run -m src.transcription audio.mp3 --language en --verbose
  uv run -m src.transcription https://podcast.com/ep.mp3 --keep-temp
        """,
    )

    parser.add_argument("input", help="Audio file path or URL to transcribe")
    parser.add_argument(
        "output", nargs="?", help="Output JSON file (default: print to stdout)"
    )
    parser.add_argument(
        "--language", default="fr", help="Language code for transcription (default: fr)"
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep downloaded temporary files for debugging",
    )
    parser.add_argument(
        "--temp-dir",
        type=Path,
        help="Custom temporary directory (default: system temp)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Detailed console output and logging"
    )

    args = parser.parse_args()

    # Setup logging
    logger = setup_logging(verbose=args.verbose)

    # Initialize variables
    input_path = None
    temp_dir = None

    try:
        # Determine if input is URL or file
        if is_url(args.input):
            # Create temporary directory for download
            temp_base = args.temp_dir or Path(tempfile.gettempdir())
            temp_dir = temp_base / f"transcript_{os.getpid()}"

            print(f"Downloading from URL: {args.input}")
            input_path = download_from_url(args.input, temp_dir)
        else:
            # Local file
            input_path = Path(args.input)
            if not input_path.exists():
                print(f"✗ File not found: {input_path}")
                sys.exit(1)

        # Transcribe with diarization
        print(f"Starting transcription with language: {args.language}")
        result = transcribe_with_diarization(input_path, args.language)

        # Format output as JSON
        json_output = json.dumps(result, indent=2, ensure_ascii=False)

        # Output results
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(json_output, encoding="utf-8")
            print(f"✓ Transcript saved to: {args.output}")
        else:
            print("\n--- TRANSCRIPT (JSON) ---")
            print(json_output)

        # Cleanup temporary files
        if temp_dir:
            cleanup_temp_files(temp_dir, keep_files=args.keep_temp)

        # Print summary
        speakers_count = len(result.get("speakers", []))
        words_count = len(result.get("words", []))
        duration = result["transcript"]["audio_duration"]

        print(f"\n--- SUMMARY ---")
        print(f"Duration: {duration:.1f}s ({duration / 60:.1f}min)")
        print(f"Speakers detected: {speakers_count}")
        print(f"Words transcribed: {words_count}")
        print(f"Language: {args.language}")
        print(f"Confidence: {result['transcript']['confidence']:.2f}")

    except KeyboardInterrupt:
        print("\nTranscription interrupted by user")
        if temp_dir:
            cleanup_temp_files(temp_dir, keep_files=False)
        sys.exit(130)

    except Exception as e:
        print(f"✗ Transcription failed: {e}")
        logger.error(f"Transcription failed: {e}")
        if temp_dir:
            cleanup_temp_files(temp_dir, keep_files=False)
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
CLI interface for transcription using AssemblyAI Universal-2 with diarization.
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
import sys
from pathlib import Path

# Import transcribe_audio function
from src.transcription.transcript import transcribe_audio


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

    try:
        # Use the imported transcribe_audio function
        result = transcribe_audio(
            input_source=args.input,
            language=args.language,
            output_file=args.output,
            verbose=args.verbose,
            keep_temp=args.keep_temp,
            temp_dir=args.temp_dir,
        )

        # Print results if no output file was specified
        if not args.output:
            json_output = json.dumps(result, indent=2, ensure_ascii=False)
            print("\n--- TRANSCRIPT (JSON) ---")
            print(json_output)

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
        sys.exit(130)

    except Exception as e:
        print(f"✗ Transcription failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

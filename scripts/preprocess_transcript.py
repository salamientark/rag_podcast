#!/usr/bin/env python3
"""Preprocess an ElevenLabs transcript JSON into readable text.

This script takes the raw transcript JSON produced by ElevenLabs
(`transcription.model_dump()`), and outputs a readable transcript with
speaker turns and timestamps.

Usage:
    uv run scripts/preprocess_transcript.py transcript.json

Notes:
    - This script expects the ElevenLabs JSON schema (word tokens + diarization).
    - The output format uses speaker turns: "Speaker A", "Speaker B", ...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.transcription.elevenlabs_preprocess import (  # noqa: E402
    preprocess_elevenlabs_transcript_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Format an ElevenLabs transcript JSON to readable text",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Print formatted transcript
  uv run scripts/preprocess_transcript.py transcript.json

  # Write formatted transcript to file
  uv run scripts/preprocess_transcript.py transcript.json --output formatted.txt
""",
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Path to ElevenLabs transcript JSON (from model_dump())",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional output text file path (default: stdout)",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.input.exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        return 2
    if not args.input.is_file():
        print(f"Error: input path is not a file: {args.input}", file=sys.stderr)
        return 2

    formatted = preprocess_elevenlabs_transcript_file(args.input)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(formatted + "\n", encoding="utf-8")
    else:
        print(formatted)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

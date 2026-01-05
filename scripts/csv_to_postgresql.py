"""CSV to PostgreSQL importer.

Imports rows from a CSV file into the configured PostgreSQL database using the
project's SQLAlchemy models.

Usage:
    uv run scripts/csv_to_postgresql.py --csv data/episodes.csv

Notes:
    - Requires `DATABASE_URL` to be configured (see `.env.example`).
    - Default mode is upsert: rows are inserted or updated by `uuid`.
"""

from __future__ import annotations

import argparse
import csv
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

import sys

sys.path.insert(1, str(Path(__file__).resolve().parent.parent))

from src.db.database import get_db_session
from src.db.models import Episode, ProcessingStage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImportStats:
    """Counters tracked during CSV import."""

    processed: int = 0
    inserted_or_updated: int = 0
    skipped: int = 0


def _parse_optional_int(value: str | None) -> int | None:
    if value is None:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    return int(stripped)


def _parse_optional_float(value: str | None) -> float | None:
    if value is None:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    return float(stripped)


def _parse_optional_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    try:
        return datetime.fromisoformat(stripped)
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(stripped, fmt)
        except ValueError:
            continue

    raise ValueError(f"Unsupported datetime format: {stripped}")


def _parse_processing_stage(value: str | None, *, coerce_unknown: bool) -> ProcessingStage | None:
    if value is None:
        return None

    stripped = value.strip().lower()
    if not stripped:
        return None

    try:
        return ProcessingStage(stripped)
    except ValueError:
        if coerce_unknown:
            logger.warning("Unknown processing_stage '%s'; coercing to 'synced'", stripped)
            return ProcessingStage.SYNCED
        raise


def _episode_kwargs_from_row(
    row: dict[str, str],
    *,
    coerce_unknown_stage: bool,
) -> dict[str, Any]:
    uuid = (row.get("uuid") or "").strip()
    if not uuid:
        raise ValueError("Missing required field: uuid")

    required_int = _parse_optional_int(row.get("episode_id"))
    if required_int is None:
        raise ValueError("Missing required field: episode_id")

    title = (row.get("title") or "").strip()
    if not title:
        raise ValueError("Missing required field: title")

    podcast = (row.get("podcast") or "").strip()
    if not podcast:
        raise ValueError("Missing required field: podcast")

    published_date = _parse_optional_datetime(row.get("published_date"))
    if published_date is None:
        raise ValueError("Missing required field: published_date")

    audio_url = (row.get("audio_url") or "").strip()
    if not audio_url:
        raise ValueError("Missing required field: audio_url")

    kwargs: dict[str, Any] = {
        "uuid": uuid,
        "episode_id": required_int,
        "podcast": podcast,
        "title": title,
        "published_date": published_date,
        "audio_url": audio_url,
    }

    description = row.get("description")
    if description is not None:
        description_stripped = description.strip()
        kwargs["description"] = description_stripped if description_stripped else None

    stage = _parse_processing_stage(
        row.get("processing_stage"), coerce_unknown=coerce_unknown_stage
    )
    if stage is not None:
        kwargs["processing_stage"] = stage

    for optional_field in (
        "audio_file_path",
        "raw_transcript_path",
        "speaker_mapping_path",
        "formatted_transcript_path",
    ):
        value = row.get(optional_field)
        if value is None:
            continue
        stripped = value.strip()
        kwargs[optional_field] = stripped if stripped else None

    duration = _parse_optional_int(row.get("transcript_duration"))
    if duration is not None:
        kwargs["transcript_duration"] = duration

    confidence = _parse_optional_float(row.get("transcript_confidence"))
    if confidence is not None:
        kwargs["transcript_confidence"] = confidence

    created_at = _parse_optional_datetime(row.get("created_at"))
    if created_at is not None:
        kwargs["created_at"] = created_at

    updated_at = _parse_optional_datetime(row.get("updated_at"))
    if updated_at is not None:
        kwargs["updated_at"] = updated_at

    return kwargs


def import_csv_to_postgresql(
    csv_path: Path,
    *,
    delimiter: str,
    batch_size: int,
    dry_run: bool,
    fail_fast: bool,
    coerce_unknown_stage: bool,
) -> ImportStats:
    """Import rows from `csv_path` into PostgreSQL."""

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    stats = ImportStats()

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValueError("CSV appears to be missing headers")

        with get_db_session() as session:
            processed = 0
            upserted = 0
            skipped = 0

            for row_index, row in enumerate(reader, start=2):
                processed += 1
                try:
                    kwargs = _episode_kwargs_from_row(
                        row, coerce_unknown_stage=coerce_unknown_stage
                    )
                except Exception as exc:
                    skipped += 1
                    logger.error(
                        "Row %s skipped due to parse error: %s", row_index, exc
                    )
                    if fail_fast:
                        raise
                    continue

                try:
                    session.merge(Episode(**kwargs))
                    upserted += 1
                except SQLAlchemyError as exc:
                    skipped += 1
                    logger.error(
                        "Row %s skipped due to database error: %s", row_index, exc
                    )
                    if fail_fast:
                        raise
                    session.rollback()
                    continue

                if upserted % batch_size == 0:
                    if dry_run:
                        session.flush()
                        session.rollback()
                    else:
                        session.commit()
                    logger.info("Imported %s rows...", upserted)

            if dry_run:
                session.flush()
                session.rollback()
            else:
                session.commit()

    return ImportStats(processed=processed, inserted_or_updated=upserted, skipped=skipped)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import Episode rows from a CSV file into PostgreSQL.",
        epilog=(
            "Examples:\n"
            "  uv run scripts/csv_to_postgresql.py --csv data/episodes.csv\n"
            "  uv run scripts/csv_to_postgresql.py --csv data/episodes.csv --dry-run\n"
            "  uv run scripts/csv_to_postgresql.py --csv data/episodes.csv --batch-size 500"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="Path to the input CSV file.",
    )
    parser.add_argument(
        "--delimiter",
        type=str,
        default=",",
        help="CSV delimiter character (default: ',').",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Commit every N rows (default: 1000).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate CSV, but do not persist changes.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first row error instead of continuing.",
    )
    parser.add_argument(
        "--coerce-unknown-stage",
        action="store_true",
        help="Coerce unknown `processing_stage` values to 'synced'.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    stats = import_csv_to_postgresql(
        args.csv,
        delimiter=args.delimiter,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        fail_fast=args.fail_fast,
        coerce_unknown_stage=args.coerce_unknown_stage,
    )

    logger.info(
        "Done. processed=%s imported=%s skipped=%s",
        stats.processed,
        stats.inserted_or_updated,
        stats.skipped,
    )


if __name__ == "__main__":
    main()

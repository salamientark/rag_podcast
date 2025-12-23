"""
SQLAlchemy ORM models for the podcast RAG system.

This module defines the database schema using SQLAlchemy's declarative base.
All models inherit from Base and use consistent naming conventions.

Models:
    Episode: Represents a podcast episode with metadata and processing status
    TimestampMixin: Provides automatic created_at/updated_at timestamps

Enums:
    ProcessingStage: Tracks episode processing pipeline stages
"""

from enum import Enum as PyEnum
from sqlalchemy import (
    Column,
    Integer,
    Float,
    Enum,
    String,
    Text,
    DateTime,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class TimestampMixin:
    """
    Mixin to add automatic timestamp tracking to models.

    Provides:
        created_at: Timestamp when record was created (set automatically)
        updated_at: Timestamp when record was last modified (updated automatically)

    Both fields use database-level defaults (func.now()) for consistency.
    """

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ProcessingStage(str, PyEnum):
    """
    Enum representing processing stages of podcast episodes.

    Stages progress in order from SYNCED → EMBEDDED:
        SYNCED: Episode metadata synced from RSS feed to database
        AUDIO_DOWNLOADED: Audio file downloaded to local storage
        RAW_TRANSCRIPT: Initial transcription completed (with speaker diarization)
        FORMATTED_TRANSCRIPT: Transcript formatted with speaker identification
        EMBEDDED: Episode chunks embedded in vector database (Qdrant)

    Each stage implies all previous stages are complete.
    Used by reconciliation logic to determine processing status from filesystem.
    """

    SYNCED = "synced"  # Episode in DB, no processing yet
    AUDIO_DOWNLOADED = "audio_downloaded"  # Audio file downloaded
    RAW_TRANSCRIPT = "raw_transcript"  # Initial raw transcription done
    FORMATTED_TRANSCRIPT = "formatted_transcript"  # Speaker-mapper transcription done
    EMBEDDED = "embedded"  # Chunks embedded in vectorial DB (Qdrant)


class Episode(Base, TimestampMixin):
    """
    Represents a podcast episode with metadata and processing tracking.

    This model stores episode information synced from RSS feeds and tracks
    the episode's progress through the processing pipeline (download, transcription,
    embedding).

    Attributes:
        uuid: Primary key, unique identifier (UUID7 format)
        podcast: Podcast name/identifier
        episode_id: Episode number within podcast (not unique across different podcasts)
        title: Episode title from RSS feed
        description: Episode description/show notes (truncated to 1000 chars)
        published_date: Publication date from RSS feed
        audio_url: Original audio file URL (usually feedpress.me redirect)
        processing_stage: Current stage in the processing pipeline (ProcessingStage enum)
        audio_file_path: Local path to downloaded audio file (set after download)
        raw_transcript_path: Path to raw transcript JSON (with diarization)
        speaker_mapping_path: Path to speaker mapping JSON file
        formatted_transcript_path: Path to formatted transcript (with speaker names)
        transcript_duration: Audio duration in seconds (from transcription)
        transcript_confidence: Transcription confidence score (0.0-1.0)
        created_at: Timestamp when episode was added to database (from TimestampMixin)
        updated_at: Timestamp of last update (from TimestampMixin)

    File Path Conventions:
        audio_file_path: data/audio/episode_{episode_id:03d}_{sanitized_title}.mp3
        raw_transcript_path: data/transcript/episode_{episode_id}_universal.json
        formatted_transcript_path: data/transcript/episode_{episode_id}_formatted.txt
    """

    __tablename__ = "episodes"

    # Primary metadata
    uuid = Column(String, primary_key=True)  # Primary key (was guid)
    podcast = Column(String, nullable=False)
    episode_id = Column(
        Integer, nullable=False
    )  # Episode number, not unique across podcasts (was id)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    published_date = Column(DateTime, nullable=False)
    audio_url = Column(String, nullable=False)

    # Processing tracking
    processing_stage = Column(
        Enum(ProcessingStage),
        nullable=False,
        default=ProcessingStage.SYNCED,
        server_default="synced",
    )

    # File paths (populated as processing progresses)
    audio_file_path = Column(String, nullable=True)
    raw_transcript_path = Column(String, nullable=True)
    speaker_mapping_path = Column(String, nullable=True)
    formatted_transcript_path = Column(String, nullable=True)

    # Transcription metadata
    transcript_duration = Column(Integer, nullable=True)  # in seconds
    transcript_confidence = Column(Float, nullable=True)  # percentage 0.0-1.0

    def __repr__(self):
        return (
            f"<Episode(uuid={self.uuid}, episode_id={self.episode_id}, title='{self.title}', "
            f"published_date='{self.published_date})', stage={self.processing_stage.value})>"
        )

"""
SQLAlchemy ORM models for the podcast RAG system.
This module defines the database schema using SQLAlchemy's declarative base.
All models inherit from Base and use consistent naming conventions.

Models:
    Podcast: Represents a podcast with its metadata and feed URL
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
    ForeignKey,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship
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


class Podcast(Base, TimestampMixin):
    """
    Represents a podcast with its metadata and RSS feed URL.

    Attributes:
        id: Primary key, auto-incrementing integer
        name: Unique podcast name (display name from RSS feed)
        slug: Unique URL-friendly identifier for CLI usage
        feed_url: RSS feed URL for syncing episodes
        created_at: Timestamp when podcast was added (from TimestampMixin)
        updated_at: Timestamp of last update (from TimestampMixin)
    """

    __tablename__ = "podcasts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    slug = Column(String, nullable=False, unique=True)
    feed_url = Column(String, nullable=False)

    # Relationship to episodes
    episodes = relationship("Episode", back_populates="podcast_rel")

    def __repr__(self):
        return f"<Podcast(id={self.id}, name='{self.name}', slug='{self.slug}')>"

    def to_dict(self):
        """Convert Podcast instance to dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "feed_url": self.feed_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Episode(Base, TimestampMixin):
    """
    Represents a podcast episode with metadata and processing tracking.

    This model stores episode information synced from RSS feeds and tracks
    the episode's progress through the processing pipeline (download, transcription,
    embedding).

    Attributes:
        uuid: Primary key, unique identifier (UUID7 format)
        podcast_id: Foreign key to podcasts table
        podcast_rel: Relationship to Podcast model
        podcast: Hybrid property returning podcast name (backward compatible)
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
        summary_path: Path to episode summary text file
        transcript_duration: Audio duration in seconds (from transcription)
        transcript_confidence: Transcription confidence score (0.0-1.0)
        created_at: Timestamp when episode was added to database (from TimestampMixin)
        updated_at: Timestamp of last update (from TimestampMixin)

    File Path Conventions:
        audio_file_path: data/audio/episode_{episode_id:03d}_{sanitized_title}.mp3
        raw_transcript_path: data/transcript/episode_{episode_id}_universal.json
        formatted_transcript_path: data/transcript/episode_{episode_id}_formatted.txt
        summary_path: data/summary/episode_{episode_id}_summary.txt
    """

    __tablename__ = "episodes"

    # Primary metadata
    uuid = Column(String, primary_key=True)  # Primary key (was guid)
    podcast_id = Column(Integer, ForeignKey("podcasts.id"), nullable=False)
    episode_id = Column(
        Integer, nullable=False
    )  # Episode number, not unique across podcasts (was id)

    # Relationship to Podcast
    podcast_rel = relationship("Podcast", back_populates="episodes")

    @hybrid_property
    def podcast(self) -> str:
        """Return podcast name for backward compatibility."""
        return self.podcast_rel.name if self.podcast_rel else None

    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    published_date = Column(DateTime, nullable=False)
    summary_path = Column(Text, nullable=True)
    audio_url = Column(String, nullable=False)

    # Processing tracking
    processing_stage = Column(
        Enum(ProcessingStage),
        nullable=False,
        default=ProcessingStage.SYNCED,
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
        """
        Return a concise string representation of the Episode showing its primary identifiers and processing stage.

        Returns:
            str: A string containing the episode's `uuid`, `episode_id`, `title`, `published_date`, and current processing stage.
        """
        return (
            f"<Episode(uuid={self.uuid}, episode_id={self.episode_id}, title='{self.title}', "
            f"published_date='{self.published_date}', stage={self.processing_stage.value})>"
        )

    def to_dict(self):
        """Convert Episode instance to dictionary representation."""
        return {
            "uuid": self.uuid,
            "podcast_id": self.podcast_id,
            "podcast": self.podcast,  # hybrid property for backward compat
            "episode_id": self.episode_id,
            "title": self.title,
            "description": self.description,
            "published_date": self.published_date.isoformat()
            if self.published_date
            else None,
            "summary_path": self.summary_path,
            "audio_url": self.audio_url,
            "processing_stage": self.processing_stage.value,
            "audio_file_path": self.audio_file_path,
            "raw_transcript_path": self.raw_transcript_path,
            "speaker_mapping_path": self.speaker_mapping_path,
            "formatted_transcript_path": self.formatted_transcript_path,
            "transcript_duration": self.transcript_duration,
            "transcript_confidence": self.transcript_confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

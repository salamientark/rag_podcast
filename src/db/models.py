from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, Float, Enum, String, Text, DateTime, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class TimestampMixin:
    """Mixin to add created_at and updated_at timestamps to models."""

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ProcessingStage(str, PyEnum):
    """Enum representing processing stages of an episodes."""
    SYNCED = "synced"                               # Episode in DB, no processing yet
    AUDIO_DOWNLOADED = "audio_downloaded"           # Audio file downloaded
    RAW_TRANSCRIPT = "raw_transcript"               # Initial raw transcription done
    FORMATTED_TRANSCRIPT = "formatted_transcript"   # Speaker-mapper transcription done
    EMBEDDED = "embedded"                           # Chunks embedded in vectorial DB (Qdrant)


class Episode(Base, TimestampMixin):
    __tablename__ = "episodes"
    # Columns
    id = Column(Integer, primary_key=True)
    guid = Column(String, nullable=False, unique=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    published_date = Column(DateTime, nullable=False)
    audio_url = Column(String, nullable=False)
    processing_stage = Column(
        Enum(ProcessingStage),
        nullable=False,
        default=ProcessingStage.SYNCED,
        server_default="synced",
    )
    audio_file_path = Column(String, nullable=True)
    raw_transcript_path = Column(String, nullable=True)
    formatted_transcript_path = Column(String, nullable=True)
    transcript_duration = Column(Integer, nullable=True)  # in seconds
    transcript_confidence = Column(Float, nullable=True)  # percentage 0.0-1.0

    # Contraints
    __table_args__ = (UniqueConstraint("guid", name="uq_guid"),)

    def __repr__(self):
        return (
            f"<Episode(id={self.id}, title='{self.title}', published_date='{self.published_date})', "
            f"stage={self.processing_stage.value})>"
        )

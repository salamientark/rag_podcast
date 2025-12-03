from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class TimestampMixin:
    """Mixin to add created_at and updated_at timestamps to models."""

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class Episode(Base, TimestampMixin):
    __tablename__ = "episodes"
    id = Column(Integer, primary_key=True)
    guid = Column(String, nullable=False, unique=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    published_date = Column(DateTime, nullable=False)
    audio_url = Column(String, nullable=False)
    __table_args__ = (UniqueConstraint("guid", name="uq_guid"),)

    def __repr__(self):
        return (
            f"<Episode(title='{self.title}', published_date='{self.published_date}')>"
        )

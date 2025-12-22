"""restructure primary key from id to uuid

Revision ID: cd7eb127a311
Revises: a9a30fc4dad6
Create Date: 2025-12-22 15:56:44.065580

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "cd7eb127a311"
down_revision: Union[str, Sequence[str], None] = "a9a30fc4dad6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Restructure primary key:
    - Rename 'guid' → 'uuid' and make it the PRIMARY KEY
    - Rename 'id' → 'episode_id' (no longer primary key, not unique)

    For SQLite, we must manually recreate the table with the new schema.
    """
    # Clean up any leftover temporary tables from previous migrations
    op.execute("DROP TABLE IF EXISTS _alembic_tmp_episodes")

    # Create new table with correct schema
    op.execute("""
        CREATE TABLE episodes_new (
            uuid VARCHAR NOT NULL,
            episode_id INTEGER NOT NULL,
            podcast VARCHAR NOT NULL DEFAULT 'unknown',
            title VARCHAR NOT NULL,
            description TEXT,
            published_date DATETIME NOT NULL,
            audio_url VARCHAR NOT NULL,
            processing_stage VARCHAR(20) NOT NULL DEFAULT 'synced',
            audio_file_path VARCHAR,
            raw_transcript_path VARCHAR,
            speaker_mapping_path VARCHAR,
            formatted_transcript_path VARCHAR,
            transcript_duration INTEGER,
            transcript_confidence FLOAT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (uuid)
        )
    """)

    # Copy data from old table to new table (renaming columns during copy)
    op.execute("""
        INSERT INTO episodes_new (
            uuid, episode_id, podcast, title, description, published_date, audio_url,
            processing_stage, audio_file_path, raw_transcript_path, speaker_mapping_path,
            formatted_transcript_path, transcript_duration, transcript_confidence,
            created_at, updated_at
        )
        SELECT 
            guid as uuid, 
            id as episode_id,
            podcast, title, description, published_date, audio_url,
            processing_stage, audio_file_path, raw_transcript_path, speaker_mapping_path,
            formatted_transcript_path, transcript_duration, transcript_confidence,
            created_at, updated_at
        FROM episodes
    """)

    # Drop old table
    op.execute("DROP TABLE episodes")

    # Rename new table to original name
    op.execute("ALTER TABLE episodes_new RENAME TO episodes")


def downgrade() -> None:
    """Downgrade schema.

    Reverse the restructuring:
    - Rename 'uuid' → 'guid' and remove as PRIMARY KEY
    - Rename 'episode_id' → 'id' and make it PRIMARY KEY again
    """
    # Create table with old schema
    op.execute("""
        CREATE TABLE episodes_old (
            id INTEGER NOT NULL,
            guid VARCHAR NOT NULL,
            podcast VARCHAR NOT NULL DEFAULT 'unknown',
            title VARCHAR NOT NULL,
            description TEXT,
            published_date DATETIME NOT NULL,
            audio_url VARCHAR NOT NULL,
            processing_stage VARCHAR(20) NOT NULL DEFAULT 'synced',
            audio_file_path VARCHAR,
            raw_transcript_path VARCHAR,
            speaker_mapping_path VARCHAR,
            formatted_transcript_path VARCHAR,
            transcript_duration INTEGER,
            transcript_confidence FLOAT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE (guid),
            CONSTRAINT uq_guid UNIQUE (guid)
        )
    """)

    # Copy data back (renaming columns)
    op.execute("""
        INSERT INTO episodes_old (
            id, guid, podcast, title, description, published_date, audio_url,
            processing_stage, audio_file_path, raw_transcript_path, speaker_mapping_path,
            formatted_transcript_path, transcript_duration, transcript_confidence,
            created_at, updated_at
        )
        SELECT 
            episode_id as id,
            uuid as guid,
            podcast, title, description, published_date, audio_url,
            processing_stage, audio_file_path, raw_transcript_path, speaker_mapping_path,
            formatted_transcript_path, transcript_duration, transcript_confidence,
            created_at, updated_at
        FROM episodes
    """)

    # Drop new table
    op.execute("DROP TABLE episodes")

    # Rename old table back
    op.execute("ALTER TABLE episodes_old RENAME TO episodes")

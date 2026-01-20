"""add_error_to_processingstage_enum

Revision ID: 8144ce02b58c
Revises: 0e6cd81255d8
Create Date: 2026-01-20 10:19:58.824908

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "8144ce02b58c"
down_revision: Union[str, Sequence[str], None] = "0e6cd81255d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ERROR value to processingstage enum."""
    op.execute("ALTER TYPE processingstage ADD VALUE IF NOT EXISTS 'ERROR'")


def downgrade() -> None:
    """Downgrade schema.

    Note: PostgreSQL does not support removing enum values directly.
    To fully downgrade, you would need to:
    1. Update all ERROR episodes to another stage
    2. Recreate the enum without ERROR
    3. Recreate the column with the new enum

    For simplicity, this downgrade just updates ERROR episodes to SYNCED.
    """
    op.execute(
        "UPDATE episodes SET processing_stage = 'SYNCED' WHERE processing_stage = 'ERROR'"
    )

"""add error columns to routes, segments and job_segment_run

Ticket 9: store why a route, segment or job segment run failed so it can be shown in the UI.

Revision ID: c4e1a9b27d53
Revises: 95e9b7774239
Create Date: 2026-10-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e1a9b27d53'
down_revision: Union[str, Sequence[str], None] = '95e9b7774239'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('routes', sa.Column('error', sa.String(), nullable=True))
    op.add_column('segments', sa.Column('error', sa.String(), nullable=True))
    op.add_column('job_segment_run', sa.Column('error', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('job_segment_run', 'error')
    op.drop_column('segments', 'error')
    op.drop_column('routes', 'error')

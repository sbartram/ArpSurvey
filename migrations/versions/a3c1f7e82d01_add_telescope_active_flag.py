"""add telescope active flag

Revision ID: a3c1f7e82d01
Revises: 4bfee6d560b0
Create Date: 2026-04-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3c1f7e82d01'
down_revision: Union[str, None] = '4bfee6d560b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OFFLINE_TELESCOPES = ['T2', 'T18', 'T20', 'T25', 'T71', 'T73', 'T74']


def upgrade() -> None:
    op.add_column('telescopes',
                  sa.Column('active', sa.Boolean(), nullable=False,
                            server_default=sa.text('true')))

    # Mark known offline telescopes as inactive
    telescopes = sa.table('telescopes',
                          sa.column('telescope_id', sa.String),
                          sa.column('active', sa.Boolean))
    op.execute(
        telescopes.update()
        .where(telescopes.c.telescope_id.in_(OFFLINE_TELESCOPES))
        .values(active=False)
    )


def downgrade() -> None:
    op.drop_column('telescopes', 'active')

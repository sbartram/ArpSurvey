"""add target preferred_telescope

Revision ID: b7d2e3f91a04
Revises: a3c1f7e82d01
Create Date: 2026-04-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7d2e3f91a04'
down_revision: Union[str, None] = 'a3c1f7e82d01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('targets',
                  sa.Column('preferred_telescope', sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column('targets', 'preferred_telescope')

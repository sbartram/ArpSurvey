"""rename observatory sites to match iTelescope dashboard

Revision ID: c8f3a2b71d05
Revises: b7d2e3f91a04
Create Date: 2026-04-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c8f3a2b71d05'
down_revision: Union[str, None] = 'b7d2e3f91a04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Old name → new name
SITE_RENAMES = {
    "New Mexico": "Utah Desert Remote Observatory",
    "Australia": "Siding Spring Observatory",
    "Chile": "Deep Sky Chile",
}

# T24 was grouped under "New Mexico", now has its own site
SIERRA_TELESCOPES = ["T24"]


def upgrade() -> None:
    telescopes = sa.table('telescopes',
                          sa.column('telescope_id', sa.String),
                          sa.column('site', sa.String))

    # Rename sites on telescopes
    for old, new in SITE_RENAMES.items():
        op.execute(
            telescopes.update()
            .where(telescopes.c.site == old)
            .values(site=new)
        )

    # Split T24 out to Sierra Remote Observatory
    op.execute(
        telescopes.update()
        .where(telescopes.c.telescope_id.in_(SIERRA_TELESCOPES))
        .values(site="Sierra Remote Observatory")
    )


def downgrade() -> None:
    telescopes = sa.table('telescopes',
                          sa.column('telescope_id', sa.String),
                          sa.column('site', sa.String))

    # Move T24 back to New Mexico
    op.execute(
        telescopes.update()
        .where(telescopes.c.telescope_id.in_(SIERRA_TELESCOPES))
        .values(site="New Mexico")
    )

    # Reverse renames
    for old, new in SITE_RENAMES.items():
        op.execute(
            telescopes.update()
            .where(telescopes.c.site == new)
            .values(site=old)
        )

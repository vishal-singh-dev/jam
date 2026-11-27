"""add asset status

Revision ID: 5a1b2c3d4e5f
Revises: 36f5337861bd
Create Date: 2026-11-27 11:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5a1b2c3d4e5f"
down_revision: str | None = "36f5337861bd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("status", sa.String(length=20), server_default="ready", nullable=False),
    )
    op.create_check_constraint(
        "chk_assets_status",
        "assets",
        "status IN ('pending', 'ready', 'failed')",
    )
    op.create_index(
        "ix_assets_owner_status",
        "assets",
        ["owner_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_assets_owner_status", table_name="assets")
    op.drop_constraint("chk_assets_status", "assets", type_="check")
    op.drop_column("assets", "status")

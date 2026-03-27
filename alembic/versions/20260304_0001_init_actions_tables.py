"""create actions tables

Revision ID: 20260304_0001
Revises:
Create Date: 2026-03-04 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260304_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "actions",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )

    op.create_table(
        "action_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("hash", sa.String(length=80), nullable=False),
        sa.Column("sig_alg", sa.String(length=32), nullable=False),
        sa.Column("sig_kid", sa.String(length=255), nullable=False),
        sa.Column("sig_b64", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["name"], ["actions.name"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_action_versions_name_version"),
    )

    op.create_index("ix_action_versions_name", "action_versions", ["name"], unique=False)
    op.create_index("ix_action_versions_sig_kid", "action_versions", ["sig_kid"], unique=False)
    op.create_index("ix_action_versions_version", "action_versions", ["version"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_action_versions_version", table_name="action_versions")
    op.drop_index("ix_action_versions_sig_kid", table_name="action_versions")
    op.drop_index("ix_action_versions_name", table_name="action_versions")
    op.drop_table("action_versions")
    op.drop_table("actions")

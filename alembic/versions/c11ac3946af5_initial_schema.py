"""initial schema

Revision ID: c11ac3946af5
Revises:
Create Date: 2026-06-13 00:03:22.496716

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision: str = "c11ac3946af5"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create icontrigger table and normalize created_at nullability."""
    op.create_table(
        "icontrigger",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "trigger_word",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column(
            "icon_url",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_icontrigger_trigger_word"),
        "icontrigger",
        ["trigger_word"],
        unique=True,
    )
    with op.batch_alter_table("channel") as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DATETIME(),
            nullable=True,
        )
    with op.batch_alter_table("sound") as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DATETIME(),
            nullable=True,
        )
    with op.batch_alter_table("user") as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DATETIME(),
            nullable=True,
        )


def downgrade() -> None:
    """Reverse: remove icontrigger and restore NOT NULL on created_at."""
    with op.batch_alter_table("user") as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DATETIME(),
            nullable=False,
        )
    with op.batch_alter_table("sound") as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DATETIME(),
            nullable=False,
        )
    with op.batch_alter_table("channel") as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DATETIME(),
            nullable=False,
        )
    op.drop_index(
        op.f("ix_icontrigger_trigger_word"), table_name="icontrigger"
    )
    op.drop_table("icontrigger")

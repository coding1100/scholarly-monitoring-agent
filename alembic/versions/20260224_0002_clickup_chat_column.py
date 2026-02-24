"""Rename ClickUp incident reference column for chat mode.

Revision ID: 20260224_0002
Revises: 20260224_0001
Create Date: 2026-02-24 00:30:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260224_0002"
down_revision: Union[str, Sequence[str], None] = "20260224_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("incidents", schema=None) as batch_op:
        batch_op.alter_column("clickup_task_id", new_column_name="clickup_chat_channel_id")


def downgrade() -> None:
    with op.batch_alter_table("incidents", schema=None) as batch_op:
        batch_op.alter_column("clickup_chat_channel_id", new_column_name="clickup_task_id")

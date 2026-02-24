"""Initial schema for monitor, check results, and incidents.

Revision ID: 20260224_0001
Revises:
Create Date: 2026-02-24 00:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260224_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


monitor_status_enum = sa.Enum(
    "unknown",
    "healthy",
    "failing",
    "paused",
    name="monitorhealthstatus",
    native_enum=False,
)
incident_status_enum = sa.Enum(
    "open",
    "resolved",
    name="incidentstatus",
    native_enum=False,
)
alert_type_enum = sa.Enum(
    "failure",
    "recovery",
    name="alerttype",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "monitors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Float(), nullable=False),
        sa.Column("expected_status_min", sa.Integer(), nullable=False),
        sa.Column("expected_status_max", sa.Integer(), nullable=False),
        sa.Column("content_substring", sa.Text(), nullable=True),
        sa.Column("failure_threshold", sa.Integer(), nullable=False),
        sa.Column("recovery_threshold", sa.Integer(), nullable=False),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", monitor_status_enum, nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("consecutive_successes", sa.Integer(), nullable=False),
        sa.Column("last_notification_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_alert_type", alert_type_enum, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_monitors")),
    )

    op.create_table(
        "check_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("monitor_id", sa.Uuid(), nullable=False),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("response_excerpt", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["monitor_id"],
            ["monitors.id"],
            name=op.f("fk_check_results_monitor_id_monitors"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_check_results")),
    )
    op.create_index(
        op.f("ix_check_results_monitor_id"),
        "check_results",
        ["monitor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_check_results_checked_at"),
        "check_results",
        ["checked_at"],
        unique=False,
    )

    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("monitor_id", sa.Uuid(), nullable=False),
        sa.Column("status", incident_status_enum, nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_check_result_id", sa.Uuid(), nullable=True),
        sa.Column("resolved_check_result_id", sa.Uuid(), nullable=True),
        sa.Column("clickup_task_id", sa.String(length=80), nullable=True),
        sa.Column("last_notification_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["monitor_id"],
            ["monitors.id"],
            name=op.f("fk_incidents_monitor_id_monitors"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["opened_check_result_id"],
            ["check_results.id"],
            name=op.f("fk_incidents_opened_check_result_id_check_results"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_check_result_id"],
            ["check_results.id"],
            name=op.f("fk_incidents_resolved_check_result_id_check_results"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
    )
    op.create_index(op.f("ix_incidents_monitor_id"), "incidents", ["monitor_id"], unique=False)
    op.create_index(op.f("ix_incidents_status"), "incidents", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_incidents_status"), table_name="incidents")
    op.drop_index(op.f("ix_incidents_monitor_id"), table_name="incidents")
    op.drop_table("incidents")

    op.drop_index(op.f("ix_check_results_checked_at"), table_name="check_results")
    op.drop_index(op.f("ix_check_results_monitor_id"), table_name="check_results")
    op.drop_table("check_results")

    op.drop_table("monitors")

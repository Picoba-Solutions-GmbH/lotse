"""Initial schema (as created by Base.metadata.create_all before migrations were introduced)

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-09 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "Packages",
        sa.Column("deployment_id", sa.String(), nullable=False),
        sa.Column("package_name", sa.String(), nullable=False),
        sa.Column("python_version", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("deployed_at", sa.DateTime(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("config", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("deployment_id"),
    )
    op.create_table(
        "Users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("is_ldap", sa.Boolean(), nullable=True),
        sa.Column("role", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "Volumes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("pvc_name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "Tasks",
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("deployment_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("hostname", sa.String(), nullable=True),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("is_ui_app", sa.Boolean(), nullable=False),
        sa.Column("ui_ip_address", sa.String(), nullable=True),
        sa.Column("ui_port", sa.Integer(), nullable=True),
        sa.Column("original_ui_port", sa.Integer(), nullable=True),
        sa.Column("vscode_port", sa.Integer(), nullable=True),
        sa.Column("arguments", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["deployment_id"], ["Packages.deployment_id"]),
        sa.PrimaryKeyConstraint("task_id"),
    )


def downgrade() -> None:
    op.drop_table("Tasks")
    op.drop_table("Volumes")
    op.drop_table("Users")
    op.drop_table("Packages")

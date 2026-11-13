"""Git sources: deploy package versions from Git tags

Revision ID: 0004_git_sources
Revises: 0003_package_modifications
Create Date: 2026-11-13 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_git_sources"
down_revision: Union[str, Sequence[str], None] = "0003_package_modifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "GitSources",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("package_name", sa.String(), nullable=False, unique=True),
        sa.Column("repo_url", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False, server_default=""),
        sa.Column("tag_prefix", sa.String(), nullable=False, server_default="v"),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("credential_secret", sa.String(), nullable=True),
        sa.Column("auto_sync", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("prune_previous", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("poll_interval_seconds", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("webhook_token", sa.String(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("latest_tag", sa.String(), nullable=True),
        sa.Column("latest_commit", sa.String(), nullable=True),
        sa.Column("last_synced_tag", sa.String(), nullable=True),
        sa.Column("last_synced_commit", sa.String(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("last_failed_commit", sa.String(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # provenance of versions deployed from Git
    op.add_column("Packages", sa.Column("source_id", sa.String(), nullable=True))
    op.add_column("Packages", sa.Column("source_ref", sa.String(), nullable=True))
    op.add_column("Packages", sa.Column("source_commit", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("Packages", "source_commit")
    op.drop_column("Packages", "source_ref")
    op.drop_column("Packages", "source_id")
    op.drop_table("GitSources")

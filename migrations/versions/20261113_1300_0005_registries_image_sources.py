"""Registries and image sources: deploy package versions from container image tags

Revision ID: 0005_registries_image_sources
Revises: 0004_git_sources
Create Date: 2026-11-13 13:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_registries_image_sources"
down_revision: Union[str, Sequence[str], None] = "0004_git_sources"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "Registries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("host", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False, server_default="generic"),
        sa.Column("api_url", sa.String(), nullable=True),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("credential_secret", sa.String(), nullable=True),
        sa.Column("pull_secret_mode", sa.String(), nullable=False, server_default="none"),
        sa.Column("pull_secret_name", sa.String(), nullable=True),
        sa.Column("discovery_path", sa.String(), nullable=True),
        sa.Column("auto_register", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("default_auto_sync", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("poll_interval_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("last_discovered_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "ImageSources",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("package_name", sa.String(), nullable=False, unique=True),
        sa.Column("registry_id", sa.String(), nullable=False),
        sa.Column("repository", sa.String(), nullable=False),
        sa.Column("tag_prefix", sa.String(), nullable=False, server_default=""),
        sa.Column("auto_sync", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("prune_previous", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("poll_interval_seconds", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("webhook_token", sa.String(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("latest_tag", sa.String(), nullable=True),
        sa.Column("latest_digest", sa.String(), nullable=True),
        sa.Column("last_synced_tag", sa.String(), nullable=True),
        sa.Column("last_synced_digest", sa.String(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("last_failed_digest", sa.String(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    # "git" or "image" for versions deployed by a source
    op.add_column("Packages", sa.Column("source_type", sa.String(), nullable=True))
    op.execute("""UPDATE "Packages" SET source_type = 'git' WHERE source_id IS NOT NULL""")


def downgrade() -> None:
    op.drop_column("Packages", "source_type")
    op.drop_table("ImageSources")
    op.drop_table("Registries")

"""Track post-deployment modifications of packages (config and files)

Revision ID: 0003_package_modifications
Revises: 0002_user_management
Create Date: 2026-11-10 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_package_modifications"
down_revision: Union[str, Sequence[str], None] = "0002_user_management"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # config as it was deployed, set on the first edit of environment variables or arguments
    op.add_column("Packages", sa.Column("original_config", sa.String(), nullable=True))
    # relative paths of package files edited after deployment
    op.add_column("Packages", sa.Column("modified_files", sa.JSON(), nullable=True))
    op.add_column("Packages", sa.Column("modified_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("Packages", "modified_at")
    op.drop_column("Packages", "modified_files")
    op.drop_column("Packages", "original_config")

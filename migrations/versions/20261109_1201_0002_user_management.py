"""User management: package ownership, sharing, AD user data and task starter

Revision ID: 0002_user_management
Revises: 0001_initial
Create Date: 2026-11-09 12:01:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_user_management"
down_revision: Union[str, Sequence[str], None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    # The existence checks only matter for development databases that already got these
    # changes from the pre-migration startup code. New migrations don't need them.
    if not _has_column("Users", "display_name"):
        op.add_column("Users", sa.Column("display_name", sa.String(), nullable=True))
    if not _has_column("Users", "email"):
        op.add_column("Users", sa.Column("email", sa.String(), nullable=True))
    if not _has_column("Tasks", "started_by"):
        op.add_column("Tasks", sa.Column("started_by", sa.String(), nullable=True))

    if not _has_table("PackageOwnership"):
        op.create_table(
            "PackageOwnership",
            sa.Column("package_name", sa.String(), nullable=False),
            sa.Column("owner_id", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(["owner_id"], ["Users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("package_name"),
        )

    if not _has_table("PackageShares"):
        op.create_table(
            "PackageShares",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("package_name", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("can_execute", sa.Boolean(), nullable=False),
            sa.Column("can_edit", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["Users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("package_name", "user_id", name="uq_package_share_user"),
        )
        op.create_index(op.f("ix_PackageShares_package_name"), "PackageShares", ["package_name"], unique=False)
        op.create_index(op.f("ix_PackageShares_user_id"), "PackageShares", ["user_id"], unique=False)

    # Roles are now Admin and User. Operators and pending (Unauthorized) users become Users.
    op.execute("""UPDATE "Users" SET role = 'User' WHERE role IN ('Operator', 'Unauthorized')""")


def downgrade() -> None:
    # Users cannot be mapped back to Operator/Unauthorized reliably, all of them become Operators.
    op.execute("""UPDATE "Users" SET role = 'Operator' WHERE role = 'User'""")

    op.drop_index(op.f("ix_PackageShares_user_id"), table_name="PackageShares")
    op.drop_index(op.f("ix_PackageShares_package_name"), table_name="PackageShares")
    op.drop_table("PackageShares")
    op.drop_table("PackageOwnership")
    op.drop_column("Tasks", "started_by")
    op.drop_column("Users", "email")
    op.drop_column("Users", "display_name")

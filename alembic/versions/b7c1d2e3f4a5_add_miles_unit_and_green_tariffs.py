"""S2: add 'miles' unit (FR-2.03) and facility green tariffs (FR-2.07)

Revision ID: b7c1d2e3f4a5
Revises: ff825a1bbd10
Create Date: 2026-10-24 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7c1d2e3f4a5"
down_revision: Union[str, None] = "ff825a1bbd10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # ADD VALUE must run outside the migration's transaction block
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE unit ADD VALUE IF NOT EXISTS 'miles'")
    # SQLite stores enums as plain text, so nothing to change there.

    op.create_table(
        "facility_green_tariffs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("facility_id", sa.Uuid(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("kg_co2e_per_kwh", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("supplier", sa.String(length=120), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_facility_green_tariffs_facility_id"), "facility_green_tariffs", ["facility_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_facility_green_tariffs_facility_id"), table_name="facility_green_tariffs")
    op.drop_table("facility_green_tariffs")
    # PostgreSQL cannot drop a single enum value; 'miles' stays in the type (harmless).

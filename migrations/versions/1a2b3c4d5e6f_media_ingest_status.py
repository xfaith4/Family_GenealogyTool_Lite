"""Add media status and source_path for ingest workflow

Revision ID: 1a2b3c4d5e6f
Revises: 8b3885a2b5e0
Create Date: 2025-12-19 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "1a2b3c4d5e6f"
down_revision = "8b3885a2b5e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("media_assets") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=50),
                nullable=False,
                server_default="unassigned",
            )
        )
        batch_op.add_column(
            sa.Column(
                "source_path",
                sa.String(length=500),
                nullable=True,
            )
        )
    op.create_index(
        "idx_media_assets_original_filename",
        "media_assets",
        ["original_filename"],
        unique=False,
        if_not_exists=True,
    )
    op.execute(sa.text("UPDATE media_assets SET status='assigned' WHERE status IS NULL AND id IN (SELECT DISTINCT asset_id FROM media_links WHERE asset_id IS NOT NULL)"))
    op.execute(sa.text("UPDATE media_assets SET status='unassigned' WHERE status IS NULL OR status=''"))
    with op.batch_alter_table("media_assets") as batch_op:
        batch_op.alter_column("status", server_default=None)


def downgrade() -> None:
    op.drop_index("idx_media_assets_original_filename", table_name="media_assets")
    with op.batch_alter_table("media_assets") as batch_op:
        batch_op.drop_column("source_path")
        batch_op.drop_column("status")

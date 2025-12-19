"""Align media schema with latest models

Revision ID: 8b3885a2b5e0
Revises: 10740efec864
Create Date: 2025-12-20 12:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8b3885a2b5e0"
down_revision = "10740efec864"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_media_assets_sha256"))

    op.rename_table("media_assets", "media_assets_old")
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=True),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("thumbnail_path", sa.String(length=500), nullable=True),
        sa.Column("thumb_width", sa.Integer(), nullable=True),
        sa.Column("thumb_height", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_media_assets_sha256"),
        "media_assets",
        ["sha256"],
        unique=True,
        if_not_exists=True,
    )
    op.execute(
        """
        INSERT INTO media_assets (id, path, sha256, original_filename, mime_type, size_bytes, created_at)
        SELECT id, file_name, sha256, original_name, mime_type, size_bytes, created_at
        FROM media_assets_old
        """
    )
    op.drop_table("media_assets_old")

    op.rename_table("media_links", "media_links_old")
    op.create_table(
        "media_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column("family_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["media_assets.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["family_id"], ["families.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["person_id"], ["persons.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_media_links_person", "media_links", ["person_id"], unique=False)
    op.create_index("idx_media_links_family", "media_links", ["family_id"], unique=False)
    op.create_index("idx_media_links_asset", "media_links", ["asset_id"], unique=False)
    op.execute(
        """
        INSERT INTO media_links (id, asset_id, person_id, family_id, description, created_at)
        SELECT id, media_asset_id, person_id, family_id, description, created_at
        FROM media_links_old
        """
    )
    op.drop_table("media_links_old")


def downgrade() -> None:
    op.rename_table("media_links", "media_links_new")
    op.create_table(
        "media_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("media_asset_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column("family_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["family_id"], ["families.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["media_asset_id"], ["media_assets.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["person_id"], ["persons.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_media_links_person", "media_links", ["person_id"], unique=False)
    op.create_index("idx_media_links_family", "media_links", ["family_id"], unique=False)
    op.execute(
        """
        INSERT INTO media_links (id, media_asset_id, person_id, family_id, description, created_at)
        SELECT id, asset_id, person_id, family_id, description, created_at
        FROM media_links_new
        """
    )
    op.drop_table("media_links_new")

    op.rename_table("media_assets", "media_assets_new")
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("file_name", sa.String(length=500), nullable=False),
        sa.Column("original_name", sa.String(length=500), nullable=True),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_media_assets_sha256"), "media_assets", ["sha256"], unique=True
    )
    op.execute(
        """
        INSERT INTO media_assets (id, file_name, original_name, mime_type, sha256, size_bytes, created_at)
        SELECT id, path, original_filename, mime_type, sha256, size_bytes, created_at
        FROM media_assets_new
        """
    )
    op.drop_table("media_assets_new")

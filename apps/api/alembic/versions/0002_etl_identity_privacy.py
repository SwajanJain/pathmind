"""add etl tables and api log ip

Revision ID: 0002_etl_identity_privacy
Revises: 0001_initial
Create Date: 2026-02-14 11:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_etl_identity_privacy"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("api_event_logs", sa.Column("client_ip", sa.String(length=64), nullable=True))

    op.create_table(
        "target_pathway_map",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("uniprot_id", sa.String(length=32), nullable=False),
        sa.Column("pathway_id", sa.String(length=64), nullable=False),
        sa.Column("pathway_name", sa.String(length=512), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("pathway_size", sa.Integer(), nullable=False),
        sa.Column("ancestor_pathway_ids", sa.JSON(), nullable=False),
        sa.Column("reactome_url", sa.String(length=1024), nullable=False),
        sa.Column("source_name", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_target_pathway_map_uniprot_id", "target_pathway_map", ["uniprot_id"], unique=False)
    op.create_index("ix_target_pathway_map_pathway_id", "target_pathway_map", ["pathway_id"], unique=False)

    op.create_table(
        "pathway_metadata",
        sa.Column("pathway_id", sa.String(length=64), nullable=False),
        sa.Column("pathway_name", sa.String(length=512), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("pathway_size", sa.Integer(), nullable=False),
        sa.Column("ancestor_pathway_ids", sa.JSON(), nullable=False),
        sa.Column("reactome_url", sa.String(length=1024), nullable=False),
        sa.Column("source_name", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("pathway_id"),
    )

    op.create_table(
        "etl_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_name", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_upserted", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_etl_runs_source_name", "etl_runs", ["source_name"], unique=False)
    op.create_index("ix_etl_runs_status", "etl_runs", ["status"], unique=False)
    op.create_index("ix_etl_runs_started_at", "etl_runs", ["started_at"], unique=False)
    op.create_index("ix_etl_runs_completed_at", "etl_runs", ["completed_at"], unique=False)

    op.create_table(
        "source_release_versions",
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("release_version", sa.String(length=128), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source_name"),
    )
    op.create_index("ix_source_release_versions_fetched_at", "source_release_versions", ["fetched_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_source_release_versions_fetched_at", table_name="source_release_versions")
    op.drop_table("source_release_versions")

    op.drop_index("ix_etl_runs_completed_at", table_name="etl_runs")
    op.drop_index("ix_etl_runs_started_at", table_name="etl_runs")
    op.drop_index("ix_etl_runs_status", table_name="etl_runs")
    op.drop_index("ix_etl_runs_source_name", table_name="etl_runs")
    op.drop_table("etl_runs")

    op.drop_table("pathway_metadata")

    op.drop_index("ix_target_pathway_map_pathway_id", table_name="target_pathway_map")
    op.drop_index("ix_target_pathway_map_uniprot_id", table_name="target_pathway_map")
    op.drop_table("target_pathway_map")

    op.drop_column("api_event_logs", "client_ip")

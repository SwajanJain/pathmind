"""create initial pathmind tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-02-14 10:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("input_drug_name", sa.String(length=255), nullable=False),
        sa.Column("canonical_drug_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("timings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_runs_canonical_drug_id", "analysis_runs", ["canonical_drug_id"], unique=False)

    op.create_table(
        "analysis_payloads",
        sa.Column("analysis_id", sa.String(length=36), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("source_versions", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("analysis_id"),
    )

    op.create_table(
        "share_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("analysis_id", sa.String(length=36), nullable=False),
        sa.Column("public", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_share_links_analysis_id", "share_links", ["analysis_id"], unique=False)

    op.create_table(
        "drug_resolution_cache",
        sa.Column("input_text", sa.String(length=255), nullable=False),
        sa.Column("canonical_inchikey", sa.String(length=64), nullable=False),
        sa.Column("chembl_parent_id", sa.String(length=64), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("input_text"),
    )
    op.create_index("ix_drug_resolution_cache_canonical_inchikey", "drug_resolution_cache", ["canonical_inchikey"], unique=False)
    op.create_index("ix_drug_resolution_cache_chembl_parent_id", "drug_resolution_cache", ["chembl_parent_id"], unique=False)

    op.create_table(
        "source_versions",
        sa.Column("source_name", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source_name"),
    )

    op.create_table(
        "api_event_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_event_logs_source", "api_event_logs", ["source"], unique=False)
    op.create_index("ix_api_event_logs_timestamp", "api_event_logs", ["timestamp"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_api_event_logs_timestamp", table_name="api_event_logs")
    op.drop_index("ix_api_event_logs_source", table_name="api_event_logs")
    op.drop_table("api_event_logs")
    op.drop_table("source_versions")
    op.drop_index("ix_drug_resolution_cache_chembl_parent_id", table_name="drug_resolution_cache")
    op.drop_index("ix_drug_resolution_cache_canonical_inchikey", table_name="drug_resolution_cache")
    op.drop_table("drug_resolution_cache")
    op.drop_index("ix_share_links_analysis_id", table_name="share_links")
    op.drop_table("share_links")
    op.drop_table("analysis_payloads")
    op.drop_index("ix_analysis_runs_canonical_drug_id", table_name="analysis_runs")
    op.drop_table("analysis_runs")


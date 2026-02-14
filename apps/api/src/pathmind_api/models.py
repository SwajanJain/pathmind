from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pathmind_api.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    input_drug_name: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_drug_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    params: Mapped[dict] = mapped_column(JSON, nullable=False)
    timings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    payload: Mapped["AnalysisPayload"] = relationship(back_populates="analysis_run", uselist=False, cascade="all,delete")
    share_links: Mapped[list["ShareLink"]] = relationship(back_populates="analysis_run", cascade="all,delete")


class AnalysisPayload(Base):
    __tablename__ = "analysis_payloads"

    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("analysis_runs.id", ondelete="CASCADE"), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_versions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="payload")


class ShareLink(Base):
    __tablename__ = "share_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    analysis_run: Mapped[AnalysisRun] = relationship(back_populates="share_links")


class DrugResolutionCache(Base):
    __tablename__ = "drug_resolution_cache"

    input_text: Mapped[str] = mapped_column(String(255), primary_key=True)
    canonical_inchikey: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chembl_parent_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class SourceVersion(Base):
    __tablename__ = "source_versions"

    source_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ApiEventLog(Base):
    __tablename__ = "api_event_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)


class TargetPathwayMap(Base):
    __tablename__ = "target_pathway_map"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uniprot_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    pathway_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    pathway_name: Mapped[str] = mapped_column(String(512), nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    pathway_size: Mapped[int] = mapped_column(Integer, nullable=False)
    ancestor_pathway_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    reactome_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_name: Mapped[str] = mapped_column(String(32), nullable=False, default="reactome")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class PathwayMetadata(Base):
    __tablename__ = "pathway_metadata"

    pathway_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pathway_name: Mapped[str] = mapped_column(String(512), nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    pathway_size: Mapped[int] = mapped_column(Integer, nullable=False)
    ancestor_pathway_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    reactome_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_name: Mapped[str] = mapped_column(String(32), nullable=False, default="reactome")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class EtlRun(Base):
    __tablename__ = "etl_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_name: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="incremental")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    rows_upserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class SourceReleaseVersion(Base):
    __tablename__ = "source_release_versions"

    source_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    release_version: Mapped[str] = mapped_column(String(128), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)

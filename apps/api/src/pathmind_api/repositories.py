from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pathmind_api import models, schemas


def create_analysis(session: Session, result: schemas.AnalysisResult) -> None:
    run = models.AnalysisRun(
        id=result.analysis_id,
        input_drug_name=result.drug_name,
        canonical_drug_id=result.canonical_drug_id,
        status="completed",
        params=result.params.model_dump(mode="json"),
        timings={},
    )
    payload = models.AnalysisPayload(
        analysis_id=result.analysis_id,
        payload=result.model_dump(mode="json"),
        source_versions=result.source_versions,
    )
    session.add(run)
    session.add(payload)
    for source_name, version in result.source_versions.items():
        existing = session.get(models.SourceVersion, source_name)
        if existing is None:
            session.add(
                models.SourceVersion(
                    source_name=source_name,
                    version=version,
                )
            )
        else:
            existing.version = version
            existing.fetched_at = datetime.now(timezone.utc)
    session.commit()


def get_analysis(session: Session, analysis_id: str) -> schemas.AnalysisResult | None:
    payload = session.get(models.AnalysisPayload, analysis_id)
    if payload is None:
        return None
    return schemas.AnalysisResult.model_validate(payload.payload)


def create_share_link(session: Session, analysis_id: str) -> models.ShareLink:
    link = models.ShareLink(analysis_id=analysis_id, public=True)
    session.add(link)
    session.commit()
    session.refresh(link)
    return link


def get_share_payload(session: Session, share_id: str) -> schemas.AnalysisResult | None:
    query = (
        select(models.AnalysisPayload.payload)
        .join(models.ShareLink, models.ShareLink.analysis_id == models.AnalysisPayload.analysis_id)
        .where(models.ShareLink.id == share_id)
    )
    row = session.execute(query).first()
    if row is None:
        return None
    return schemas.AnalysisResult.model_validate(row[0])


def cache_resolution(session: Session, resolution: schemas.DrugResolution) -> None:
    cached = session.get(models.DrugResolutionCache, resolution.query.lower())
    payload = resolution.model_dump(mode="json")
    if cached is None:
        cached = models.DrugResolutionCache(
            input_text=resolution.query.lower(),
            canonical_inchikey=resolution.canonical_inchikey,
            chembl_parent_id=resolution.chembl_parent_id,
            metadata_json=payload,
        )
        session.add(cached)
    else:
        cached.canonical_inchikey = resolution.canonical_inchikey
        cached.chembl_parent_id = resolution.chembl_parent_id
        cached.metadata_json = payload
    session.commit()


def get_cached_resolution(session: Session, query: str) -> schemas.DrugResolution | None:
    cached = session.get(models.DrugResolutionCache, query.lower())
    if cached is None:
        return None
    return schemas.DrugResolution.model_validate(cached.metadata_json)


def latest_source_timestamp(session: Session) -> datetime | None:
    query = select(func.max(models.EtlRun.completed_at)).where(models.EtlRun.status == "completed")
    return session.execute(query).scalar()


def cache_hit_rate_from_logs(session: Session) -> float:
    total_query = select(func.count(models.ApiEventLog.id)).where(
        models.ApiEventLog.source == "cache",
        models.ApiEventLog.status.in_(["hit", "miss"]),
    )
    hit_query = select(func.count(models.ApiEventLog.id)).where(
        models.ApiEventLog.source == "cache",
        models.ApiEventLog.status == "hit",
    )
    total = int(session.execute(total_query).scalar() or 0)
    hits = int(session.execute(hit_query).scalar() or 0)
    if total == 0:
        return 0.0
    return hits / total


def log_api_event(
    session: Session,
    *,
    source: str,
    status: str,
    latency_ms: int | None = None,
    error_code: str | None = None,
    details: str | None = None,
    client_ip: str | None = None,
) -> None:
    session.add(
        models.ApiEventLog(
            source=source,
            status=status,
            latency_ms=latency_ms,
            error_code=error_code,
            details=details,
            client_ip=client_ip,
        )
    )
    session.commit()


def start_etl_run(session: Session, source_name: str, mode: str) -> models.EtlRun:
    run = models.EtlRun(id=str(uuid4()), source_name=source_name, mode=mode, status="running")
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def finish_etl_run(session: Session, run_id: str, *, status: str, rows_upserted: int, details: dict) -> None:
    run = session.get(models.EtlRun, run_id)
    if run is None:
        return
    run.status = status
    run.rows_upserted = rows_upserted
    run.details = details
    run.completed_at = datetime.now(timezone.utc)
    session.commit()


def upsert_source_release_version(session: Session, source_name: str, release_version: str) -> None:
    existing = session.get(models.SourceReleaseVersion, source_name)
    if existing is None:
        session.add(models.SourceReleaseVersion(source_name=source_name, release_version=release_version))
    else:
        existing.release_version = release_version
        existing.fetched_at = datetime.now(timezone.utc)
    session.commit()


def latest_source_release_versions(session: Session) -> dict[str, str]:
    query = select(models.SourceReleaseVersion)
    rows = session.execute(query).scalars().all()
    return {row.source_name: row.release_version for row in rows}


def upsert_target_pathway_rows(session: Session, uniprot_id: str, pathways: list[dict]) -> int:
    existing_query = select(models.TargetPathwayMap).where(models.TargetPathwayMap.uniprot_id == uniprot_id)
    existing_rows = session.execute(existing_query).scalars().all()
    existing_by_pathway = {row.pathway_id: row for row in existing_rows}
    touched_pathway_ids: set[str] = set()
    upserted = 0

    for pathway in pathways:
        pathway_id = pathway["pathway_id"]
        touched_pathway_ids.add(pathway_id)
        row = existing_by_pathway.get(pathway_id)
        if row is None:
            session.add(
                models.TargetPathwayMap(
                    uniprot_id=uniprot_id,
                    pathway_id=pathway_id,
                    pathway_name=pathway["pathway_name"],
                    depth=pathway["depth"],
                    pathway_size=max(int(pathway["pathway_size"]), 1),
                    ancestor_pathway_ids=pathway.get("ancestor_pathway_ids", []),
                    reactome_url=pathway["reactome_url"],
                    source_name="reactome",
                )
            )
            upserted += 1
        else:
            row.pathway_name = pathway["pathway_name"]
            row.depth = pathway["depth"]
            row.pathway_size = max(int(pathway["pathway_size"]), 1)
            row.ancestor_pathway_ids = pathway.get("ancestor_pathway_ids", [])
            row.reactome_url = pathway["reactome_url"]
            row.updated_at = datetime.now(timezone.utc)

        meta = session.get(models.PathwayMetadata, pathway_id)
        if meta is None:
            session.add(
                models.PathwayMetadata(
                    pathway_id=pathway_id,
                    pathway_name=pathway["pathway_name"],
                    depth=pathway["depth"],
                    pathway_size=max(int(pathway["pathway_size"]), 1),
                    ancestor_pathway_ids=pathway.get("ancestor_pathway_ids", []),
                    reactome_url=pathway["reactome_url"],
                    source_name="reactome",
                )
            )
        else:
            meta.pathway_name = pathway["pathway_name"]
            meta.depth = pathway["depth"]
            meta.pathway_size = max(int(pathway["pathway_size"]), 1)
            meta.ancestor_pathway_ids = pathway.get("ancestor_pathway_ids", [])
            meta.reactome_url = pathway["reactome_url"]
            meta.updated_at = datetime.now(timezone.utc)

    for row in existing_rows:
        if row.pathway_id not in touched_pathway_ids:
            session.delete(row)

    session.commit()
    return upserted


def get_pathways_for_uniprot(session: Session, uniprot_id: str) -> list[dict]:
    query = select(models.TargetPathwayMap).where(models.TargetPathwayMap.uniprot_id == uniprot_id)
    rows = session.execute(query).scalars().all()
    return [
        {
            "pathway_id": row.pathway_id,
            "pathway_name": row.pathway_name,
            "depth": row.depth,
            "pathway_size": row.pathway_size,
            "ancestor_pathway_ids": row.ancestor_pathway_ids or [],
            "reactome_url": row.reactome_url,
        }
        for row in rows
    ]


def get_recent_uniprot_targets(session: Session, max_items: int = 5000) -> list[str]:
    since = datetime.now(timezone.utc) - timedelta(days=30)
    query = (
        select(models.AnalysisPayload.payload)
        .join(models.AnalysisRun, models.AnalysisRun.id == models.AnalysisPayload.analysis_id)
        .where(models.AnalysisRun.created_at >= since)
        .order_by(models.AnalysisRun.created_at.desc())
        .limit(max_items)
    )
    payloads = session.execute(query).scalars().all()
    target_ids: set[str] = set()
    for payload in payloads:
        for target in payload.get("targets", []):
            uniprot_id = target.get("uniprot_id")
            if uniprot_id:
                target_ids.add(str(uniprot_id))
    return sorted(target_ids)


def list_mapped_uniprot_targets(session: Session, max_items: int = 20000) -> list[str]:
    query = select(models.TargetPathwayMap.uniprot_id).distinct().limit(max_items)
    rows = session.execute(query).scalars().all()
    return sorted({row for row in rows if row})


def purge_old_api_logs(session: Session, retention_days: int = 90) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    query = select(models.ApiEventLog).where(models.ApiEventLog.timestamp < cutoff)
    rows = session.execute(query).scalars().all()
    deleted = len(rows)
    for row in rows:
        session.delete(row)
    session.commit()
    return deleted

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


def create_job_run(
    session: Session,
    *,
    job_type: str,
    request_payload: dict,
    version_snapshot: dict,
) -> models.JobRun:
    job = models.JobRun(
        id=str(uuid4()),
        job_type=job_type,
        status="queued",
        progress=0.0,
        request_payload=request_payload,
        version_snapshot=version_snapshot,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def get_job_run(session: Session, job_id: str) -> models.JobRun | None:
    return session.get(models.JobRun, job_id)


def start_job_run(session: Session, job_id: str) -> models.JobRun | None:
    job = session.get(models.JobRun, job_id)
    if job is None:
        return None
    job.status = "running"
    job.progress = max(job.progress, 0.01)
    job.started_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(job)
    return job


def update_job_progress(session: Session, job_id: str, progress: float) -> models.JobRun | None:
    job = session.get(models.JobRun, job_id)
    if job is None:
        return None
    job.progress = min(max(progress, 0.0), 1.0)
    session.commit()
    session.refresh(job)
    return job


def finish_job_run(
    session: Session,
    job_id: str,
    *,
    status: str,
    result_payload: dict | None = None,
    error: str | None = None,
    progress: float = 1.0,
) -> models.JobRun | None:
    job = session.get(models.JobRun, job_id)
    if job is None:
        return None
    job.status = status
    job.progress = min(max(progress, 0.0), 1.0)
    job.result_payload = result_payload
    job.error = error
    job.finished_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(job)
    return job


def create_compound_analysis(
    session: Session,
    *,
    smiles: str,
    canonical_smiles: str,
    inchikey: str | None,
    prediction_method: str,
) -> models.CompoundAnalysis:
    record = models.CompoundAnalysis(
        id=str(uuid4()),
        smiles=smiles,
        canonical_smiles=canonical_smiles,
        inchikey=inchikey,
        prediction_method=prediction_method,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def add_predicted_targets(session: Session, compound_analysis_id: str, targets: list[dict]) -> int:
    inserted = 0
    for target in targets:
        session.add(
            models.PredictedTarget(
                id=str(uuid4()),
                compound_analysis_id=compound_analysis_id,
                target_chembl_id=str(target.get("target_chembl_id")),
                confidence=float(target.get("confidence", 0.0)),
                tier=str(target.get("tier", "low")),
                evidence=target.get("evidence", {}),
                predicted_pchembl_min=target.get("predicted_pchembl_min"),
                predicted_pchembl_max=target.get("predicted_pchembl_max"),
            )
        )
        inserted += 1
    session.commit()
    return inserted


def create_deg_upload(
    session: Session,
    *,
    filename: str,
    id_type: str,
    gene_count: int,
    sig_gene_count: int,
    mapping_summary: dict,
) -> models.DegUpload:
    upload = models.DegUpload(
        id=str(uuid4()),
        filename=filename,
        id_type=id_type,
        gene_count=gene_count,
        sig_gene_count=sig_gene_count,
        mapping_summary=mapping_summary,
    )
    session.add(upload)
    session.commit()
    session.refresh(upload)
    return upload


def add_deg_genes(session: Session, upload_id: str, rows: list[dict]) -> int:
    inserted = 0
    for row in rows:
        session.add(
            models.DegGene(
                id=str(uuid4()),
                upload_id=upload_id,
                input_gene=str(row.get("input_gene", "")),
                canonical_gene_symbol=row.get("canonical_gene_symbol"),
                uniprot_id=row.get("uniprot_id"),
                mapping_status=str(row.get("mapping_status", "unknown")),
                log2fc=float(row.get("log2fc", 0.0)),
                padj=row.get("padj"),
                base_mean=row.get("base_mean"),
            )
        )
        inserted += 1
    session.commit()
    return inserted


def get_deg_upload(session: Session, upload_id: str) -> models.DegUpload | None:
    return session.get(models.DegUpload, upload_id)


def list_deg_genes(session: Session, upload_id: str) -> list[models.DegGene]:
    query = select(models.DegGene).where(models.DegGene.upload_id == upload_id)
    return session.execute(query).scalars().all()


def create_enrichment_run(
    session: Session,
    *,
    upload_id: str,
    method: str,
    version_snapshot: dict,
) -> models.EnrichmentRun:
    run = models.EnrichmentRun(id=str(uuid4()), upload_id=upload_id, method=method, version_snapshot=version_snapshot)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def add_enrichment_rows(session: Session, run_id: str, rows: list[dict]) -> int:
    inserted = 0
    for row in rows:
        session.add(
            models.EnrichmentRow(
                id=str(uuid4()),
                run_id=run_id,
                pathway_id=str(row.get("pathway_id")),
                pathway_name=str(row.get("pathway_name")),
                p_value=row.get("p_value"),
                fdr=row.get("fdr"),
                enrichment_score=row.get("enrichment_score"),
                overlap_count=int(row.get("overlap_count", 0)),
                genes_in_pathway=int(row.get("genes_in_pathway", 0)),
                overlap_genes=row.get("overlap_genes", []),
                direction=str(row.get("direction", "mixed")),
                leading_edge_genes=row.get("leading_edge_genes", []),
            )
        )
        inserted += 1
    session.commit()
    return inserted


def get_enrichment_run(session: Session, run_id: str) -> models.EnrichmentRun | None:
    return session.get(models.EnrichmentRun, run_id)


def list_enrichment_rows(session: Session, run_id: str) -> list[models.EnrichmentRow]:
    query = select(models.EnrichmentRow).where(models.EnrichmentRow.run_id == run_id)
    return session.execute(query).scalars().all()


def create_tf_activity_run(
    session: Session,
    *,
    upload_id: str,
    method: str,
    version_snapshot: dict,
) -> models.TfActivityRun:
    run = models.TfActivityRun(id=str(uuid4()), upload_id=upload_id, method=method, version_snapshot=version_snapshot)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def add_tf_activity_rows(session: Session, run_id: str, rows: list[dict]) -> int:
    inserted = 0
    for row in rows:
        session.add(
            models.TfActivityRow(
                id=str(uuid4()),
                run_id=run_id,
                tf_name=str(row.get("tf_name")),
                activity_score=float(row.get("activity_score", 0.0)),
                p_value=row.get("p_value"),
                direction=str(row.get("direction", "unknown")),
                n_targets=int(row.get("n_targets", 0)),
                concordant_targets=int(row.get("concordant_targets", 0)),
                top_target_genes=row.get("top_target_genes", []),
            )
        )
        inserted += 1
    session.commit()
    return inserted


def get_tf_activity_run(session: Session, run_id: str) -> models.TfActivityRun | None:
    return session.get(models.TfActivityRun, run_id)


def list_tf_activity_rows(session: Session, run_id: str) -> list[models.TfActivityRow]:
    query = select(models.TfActivityRow).where(models.TfActivityRow.run_id == run_id)
    return session.execute(query).scalars().all()


def upsert_gene_identifier_map(
    session: Session,
    *,
    gene_symbol: str,
    ensembl_id: str | None,
    uniprot_id: str | None,
    aliases: list[str],
) -> None:
    key = gene_symbol.strip().upper()
    if not key:
        return
    existing = session.get(models.GeneIdentifierMap, key)
    if existing is None:
        session.add(
            models.GeneIdentifierMap(
                gene_symbol=key,
                ensembl_id=ensembl_id,
                uniprot_id=uniprot_id,
                aliases=sorted(set(alias.strip().upper() for alias in aliases if alias.strip())),
            )
        )
    else:
        existing.ensembl_id = ensembl_id
        existing.uniprot_id = uniprot_id
        existing.aliases = sorted(set(alias.strip().upper() for alias in aliases if alias.strip()))
        existing.updated_at = datetime.now(timezone.utc)
    session.commit()


def get_gene_identifier(session: Session, gene_symbol: str) -> models.GeneIdentifierMap | None:
    key = gene_symbol.strip().upper()
    if not key:
        return None
    query = select(models.GeneIdentifierMap).where(models.GeneIdentifierMap.gene_symbol == key)
    direct = session.execute(query).scalar_one_or_none()
    if direct is not None:
        return direct
    alias_query = select(models.GeneIdentifierMap)
    for row in session.execute(alias_query).scalars():
        aliases = {item.strip().upper() for item in (row.aliases or [])}
        if key in aliases:
            return row
    return None


def upsert_tissue_expression_rows(session: Session, rows: list[dict]) -> int:
    upserted = 0
    for row in rows:
        gene_symbol = str(row.get("gene_symbol", "")).strip().upper()
        tissue = str(row.get("tissue", "")).strip()
        if not gene_symbol or not tissue:
            continue
        query = select(models.TissueExpression).where(
            models.TissueExpression.gene_symbol == gene_symbol,
            models.TissueExpression.tissue == tissue,
        )
        existing = session.execute(query).scalar_one_or_none()
        payload = {
            "uniprot_id": row.get("uniprot_id"),
            "gtex_tpm": row.get("gtex_tpm"),
            "hpa_rna_nx": row.get("hpa_rna_nx"),
            "hpa_protein_level": row.get("hpa_protein_level"),
            "gtex_present": bool(row.get("gtex_present", False)),
            "hpa_present": bool(row.get("hpa_present", False)),
        }
        if existing is None:
            session.add(
                models.TissueExpression(
                    gene_symbol=gene_symbol,
                    tissue=tissue,
                    **payload,
                )
            )
            upserted += 1
        else:
            existing.uniprot_id = payload["uniprot_id"]
            existing.gtex_tpm = payload["gtex_tpm"]
            existing.hpa_rna_nx = payload["hpa_rna_nx"]
            existing.hpa_protein_level = payload["hpa_protein_level"]
            existing.gtex_present = payload["gtex_present"]
            existing.hpa_present = payload["hpa_present"]
            existing.updated_at = datetime.now(timezone.utc)
    session.commit()
    return upserted


def get_tissue_expression_for_gene(session: Session, gene_symbol: str) -> list[models.TissueExpression]:
    key = gene_symbol.strip().upper()
    query = (
        select(models.TissueExpression)
        .where(models.TissueExpression.gene_symbol == key)
        .order_by(models.TissueExpression.tissue.asc())
    )
    return session.execute(query).scalars().all()


def get_tissue_expression_for_genes(session: Session, gene_symbols: list[str]) -> list[models.TissueExpression]:
    keys = sorted({symbol.strip().upper() for symbol in gene_symbols if symbol.strip()})
    if not keys:
        return []
    query = select(models.TissueExpression).where(models.TissueExpression.gene_symbol.in_(keys))
    return session.execute(query).scalars().all()


def upsert_toxicity_pathway_gene_sets(session: Session, rows: list[dict]) -> int:
    upserted = 0
    for row in rows:
        pathway_key = str(row.get("pathway_key", "")).strip()
        if not pathway_key:
            continue
        existing = session.get(models.ToxicityPathwayGeneSet, pathway_key)
        genes = sorted({item.strip().upper() for item in (row.get("genes") or []) if str(item).strip()})
        if existing is None:
            session.add(
                models.ToxicityPathwayGeneSet(
                    pathway_key=pathway_key,
                    label=str(row.get("label") or pathway_key),
                    reactome_pathway_id=row.get("reactome_pathway_id"),
                    risk_type=str(row.get("risk_type") or "general"),
                    genes=genes,
                )
            )
            upserted += 1
        else:
            existing.label = str(row.get("label") or pathway_key)
            existing.reactome_pathway_id = row.get("reactome_pathway_id")
            existing.risk_type = str(row.get("risk_type") or "general")
            existing.genes = genes
            existing.updated_at = datetime.now(timezone.utc)
    session.commit()
    return upserted


def list_toxicity_pathway_gene_sets(session: Session) -> list[models.ToxicityPathwayGeneSet]:
    query = select(models.ToxicityPathwayGeneSet).order_by(models.ToxicityPathwayGeneSet.pathway_key.asc())
    return session.execute(query).scalars().all()


def upsert_dili_rank_entries(session: Session, rows: list[dict]) -> int:
    upserted = 0
    for row in rows:
        norm = str(row.get("drug_name_norm", "")).strip().lower()
        if not norm:
            continue
        query = select(models.DiliRankEntry).where(models.DiliRankEntry.drug_name_norm == norm)
        existing = session.execute(query).scalar_one_or_none()
        if existing is None:
            session.add(
                models.DiliRankEntry(
                    id=str(uuid4()),
                    drug_name_norm=norm,
                    drug_name_original=str(row.get("drug_name_original") or norm),
                    dili_category=str(row.get("dili_category") or "Ambiguous"),
                    source_url=row.get("source_url"),
                )
            )
            upserted += 1
        else:
            existing.drug_name_original = str(row.get("drug_name_original") or existing.drug_name_original)
            existing.dili_category = str(row.get("dili_category") or existing.dili_category)
            existing.source_url = row.get("source_url") or existing.source_url
            existing.updated_at = datetime.now(timezone.utc)
    session.commit()
    return upserted


def get_dili_rank_entry(session: Session, drug_name: str) -> models.DiliRankEntry | None:
    norm = drug_name.strip().lower()
    if not norm:
        return None
    query = select(models.DiliRankEntry).where(models.DiliRankEntry.drug_name_norm == norm)
    return session.execute(query).scalar_one_or_none()


def upsert_aop_chains(session: Session, rows: list[dict]) -> int:
    upserted = 0
    for row in rows:
        aop_id = str(row.get("aop_id", "")).strip()
        if not aop_id:
            continue
        existing = session.get(models.AopChain, aop_id)
        key_events = [str(item).strip() for item in (row.get("key_events") or []) if str(item).strip()]
        matched_genes = sorted({str(item).strip().upper() for item in (row.get("matched_genes") or []) if str(item).strip()})
        if existing is None:
            session.add(
                models.AopChain(
                    aop_id=aop_id,
                    mie=str(row.get("mie") or ""),
                    adverse_outcome=str(row.get("adverse_outcome") or ""),
                    key_events=key_events,
                    matched_genes=matched_genes,
                    source_url=row.get("source_url"),
                )
            )
            upserted += 1
        else:
            existing.mie = str(row.get("mie") or existing.mie)
            existing.adverse_outcome = str(row.get("adverse_outcome") or existing.adverse_outcome)
            existing.key_events = key_events
            existing.matched_genes = matched_genes
            existing.source_url = row.get("source_url") or existing.source_url
            existing.updated_at = datetime.now(timezone.utc)
    session.commit()
    return upserted


def list_aop_chains(session: Session) -> list[models.AopChain]:
    query = select(models.AopChain).order_by(models.AopChain.aop_id.asc())
    return session.execute(query).scalars().all()


def upsert_dataset_cache_meta(
    session: Session,
    *,
    dataset_key: str,
    local_path: str,
    checksum: str | None,
    version: str | None,
) -> None:
    existing = session.get(models.DatasetCacheMeta, dataset_key)
    if existing is None:
        session.add(
            models.DatasetCacheMeta(
                dataset_key=dataset_key,
                local_path=local_path,
                checksum=checksum,
                version=version,
            )
        )
    else:
        existing.local_path = local_path
        existing.checksum = checksum
        existing.version = version
        existing.fetched_at = datetime.now(timezone.utc)
    session.commit()


def get_dataset_cache_meta(session: Session, dataset_key: str) -> models.DatasetCacheMeta | None:
    return session.get(models.DatasetCacheMeta, dataset_key)


def list_dataset_cache_meta(session: Session, dataset_prefix: str | None = None) -> list[models.DatasetCacheMeta]:
    query = select(models.DatasetCacheMeta)
    if dataset_prefix:
        query = query.where(models.DatasetCacheMeta.dataset_key.like(f"{dataset_prefix}%"))
    return session.execute(query).scalars().all()


def get_uniprot_ids_for_pathway(session: Session, pathway_id: str, max_items: int = 5000) -> list[str]:
    query = (
        select(models.TargetPathwayMap.uniprot_id)
        .where(models.TargetPathwayMap.pathway_id == pathway_id)
        .limit(max_items)
    )
    rows = session.execute(query).scalars().all()
    return sorted({str(row) for row in rows if row})


def get_pathway_metadata(session: Session, pathway_id: str) -> models.PathwayMetadata | None:
    return session.get(models.PathwayMetadata, pathway_id)


def get_gene_identifier_by_uniprot(session: Session, uniprot_id: str) -> models.GeneIdentifierMap | None:
    query = select(models.GeneIdentifierMap).where(models.GeneIdentifierMap.uniprot_id == uniprot_id)
    return session.execute(query).scalar_one_or_none()


def create_patient_profile(
    session: Session,
    *,
    label: str,
    notes: str | None = None,
    save_derived_default: bool = False,
) -> models.PatientProfile:
    profile = models.PatientProfile(
        id=str(uuid4()),
        label=label,
        status="active",
        notes=notes,
        save_derived_default=save_derived_default,
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def get_patient_profile(session: Session, patient_id: str) -> models.PatientProfile | None:
    return session.get(models.PatientProfile, patient_id)


def hard_delete_patient_profile(session: Session, patient_id: str) -> bool:
    profile = session.get(models.PatientProfile, patient_id)
    if profile is None:
        return False
    session.delete(profile)
    session.commit()
    return True


def add_patient_pgx_gene_calls(session: Session, patient_id: str, rows: list[dict]) -> int:
    query = select(models.PatientPgxGeneCall).where(models.PatientPgxGeneCall.patient_id == patient_id)
    existing = session.execute(query).scalars().all()
    for row in existing:
        session.delete(row)
    inserted = 0
    for row in rows:
        session.add(
            models.PatientPgxGeneCall(
                id=str(uuid4()),
                patient_id=patient_id,
                gene=str(row.get("gene", "")).upper(),
                diplotype=row.get("diplotype"),
                phenotype=row.get("phenotype"),
                activity_score=row.get("activity_score"),
                state=str(row.get("state", "unknown")),
                reason_code=str(row.get("reason_code", "gene_not_called")),
                provenance=row.get("provenance", {}),
                confidence_note=row.get("confidence_note"),
            )
        )
        inserted += 1
    session.commit()
    return inserted


def add_patient_pgx_drug_recommendations(session: Session, patient_id: str, rows: list[dict]) -> int:
    query = select(models.PatientPgxDrugRecommendation).where(models.PatientPgxDrugRecommendation.patient_id == patient_id)
    existing = session.execute(query).scalars().all()
    for row in existing:
        session.delete(row)
    inserted = 0
    for row in rows:
        session.add(
            models.PatientPgxDrugRecommendation(
                id=str(uuid4()),
                patient_id=patient_id,
                drug_id=row.get("drug_id"),
                drug_name=str(row.get("drug_name", "")),
                recommendation=str(row.get("recommendation", "insufficient_data")),
                evidence_level=row.get("evidence_level"),
                cpic_guideline_id=row.get("cpic_guideline_id"),
                state=str(row.get("state", "unknown")),
                reason_code=str(row.get("reason_code", "guideline_not_found")),
                provenance=row.get("provenance", {}),
                confidence_note=row.get("confidence_note"),
            )
        )
        inserted += 1
    session.commit()
    return inserted


def list_patient_pgx_gene_calls(session: Session, patient_id: str) -> list[models.PatientPgxGeneCall]:
    query = (
        select(models.PatientPgxGeneCall)
        .where(models.PatientPgxGeneCall.patient_id == patient_id)
        .order_by(models.PatientPgxGeneCall.gene.asc())
    )
    return session.execute(query).scalars().all()


def list_patient_pgx_drug_recommendations(session: Session, patient_id: str) -> list[models.PatientPgxDrugRecommendation]:
    query = (
        select(models.PatientPgxDrugRecommendation)
        .where(models.PatientPgxDrugRecommendation.patient_id == patient_id)
        .order_by(models.PatientPgxDrugRecommendation.drug_name.asc())
    )
    return session.execute(query).scalars().all()


def get_patient_pgx_drug_recommendation(
    session: Session,
    *,
    patient_id: str,
    drug_id: str,
) -> models.PatientPgxDrugRecommendation | None:
    query = select(models.PatientPgxDrugRecommendation).where(
        models.PatientPgxDrugRecommendation.patient_id == patient_id,
        (models.PatientPgxDrugRecommendation.drug_id == drug_id)
        | (func.lower(models.PatientPgxDrugRecommendation.drug_name) == drug_id.lower()),
    )
    return session.execute(query).scalar_one_or_none()


def create_patient_expression_run(
    session: Session,
    *,
    patient_id: str,
    filename: str,
    id_type: str,
    gene_count: int,
    mapped_gene_count: int,
    state: str,
    reason_code: str,
    version_snapshot: dict,
) -> models.PatientExpressionRun:
    run = models.PatientExpressionRun(
        id=str(uuid4()),
        patient_id=patient_id,
        filename=filename,
        id_type=id_type,
        gene_count=gene_count,
        mapped_gene_count=mapped_gene_count,
        state=state,
        reason_code=reason_code,
        version_snapshot=version_snapshot,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def add_patient_pathway_activity_rows(session: Session, patient_id: str, run_id: str, rows: list[dict]) -> int:
    query = select(models.PatientPathwayActivity).where(models.PatientPathwayActivity.run_id == run_id)
    existing = session.execute(query).scalars().all()
    for row in existing:
        session.delete(row)
    inserted = 0
    for row in rows:
        session.add(
            models.PatientPathwayActivity(
                id=str(uuid4()),
                patient_id=patient_id,
                run_id=run_id,
                pathway_id=str(row.get("pathway_id", "")),
                pathway_name=str(row.get("pathway_name", "")),
                activity_score=row.get("activity_score"),
                p_value=row.get("p_value"),
                percentile=row.get("percentile"),
                method=str(row.get("method", "gsea_prerank")),
                state=str(row.get("state", "unknown")),
                reason_code=str(row.get("reason_code", "dataset_not_loaded")),
                provenance=row.get("provenance", {}),
            )
        )
        inserted += 1
    session.commit()
    return inserted


def list_patient_pathway_activity(session: Session, patient_id: str) -> list[models.PatientPathwayActivity]:
    query = (
        select(models.PatientPathwayActivity)
        .where(models.PatientPathwayActivity.patient_id == patient_id)
        .order_by(func.coalesce(models.PatientPathwayActivity.activity_score, -1e9).desc())
    )
    return session.execute(query).scalars().all()


def upsert_patient_drug_response(
    session: Session,
    *,
    patient_id: str,
    drug_id: str,
    drug_name: str,
    recommendation: str,
    state: str,
    reason_code: str,
    confidence_level: str,
    component_scores: dict,
    version_snapshot: dict,
) -> models.PatientDrugResponse:
    query = select(models.PatientDrugResponse).where(
        models.PatientDrugResponse.patient_id == patient_id,
        models.PatientDrugResponse.drug_id == drug_id,
    )
    existing = session.execute(query).scalar_one_or_none()
    if existing is None:
        existing = models.PatientDrugResponse(
            id=str(uuid4()),
            patient_id=patient_id,
            drug_id=drug_id,
            drug_name=drug_name,
            recommendation=recommendation,
            state=state,
            reason_code=reason_code,
            confidence_level=confidence_level,
            component_scores=component_scores,
            version_snapshot=version_snapshot,
        )
        session.add(existing)
    else:
        existing.drug_name = drug_name
        existing.recommendation = recommendation
        existing.state = state
        existing.reason_code = reason_code
        existing.confidence_level = confidence_level
        existing.component_scores = component_scores
        existing.version_snapshot = version_snapshot
        existing.created_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(existing)
    return existing


def get_patient_drug_response(session: Session, patient_id: str, drug_id: str) -> models.PatientDrugResponse | None:
    query = select(models.PatientDrugResponse).where(
        models.PatientDrugResponse.patient_id == patient_id,
        models.PatientDrugResponse.drug_id == drug_id,
    )
    return session.execute(query).scalar_one_or_none()


def delete_deg_upload(session: Session, upload_id: str) -> bool:
    upload = session.get(models.DegUpload, upload_id)
    if upload is None:
        return False
    session.delete(upload)
    session.commit()
    return True


def get_drug_pathway_ids(session: Session, drug_id: str) -> set[str]:
    """Return pathway IDs associated with a drug via target-pathway mapping.

    Looks up prior analysis runs for the drug, extracts target uniprot IDs,
    then queries TargetPathwayMap for associated pathway IDs.
    """
    run_query = (
        select(models.AnalysisRun)
        .where(models.AnalysisRun.canonical_drug_id == drug_id)
        .order_by(models.AnalysisRun.created_at.desc())
        .limit(1)
    )
    run = session.execute(run_query).scalar_one_or_none()
    if run is None:
        return set()
    payload_row = session.execute(
        select(models.AnalysisPayload).where(models.AnalysisPayload.analysis_id == run.id)
    ).scalar_one_or_none()
    if payload_row is None or not payload_row.payload:
        return set()
    payload = payload_row.payload
    pathway_ids: set[str] = set()
    for pathway in payload.get("pathways", []):
        pid = pathway.get("pathway_id")
        if pid:
            pathway_ids.add(str(pid))
    return pathway_ids

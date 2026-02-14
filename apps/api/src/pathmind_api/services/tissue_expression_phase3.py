from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from pathmind_api.clients.gtex import GTExClient
from pathmind_api.clients.hpa import HPAClient
from pathmind_api.etl.phase3_ingest import _merge_expression_rows
from pathmind_api.repositories import (
    get_dataset_cache_meta,
    get_gene_identifier,
    get_gene_identifier_by_uniprot,
    get_pathway_metadata,
    get_tissue_expression_for_gene,
    get_uniprot_ids_for_pathway,
    latest_source_release_versions,
    upsert_gene_identifier_map,
    upsert_tissue_expression_rows,
)
from pathmind_api.schemas_phase3 import (
    EvidenceRecord,
    PathwayExpressionGeneRow,
    PathwayExpressionResponse,
    Phase3DatasetStatusItem,
    Phase3DatasetStatusResponse,
    TissueExpressionPoint,
    TissueExpressionResponse,
)

log = logging.getLogger(__name__)


def _signal_for_measurement(*, gtex_tpm: float | None, hpa_protein_level: str | None, gtex_present: bool, hpa_present: bool) -> EvidenceRecord:
    if gtex_present or hpa_present:
        expression_positive = (gtex_tpm is not None and gtex_tpm >= 1.0) or (hpa_protein_level in {"Medium", "High"})
        if expression_positive:
            return EvidenceRecord(
                state="positive",
                reason_code="measured_expression_present",
                provenance={"gtex_tpm": gtex_tpm, "hpa_protein_level": hpa_protein_level},
            )
        return EvidenceRecord(
            state="negative",
            reason_code="measured_expression_low",
            provenance={"gtex_tpm": gtex_tpm, "hpa_protein_level": hpa_protein_level},
        )
    return EvidenceRecord(
        state="unknown",
        reason_code="measurement_missing",
        provenance={"gtex_present": gtex_present, "hpa_present": hpa_present},
    )


class Phase3DatasetService:
    def __init__(self, required_datasets: list[str]) -> None:
        self.required_datasets = [item.strip() for item in required_datasets if item.strip()]

    def status(self, session: Session) -> Phase3DatasetStatusResponse:
        now = datetime.now(timezone.utc)
        version_map = latest_source_release_versions(session)
        rows: list[Phase3DatasetStatusItem] = []
        stale_cutoff = now - timedelta(days=400)

        for dataset in self.required_datasets:
            meta = get_dataset_cache_meta(session, dataset)
            if meta is None:
                rows.append(
                    Phase3DatasetStatusItem(
                        dataset=dataset,
                        status="missing",
                        reason="dataset_not_loaded",
                        version=version_map.get(dataset),
                        fetched_at=None,
                    )
                )
                continue

            fetched_at = meta.fetched_at
            if fetched_at and fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            if fetched_at is not None and fetched_at < stale_cutoff:
                rows.append(
                    Phase3DatasetStatusItem(
                        dataset=dataset,
                        status="stale",
                        reason="dataset_stale",
                        version=meta.version or version_map.get(dataset),
                        fetched_at=fetched_at,
                    )
                )
            else:
                rows.append(
                    Phase3DatasetStatusItem(
                        dataset=dataset,
                        status="ready",
                        reason=None,
                        version=meta.version or version_map.get(dataset),
                        fetched_at=fetched_at,
                    )
                )

        if rows and all(item.status == "ready" for item in rows):
            overall = "ready"
        elif any(item.status in {"ready", "stale"} for item in rows):
            overall = "degraded"
        elif rows:
            overall = "missing"
        else:
            overall = "unknown"

        return Phase3DatasetStatusResponse(
            overall_status=overall,
            datasets=rows,
            version_snapshot={item.dataset: (item.version or "unknown") for item in rows},
        )


class TissueExpressionServicePhase3:
    def __init__(
        self,
        top_tissues: list[str] | None = None,
        *,
        gtex_client: GTExClient | None = None,
        hpa_client: HPAClient | None = None,
        cache_ttl_hours: int = 168,
    ) -> None:
        self.top_tissues = [item.strip() for item in (top_tissues or []) if item.strip()]
        self.gtex_client = gtex_client
        self.hpa_client = hpa_client
        self.cache_ttl = timedelta(hours=cache_ttl_hours)

    async def _ensure_gene_cached(self, session: Session, gene_symbol: str) -> None:
        """Fetch tissue data from GTEx + HPA APIs if not already in the DB (or stale)."""
        gene_key = gene_symbol.strip().upper()
        if not gene_key:
            return

        # Check existing DB rows
        existing = get_tissue_expression_for_gene(session, gene_key)
        if existing:
            # Check freshness via updated_at of the first row
            newest = max((row.updated_at for row in existing), default=None)
            if newest is not None:
                if newest.tzinfo is None:
                    newest = newest.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - newest < self.cache_ttl:
                    return  # cache hit — data is fresh

        # Fetch from APIs
        all_rows: list[dict] = []
        if self.gtex_client is not None:
            try:
                gtex_rows = await self.gtex_client.fetch_median_expression(gene_key)
                all_rows.extend(gtex_rows)
            except Exception:
                log.warning("GTEx API fetch failed for %s — proceeding without GTEx", gene_key, exc_info=True)

        if self.hpa_client is not None:
            try:
                hpa_rows = await self.hpa_client.fetch_tissue_expression(gene_key)
                all_rows.extend(hpa_rows)
            except Exception:
                log.warning("HPA API fetch failed for %s — proceeding without HPA", gene_key, exc_info=True)

        if not all_rows:
            return  # nothing to cache

        merged = _merge_expression_rows(all_rows)
        upsert_tissue_expression_rows(session, merged)

        # Also register gene in identifier map
        for row in merged:
            upsert_gene_identifier_map(
                session,
                gene_symbol=row["gene_symbol"],
                ensembl_id=None,
                uniprot_id=row.get("uniprot_id"),
                aliases=[],
            )

        log.debug("Cached %d tissue rows for %s from API", len(merged), gene_key)

    async def by_gene(self, session: Session, gene: str) -> TissueExpressionResponse:
        gene_key = gene.strip().upper()
        mapping = get_gene_identifier(session, gene_key)
        canonical_gene = mapping.gene_symbol if mapping is not None else gene_key

        # Ensure API data is cached before reading from DB
        await self._ensure_gene_cached(session, canonical_gene)

        rows = get_tissue_expression_for_gene(session, canonical_gene)
        version_map = latest_source_release_versions(session)

        if not rows:
            return TissueExpressionResponse(
                gene_symbol=canonical_gene,
                expression=[
                    TissueExpressionPoint(
                        tissue="unknown",
                        evidence=EvidenceRecord(
                            state="unknown",
                            reason_code="dataset_not_loaded_or_gene_missing",
                            provenance={"gene_symbol": canonical_gene},
                        ),
                    )
                ],
                version_snapshot={
                    "gtex": version_map.get("gtex", "unknown"),
                    "hpa": version_map.get("hpa", "unknown"),
                },
            )

        points = [
            TissueExpressionPoint(
                tissue=row.tissue,
                gtex_tpm=row.gtex_tpm,
                hpa_rna_nx=row.hpa_rna_nx,
                hpa_protein_level=row.hpa_protein_level,
                evidence=_signal_for_measurement(
                    gtex_tpm=row.gtex_tpm,
                    hpa_protein_level=row.hpa_protein_level,
                    gtex_present=row.gtex_present,
                    hpa_present=row.hpa_present,
                ),
            )
            for row in rows
        ]
        points.sort(key=lambda item: ((item.gtex_tpm or 0.0), (item.hpa_rna_nx or 0.0)), reverse=True)
        if self.top_tissues:
            rank = {name: index for index, name in enumerate(self.top_tissues)}
            points.sort(key=lambda item: rank.get(item.tissue, 10_000))
        return TissueExpressionResponse(
            gene_symbol=canonical_gene,
            expression=points,
            version_snapshot={
                "gtex": version_map.get("gtex", "unknown"),
                "hpa": version_map.get("hpa", "unknown"),
            },
        )

    async def for_pathway(self, session: Session, pathway_id: str) -> PathwayExpressionResponse:
        pathway = get_pathway_metadata(session, pathway_id)
        name = pathway.pathway_name if pathway is not None else pathway_id
        uniprot_ids = get_uniprot_ids_for_pathway(session, pathway_id, max_items=500)
        rows: list[PathwayExpressionGeneRow] = []

        for uniprot_id in uniprot_ids:
            mapping = get_gene_identifier_by_uniprot(session, uniprot_id)
            if mapping is None:
                rows.append(
                    PathwayExpressionGeneRow(
                        gene_symbol=uniprot_id,
                        uniprot_id=uniprot_id,
                        evidence=EvidenceRecord(
                            state="unknown",
                            reason_code="identifier_mapping_missing",
                            provenance={"uniprot_id": uniprot_id},
                        ),
                        tissues=[],
                    )
                )
                continue
            gene_response = await self.by_gene(session, mapping.gene_symbol)
            rows.append(
                PathwayExpressionGeneRow(
                    gene_symbol=mapping.gene_symbol,
                    uniprot_id=mapping.uniprot_id,
                    evidence=EvidenceRecord(
                        state="positive" if any(point.evidence.state == "positive" for point in gene_response.expression) else "unknown",
                        reason_code="pathway_gene_tissue_overlay",
                        provenance={"pathway_id": pathway_id},
                    ),
                    tissues=gene_response.expression[: min(len(gene_response.expression), 8)],
                )
            )

        version_map = latest_source_release_versions(session)
        return PathwayExpressionResponse(
            pathway_id=pathway_id,
            pathway_name=name,
            genes=rows,
            version_snapshot={
                "gtex": version_map.get("gtex", "unknown"),
                "hpa": version_map.get("hpa", "unknown"),
                "reactome": version_map.get("reactome", "unknown"),
            },
        )

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from statistics import median

from sqlalchemy.orm import Session

from pathmind_api.clients import ChEMBLClient
from pathmind_api.clients.gtex import GTExClient
from pathmind_api.clients.hpa import HPAClient
from pathmind_api.etl.phase3_ingest import _merge_expression_rows
from pathmind_api.repositories import (
    get_tissue_expression_for_gene,
    get_tissue_expression_for_genes,
    latest_source_release_versions,
    upsert_gene_identifier_map,
    upsert_tissue_expression_rows,
)
from pathmind_api.schemas_phase3 import EvidenceRecord, TissueImpactCell, TissueImpactResponse

log = logging.getLogger(__name__)

_DEFAULT_TISSUE_EXPOSURE = {
    "Liver": 15.0,
    "Heart": 3.0,
    "Brain": 0.2,
    "Kidney": 5.0,
    "Lung": 2.0,
    "Intestine": 4.0,
    "Blood": 1.0,
    "Adipose Tissue": 2.5,
}


class TissueImpactServicePhase3:
    def __init__(
        self,
        chembl: ChEMBLClient,
        top_tissues: list[str],
        *,
        gtex_client: GTExClient | None = None,
        hpa_client: HPAClient | None = None,
        cache_ttl_hours: int = 168,
    ) -> None:
        self.chembl = chembl
        self.top_tissues = top_tissues or list(_DEFAULT_TISSUE_EXPOSURE.keys())
        self.gtex_client = gtex_client
        self.hpa_client = hpa_client
        self.cache_ttl = timedelta(hours=cache_ttl_hours)

    async def _ensure_gene_cached(self, session: Session, gene_symbol: str) -> None:
        """Fetch tissue data from GTEx + HPA APIs if missing/stale in DB."""
        gene_key = gene_symbol.strip().upper()
        if not gene_key:
            return

        existing = get_tissue_expression_for_gene(session, gene_key)
        if existing:
            newest = max((row.updated_at for row in existing), default=None)
            if newest is not None:
                if newest.tzinfo is None:
                    newest = newest.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - newest < self.cache_ttl:
                    return

        all_rows: list[dict] = []
        if self.gtex_client is not None:
            try:
                all_rows.extend(await self.gtex_client.fetch_median_expression(gene_key))
            except Exception:
                log.warning("GTEx fetch failed for %s in tissue-impact", gene_key, exc_info=True)

        if self.hpa_client is not None:
            try:
                all_rows.extend(await self.hpa_client.fetch_tissue_expression(gene_key))
            except Exception:
                log.warning("HPA fetch failed for %s in tissue-impact", gene_key, exc_info=True)

        if not all_rows:
            return

        merged = _merge_expression_rows(all_rows)
        upsert_tissue_expression_rows(session, merged)
        for row in merged:
            upsert_gene_identifier_map(
                session,
                gene_symbol=row["gene_symbol"],
                ensembl_id=None,
                uniprot_id=row.get("uniprot_id"),
                aliases=[],
            )

    async def evaluate(self, session: Session, drug_id: str) -> TissueImpactResponse:
        activities = await self.chembl.fetch_activities(drug_id)
        target_values: dict[str, list[float]] = {}
        target_ids: set[str] = set()
        for activity in activities:
            target_id = activity.get("target_chembl_id")
            raw = activity.get("pchembl_value")
            if not target_id or raw in {None, ""}:
                continue
            try:
                value = float(raw)
            except Exception:
                continue
            target_values.setdefault(str(target_id), []).append(value)
            target_ids.add(str(target_id))

        details = await self.chembl.fetch_target_details(sorted(target_ids)) if target_ids else {}
        target_genes = sorted(
            {
                str((details.get(target_id) or {}).get("gene_symbol") or "").strip().upper()
                for target_id in target_ids
            }
        )
        target_genes = [item for item in target_genes if item]
        potency_values = [median(values) for values in target_values.values() if values]
        potency_factor = (median(potency_values) / 10.0) if potency_values else None

        # Pre-fetch tissue data for each target gene via API if needed
        for gene in target_genes:
            await self._ensure_gene_cached(session, gene)

        tissue_rows = get_tissue_expression_for_genes(session, target_genes)
        by_tissue: dict[str, list[float]] = {}
        for row in tissue_rows:
            if row.gtex_tpm is not None:
                by_tissue.setdefault(row.tissue, []).append(row.gtex_tpm)
            elif row.hpa_rna_nx is not None:
                by_tissue.setdefault(row.tissue, []).append(row.hpa_rna_nx)

        cells: list[TissueImpactCell] = []
        for tissue in self.top_tissues:
            expression_values = by_tissue.get(tissue, [])
            expression_score = (sum(expression_values) / len(expression_values)) if expression_values else None
            exposure_score = _DEFAULT_TISSUE_EXPOSURE.get(tissue, 1.0)
            if expression_score is None or potency_factor is None:
                cells.append(
                    TissueImpactCell(
                        tissue=tissue,
                        exposure_score=exposure_score,
                        expression_score=expression_score,
                        impact_score=None,
                        key_risk=None,
                        signal=EvidenceRecord(
                            state="unknown",
                            reason_code="insufficient_inputs",
                            provenance={"has_expression": expression_score is not None, "has_potency": potency_factor is not None},
                        ),
                    )
                )
                continue

            normalized_expression = min(expression_score / 100.0, 1.0)
            impact = exposure_score * normalized_expression * potency_factor
            if impact >= 2.0:
                state = "positive"
                reason = "high_relative_impact"
            else:
                state = "negative"
                reason = "low_relative_impact"
            key_risk = None
            if tissue == "Liver" and state == "positive":
                key_risk = "dili_risk"
            elif tissue == "Heart" and state == "positive":
                key_risk = "qt_risk"
            elif tissue == "Kidney" and state == "positive":
                key_risk = "renal_risk"
            cells.append(
                TissueImpactCell(
                    tissue=tissue,
                    exposure_score=round(exposure_score, 6),
                    expression_score=round(expression_score, 6),
                    impact_score=round(impact, 6),
                    key_risk=key_risk,
                    signal=EvidenceRecord(
                        state=state,  # type: ignore[arg-type]
                        reason_code=reason,
                        provenance={"target_gene_count": len(target_genes)},
                    ),
                )
            )

        versions = latest_source_release_versions(session)
        return TissueImpactResponse(
            drug_id=drug_id,
            cells=cells,
            version_snapshot={
                "gtex": versions.get("gtex", "unknown"),
                "hpa": versions.get("hpa", "unknown"),
                "chembl": versions.get("chembl", "unknown"),
            },
        )

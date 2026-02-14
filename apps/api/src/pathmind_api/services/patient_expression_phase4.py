from sqlalchemy.orm import Session

from pathmind_api.repositories import (
    add_patient_pathway_activity_rows,
    create_patient_expression_run,
    delete_deg_upload,
    latest_source_release_versions,
    list_patient_pathway_activity,
)
from pathmind_api.schemas_phase3 import EvidenceRecord
from pathmind_api.schemas_phase4 import PatientPathwayActivityResponse, PatientPathwayActivityRow
from pathmind_api.services.enrichment import EnrichmentService
from pathmind_api.services.expression_ingest import ExpressionIngestService


def _row_state(row: dict) -> tuple[str, str]:
    score = row.get("enrichment_score")
    p_value = row.get("p_value")
    fdr = row.get("fdr")
    if score is None:
        return ("unknown", "missing_enrichment_score")

    significant = False
    if fdr is not None and float(fdr) < 0.25:
        significant = True
    elif p_value is not None and float(p_value) < 0.05:
        significant = True

    if significant:
        if float(score) > 0:
            return ("positive", "significant_high_activity")
        else:
            return ("negative", "significant_suppressed_activity")
    return ("unknown", "not_significant")


class PatientExpressionServicePhase4:
    def __init__(self, *, ingest_service: ExpressionIngestService, enrichment_service: EnrichmentService) -> None:
        self.ingest_service = ingest_service
        self.enrichment_service = enrichment_service

    async def process_expression(
        self,
        session: Session,
        *,
        filename: str,
        content: bytes,
        version_snapshot: dict[str, str],
        keep_phase2_rows: bool,
    ) -> dict:
        upload = await self.ingest_service.ingest(session, filename=filename, content=content)
        enrichment = self.enrichment_service.run(
            session,
            upload_id=upload.upload_id,
            method="gsea_prerank",
            version_snapshot=version_snapshot,
        )

        pathways = []
        for row in enrichment.pathways[:20]:
            state, reason_code = _row_state(row)
            pathways.append(
                {
                    "pathway_id": row.get("pathway_id"),
                    "pathway_name": row.get("pathway_name"),
                    "activity_score": row.get("enrichment_score"),
                    "p_value": row.get("p_value"),
                    "fdr": row.get("fdr"),
                    "percentile": None,
                    "method": enrichment.method,
                    "state": state,
                    "reason_code": reason_code,
                    "provenance": {
                        "upload_id": upload.upload_id,
                        "overlap_count": row.get("overlap_count"),
                        "direction": row.get("direction"),
                    },
                }
            )

        if pathways:
            scores = [item["activity_score"] for item in pathways if item["activity_score"] is not None]
            if len(scores) >= 2:
                sorted_scores = sorted(scores)
                for item in pathways:
                    score = item.get("activity_score")
                    if score is None:
                        item["percentile"] = None
                    else:
                        rank = sum(1 for s in sorted_scores if s <= score)
                        item["percentile"] = round(100.0 * rank / len(sorted_scores), 1)
            elif len(scores) == 1:
                for item in pathways:
                    item["percentile"] = 50.0 if item.get("activity_score") is not None else None

        if not keep_phase2_rows:
            delete_deg_upload(session, upload.upload_id)

        return {
            "upload": upload,
            "enrichment": enrichment,
            "pathways": pathways,
        }

    def persist_patient_expression(
        self,
        session: Session,
        *,
        patient_id: str,
        filename: str,
        upload_summary: dict,
        pathways: list[dict],
        version_snapshot: dict[str, str],
    ) -> str:
        mapped_gene_count = int(upload_summary.get("mapping_summary", {}).get("mapped", 0))
        run = create_patient_expression_run(
            session,
            patient_id=patient_id,
            filename=filename,
            id_type=str(upload_summary.get("id_type", "unknown")),
            gene_count=int(upload_summary.get("gene_count", 0)),
            mapped_gene_count=mapped_gene_count,
            state="positive" if pathways else "unknown",
            reason_code="expression_processed" if pathways else "limited_data",
            version_snapshot=version_snapshot,
        )
        rows = pathways
        if not rows:
            rows = [
                {
                    "pathway_id": "unknown",
                    "pathway_name": "No pathway activity available",
                    "activity_score": None,
                    "p_value": None,
                    "percentile": None,
                    "method": "gsea_prerank",
                    "state": "unknown",
                    "reason_code": "limited_data",
                    "provenance": {},
                }
            ]
        add_patient_pathway_activity_rows(session, patient_id, run.id, rows)
        return run.id

    def get_patient_pathway_activity(self, session: Session, patient_id: str) -> PatientPathwayActivityResponse:
        rows = list_patient_pathway_activity(session, patient_id)
        versions = latest_source_release_versions(session)
        return PatientPathwayActivityResponse(
            patient_id=patient_id,
            pathways=[
                PatientPathwayActivityRow(
                    pathway_id=row.pathway_id,
                    pathway_name=row.pathway_name,
                    activity_score=row.activity_score,
                    p_value=row.p_value,
                    percentile=row.percentile,
                    method=row.method,
                    evidence=EvidenceRecord(
                        state=row.state,  # type: ignore[arg-type]
                        reason_code=row.reason_code,
                        provenance=row.provenance or {},
                    ),
                )
                for row in rows
            ],
            version_snapshot={
                "progeny": versions.get("progeny", "unknown"),
                "reactome": versions.get("reactome", "unknown"),
                "hgnc": versions.get("hgnc", "unknown"),
            },
        )

from statistics import mean

from sqlalchemy.orm import Session

from pathmind_api.repositories import (
    get_drug_pathway_ids,
    get_patient_drug_response,
    get_patient_pgx_drug_recommendation,
    latest_source_release_versions,
    list_patient_pathway_activity,
    upsert_patient_drug_response,
)
from pathmind_api.schemas_phase3 import EvidenceRecord
from pathmind_api.schemas_phase4 import PatientDrugResponse


class DrugResponseServicePhase4:
    def get_or_compute(self, session: Session, *, patient_id: str, drug_id: str, drug_name: str | None = None) -> PatientDrugResponse:
        cached = get_patient_drug_response(session, patient_id, drug_id)
        versions = latest_source_release_versions(session)
        if cached is not None:
            return PatientDrugResponse(
                patient_id=patient_id,
                drug_id=drug_id,
                drug_name=cached.drug_name,
                recommendation=cached.recommendation,  # type: ignore[arg-type]
                confidence_level=cached.confidence_level,  # type: ignore[arg-type]
                evidence=EvidenceRecord(
                    state=cached.state,  # type: ignore[arg-type]
                    reason_code=cached.reason_code,
                    provenance={"source": "cached_patient_drug_response"},
                ),
                component_scores=cached.component_scores or {},
                version_snapshot=cached.version_snapshot or {},
            )

        pgx_row = get_patient_pgx_drug_recommendation(session, patient_id=patient_id, drug_id=drug_id)

        drug_pathway_ids = get_drug_pathway_ids(session, drug_id)
        all_pathway_rows = list_patient_pathway_activity(session, patient_id)
        if drug_pathway_ids:
            relevant_rows = [row for row in all_pathway_rows if row.pathway_id in drug_pathway_ids]
        else:
            relevant_rows = all_pathway_rows

        pathway_scores = [row.activity_score for row in relevant_rows if row.activity_score is not None]
        mean_pathway = mean(pathway_scores) if pathway_scores else 0.0
        max_pathway = max(pathway_scores) if pathway_scores else None

        significant_pathways = [
            row for row in relevant_rows
            if row.p_value is not None and row.p_value < 0.05
            and row.activity_score is not None and abs(row.activity_score) >= 1.0
        ]

        recommendation = "insufficient_data"
        state = "unknown"
        reason_code = "insufficient_patient_data"
        confidence = "unknown"

        if pgx_row is not None:
            if pgx_row.recommendation == "avoid":
                recommendation = "avoid"
                state = "positive"
                reason_code = "pgx_avoid_rule"
                confidence = "high"
            elif pgx_row.recommendation == "adjust":
                recommendation = "use_with_caution"
                state = "positive"
                reason_code = "pgx_adjust_rule"
                confidence = "high"
            elif pgx_row.recommendation == "standard":
                recommendation = "standard_consideration"
                state = "negative"
                reason_code = "pgx_standard_rule"
                confidence = "moderate"
            else:
                recommendation = "insufficient_data"
                state = "unknown"
                reason_code = pgx_row.reason_code
                confidence = "low"

        if recommendation == "standard_consideration" and significant_pathways:
            recommendation = "use_with_caution"
            state = "positive"
            reason_code = "significant_pathway_activity_override"
            confidence = "moderate"
        elif recommendation == "insufficient_data" and max_pathway is not None:
            if significant_pathways:
                recommendation = "use_with_caution"
                state = "positive"
                reason_code = "pathway_only_signal"
                confidence = "low"
            else:
                recommendation = "standard_consideration"
                state = "unknown"
                reason_code = "pathway_only_signal"
                confidence = "low"

        component_scores = {
            "pgx_state": pgx_row.state if pgx_row is not None else "unknown",
            "pgx_recommendation": pgx_row.recommendation if pgx_row is not None else "insufficient_data",
            "pathway_count": len(relevant_rows),
            "pathway_mean_activity": mean_pathway,
            "pathway_max_activity": max_pathway,
            "significant_pathway_count": len(significant_pathways),
            "drug_pathway_ids_found": len(drug_pathway_ids),
        }
        snapshot = {
            "pharmcat": versions.get("pharmcat", "unknown"),
            "cpic": versions.get("cpic", "unknown"),
            "progeny": versions.get("progeny", "unknown"),
            "reactome": versions.get("reactome", "unknown"),
        }
        persisted = upsert_patient_drug_response(
            session,
            patient_id=patient_id,
            drug_id=drug_id,
            drug_name=drug_name or (pgx_row.drug_name if pgx_row is not None else drug_id),
            recommendation=recommendation,
            state=state,
            reason_code=reason_code,
            confidence_level=confidence,
            component_scores=component_scores,
            version_snapshot=snapshot,
        )
        return PatientDrugResponse(
            patient_id=patient_id,
            drug_id=drug_id,
            drug_name=persisted.drug_name,
            recommendation=persisted.recommendation,  # type: ignore[arg-type]
            confidence_level=persisted.confidence_level,  # type: ignore[arg-type]
            evidence=EvidenceRecord(
                state=persisted.state,  # type: ignore[arg-type]
                reason_code=persisted.reason_code,
                provenance={"source": "computed_patient_drug_response"},
            ),
            component_scores=persisted.component_scores or {},
            version_snapshot=persisted.version_snapshot or {},
        )

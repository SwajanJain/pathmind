import csv
import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from pathmind_api.repositories import (
    add_patient_pgx_drug_recommendations,
    add_patient_pgx_gene_calls,
    get_patient_pgx_drug_recommendation,
    latest_source_release_versions,
    list_patient_pgx_drug_recommendations,
    list_patient_pgx_gene_calls,
)
from pathmind_api.schemas_phase3 import EvidenceRecord
from pathmind_api.schemas_phase4 import (
    PatientPgxDrugRecommendation,
    PatientPgxDrugResponse,
    PatientPgxGeneCall,
    PatientPgxResponse,
    PgxDrugRecommendationParsed,
    PgxGeneCallParsed,
    PgxProcessingResult,
)
from pathmind_api.services.pharmcat_runner_phase4 import PharmcatRunnerPhase4


def _normalize(value: str) -> str:
    return value.strip().lower()


_STANDARD_PHENOTYPES = {
    "poor metabolizer",
    "intermediate metabolizer",
    "normal metabolizer",
    "extensive metabolizer",
    "rapid metabolizer",
    "ultrarapid metabolizer",
    "indeterminate",
    "possible intermediate metabolizer",
}


def _normalize_phenotype(raw: str) -> str:
    lowered = raw.strip().lower()
    for standard in sorted(_STANDARD_PHENOTYPES, key=len, reverse=True):
        if standard == lowered or standard in lowered:
            return standard
    return lowered


def _classify_gene_state(gene_call: PgxGeneCallParsed) -> tuple[str, str]:
    phenotype = _normalize(gene_call.phenotype or "")
    diplotype = _normalize(gene_call.diplotype or "")
    if not phenotype and not diplotype:
        return ("unknown", "gene_not_called")
    risk_markers = ["poor", "ultrarapid", "deficient", "decreased", "contraindication", "high_risk"]
    caution_markers = ["intermediate", "possible intermediate"]
    neutral_markers = ["normal", "extensive", "typical", "reference"]
    if any(marker in phenotype for marker in risk_markers):
        return ("positive", "phenotype_actionable_risk")
    if any(marker in phenotype for marker in caution_markers):
        return ("positive", "phenotype_intermediate_caution")
    if any(marker in phenotype for marker in neutral_markers):
        return ("negative", "phenotype_no_action")
    return ("unknown", "phenotype_unknown")


def _recommendation_state(raw: str) -> tuple[str, str, str]:
    lowered = _normalize(raw)
    if any(token in lowered for token in ["avoid", "contraindicated", "do not use"]):
        return ("avoid", "positive", "cpic_avoid")
    if any(token in lowered for token in ["adjust", "reduce", "decrease", "increase monitoring", "alternative"]):
        return ("adjust", "positive", "cpic_adjust")
    if any(token in lowered for token in ["standard", "usual", "no action", "normal dosing"]):
        return ("standard", "negative", "cpic_standard")
    return ("insufficient_data", "unknown", "cpic_unmapped_recommendation")


class PgxServicePhase4:
    def __init__(self, *, phase4_data_dir: str, runner: PharmcatRunnerPhase4) -> None:
        self.phase4_data_dir = Path(phase4_data_dir)
        self.runner = runner

    @lru_cache(maxsize=1)
    def _cpic_rules(self) -> list[dict]:
        root = self.phase4_data_dir
        candidates = [
            root / "cpic_recommendations.tsv",
            root / "cpic_recommendations.csv",
            root / "cpic_recommendations.json",
        ]
        path = next((item for item in candidates if item.exists()), None)
        if path is None:
            return []
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return [row for row in payload if isinstance(row, dict)]
            if isinstance(payload, dict):
                rows = payload.get("rows", [])
                return [row for row in rows if isinstance(row, dict)]
            return []
        delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            return [dict(row) for row in reader]

    def _match_rules(self, gene: str, phenotype: str | None) -> list[dict]:
        gene_key = _normalize(gene)
        phenotype_key = _normalize_phenotype(phenotype or "")
        matches: list[dict] = []
        for row in self._cpic_rules():
            row_gene = _normalize(str(row.get("gene") or ""))
            if row_gene != gene_key:
                continue
            row_phenotype = _normalize_phenotype(str(row.get("phenotype") or ""))
            if row_phenotype and phenotype_key and row_phenotype != phenotype_key:
                continue
            matches.append(row)
        return matches

    def process_vcf(self, vcf_path: Path, version_snapshot: dict[str, str]) -> PgxProcessingResult:
        parsed_calls = self.runner.run_from_vcf(vcf_path)
        normalized_calls: list[PgxGeneCallParsed] = []
        recommendations: list[PgxDrugRecommendationParsed] = []

        for call in parsed_calls:
            state, reason = _classify_gene_state(call)
            normalized = call.model_copy(update={"state": state, "reason_code": reason})
            normalized_calls.append(normalized)
            for rule in self._match_rules(normalized.gene, normalized.phenotype):
                recommendation, rec_state, rec_reason = _recommendation_state(str(rule.get("recommendation") or ""))
                recommendations.append(
                    PgxDrugRecommendationParsed(
                        drug_id=(str(rule.get("drug_id") or "").strip() or None),
                        drug_name=str(rule.get("drug_name") or rule.get("drug") or "unknown_drug"),
                        recommendation=recommendation,  # type: ignore[arg-type]
                        evidence_level=str(rule.get("evidence_level") or "").strip() or None,
                        cpic_guideline_id=str(rule.get("cpic_guideline_id") or "").strip() or None,
                        state=rec_state,  # type: ignore[arg-type]
                        reason_code=rec_reason,
                        provenance={
                            "gene": normalized.gene,
                            "phenotype": normalized.phenotype,
                            "rule_source": "cpic_local_snapshot",
                        },
                    )
                )

        if not recommendations:
            recommendations.append(
                PgxDrugRecommendationParsed(
                    drug_id=None,
                    drug_name="unknown_drug",
                    recommendation="insufficient_data",
                    evidence_level=None,
                    cpic_guideline_id=None,
                    state="unknown",
                    reason_code="guideline_not_found",
                    provenance={"rule_source": "cpic_local_snapshot"},
                )
            )

        snapshot = dict(version_snapshot)
        snapshot["cpic_rules_loaded"] = str(len(self._cpic_rules()))
        return PgxProcessingResult(gene_calls=normalized_calls, drug_recommendations=recommendations, version_snapshot=snapshot)

    def persist_patient_results(self, session: Session, *, patient_id: str, result: PgxProcessingResult) -> None:
        add_patient_pgx_gene_calls(
            session,
            patient_id,
            [call.model_dump(mode="json") for call in result.gene_calls],
        )
        add_patient_pgx_drug_recommendations(
            session,
            patient_id,
            [item.model_dump(mode="json") for item in result.drug_recommendations],
        )

    def get_patient_pgx(self, session: Session, patient_id: str) -> PatientPgxResponse:
        gene_rows = list_patient_pgx_gene_calls(session, patient_id)
        drug_rows = list_patient_pgx_drug_recommendations(session, patient_id)
        versions = latest_source_release_versions(session)
        return PatientPgxResponse(
            patient_id=patient_id,
            gene_calls=[
                PatientPgxGeneCall(
                    gene=row.gene,
                    diplotype=row.diplotype,
                    phenotype=row.phenotype,
                    activity_score=row.activity_score,
                    evidence=EvidenceRecord(
                        state=row.state,  # type: ignore[arg-type]
                        reason_code=row.reason_code,
                        provenance=row.provenance or {},
                        confidence_note=row.confidence_note,
                    ),
                )
                for row in gene_rows
            ],
            drug_recommendations=[
                PatientPgxDrugRecommendation(
                    drug_id=row.drug_id,
                    drug_name=row.drug_name,
                    recommendation=row.recommendation,  # type: ignore[arg-type]
                    evidence_level=row.evidence_level,
                    cpic_guideline_id=row.cpic_guideline_id,
                    evidence=EvidenceRecord(
                        state=row.state,  # type: ignore[arg-type]
                        reason_code=row.reason_code,
                        provenance=row.provenance or {},
                        confidence_note=row.confidence_note,
                    ),
                )
                for row in drug_rows
            ],
            version_snapshot={
                "pharmcat": versions.get("pharmcat", "unknown"),
                "cpic": versions.get("cpic", "unknown"),
                "pharmgkb": versions.get("pharmgkb", "unknown"),
            },
        )

    def get_patient_pgx_drug(self, session: Session, *, patient_id: str, drug_id: str) -> PatientPgxDrugResponse:
        row = get_patient_pgx_drug_recommendation(session, patient_id=patient_id, drug_id=drug_id)
        versions = latest_source_release_versions(session)
        if row is None:
            return PatientPgxDrugResponse(
                patient_id=patient_id,
                drug_id=drug_id,
                drug_name=drug_id,
                recommendation="insufficient_data",
                evidence=EvidenceRecord(
                    state="unknown",
                    reason_code="guideline_not_found",
                    provenance={"drug_id": drug_id},
                ),
                version_snapshot={
                    "pharmcat": versions.get("pharmcat", "unknown"),
                    "cpic": versions.get("cpic", "unknown"),
                },
            )
        return PatientPgxDrugResponse(
            patient_id=patient_id,
            drug_id=drug_id,
            drug_name=row.drug_name,
            recommendation=row.recommendation,  # type: ignore[arg-type]
            evidence_level=row.evidence_level,
            evidence=EvidenceRecord(
                state=row.state,  # type: ignore[arg-type]
                reason_code=row.reason_code,
                provenance=row.provenance or {},
                confidence_note=row.confidence_note,
            ),
            version_snapshot={
                "pharmcat": versions.get("pharmcat", "unknown"),
                "cpic": versions.get("cpic", "unknown"),
            },
        )

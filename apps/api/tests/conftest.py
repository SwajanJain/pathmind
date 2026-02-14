from datetime import datetime, timezone
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("PATHMIND_DATABASE_URL", "sqlite://")

from pathmind_api.cache import InMemoryCache
from pathmind_api.database import Base, get_db
from pathmind_api.deps import (
    get_analysis_service,
    get_aop_phase3_service,
    get_cache,
    get_causal_chain_service,
    get_drug_response_phase4_service,
    get_enrichment_service,
    get_expression_ingest_service,
    get_herg_phase3_service,
    get_job_service,
    get_lincs_provider,
    get_patient_expression_phase4_service,
    get_patient_profile_phase4_service,
    get_phase4_dataset_service,
    get_phase3_dataset_service,
    get_pgx_phase4_service,
    get_predict_targets_service,
    get_selectivity_service,
    get_tissue_expression_phase3_service,
    get_tissue_impact_phase3_service,
    get_toxicity_phase3_service,
    get_tf_activity_service,
)
from pathmind_api.main import create_app
from pathmind_api.schemas import (
    AnalysisParams,
    AnalysisResult,
    AssociationGraph,
    CompareResult,
    DrugResolution,
    DrugResolutionCandidate,
    DrugSuggestItem,
    GraphEdge,
    GraphNode,
    PathwayScore,
    TargetHit,
)
from pathmind_api.schemas_phase2 import (
    CausalChainResponse,
    EnrichmentResult,
    JobStatusResponse,
    LincsDrugSignatureResponse,
    LincsQueryRequest,
    LincsQueryResponse,
    OccupancyResponse,
    PredictTargetsRequest,
    PredictTargetsResult,
    PredictedTargetHit,
    SelectivityResponse,
    SelectivityTargetRow,
    TargetEvidencePredicted,
    TfActivityResult,
    UploadDegResponse,
)
from pathmind_api.schemas_phase3 import (
    AopChainMatch,
    AopResponse,
    DiliResponse,
    EvidenceRecord,
    HergResponse,
    PathwayExpressionResponse,
    Phase3DatasetStatusItem,
    Phase3DatasetStatusResponse,
    TissueExpressionPoint,
    TissueExpressionResponse,
    TissueImpactResponse,
    ToxicityFlag,
    ToxicityResponse,
)
from pathmind_api.schemas_phase4 import (
    PatientDeleteResponse,
    PatientDrugResponse,
    PatientPathwayActivityResponse,
    PatientPathwayActivityRow,
    PatientPgxDrugRecommendation,
    PatientPgxDrugResponse,
    PatientPgxGeneCall,
    PatientPgxResponse,
    PatientProfileResponse,
    Phase4DatasetStatusItem,
    Phase4DatasetStatusResponse,
    PgxDrugRecommendationParsed,
    PgxGeneCallParsed,
    PgxProcessingResult,
)
from pathmind_api.service import AmbiguousDrugError, AnalysisService, FatalAnalysisError


def _analysis_payload(drug_name: str, degraded: list[str] | None = None) -> AnalysisResult:
    analysis_id = str(uuid4())
    canonical = f"CHEMBL-{drug_name.upper()}"
    targets = [
        TargetHit(
            target_chembl_id=f"T-{drug_name[:3]}-1",
            target_name="EGFR",
            uniprot_id="P00533",
            action_type="INHIBITOR",
            median_pchembl=8.9,
            assay_count=7,
            confidence_score=9,
            confidence_tier="high",
            low_confidence=False,
            source_assay_ids=["A1", "A2"],
        ),
        TargetHit(
            target_chembl_id=f"T-{drug_name[:3]}-2",
            target_name="ERBB2",
            uniprot_id="P04626",
            action_type="INHIBITOR",
            median_pchembl=6.4,
            assay_count=3,
            confidence_score=8,
            confidence_tier="medium",
            low_confidence=False,
            source_assay_ids=["A3", "A4"],
        ),
    ]
    pathways = [
        PathwayScore(
            pathway_id=f"R-{drug_name[:3]}-1",
            pathway_name="EGFR signaling",
            depth=3,
            pathway_size=120,
            targets_hit=2,
            median_pchembl=7.65,
            score=0.1275,
            target_ids=[target.target_chembl_id for target in targets],
            reactome_url="https://reactome.org/content/detail/R-HSA-177929",
            ancestor_pathway_ids=["R-HSA-162582"],
        ),
        PathwayScore(
            pathway_id=f"R-{drug_name[:3]}-2",
            pathway_name="PI3K/AKT signaling",
            depth=4,
            pathway_size=80,
            targets_hit=1,
            median_pchembl=6.4,
            score=0.08,
            target_ids=[targets[1].target_chembl_id],
            reactome_url="https://reactome.org/content/detail/R-HSA-109704",
            ancestor_pathway_ids=["R-HSA-162582"],
        ),
    ]
    graph = AssociationGraph(
        nodes=[
            GraphNode(id=f"drug:{canonical}", label=drug_name, kind="drug"),
            GraphNode(id=f"target:{targets[0].target_chembl_id}", label=targets[0].target_name, kind="target"),
            GraphNode(id=f"pathway:{pathways[0].pathway_id}", label=pathways[0].pathway_name, kind="pathway"),
        ],
        edges=[
            GraphEdge(
                id="e1",
                source=f"drug:{canonical}",
                target=f"target:{targets[0].target_chembl_id}",
                kind="drug_target",
                weight=8.9,
            ),
            GraphEdge(
                id="e2",
                source=f"target:{targets[0].target_chembl_id}",
                target=f"pathway:{pathways[0].pathway_id}",
                kind="target_pathway",
                weight=0.1275,
            ),
        ],
    )
    return AnalysisResult(
        analysis_id=analysis_id,
        created_at=datetime.now(timezone.utc),
        drug_name=drug_name,
        canonical_drug_id=canonical,
        params=AnalysisParams(),
        resolution=DrugResolution(
            query=drug_name,
            display_name=drug_name.title(),
            chembl_parent_id=canonical,
            canonical_inchikey=f"{drug_name.upper()}-KEY",
            synonyms=[],
            clinical_phase=4,
            mechanism_of_action="EGFR inhibitor",
        ),
        targets=targets,
        pathways=pathways,
        graph=graph,
        source_versions={"chembl": "test"},
        degraded_messages=degraded or [],
        attribution="Data sources: test",
    )


class StubAnalysisService(AnalysisService):
    def __init__(self) -> None:
        pass

    async def suggest(self, query: str) -> list[DrugSuggestItem]:
        return [DrugSuggestItem(display_name="Erlotinib", chembl_id="CHEMBL553")]

    async def resolve_drug_identity(self, query: str, resolution_choice: str | None = None):
        if query == "ambiguous_drug" and not resolution_choice:
            raise AmbiguousDrugError(
                candidates=[
                    DrugResolutionCandidate(
                        chembl_parent_id="CHEMBL-A",
                        display_name="Ambiguous A",
                        canonical_inchikey="A-KEY",
                        match_reasons=["chembl_parent_match"],
                    ),
                    DrugResolutionCandidate(
                        chembl_parent_id="CHEMBL-B",
                        display_name="Ambiguous B",
                        canonical_inchikey="B-KEY",
                        match_reasons=["chembl_parent_match"],
                    ),
                ]
            )
        resolution = DrugResolution(
            query=query,
            display_name=query.title(),
            chembl_parent_id=resolution_choice or "CHEMBL553",
            canonical_inchikey="TEST-KEY",
            synonyms=[],
        )
        return resolution, []

    async def run_analysis(self, drug_name: str, params: AnalysisParams, resolution_choice: str | None = None) -> AnalysisResult:
        if drug_name == "chembl_down":
            raise FatalAnalysisError("ChEMBL is temporarily unavailable.")
        if drug_name == "ambiguous_drug" and not resolution_choice:
            raise AmbiguousDrugError(
                candidates=[
                    DrugResolutionCandidate(
                        chembl_parent_id="CHEMBL-A",
                        display_name="Ambiguous A",
                        canonical_inchikey="A-KEY",
                        match_reasons=["chembl_parent_match"],
                    )
                ]
            )
        degraded = {
            "reactome_down": ["Pathway data temporarily unavailable. Showing target binding data only."],
            "opentargets_down": ["Drug mechanism data unavailable. Direction information may be missing."],
            "pubchem_down": ["Drug structure image unavailable."],
            "uniprot_down": ["Some target annotations may be incomplete."],
        }.get(drug_name, [])
        payload = _analysis_payload(drug_name=drug_name, degraded=degraded)
        payload.params = params
        if resolution_choice:
            payload.canonical_drug_id = resolution_choice
            payload.resolution.chembl_parent_id = resolution_choice
        return payload

    async def health(self) -> dict:
        from pathmind_api.clients.base import HealthResult

        return {
            "status": "healthy",
            "checks": {
                "chembl": HealthResult(status="up", latency_ms=100),
                "reactome": HealthResult(status="up", latency_ms=80),
                "opentargets": HealthResult(status="up", latency_ms=90),
                "pubchem": HealthResult(status="up", latency_ms=70),
                "uniprot": HealthResult(status="up", latency_ms=110),
            },
        }


class StubJobService:
    def __init__(self) -> None:
        self.jobs: dict[str, JobStatusResponse] = {}

    def create_job(self, *, job_type: str, request_payload: dict, version_snapshot: dict) -> str:
        job_id = str(uuid4())
        self.jobs[job_id] = JobStatusResponse(
            job_id=job_id,
            job_type=job_type,
            status="queued",
            progress=0.0,
            created_at=datetime.now(timezone.utc),
            version_snapshot=version_snapshot,
        )
        return job_id

    def get_status(self, job_id: str):
        return self.jobs.get(job_id)

    async def run_job(self, job_id: str, worker):
        current = self.jobs[job_id]
        self.jobs[job_id] = current.model_copy(update={"status": "running", "progress": 0.1, "started_at": datetime.now(timezone.utc)})

        def set_progress(value: float) -> None:
            self.jobs[job_id] = self.jobs[job_id].model_copy(update={"progress": value})

        try:
            result = await worker(set_progress)
            self.jobs[job_id] = self.jobs[job_id].model_copy(
                update={
                    "status": "succeeded",
                    "progress": 1.0,
                    "finished_at": datetime.now(timezone.utc),
                    "result": result,
                }
            )
        except Exception as exc:
            self.jobs[job_id] = self.jobs[job_id].model_copy(
                update={
                    "status": "failed",
                    "progress": 1.0,
                    "finished_at": datetime.now(timezone.utc),
                    "error": str(exc),
                }
            )


class StubPredictTargetsService:
    async def run(self, session, payload: PredictTargetsRequest) -> PredictTargetsResult:
        return PredictTargetsResult(
            compound_analysis_id="cmp-1",
            smiles=payload.smiles,
            canonical_smiles=payload.smiles,
            targets=[
                PredictedTargetHit(
                    target_chembl_id="CHEMBL203",
                    target_name="EGFR",
                    confidence=0.9,
                    tier="high_predicted",
                    evidence=TargetEvidencePredicted(
                        evidence_type="predicted_similarity",
                        similar_compounds=[{"chembl_id": "CHEMBL553", "similarity": 0.91, "pchembl_value": 8.5}],
                        unknowns=["no_assays_for_exact_compound"],
                    ),
                    predicted_pchembl_min=7.8,
                    predicted_pchembl_max=8.8,
                    confidence_discount=0.85,
                    unknowns=["no_assays_for_exact_compound"],
                )
            ],
            pathway_preview=[
                {
                    "pathway_id": "R-HSA-177929",
                    "pathway_name": "EGFR signaling",
                    "depth": 3,
                    "score": 0.08,
                    "targets_hit": 1,
                    "reactome_url": "https://reactome.org/content/detail/R-HSA-177929",
                }
            ],
            version_snapshot={"prediction_method": payload.method},
        )


class StubSelectivityService:
    async def selectivity(self, drug_id: str) -> SelectivityResponse:
        return SelectivityResponse(
            drug_id=drug_id,
            targets=[
                SelectivityTargetRow(
                    target_chembl_id="CHEMBL203",
                    target_name="EGFR",
                    median_pchembl=8.5,
                    assay_count=4,
                    pchembl_iqr=0.3,
                    potency_band="potent",
                )
            ],
            version_snapshot={"chembl": "test"},
        )

    async def occupancy(self, drug_id: str, concentration_nM: float) -> OccupancyResponse:
        return OccupancyResponse(
            drug_id=drug_id,
            concentration_nM=concentration_nM,
            targets=[
                {
                    "target_chembl_id": "CHEMBL203",
                    "target_name": "EGFR",
                    "concentration_nM": concentration_nM,
                    "ic50_nM": 5.0,
                    "occupancy": 0.95,
                    "engaged": True,
                    "unknowns": [],
                }
            ],
            version_snapshot={"chembl": "test"},
        )


class StubExpressionIngestService:
    async def ingest(self, session, *, filename: str, content: bytes) -> UploadDegResponse:
        return UploadDegResponse(
            upload_id="upload-1",
            filename=filename,
            id_type="hgnc",
            gene_count=20,
            sig_gene_count=12,
            mapping_summary={"mapped": 18, "unknown": 2},
            unknown_gene_count=2,
            version_snapshot={"hgnc_mapping": "test"},
        )


class StubEnrichmentService:
    def run(self, session, *, upload_id: str, method: str, version_snapshot: dict[str, str]) -> EnrichmentResult:
        return EnrichmentResult(
            run_id="enrich-1",
            upload_id=upload_id,
            method="gsea_prerank",
            pathways=[
                {
                    "pathway_id": "R-HSA-177929",
                    "pathway_name": "EGFR signaling",
                    "p_value": 0.02,
                    "fdr": 0.05,
                    "enrichment_score": 1.8,
                    "overlap_count": 5,
                    "genes_in_pathway": 100,
                    "overlap_genes": ["EGFR", "ERBB2"],
                    "direction": "up",
                    "leading_edge_genes": ["EGFR"],
                }
            ],
            version_snapshot=version_snapshot,
        )


class StubTfActivityService:
    def run(self, session, *, upload_id: str, method: str, version_snapshot: dict[str, str]) -> TfActivityResult:
        return TfActivityResult(
            run_id="tf-1",
            upload_id=upload_id,
            method="consensus",
            factors=[
                {
                    "tf_name": "STAT3",
                    "activity_score": 1.2,
                    "p_value": 0.03,
                    "direction": "activated",
                    "n_targets": 12,
                    "concordant_targets": 9,
                    "top_target_genes": ["SOCS3"],
                }
            ],
            version_snapshot=version_snapshot,
        )


class StubCausalChainService:
    async def run(self, session, *, drug_id: str, upload_id: str) -> CausalChainResponse:
        return CausalChainResponse(
            drug_id=drug_id,
            upload_id=upload_id,
            explained_genes=["EGFR"],
            unexplained_genes=["TP53"],
            edges=[{"source": f"drug:{drug_id}", "target": "target:CHEMBL203", "kind": "drug_target", "confidence": 1.0}],
            coverage_ratio=0.5,
            version_snapshot={"causal_chain_method": "stub"},
        )


class StubLincsProvider:
    async def drug_signature(self, name: str) -> LincsDrugSignatureResponse:
        return LincsDrugSignatureResponse(
            drug_name=name,
            provider_status="disabled",
            unknown_reason="provider_disabled",
            signatures=[],
            version_snapshot={"provider": "stub"},
        )

    async def query_signature(self, payload: LincsQueryRequest) -> LincsQueryResponse:
        return LincsQueryResponse(
            provider_status="disabled",
            unknown_reason="provider_disabled",
            matches=[],
            version_snapshot={"provider": "stub"},
        )


class StubPhase3DatasetService:
    def status(self, session) -> Phase3DatasetStatusResponse:
        return Phase3DatasetStatusResponse(
            overall_status="ready",
            datasets=[
                Phase3DatasetStatusItem(dataset="gtex", status="ready", version="test-v1"),
                Phase3DatasetStatusItem(dataset="hpa", status="ready", version="test-v1"),
                Phase3DatasetStatusItem(dataset="dilirank", status="ready", version="test-v1"),
                Phase3DatasetStatusItem(dataset="aopwiki", status="ready", version="test-v1"),
            ],
            version_snapshot={"gtex": "test-v1", "hpa": "test-v1", "dilirank": "test-v1", "aopwiki": "test-v1"},
        )


class StubTissueExpressionService:
    async def by_gene(self, session, gene: str) -> TissueExpressionResponse:
        return TissueExpressionResponse(
            gene_symbol=gene.upper(),
            expression=[
                TissueExpressionPoint(
                    tissue="Liver",
                    gtex_tpm=25.0,
                    hpa_rna_nx=40.0,
                    hpa_protein_level="High",
                    evidence=EvidenceRecord(state="positive", reason_code="measured_expression_present", provenance={}),
                ),
                TissueExpressionPoint(
                    tissue="Brain",
                    gtex_tpm=0.2,
                    hpa_rna_nx=0.1,
                    hpa_protein_level="Low",
                    evidence=EvidenceRecord(state="negative", reason_code="measured_expression_low", provenance={}),
                ),
            ],
            version_snapshot={"gtex": "test-v1", "hpa": "test-v1"},
        )

    async def for_pathway(self, session, pathway_id: str) -> PathwayExpressionResponse:
        return PathwayExpressionResponse(
            pathway_id=pathway_id,
            pathway_name="EGFR signaling",
            genes=[],
            version_snapshot={"gtex": "test-v1", "hpa": "test-v1", "reactome": "test-v1"},
        )


class StubHergService:
    async def evaluate(self, drug_id: str) -> HergResponse:
        return HergResponse(
            drug_id=drug_id,
            ic50_nM=120.0,
            assay_count=3,
            cmax_free_nM=None,
            safety_margin=None,
            herg_signal=EvidenceRecord(state="positive", reason_code="ic50_threshold", provenance={}),
            margin_signal=EvidenceRecord(state="unknown", reason_code="cmax_missing", provenance={}),
            version_snapshot={"chembl": "test-v1"},
        )


class StubToxicityService:
    async def evaluate(self, session, drug_id: str) -> ToxicityResponse:
        return ToxicityResponse(
            drug_id=drug_id,
            flags=[
                ToxicityFlag(
                    pathway_key="cyp_metabolism",
                    label="CYP metabolism",
                    risk_type="dili",
                    overlapping_genes=["CYP3A4"],
                    severity=0.25,
                    signal=EvidenceRecord(state="positive", reason_code="mechanistic_overlap", provenance={}),
                )
            ],
            herg=await StubHergService().evaluate(drug_id),
            dili=DiliResponse(
                drug_name=drug_id,
                category="Most-DILI-concern",
                signal=EvidenceRecord(state="positive", reason_code="dilirank_concern", provenance={}),
                version_snapshot={"dilirank": "test-v1"},
            ),
            toxcast=EvidenceRecord(state="unknown", reason_code="provider_disabled", provenance={}),
            version_snapshot={"chembl": "test-v1", "dilirank": "test-v1"},
        )


class StubAopService:
    async def evaluate(self, session, drug_id: str) -> AopResponse:
        return AopResponse(
            drug_id=drug_id,
            matches=[
                AopChainMatch(
                    aop_id="17",
                    mie="hERG blockade",
                    adverse_outcome="Sudden cardiac death",
                    key_events=["QT prolongation"],
                    matched_genes=["KCNH2"],
                    signal=EvidenceRecord(state="positive", reason_code="aop_match_found", provenance={}),
                )
            ],
            signal=EvidenceRecord(state="positive", reason_code="aop_chain_match", provenance={}),
            version_snapshot={"aopwiki": "test-v1"},
        )


class StubTissueImpactService:
    async def evaluate(self, session, drug_id: str) -> TissueImpactResponse:
        return TissueImpactResponse(
            drug_id=drug_id,
            cells=[],
            version_snapshot={"gtex": "test-v1", "hpa": "test-v1", "chembl": "test-v1"},
        )


class StubPhase4DatasetService:
    def status(self, session) -> Phase4DatasetStatusResponse:
        return Phase4DatasetStatusResponse(
            overall_status="ready",
            datasets=[
                Phase4DatasetStatusItem(dataset="pharmcat", required=True, status="ready", version="test-v1"),
                Phase4DatasetStatusItem(dataset="cpic", required=True, status="ready", version="test-v1"),
                Phase4DatasetStatusItem(dataset="hgnc", required=True, status="ready", version="test-v1"),
                Phase4DatasetStatusItem(dataset="progeny", required=True, status="ready", version="test-v1"),
                Phase4DatasetStatusItem(dataset="pharmgkb", required=False, status="missing", reason="optional_not_loaded", version=None),
            ],
            version_snapshot={"pharmcat": "test-v1", "cpic": "test-v1", "hgnc": "test-v1", "progeny": "test-v1"},
        )


class StubPatientProfileService:
    def __init__(self, state: dict) -> None:
        self.state = state

    def create(self, session, *, label: str, save_derived_default: bool = False) -> PatientProfileResponse:
        patient_id = str(uuid4())
        profile = PatientProfileResponse(
            patient_id=patient_id,
            label=label,
            status="active",
            has_pgx=False,
            has_expression=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            version_snapshot={},
        )
        self.state.setdefault("profiles", {})[patient_id] = profile
        return profile

    def get(self, session, patient_id: str) -> PatientProfileResponse | None:
        return self.state.get("profiles", {}).get(patient_id)

    def delete(self, session, patient_id: str) -> PatientDeleteResponse:
        profiles = self.state.setdefault("profiles", {})
        if patient_id in profiles:
            profiles.pop(patient_id, None)
            self.state.setdefault("pgx", {}).pop(patient_id, None)
            self.state.setdefault("pathways", {}).pop(patient_id, None)
            self.state.setdefault("drug_responses", {}).pop(patient_id, None)
            return PatientDeleteResponse(patient_id=patient_id, deleted=True)
        return PatientDeleteResponse(patient_id=patient_id, deleted=False)


class StubPgxService:
    def __init__(self, state: dict) -> None:
        self.state = state

    def process_vcf(self, vcf_path, version_snapshot: dict[str, str]) -> PgxProcessingResult:
        return PgxProcessingResult(
            gene_calls=[
                PgxGeneCallParsed(
                    gene="CYP2D6",
                    diplotype="*1/*4",
                    phenotype="Intermediate Metabolizer",
                    activity_score=1.0,
                    state="positive",
                    reason_code="phenotype_actionable_risk",
                    provenance={"source": "stub"},
                )
            ],
            drug_recommendations=[
                PgxDrugRecommendationParsed(
                    drug_id="CHEMBL553",
                    drug_name="erlotinib",
                    recommendation="adjust",
                    evidence_level="1A",
                    cpic_guideline_id="CPIC-TEST-1",
                    state="positive",
                    reason_code="cpic_adjust",
                    provenance={"source": "stub"},
                )
            ],
            version_snapshot=version_snapshot,
        )

    def persist_patient_results(self, session, *, patient_id: str, result: PgxProcessingResult) -> None:
        response = PatientPgxResponse(
            patient_id=patient_id,
            gene_calls=[
                PatientPgxGeneCall(
                    gene=item.gene,
                    diplotype=item.diplotype,
                    phenotype=item.phenotype,
                    activity_score=item.activity_score,
                    evidence=EvidenceRecord(
                        state=item.state,
                        reason_code=item.reason_code,
                        provenance=item.provenance,
                        confidence_note=item.confidence_note,
                    ),
                )
                for item in result.gene_calls
            ],
            drug_recommendations=[
                PatientPgxDrugRecommendation(
                    drug_id=item.drug_id,
                    drug_name=item.drug_name,
                    recommendation=item.recommendation,
                    evidence_level=item.evidence_level,
                    cpic_guideline_id=item.cpic_guideline_id,
                    evidence=EvidenceRecord(
                        state=item.state,
                        reason_code=item.reason_code,
                        provenance=item.provenance,
                        confidence_note=item.confidence_note,
                    ),
                )
                for item in result.drug_recommendations
            ],
            version_snapshot=result.version_snapshot,
        )
        self.state.setdefault("pgx", {})[patient_id] = response
        profile = self.state.setdefault("profiles", {}).get(patient_id)
        if profile:
            self.state["profiles"][patient_id] = profile.model_copy(update={"has_pgx": True})

    def get_patient_pgx(self, session, patient_id: str) -> PatientPgxResponse:
        return self.state.get("pgx", {}).get(
            patient_id,
            PatientPgxResponse(patient_id=patient_id, gene_calls=[], drug_recommendations=[], version_snapshot={"pharmcat": "unknown", "cpic": "unknown"}),
        )

    def get_patient_pgx_drug(self, session, *, patient_id: str, drug_id: str) -> PatientPgxDrugResponse:
        payload = self.get_patient_pgx(session, patient_id)
        for row in payload.drug_recommendations:
            if row.drug_id == drug_id or row.drug_name.lower() == drug_id.lower():
                return PatientPgxDrugResponse(
                    patient_id=patient_id,
                    drug_id=drug_id,
                    drug_name=row.drug_name,
                    recommendation=row.recommendation,
                    evidence_level=row.evidence_level,
                    evidence=row.evidence,
                    version_snapshot=payload.version_snapshot,
                )
        return PatientPgxDrugResponse(
            patient_id=patient_id,
            drug_id=drug_id,
            drug_name=drug_id,
            recommendation="insufficient_data",
            evidence=EvidenceRecord(state="unknown", reason_code="guideline_not_found", provenance={}),
            version_snapshot=payload.version_snapshot,
        )


class StubPatientExpressionService:
    def __init__(self, state: dict) -> None:
        self.state = state

    async def process_expression(self, session, *, filename: str, content: bytes, version_snapshot: dict[str, str], keep_phase2_rows: bool):
        upload = UploadDegResponse(
            upload_id="upload-phase4",
            filename=filename,
            id_type="hgnc",
            gene_count=20,
            sig_gene_count=10,
            mapping_summary={"mapped": 18, "unknown": 2},
            unknown_gene_count=2,
            version_snapshot=version_snapshot,
        )
        enrichment = EnrichmentResult(
            run_id="enrich-phase4",
            upload_id=upload.upload_id,
            method="gsea_prerank",
            pathways=[],
            version_snapshot=version_snapshot,
        )
        pathways = [
            {
                "pathway_id": "R-HSA-177929",
                "pathway_name": "EGFR signaling",
                "activity_score": 1.9,
                "p_value": 0.01,
                "percentile": 85.0,
                "method": "gsea_prerank",
                "state": "positive",
                "reason_code": "high_activity",
                "provenance": {"source": "stub"},
            }
        ]
        return {"upload": upload, "enrichment": enrichment, "pathways": pathways}

    def persist_patient_expression(self, session, *, patient_id: str, filename: str, upload_summary: dict, pathways: list[dict], version_snapshot: dict[str, str]) -> str:
        response = PatientPathwayActivityResponse(
            patient_id=patient_id,
            pathways=[
                PatientPathwayActivityRow(
                    pathway_id=row["pathway_id"],
                    pathway_name=row["pathway_name"],
                    activity_score=row["activity_score"],
                    p_value=row["p_value"],
                    percentile=row["percentile"],
                    method=row["method"],
                    evidence=EvidenceRecord(state=row["state"], reason_code=row["reason_code"], provenance=row["provenance"]),
                )
                for row in pathways
            ],
            version_snapshot=version_snapshot,
        )
        self.state.setdefault("pathways", {})[patient_id] = response
        profile = self.state.setdefault("profiles", {}).get(patient_id)
        if profile:
            self.state["profiles"][patient_id] = profile.model_copy(update={"has_expression": True})
        return "run-phase4"

    def get_patient_pathway_activity(self, session, patient_id: str) -> PatientPathwayActivityResponse:
        return self.state.get("pathways", {}).get(
            patient_id,
            PatientPathwayActivityResponse(patient_id=patient_id, pathways=[], version_snapshot={"progeny": "unknown"}),
        )


class StubDrugResponseService:
    def __init__(self, state: dict) -> None:
        self.state = state

    def get_or_compute(self, session, *, patient_id: str, drug_id: str, drug_name: str | None = None) -> PatientDrugResponse:
        cached = self.state.get("drug_responses", {}).get((patient_id, drug_id))
        if cached:
            return cached
        response = PatientDrugResponse(
            patient_id=patient_id,
            drug_id=drug_id,
            drug_name=drug_name or drug_id,
            recommendation="use_with_caution",
            confidence_level="moderate",
            evidence=EvidenceRecord(state="positive", reason_code="pgx_adjust_rule", provenance={"source": "stub"}),
            component_scores={"pgx_state": "positive", "pathway_max_activity": 1.9},
            version_snapshot={"pharmcat": "test-v1", "cpic": "test-v1", "progeny": "test-v1"},
        )
        self.state.setdefault("drug_responses", {})[(patient_id, drug_id)] = response
        return response


@pytest.fixture()
def client():
    app = create_app()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    cache = InMemoryCache()
    service = StubAnalysisService()
    job_service = StubJobService()
    predict_service = StubPredictTargetsService()
    selectivity_service = StubSelectivityService()
    ingest_service = StubExpressionIngestService()
    enrichment_service = StubEnrichmentService()
    tf_service = StubTfActivityService()
    causal_service = StubCausalChainService()
    lincs_provider = StubLincsProvider()
    phase3_dataset_service = StubPhase3DatasetService()
    tissue_expression_service = StubTissueExpressionService()
    herg_service = StubHergService()
    toxicity_service = StubToxicityService()
    aop_service = StubAopService()
    tissue_impact_service = StubTissueImpactService()
    phase4_dataset_service = StubPhase4DatasetService()
    phase4_state: dict = {"profiles": {}, "pgx": {}, "pathways": {}, "drug_responses": {}}
    patient_profile_service = StubPatientProfileService(phase4_state)
    pgx_service = StubPgxService(phase4_state)
    patient_expression_service = StubPatientExpressionService(phase4_state)
    drug_response_service = StubDrugResponseService(phase4_state)

    def override_db():
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_cache] = lambda: cache
    app.dependency_overrides[get_analysis_service] = lambda: service
    app.dependency_overrides[get_job_service] = lambda: job_service
    app.dependency_overrides[get_predict_targets_service] = lambda: predict_service
    app.dependency_overrides[get_selectivity_service] = lambda: selectivity_service
    app.dependency_overrides[get_expression_ingest_service] = lambda: ingest_service
    app.dependency_overrides[get_enrichment_service] = lambda: enrichment_service
    app.dependency_overrides[get_tf_activity_service] = lambda: tf_service
    app.dependency_overrides[get_causal_chain_service] = lambda: causal_service
    app.dependency_overrides[get_lincs_provider] = lambda: lincs_provider
    app.dependency_overrides[get_phase3_dataset_service] = lambda: phase3_dataset_service
    app.dependency_overrides[get_tissue_expression_phase3_service] = lambda: tissue_expression_service
    app.dependency_overrides[get_herg_phase3_service] = lambda: herg_service
    app.dependency_overrides[get_toxicity_phase3_service] = lambda: toxicity_service
    app.dependency_overrides[get_aop_phase3_service] = lambda: aop_service
    app.dependency_overrides[get_tissue_impact_phase3_service] = lambda: tissue_impact_service
    app.dependency_overrides[get_phase4_dataset_service] = lambda: phase4_dataset_service
    app.dependency_overrides[get_patient_profile_phase4_service] = lambda: patient_profile_service
    app.dependency_overrides[get_pgx_phase4_service] = lambda: pgx_service
    app.dependency_overrides[get_patient_expression_phase4_service] = lambda: patient_expression_service
    app.dependency_overrides[get_drug_response_phase4_service] = lambda: drug_response_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides = {}

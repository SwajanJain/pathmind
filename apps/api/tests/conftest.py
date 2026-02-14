from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pathmind_api.cache import InMemoryCache
from pathmind_api.database import Base, get_db
from pathmind_api.deps import get_analysis_service, get_cache
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


@pytest.fixture()
def client():
    app = create_app()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    cache = InMemoryCache()
    service = StubAnalysisService()

    def override_db():
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_cache] = lambda: cache
    app.dependency_overrides[get_analysis_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides = {}

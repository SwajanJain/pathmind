from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pathmind_api.database import Base
from pathmind_api.models import DatasetCacheMeta, DiliRankEntry
from pathmind_api.repositories import list_toxicity_pathway_gene_sets, upsert_tissue_expression_rows
from pathmind_api.etl.phase3_ingest import refresh_toxicity_gene_sets
from pathmind_api.services.dili_phase3 import DiliServicePhase3
from pathmind_api.services.herg_phase3 import HergServicePhase3
from pathmind_api.services.tissue_expression_phase3 import Phase3DatasetService, TissueExpressionServicePhase3
from pathmind_api.services.tissue_impact_phase3 import TissueImpactServicePhase3
from pathmind_api.services.toxcast_provider_phase3 import ConfiguredToxcastProvider, DisabledToxcastProvider


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    return Session()


class DummyChemblHerg:
    async def fetch_activities(self, drug_id: str):
        if drug_id == "CHEMBL553":
            return [
                {"target_chembl_id": "CHEMBL240", "pchembl_value": 7.0},
                {"target_chembl_id": "CHEMBL240", "pchembl_value": 6.8},
            ]
        return []


class DummyChemblImpact:
    async def fetch_activities(self, drug_id: str):
        return [{"target_chembl_id": "CHEMBL203", "pchembl_value": 8.0}]

    async def fetch_target_details(self, target_ids):
        return {"CHEMBL203": {"gene_symbol": "EGFR"}}


def test_herg_cmax_missing_yields_unknown_margin():
    service = HergServicePhase3(chembl=DummyChemblHerg(), cmax_free_lookup={})
    result = __import__("asyncio").run(service.evaluate("CHEMBL553"))
    assert result.herg_signal.state in {"positive", "negative"}
    assert result.margin_signal.state == "unknown"
    assert result.margin_signal.reason_code == "cmax_missing"


def test_dili_mapping_states():
    session = _session()
    session.add(
        DiliRankEntry(
            id="1",
            drug_name_norm="erlotinib",
            drug_name_original="Erlotinib",
            dili_category="Most-DILI-concern",
            source_url=None,
        )
    )
    session.commit()
    service = DiliServicePhase3()
    positive = service.evaluate(session, "erlotinib")
    assert positive.signal.state == "positive"
    unknown = service.evaluate(session, "not_in_list")
    assert unknown.signal.state == "unknown"


def test_dataset_status_reports_missing_and_stale():
    session = _session()
    stale_time = datetime.now(timezone.utc) - timedelta(days=500)
    session.add(
        DatasetCacheMeta(
            dataset_key="gtex",
            local_path="/tmp/gtex.tsv",
            checksum="abc",
            version="v1",
            fetched_at=stale_time,
        )
    )
    session.commit()
    service = Phase3DatasetService(required_datasets=["gtex", "hpa"])
    status = service.status(session)
    by_name = {item.dataset: item for item in status.datasets}
    assert by_name["gtex"].status == "stale"
    assert by_name["hpa"].status == "missing"


def test_tissue_expression_states():
    session = _session()
    upsert_tissue_expression_rows(
        session,
        [
            {
                "gene_symbol": "EGFR",
                "tissue": "Liver",
                "gtex_tpm": 10.0,
                "hpa_rna_nx": None,
                "hpa_protein_level": "Medium",
                "gtex_present": True,
                "hpa_present": True,
                "uniprot_id": "P00533",
            }
        ],
    )
    service = TissueExpressionServicePhase3()
    response = __import__("asyncio").run(service.by_gene(session, "EGFR"))
    assert response.expression[0].evidence.state in {"positive", "negative"}


def test_tissue_impact_unknown_when_inputs_missing():
    session = _session()
    service = TissueImpactServicePhase3(chembl=DummyChemblImpact(), top_tissues=["Liver"])
    result = __import__("asyncio").run(service.evaluate(session, "CHEMBL553"))
    assert result.cells[0].signal.state == "unknown"


def test_toxcast_disabled_provider_unknown():
    provider = DisabledToxcastProvider()
    result = __import__("asyncio").run(provider.summary_signal("CHEMBL553"))
    assert result.state == "unknown"
    assert result.reason_code == "provider_disabled"


def test_toxcast_configured_missing_key_unknown():
    provider = ConfiguredToxcastProvider(provider_name="epa", api_key=None)
    result = __import__("asyncio").run(provider.summary_signal("CHEMBL553"))
    assert result.state == "unknown"
    assert result.reason_code == "provider_missing_api_key"


def test_phase3_default_toxicity_gene_sets_count(tmp_path):
    session = _session()
    sync_result = refresh_toxicity_gene_sets(session, data_dir=str(tmp_path))
    rows = list_toxicity_pathway_gene_sets(session)
    assert sync_result.rows_upserted >= 10
    assert len(rows) >= 10

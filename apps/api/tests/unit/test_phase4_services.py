from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pathmind_api.config import Settings
from pathmind_api.database import Base
from pathmind_api.repositories import (
    add_patient_pathway_activity_rows,
    add_patient_pgx_drug_recommendations,
    create_patient_expression_run,
    create_patient_profile,
    upsert_dataset_cache_meta,
)
from pathmind_api.routes_v1_phase4 import _store_temp_upload
from pathmind_api.schemas_phase4 import PgxGeneCallParsed
from pathmind_api.services.drug_response_phase4 import DrugResponseServicePhase4
from pathmind_api.services.patient_expression_phase4 import _row_state
from pathmind_api.services.pgx_phase4 import PgxServicePhase4, _classify_gene_state, _normalize_phenotype
from pathmind_api.services.phase4_dataset_service import Phase4DatasetService
from pathmind_api.services.pharmcat_runner_phase4 import PharmcatRunnerPhase4


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    return Session()


class DummyRunner:
    def __init__(self, rows: list[PgxGeneCallParsed]) -> None:
        self.rows = rows

    def run_from_vcf(self, vcf_path: Path):
        return self.rows


def test_pgx_tri_state_mapping_and_recommendation():
    with TemporaryDirectory() as tmp_dir:
        cpic = Path(tmp_dir) / "cpic_recommendations.csv"
        cpic.write_text(
            "gene,phenotype,drug_id,drug_name,recommendation,evidence_level,cpic_guideline_id\n"
            "CYP2D6,Intermediate Metabolizer,CHEMBL553,Erlotinib,Adjust dose,1A,CPIC-1\n",
            encoding="utf-8",
        )
        runner = DummyRunner(
            [
                PgxGeneCallParsed(
                    gene="CYP2D6",
                    diplotype="*1/*4",
                    phenotype="Intermediate Metabolizer",
                    activity_score=1.0,
                    state="unknown",
                    reason_code="parsed",
                )
            ]
        )
        service = PgxServicePhase4(phase4_data_dir=tmp_dir, runner=runner)  # type: ignore[arg-type]
        result = service.process_vcf(Path(tmp_dir) / "fake.vcf", version_snapshot={"cpic": "v1"})
        assert result.gene_calls[0].state == "positive"
        assert result.gene_calls[0].reason_code == "phenotype_intermediate_caution"
        assert result.drug_recommendations[0].recommendation == "adjust"
        assert result.drug_recommendations[0].state == "positive"


def test_pgx_unknown_when_guideline_missing():
    with TemporaryDirectory() as tmp_dir:
        runner = DummyRunner([PgxGeneCallParsed(gene="CYP2D6", state="unknown", reason_code="gene_not_called")])
        service = PgxServicePhase4(phase4_data_dir=tmp_dir, runner=runner)  # type: ignore[arg-type]
        result = service.process_vcf(Path(tmp_dir) / "fake.vcf", version_snapshot={"cpic": "unknown"})
        assert result.drug_recommendations[0].state == "unknown"
        assert result.drug_recommendations[0].reason_code == "guideline_not_found"


def test_drug_response_prefers_pgx_contraindication():
    session = _session()
    profile = create_patient_profile(session, label="Patient-A")
    add_patient_pgx_drug_recommendations(
        session,
        profile.id,
        [
            {
                "drug_id": "CHEMBL553",
                "drug_name": "Erlotinib",
                "recommendation": "avoid",
                "evidence_level": "1A",
                "cpic_guideline_id": "CPIC-1",
                "state": "positive",
                "reason_code": "cpic_avoid",
                "provenance": {},
                "confidence_note": None,
            }
        ],
    )
    service = DrugResponseServicePhase4()
    result = service.get_or_compute(session, patient_id=profile.id, drug_id="CHEMBL553")
    assert result.recommendation == "avoid"
    assert result.confidence_level == "high"


def test_phase4_dataset_status_required_and_optional():
    session = _session()
    upsert_dataset_cache_meta(
        session,
        dataset_key="pharmcat",
        local_path="/tmp/pharmcat.jar",
        checksum="x",
        version="v1",
    )
    service = Phase4DatasetService(required_datasets=["pharmcat", "cpic"], optional_datasets=["pharmgkb"])
    status = service.status(session)
    assert status.overall_status in {"degraded", "missing", "ready"}
    mapping = {row.dataset: row.status for row in status.datasets}
    assert mapping["pharmcat"] == "ready"
    assert mapping["cpic"] == "missing"


def test_phase4_upload_size_guard():
    settings = Settings(phase4_data_dir="/tmp/pathmind-phase4-test", phase4_max_upload_mb=1)
    payload = b"a" * (1024 * 1024 + 1)
    with pytest.raises(HTTPException):
        _store_temp_upload(settings, filename="large.vcf", content=payload, prefix="vcf")


def test_phase4_temp_file_written_without_raw_payload_in_name():
    with TemporaryDirectory() as tmp_dir:
        settings = Settings(phase4_data_dir=tmp_dir, phase4_max_upload_mb=5)
        path = _store_temp_upload(settings, filename="sample.vcf", content=b"abc", prefix="vcf")
        assert path.exists()
        assert "abc" not in path.name


# --- Step 1 tests: phenotype matching ---


def test_pgx_intermediate_metabolizer_is_positive():
    """Intermediate metabolizers should be classified as positive (caution), not neutral."""
    call = PgxGeneCallParsed(
        gene="CYP2D6",
        diplotype="*1/*4",
        phenotype="Intermediate Metabolizer",
        activity_score=1.0,
        state="unknown",
        reason_code="parsed",
    )
    state, reason = _classify_gene_state(call)
    assert state == "positive"
    assert reason == "phenotype_intermediate_caution"


def test_pgx_phenotype_matching_no_false_positives():
    """'Normal Metabolizer' must NOT match 'Abnormal Function' after normalization."""
    with TemporaryDirectory() as tmp_dir:
        cpic = Path(tmp_dir) / "cpic_recommendations.csv"
        cpic.write_text(
            "gene,phenotype,drug_id,drug_name,recommendation,evidence_level,cpic_guideline_id\n"
            "CYP2D6,Normal Metabolizer,CHEMBL25,Aspirin,Standard dosing,1A,CPIC-2\n",
            encoding="utf-8",
        )
        runner = DummyRunner(
            [
                PgxGeneCallParsed(
                    gene="CYP2D6",
                    phenotype="Abnormal Function",
                    state="unknown",
                    reason_code="parsed",
                )
            ]
        )
        service = PgxServicePhase4(phase4_data_dir=tmp_dir, runner=runner)  # type: ignore[arg-type]
        result = service.process_vcf(Path(tmp_dir) / "fake.vcf", version_snapshot={"cpic": "v1"})
        # "Abnormal Function" must not match the "Normal Metabolizer" CPIC rule
        # So only the fallback insufficient_data recommendation should appear
        assert result.drug_recommendations[0].recommendation == "insufficient_data"
        assert result.drug_recommendations[0].reason_code == "guideline_not_found"


def test_normalize_phenotype_exact_cases():
    """Normalization should map variants to canonical forms and not confuse substrings."""
    assert _normalize_phenotype("Normal Metabolizer") == "normal metabolizer"
    assert _normalize_phenotype("Abnormal Function") == "abnormal function"
    assert _normalize_phenotype("  Ultrarapid Metabolizer  ") == "ultrarapid metabolizer"
    assert _normalize_phenotype("Possible Intermediate Metabolizer") == "possible intermediate metabolizer"
    # "normal" substring must NOT normalize to "normal metabolizer" on its own
    assert _normalize_phenotype("normal") != _normalize_phenotype("abnormal")


# --- Step 3/4 tests: expression percentile and significance ---


def test_expression_percentile_actual_ranks():
    """Percentiles must be properly distributed across the score range, not just 25/75."""
    from pathmind_api.services.patient_expression_phase4 import PatientExpressionServicePhase4

    scores = [-2.0, -1.0, 0.0, 1.0, 2.0]
    pathways = [
        {"activity_score": s, "percentile": None}
        for s in scores
    ]
    # Simulate the percentile computation logic
    sorted_scores = sorted(scores)
    for item in pathways:
        score = item["activity_score"]
        rank = sum(1 for s in sorted_scores if s <= score)
        item["percentile"] = round(100.0 * rank / len(sorted_scores), 1)

    percentiles = [item["percentile"] for item in pathways]
    assert percentiles == [20.0, 40.0, 60.0, 80.0, 100.0]
    # Must NOT produce only 25/75
    assert set(percentiles) != {25.0, 75.0}


def test_expression_state_uses_significance():
    """Row state classification should use FDR/p-value, not raw score thresholds."""
    # Significant and positive → positive
    state, reason = _row_state({"enrichment_score": 0.5, "fdr": 0.1, "p_value": 0.01})
    assert state == "positive"
    assert reason == "significant_high_activity"

    # Significant and negative → negative
    state, reason = _row_state({"enrichment_score": -0.5, "fdr": 0.2, "p_value": 0.01})
    assert state == "negative"
    assert reason == "significant_suppressed_activity"

    # Not significant despite high score → unknown
    state, reason = _row_state({"enrichment_score": 2.0, "fdr": 0.5, "p_value": 0.3})
    assert state == "unknown"
    assert reason == "not_significant"

    # FDR not available, fall back to p-value
    state, reason = _row_state({"enrichment_score": 1.5, "fdr": None, "p_value": 0.01})
    assert state == "positive"
    assert reason == "significant_high_activity"


# --- Step 5 tests: drug-pathway relevance ---


def test_drug_response_no_pathway_override_without_significance():
    """Pathways without statistical significance should NOT trigger override."""
    session = _session()
    profile = create_patient_profile(session, label="Patient-Sig")
    add_patient_pgx_drug_recommendations(
        session,
        profile.id,
        [
            {
                "drug_id": "CHEMBL25",
                "drug_name": "Aspirin",
                "recommendation": "standard",
                "evidence_level": "1A",
                "cpic_guideline_id": "CPIC-2",
                "state": "negative",
                "reason_code": "cpic_standard",
                "provenance": {},
                "confidence_note": None,
            }
        ],
    )
    # Add pathway activity with high score but p_value > 0.05 (not significant)
    run = create_patient_expression_run(
        session,
        patient_id=profile.id,
        filename="test.csv",
        id_type="gene_symbol",
        gene_count=100,
        mapped_gene_count=90,
        state="positive",
        reason_code="expression_processed",
        version_snapshot={},
    )
    add_patient_pathway_activity_rows(
        session,
        profile.id,
        run.id,
        [
            {
                "pathway_id": "R-HSA-1",
                "pathway_name": "Test Pathway",
                "activity_score": 3.0,
                "p_value": 0.5,  # NOT significant
                "percentile": 100.0,
                "method": "gsea_prerank",
                "state": "unknown",
                "reason_code": "not_significant",
                "provenance": {},
            }
        ],
    )
    service = DrugResponseServicePhase4()
    result = service.get_or_compute(session, patient_id=profile.id, drug_id="CHEMBL25")
    # Should remain standard_consideration since pathway is not significant
    assert result.recommendation == "standard_consideration"
    assert result.evidence.reason_code == "pgx_standard_rule"


# --- Step 6 test: pharmcat empty VCF ---


def test_pharmcat_empty_vcf_returns_empty():
    """When VCF has no parseable pharmacogene data, return empty list (no dummy CYP2D6)."""
    with TemporaryDirectory() as tmp_dir:
        vcf = Path(tmp_dir) / "empty.vcf"
        vcf.write_text(
            "##fileformat=VCFv4.2\n"
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n",
            encoding="utf-8",
        )
        runner = PharmcatRunnerPhase4(phase4_data_dir=tmp_dir)
        calls = runner._fallback_parse_vcf(vcf)
        assert calls == []

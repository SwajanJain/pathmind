from functools import lru_cache

from pathmind_api.cache import CacheBackend, build_cache
from pathmind_api.clients import AOPWikiClient, ChEMBLClient, GTExClient, HPAClient, OpenTargetsClient, PubChemClient, ReactomeClient, UniProtClient
from pathmind_api.config import Settings, get_settings
from pathmind_api.database import SessionLocal
from pathmind_api.services import (
    AopServicePhase3,
    CausalChainService,
    ConfiguredLincsProvider,
    ConfiguredToxcastProvider,
    DisabledLincsProvider,
    DisabledToxcastProvider,
    DiliServicePhase3,
    DrugResponseServicePhase4,
    EnrichmentService,
    ExpressionIngestService,
    HergServicePhase3,
    JobService,
    LincsProvider,
    PatientExpressionServicePhase4,
    PatientProfileServicePhase4,
    Phase4DatasetService,
    PharmcatRunnerPhase4,
    Phase3DatasetService,
    PgxServicePhase4,
    PredictTargetsService,
    SelectivityService,
    TissueExpressionServicePhase3,
    TissueImpactServicePhase3,
    ToxcastProvider,
    ToxicityServicePhase3,
    TfActivityService,
)
from pathmind_api.service import AnalysisService


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_cache() -> CacheBackend:
    settings = get_settings()
    return build_cache(settings.redis_url)


@lru_cache(maxsize=1)
def get_analysis_service() -> AnalysisService:
    settings: Settings = get_settings()
    chembl = ChEMBLClient("chembl", settings.chembl_base_url, timeout_seconds=settings.http_timeout_seconds)
    pubchem = PubChemClient("pubchem", settings.pubchem_base_url, timeout_seconds=settings.http_timeout_seconds)
    uniprot = UniProtClient("uniprot", settings.uniprot_base_url, timeout_seconds=settings.http_timeout_seconds)
    reactome = ReactomeClient("reactome", settings.reactome_base_url, timeout_seconds=settings.http_timeout_seconds)
    opentargets = OpenTargetsClient("opentargets", settings.opentargets_base_url, timeout_seconds=settings.http_timeout_seconds)
    return AnalysisService(
        chembl=chembl,
        pubchem=pubchem,
        uniprot=uniprot,
        reactome=reactome,
        opentargets=opentargets,
        session_factory=SessionLocal,
    )


@lru_cache(maxsize=1)
def get_job_service() -> JobService:
    settings = get_settings()
    return JobService(session_factory=SessionLocal, max_concurrency=settings.phase2_jobs_max_concurrency)


@lru_cache(maxsize=1)
def get_predict_targets_service() -> PredictTargetsService:
    settings: Settings = get_settings()
    chembl = ChEMBLClient("chembl", settings.chembl_base_url, timeout_seconds=settings.http_timeout_seconds)
    reactome = ReactomeClient("reactome", settings.reactome_base_url, timeout_seconds=settings.http_timeout_seconds)
    return PredictTargetsService(chembl=chembl, reactome=reactome)


@lru_cache(maxsize=1)
def get_selectivity_service() -> SelectivityService:
    settings: Settings = get_settings()
    chembl = ChEMBLClient("chembl", settings.chembl_base_url, timeout_seconds=settings.http_timeout_seconds)
    return SelectivityService(chembl=chembl)


@lru_cache(maxsize=1)
def get_expression_ingest_service() -> ExpressionIngestService:
    settings: Settings = get_settings()
    uniprot = UniProtClient("uniprot", settings.uniprot_base_url, timeout_seconds=settings.http_timeout_seconds)
    return ExpressionIngestService(uniprot=uniprot, phase2_data_dir=settings.phase2_data_dir)


@lru_cache(maxsize=1)
def get_enrichment_service() -> EnrichmentService:
    settings = get_settings()
    return EnrichmentService(phase2_data_dir=settings.phase2_data_dir, random_seed=settings.enrichment_random_seed)


@lru_cache(maxsize=1)
def get_tf_activity_service() -> TfActivityService:
    settings = get_settings()
    return TfActivityService(phase2_data_dir=settings.phase2_data_dir)


@lru_cache(maxsize=1)
def get_causal_chain_service() -> CausalChainService:
    settings: Settings = get_settings()
    chembl = ChEMBLClient("chembl", settings.chembl_base_url, timeout_seconds=settings.http_timeout_seconds)
    return CausalChainService(chembl=chembl, phase2_data_dir=settings.phase2_data_dir)


@lru_cache(maxsize=1)
def get_lincs_provider() -> LincsProvider:
    settings = get_settings()
    provider = (settings.lincs_provider or "disabled").strip().lower()
    if provider == "disabled":
        return DisabledLincsProvider()
    return ConfiguredLincsProvider(provider_name=provider)


@lru_cache(maxsize=1)
def get_gtex_client() -> GTExClient:
    settings = get_settings()
    return GTExClient("gtex", settings.gtex_base_url, timeout_seconds=settings.http_timeout_seconds)


@lru_cache(maxsize=1)
def get_hpa_client() -> HPAClient:
    settings = get_settings()
    return HPAClient("hpa", settings.hpa_base_url, timeout_seconds=settings.http_timeout_seconds)


@lru_cache(maxsize=1)
def get_aopwiki_client() -> AOPWikiClient:
    settings = get_settings()
    return AOPWikiClient("aopwiki", settings.aopwiki_base_url, timeout_seconds=settings.http_timeout_seconds)


@lru_cache(maxsize=1)
def get_phase3_dataset_service() -> Phase3DatasetService:
    settings = get_settings()
    return Phase3DatasetService(required_datasets=_split_csv(settings.phase3_required_datasets))


@lru_cache(maxsize=1)
def get_tissue_expression_phase3_service() -> TissueExpressionServicePhase3:
    settings = get_settings()
    return TissueExpressionServicePhase3(
        top_tissues=_split_csv(settings.phase3_top_tissues),
        gtex_client=get_gtex_client(),
        hpa_client=get_hpa_client(),
        cache_ttl_hours=settings.phase3_tissue_cache_ttl_hours,
    )


@lru_cache(maxsize=1)
def get_herg_phase3_service() -> HergServicePhase3:
    settings: Settings = get_settings()
    chembl = ChEMBLClient("chembl", settings.chembl_base_url, timeout_seconds=settings.http_timeout_seconds)
    return HergServicePhase3(chembl=chembl)


@lru_cache(maxsize=1)
def get_dili_phase3_service() -> DiliServicePhase3:
    return DiliServicePhase3()


@lru_cache(maxsize=1)
def get_aop_phase3_service() -> AopServicePhase3:
    settings: Settings = get_settings()
    chembl = ChEMBLClient("chembl", settings.chembl_base_url, timeout_seconds=settings.http_timeout_seconds)
    return AopServicePhase3(chembl=chembl)


@lru_cache(maxsize=1)
def get_toxcast_provider() -> ToxcastProvider:
    settings = get_settings()
    provider = (settings.toxcast_provider or "disabled").strip().lower()
    if provider == "disabled":
        return DisabledToxcastProvider()
    return ConfiguredToxcastProvider(
        provider_name=provider,
        api_key=settings.toxcast_api_key,
        timeout_seconds=settings.http_timeout_seconds,
    )


@lru_cache(maxsize=1)
def get_toxicity_phase3_service() -> ToxicityServicePhase3:
    settings: Settings = get_settings()
    chembl = ChEMBLClient("chembl", settings.chembl_base_url, timeout_seconds=settings.http_timeout_seconds)
    return ToxicityServicePhase3(
        chembl=chembl,
        herg_service=get_herg_phase3_service(),
        dili_service=get_dili_phase3_service(),
        toxcast_provider=get_toxcast_provider(),
    )


@lru_cache(maxsize=1)
def get_tissue_impact_phase3_service() -> TissueImpactServicePhase3:
    settings: Settings = get_settings()
    chembl = ChEMBLClient("chembl", settings.chembl_base_url, timeout_seconds=settings.http_timeout_seconds)
    return TissueImpactServicePhase3(
        chembl=chembl,
        top_tissues=_split_csv(settings.phase3_top_tissues),
        gtex_client=get_gtex_client(),
        hpa_client=get_hpa_client(),
        cache_ttl_hours=settings.phase3_tissue_cache_ttl_hours,
    )


@lru_cache(maxsize=1)
def get_phase4_dataset_service() -> Phase4DatasetService:
    settings = get_settings()
    return Phase4DatasetService(
        required_datasets=_split_csv(settings.phase4_required_datasets),
        optional_datasets=_split_csv(settings.phase4_optional_datasets),
    )


@lru_cache(maxsize=1)
def get_patient_profile_phase4_service() -> PatientProfileServicePhase4:
    return PatientProfileServicePhase4()


@lru_cache(maxsize=1)
def get_pharmcat_runner_phase4() -> PharmcatRunnerPhase4:
    settings = get_settings()
    return PharmcatRunnerPhase4(
        phase4_data_dir=settings.phase4_data_dir,
        java_bin=settings.phase4_java_bin,
        pharmcat_jar_path=settings.phase4_pharmcat_jar_path,
        timeout_seconds=settings.phase4_vcf_timeout_sec,
    )


@lru_cache(maxsize=1)
def get_pgx_phase4_service() -> PgxServicePhase4:
    settings = get_settings()
    return PgxServicePhase4(phase4_data_dir=settings.phase4_data_dir, runner=get_pharmcat_runner_phase4())


@lru_cache(maxsize=1)
def get_patient_expression_phase4_service() -> PatientExpressionServicePhase4:
    return PatientExpressionServicePhase4(
        ingest_service=get_expression_ingest_service(),
        enrichment_service=get_enrichment_service(),
    )


@lru_cache(maxsize=1)
def get_drug_response_phase4_service() -> DrugResponseServicePhase4:
    return DrugResponseServicePhase4()

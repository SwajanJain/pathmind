from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PATHMIND_")

    environment: str = "development"
    database_url: str = "sqlite:///./pathmind.db"
    redis_url: str = "redis://localhost:6379/0"
    http_timeout_seconds: float = 15.0
    cache_ttl_analysis_seconds: int = 60 * 60 * 24
    cache_ttl_short_seconds: int = 60 * 60
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    chembl_base_url: str = "https://www.ebi.ac.uk/chembl/api/data"
    pubchem_base_url: str = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
    uniprot_base_url: str = "https://rest.uniprot.org"
    reactome_base_url: str = "https://reactome.org/ContentService"
    opentargets_base_url: str = "https://api.platform.opentargets.org/api/v4"
    phase2_data_dir: str = "./data/phase2"
    phase2_jobs_max_concurrency: int = 2
    lincs_provider: str = "disabled"
    lincs_api_key: str | None = None
    enrichment_random_seed: int = 42
    phase3_data_dir: str = "./data/phase3"
    phase3_required_datasets: str = "gtex,hpa,dilirank,aopwiki"
    toxcast_provider: str = "disabled"
    toxcast_api_key: str | None = None
    phase3_top_tissues: str = "Liver,Heart,Brain,Kidney,Lung,Intestine,Blood,Adipose Tissue"
    gtex_base_url: str = "https://gtexportal.org/api/v2"
    hpa_base_url: str = "https://www.proteinatlas.org"
    aopwiki_base_url: str = "https://aopwiki.org"
    phase3_auto_seed: bool = True
    phase3_tissue_cache_ttl_hours: int = 168  # 7 days
    phase4_data_dir: str = "./data/phase4"
    phase4_required_datasets: str = "pharmcat,cpic,hgnc,progeny"
    phase4_optional_datasets: str = "pharmgkb"
    phase4_temp_ttl_hours: int = 24
    phase4_max_upload_mb: int = 100
    phase4_vcf_timeout_sec: int = 120
    phase4_java_bin: str = "java"
    phase4_pharmcat_jar_path: str | None = None
    phase4_enable_patient_sharing: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

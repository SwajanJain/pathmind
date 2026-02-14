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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


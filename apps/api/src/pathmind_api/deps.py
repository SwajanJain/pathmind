from functools import lru_cache

from pathmind_api.cache import CacheBackend, build_cache
from pathmind_api.clients import ChEMBLClient, OpenTargetsClient, PubChemClient, ReactomeClient, UniProtClient
from pathmind_api.config import Settings, get_settings
from pathmind_api.database import SessionLocal
from pathmind_api.service import AnalysisService


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

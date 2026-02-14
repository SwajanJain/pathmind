"""Startup auto-seeder for Phase 3 static datasets.

Called once from ``main.py`` during the ``startup`` event. Idempotent — only
seeds tables that are empty. Non-fatal on API errors so the app always boots.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from pathmind_api import models
from pathmind_api.clients.aopwiki import AOPWikiClient
from pathmind_api.etl.phase3_ingest import _DEFAULT_TOXICITY_GENE_SETS
from pathmind_api.repositories import (
    upsert_aop_chains,
    upsert_dataset_cache_meta,
    upsert_dili_rank_entries,
    upsert_source_release_version,
    upsert_toxicity_pathway_gene_sets,
)
from pathmind_api.services.dili_data import DILIRANK_ENTRIES

log = logging.getLogger(__name__)


def _table_empty(session: Session, model: Any) -> bool:
    count = session.execute(select(func.count()).select_from(model)).scalar() or 0
    return count == 0


def _record_api_dataset(session: Session, dataset_key: str, version: str) -> None:
    """Register an API-sourced dataset in cache-meta so status endpoint reports 'ready'."""
    upsert_dataset_cache_meta(
        session,
        dataset_key=dataset_key,
        local_path="api-live",
        checksum=None,
        version=version,
    )
    upsert_source_release_version(session, dataset_key, version)


async def auto_seed_phase3(
    session_factory: sessionmaker,
    *,
    aopwiki_client: AOPWikiClient | None = None,
) -> dict:
    """Seed Phase 3 reference data on first startup.

    Returns a summary dict: ``{dataset: rows_seeded, ...}``.
    """
    summary: dict[str, int] = {}

    # 1. DILIrank
    try:
        session: Session = session_factory()
        try:
            if _table_empty(session, models.DiliRankEntry):
                count = upsert_dili_rank_entries(session, DILIRANK_ENTRIES)
                _record_api_dataset(session, "dilirank", "bundled-v1")
                summary["dilirank"] = count
                log.info("Auto-seeded %d DILIrank entries", count)
            else:
                log.debug("DILIrank table already populated — skipping")
        finally:
            session.close()
    except Exception:
        log.exception("Failed to auto-seed DILIrank (non-fatal)")

    # 2. Toxicity pathway gene sets
    try:
        session = session_factory()
        try:
            if _table_empty(session, models.ToxicityPathwayGeneSet):
                count = upsert_toxicity_pathway_gene_sets(session, _DEFAULT_TOXICITY_GENE_SETS)
                _record_api_dataset(session, "toxicity_gene_sets", "default")
                summary["toxicity_gene_sets"] = count
                log.info("Auto-seeded %d toxicity gene sets", count)
            else:
                log.debug("Toxicity gene sets table already populated — skipping")
        finally:
            session.close()
    except Exception:
        log.exception("Failed to auto-seed toxicity gene sets (non-fatal)")

    # 3. AOP chains from AOPWiki API
    if aopwiki_client is not None:
        try:
            session = session_factory()
            try:
                if _table_empty(session, models.AopChain):
                    rows = await aopwiki_client.fetch_all_aops()
                    if rows:
                        count = upsert_aop_chains(session, rows)
                        _record_api_dataset(session, "aopwiki", f"api-{datetime.now(timezone.utc).strftime('%Y%m%d')}")
                        summary["aop_chains"] = count
                        log.info("Auto-seeded %d AOP chains from AOPWiki API", count)
                    else:
                        log.warning("AOPWiki API returned 0 chains — skipping seed")
                else:
                    log.debug("AOP chains table already populated — skipping")
            finally:
                session.close()
        except Exception:
            log.exception("Failed to auto-seed AOP chains from API (non-fatal)")

    # 4. Register GTEx + HPA as api-live so the status endpoint doesn't report "missing"
    try:
        session = session_factory()
        try:
            for ds_key in ("gtex", "hpa"):
                existing = session.get(models.DatasetCacheMeta, ds_key)
                if existing is None:
                    _record_api_dataset(session, ds_key, "api-live")
                    log.debug("Registered %s as api-live in dataset_cache_meta", ds_key)
        finally:
            session.close()
    except Exception:
        log.exception("Failed to register GTEx/HPA api-live markers (non-fatal)")

    if summary:
        log.info("Phase 3 auto-seed complete: %s", summary)
    else:
        log.info("Phase 3 auto-seed: all tables already populated")

    return summary

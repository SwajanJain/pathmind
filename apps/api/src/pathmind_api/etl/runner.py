import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from pathmind_api.clients import ReactomeClient
from pathmind_api.clients.base import DownstreamError
from pathmind_api.config import get_settings
from pathmind_api.database import SessionLocal
from pathmind_api.repositories import (
    finish_etl_run,
    get_recent_uniprot_targets,
    list_mapped_uniprot_targets,
    purge_old_api_logs,
    start_etl_run,
    upsert_source_release_version,
    upsert_target_pathway_rows,
)


@dataclass
class EtlRunSummary:
    run_id: str
    status: str
    mode: str
    targets_total: int
    targets_processed: int
    rows_upserted: int
    failures: int
    release_version: str


async def run_reactome_etl(
    *,
    mode: str = "nightly",
    max_targets: int = 5000,
    seed_uniprot_ids: list[str] | None = None,
) -> EtlRunSummary:
    settings = get_settings()
    session = SessionLocal()
    reactome = ReactomeClient("reactome", settings.reactome_base_url, timeout_seconds=settings.http_timeout_seconds)
    run = start_etl_run(session, source_name="reactome", mode=mode)

    seed_targets = {item.strip() for item in (seed_uniprot_ids or []) if item and item.strip()}
    mapped_targets = set(list_mapped_uniprot_targets(session, max_items=max_targets))
    recent_targets = set(get_recent_uniprot_targets(session, max_items=max_targets))
    targets = sorted(seed_targets | mapped_targets | recent_targets)

    processed = 0
    rows_upserted = 0
    failures: list[dict[str, str]] = []

    try:
        for uniprot_id in targets:
            try:
                pathways = await reactome.pathways_for_uniprot(uniprot_id)
            except DownstreamError as exc:
                failures.append({"uniprot_id": uniprot_id, "error": str(exc)})
                continue
            processed += 1
            rows_upserted += upsert_target_pathway_rows(session, uniprot_id, pathways)

        try:
            release_version = await reactome.fetch_release_version()
        except DownstreamError:
            release_version = f"unknown-{datetime.now(timezone.utc).date().isoformat()}"
        upsert_source_release_version(session, "reactome", release_version)

        details = {
            "targets_total": len(targets),
            "targets_processed": processed,
            "failures": failures[:100],
            "failure_count": len(failures),
            "release_version": release_version,
            "resumable": True,
            "idempotent": True,
        }
        finish_etl_run(
            session,
            run.id,
            status="completed",
            rows_upserted=rows_upserted,
            details=details,
        )
        return EtlRunSummary(
            run_id=run.id,
            status="completed",
            mode=mode,
            targets_total=len(targets),
            targets_processed=processed,
            rows_upserted=rows_upserted,
            failures=len(failures),
            release_version=release_version,
        )
    except Exception as exc:
        finish_etl_run(
            session,
            run.id,
            status="failed",
            rows_upserted=rows_upserted,
            details={"error": str(exc), "targets_total": len(targets), "targets_processed": processed},
        )
        raise
    finally:
        session.close()
        await reactome.close()


def run_reactome_etl_sync(
    *,
    mode: str = "nightly",
    max_targets: int = 5000,
    seed_uniprot_ids: list[str] | None = None,
) -> EtlRunSummary:
    return asyncio.run(run_reactome_etl(mode=mode, max_targets=max_targets, seed_uniprot_ids=seed_uniprot_ids))


def run_retention_purge(*, retention_days: int = 90) -> dict[str, int]:
    session = SessionLocal()
    try:
        deleted = purge_old_api_logs(session, retention_days=retention_days)
    finally:
        session.close()
    return {"retention_days": retention_days, "deleted_rows": deleted}


def summary_to_dict(summary: EtlRunSummary) -> dict:
    return asdict(summary)

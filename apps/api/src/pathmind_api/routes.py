import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from pathmind_api.cache import CacheBackend
from pathmind_api.config import Settings, get_settings
from pathmind_api.database import get_db
from pathmind_api.deps import get_analysis_service, get_cache
from pathmind_api.privacy import anonymize_ip
from pathmind_api.repositories import (
    cache_hit_rate_from_logs,
    cache_resolution,
    create_analysis,
    create_share_link,
    get_analysis,
    get_share_payload,
    latest_source_timestamp,
    log_api_event,
)
from pathmind_api.schemas import (
    AnalyticsEventRequest,
    AnalysisResult,
    AnalysisRunRequest,
    ApiDependencyHealth,
    ApiHealthStatus,
    CompareResult,
    CompareRunRequest,
    DrugResolveRequest,
    DrugResolveResponse,
    DrugSuggestResponse,
    ExportMetadata,
    JsonExportResponse,
    ShareResponse,
)
from pathmind_api.service import AmbiguousDrugError, AnalysisService, FatalAnalysisError

router = APIRouter(prefix="/api", tags=["pathmind"])


def _cache_key(request: AnalysisRunRequest) -> str:
    serialized = json.dumps(request.model_dump(mode="json"), sort_keys=True)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"analysis:{digest}"


def _request_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return anonymize_ip(forwarded.split(",")[0].strip())
    if request.client is None:
        return None
    return anonymize_ip(request.client.host)


def _export_metadata(analysis: AnalysisResult) -> ExportMetadata:
    return ExportMetadata(
        analysis_id=analysis.analysis_id,
        created_at=analysis.created_at,
        params=analysis.params,
        attribution=analysis.attribution,
        source_versions=analysis.source_versions,
        version_snapshot=analysis.version_snapshot,
        analysis_flags=analysis.analysis_flags,
        export_manifest=analysis.export_manifest,
    )


@router.get("/health", response_model=ApiHealthStatus)
async def health_endpoint(
    request: Request,
    service: AnalysisService = Depends(get_analysis_service),
    db: Session = Depends(get_db),
) -> ApiHealthStatus:
    health = await service.health()
    etl_last_run = latest_source_timestamp(db)
    if etl_last_run is not None and etl_last_run.tzinfo is None:
        etl_last_run = etl_last_run.replace(tzinfo=timezone.utc)
    status = health["status"]
    if etl_last_run is None or etl_last_run < datetime.now(timezone.utc) - timedelta(hours=36):
        if status == "healthy":
            status = "degraded"
    client_ip = _request_ip(request)
    for source_name, value in health["checks"].items():
        log_api_event(
            db,
            source=source_name,
            status=value.status,
            latency_ms=value.latency_ms,
            error_code=value.error,
            client_ip=client_ip,
        )
    return ApiHealthStatus(
        status=status,
        apis={
            name: ApiDependencyHealth(status=value.status, latency_ms=value.latency_ms, error=value.error)
            for name, value in health["checks"].items()
        },
        cache_hit_rate=cache_hit_rate_from_logs(db),
        etl_last_run=etl_last_run,
    )


@router.get("/drugs/suggest", response_model=DrugSuggestResponse)
async def suggest_drugs(q: str, service: AnalysisService = Depends(get_analysis_service)) -> DrugSuggestResponse:
    if len(q.strip()) < 2:
        return DrugSuggestResponse(query=q, suggestions=[])
    suggestions = await service.suggest(q)
    return DrugSuggestResponse(query=q, suggestions=suggestions)


@router.post("/drugs/resolve", response_model=DrugResolveResponse)
async def resolve_drug(payload: DrugResolveRequest, service: AnalysisService = Depends(get_analysis_service)) -> DrugResolveResponse:
    try:
        resolution, candidates = await service.resolve_drug_identity(payload.query, payload.resolution_choice)
    except AmbiguousDrugError as exc:
        return DrugResolveResponse(query=payload.query, status="ambiguous", candidates=exc.candidates)
    except ValueError as exc:
        if "No ChEMBL molecule found" in str(exc):
            return DrugResolveResponse(query=payload.query, status="not_found", candidates=[])
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DrugResolveResponse(query=payload.query, status="resolved", resolution=resolution, candidates=candidates)


@router.post("/analysis/run", response_model=AnalysisResult)
async def run_analysis(
    payload: AnalysisRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    cache: CacheBackend = Depends(get_cache),
    settings: Settings = Depends(get_settings),
    service: AnalysisService = Depends(get_analysis_service),
) -> AnalysisResult:
    client_ip = _request_ip(request)
    key = _cache_key(payload)
    if not payload.do_not_log:
        cached_payload = cache.get(key)
        if cached_payload is not None:
            log_api_event(db, source="cache", status="hit", client_ip=client_ip)
            return AnalysisResult.model_validate(cached_payload)
        log_api_event(db, source="cache", status="miss", client_ip=client_ip)

    try:
        result = await service.run_analysis(payload.drug_name, payload.params, resolution_choice=payload.resolution_choice)
    except AmbiguousDrugError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "candidates": [candidate.model_dump(mode="json") for candidate in exc.candidates]},
        ) from exc
    except FatalAnalysisError as exc:
        log_api_event(db, source="analysis", status="error", error_code="fatal", details=str(exc), client_ip=client_ip)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        log_api_event(db, source="analysis", status="error", error_code="not_found", details=str(exc), client_ip=client_ip)
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not payload.do_not_log:
        create_analysis(db, result)
        cache_resolution(db, result.resolution)
        log_api_event(db, source="analysis", status="stored", client_ip=client_ip)
        cache.set(key, result.model_dump(mode="json"), ttl_seconds=settings.cache_ttl_analysis_seconds)
    else:
        log_api_event(db, source="analysis", status="privacy_mode", details="do_not_log enabled", client_ip=client_ip)
        cache.set(f"analysis-id:{result.analysis_id}", result.model_dump(mode="json"), ttl_seconds=settings.cache_ttl_short_seconds)
    return result


@router.get("/analysis/{analysis_id}", response_model=AnalysisResult)
def get_analysis_result(analysis_id: str, db: Session = Depends(get_db), cache: CacheBackend = Depends(get_cache)) -> AnalysisResult:
    result = get_analysis(db, analysis_id)
    if result is None:
        cached = cache.get(f"analysis-id:{analysis_id}")
        if cached is None:
            raise HTTPException(status_code=404, detail="Analysis not found")
        return AnalysisResult.model_validate(cached)
    return result


@router.post("/analysis/{analysis_id}/share", response_model=ShareResponse)
def share_analysis(analysis_id: str, request: Request, db: Session = Depends(get_db)) -> ShareResponse:
    analysis = get_analysis(db, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    link = create_share_link(db, analysis_id)
    base_url = str(request.base_url).rstrip("/")
    return ShareResponse(
        share_id=link.id,
        analysis_id=analysis_id,
        public_url=f"{base_url}/api/share/{link.id}",
        created_at=link.created_at,
    )


@router.get("/share/{share_id}", response_model=AnalysisResult)
def get_share(share_id: str, db: Session = Depends(get_db)) -> AnalysisResult:
    result = get_share_payload(db, share_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Share link not found")
    return result


@router.post("/analytics/event", status_code=204)
def analytics_event(payload: AnalyticsEventRequest, request: Request, db: Session = Depends(get_db)) -> Response:
    client_ip = _request_ip(request)
    log_api_event(
        db,
        source="analytics",
        status="accepted",
        details=f"{payload.event_name}:{payload.page_path}"[:500],
        client_ip=client_ip,
    )
    return Response(status_code=204)


@router.get("/analysis/{analysis_id}/export.csv", response_class=PlainTextResponse)
def export_analysis_csv(analysis_id: str, db: Session = Depends(get_db), cache: CacheBackend = Depends(get_cache)) -> PlainTextResponse:
    analysis = get_analysis_result(analysis_id=analysis_id, db=db, cache=cache)
    metadata = _export_metadata(analysis)

    lines = [
        "# pathmind_export_version: 1",
        f"# analysis_id: {metadata.analysis_id}",
        f"# created_at: {metadata.created_at.isoformat()}",
        f"# params: {json.dumps(metadata.params.model_dump(mode='json'), sort_keys=True)}",
        f"# source_versions: {json.dumps(metadata.source_versions, sort_keys=True)}",
        f"# version_snapshot: {json.dumps(metadata.version_snapshot, sort_keys=True)}",
        f"# analysis_flags: {json.dumps(metadata.analysis_flags.model_dump(mode='json'), sort_keys=True)}",
        f"# attribution: {metadata.attribution}",
    ]
    header = "pathway_id,pathway_name,score,targets_hit,coverage_ratio,depth,pathway_size,median_pchembl,reactome_url"
    rows = [
        ",".join(
            [
                pathway.pathway_id,
                f"\"{pathway.pathway_name.replace('"', '""')}\"",
                f"{pathway.score}",
                str(pathway.targets_hit),
                str(pathway.coverage_ratio),
                str(pathway.depth),
                str(pathway.pathway_size),
                str(pathway.median_pchembl),
                pathway.reactome_url,
            ]
        )
        for pathway in analysis.pathways
    ]
    payload = "\n".join(lines + [header] + rows)
    return PlainTextResponse(
        payload,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{analysis.analysis_id}-pathways.csv"'},
    )


@router.get("/analysis/{analysis_id}/export.json", response_model=JsonExportResponse)
def export_analysis_json(analysis_id: str, db: Session = Depends(get_db), cache: CacheBackend = Depends(get_cache)) -> JsonExportResponse:
    analysis = get_analysis_result(analysis_id=analysis_id, db=db, cache=cache)
    return JsonExportResponse(metadata=_export_metadata(analysis), analysis=analysis)


@router.post("/compare/run", response_model=CompareResult)
async def compare(
    payload: CompareRunRequest,
    service: AnalysisService = Depends(get_analysis_service),
) -> CompareResult:
    try:
        return await service.compare(payload.drug_a, payload.drug_b, payload.params)
    except AmbiguousDrugError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "candidates": [candidate.model_dump(mode="json") for candidate in exc.candidates]},
        ) from exc
    except FatalAnalysisError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

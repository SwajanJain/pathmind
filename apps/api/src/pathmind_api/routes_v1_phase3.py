import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from pathmind_api.database import get_db
from pathmind_api.deps import (
    get_aop_phase3_service,
    get_herg_phase3_service,
    get_job_service,
    get_phase3_dataset_service,
    get_tissue_expression_phase3_service,
    get_tissue_impact_phase3_service,
    get_toxicity_phase3_service,
)
from pathmind_api.etl.runner import run_phase3_dataset_sync
from pathmind_api.schemas_phase2 import JobCreateResponse
from pathmind_api.schemas_phase3 import (
    AopResponse,
    HergResponse,
    PathwayExpressionResponse,
    Phase3DatasetStatusResponse,
    Phase3DatasetSyncRequest,
    TissueExpressionResponse,
    TissueImpactResponse,
    ToxicityResponse,
)
from pathmind_api.services import (
    AopServicePhase3,
    HergServicePhase3,
    JobService,
    Phase3DatasetService,
    TissueExpressionServicePhase3,
    TissueImpactServicePhase3,
    ToxicityServicePhase3,
)

router_v1_phase3 = APIRouter(prefix="/api/v1", tags=["pathmind-phase3"])


@router_v1_phase3.get("/tissue-expression/{gene}", response_model=TissueExpressionResponse)
async def tissue_expression_by_gene(
    gene: str,
    db: Session = Depends(get_db),
    service: TissueExpressionServicePhase3 = Depends(get_tissue_expression_phase3_service),
) -> TissueExpressionResponse:
    return await service.by_gene(db, gene)


@router_v1_phase3.get("/tissue-expression/pathway/{pathway_id}", response_model=PathwayExpressionResponse)
async def tissue_expression_by_pathway(
    pathway_id: str,
    db: Session = Depends(get_db),
    service: TissueExpressionServicePhase3 = Depends(get_tissue_expression_phase3_service),
) -> PathwayExpressionResponse:
    return await service.for_pathway(db, pathway_id)


@router_v1_phase3.get("/herg/{drug_id}", response_model=HergResponse)
async def herg_signal(
    drug_id: str,
    service: HergServicePhase3 = Depends(get_herg_phase3_service),
) -> HergResponse:
    return await service.evaluate(drug_id)


@router_v1_phase3.get("/toxicity/{drug_id}", response_model=ToxicityResponse)
async def toxicity_summary(
    drug_id: str,
    db: Session = Depends(get_db),
    service: ToxicityServicePhase3 = Depends(get_toxicity_phase3_service),
) -> ToxicityResponse:
    return await service.evaluate(db, drug_id)


@router_v1_phase3.get("/toxicity/{drug_id}/aop", response_model=AopResponse)
async def toxicity_aop(
    drug_id: str,
    db: Session = Depends(get_db),
    service: AopServicePhase3 = Depends(get_aop_phase3_service),
) -> AopResponse:
    return await service.evaluate(db, drug_id)


@router_v1_phase3.get("/tissue-impact/{drug_id}", response_model=TissueImpactResponse)
async def tissue_impact(
    drug_id: str,
    db: Session = Depends(get_db),
    service: TissueImpactServicePhase3 = Depends(get_tissue_impact_phase3_service),
) -> TissueImpactResponse:
    return await service.evaluate(db, drug_id)


@router_v1_phase3.get("/datasets/phase3/status", response_model=Phase3DatasetStatusResponse)
def phase3_dataset_status(
    db: Session = Depends(get_db),
    service: Phase3DatasetService = Depends(get_phase3_dataset_service),
) -> Phase3DatasetStatusResponse:
    return service.status(db)


@router_v1_phase3.post("/datasets/phase3/sync", response_model=JobCreateResponse)
async def phase3_dataset_sync(
    payload: Phase3DatasetSyncRequest,
    background_tasks: BackgroundTasks,
    job_service: JobService = Depends(get_job_service),
) -> JobCreateResponse:
    datasets = [item.strip().lower() for item in payload.datasets if item.strip()]
    if not datasets:
        raise HTTPException(status_code=400, detail="At least one dataset is required.")
    snapshot = {"phase": "3", "datasets": ",".join(datasets)}
    job_id = job_service.create_job(
        job_type="phase3_dataset_sync",
        request_payload={"datasets": datasets},
        version_snapshot=snapshot,
    )

    async def worker(set_progress):
        set_progress(0.1)
        summary = run_phase3_dataset_sync(datasets=datasets, mode="manual")
        set_progress(0.95)
        return {"status": summary.status, "mode": summary.mode, "datasets": summary.datasets}

    background_tasks.add_task(asyncio.run, job_service.run_job(job_id, worker))
    return JobCreateResponse(job_id=job_id, status="queued")

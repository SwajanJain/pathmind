from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pathmind_api.config import get_settings
from pathmind_api.database import Base, engine
from pathmind_api.deps import (
    get_aop_phase3_service,
    get_aopwiki_client,
    get_analysis_service,
    get_expression_ingest_service,
    get_gtex_client,
    get_herg_phase3_service,
    get_hpa_client,
    get_predict_targets_service,
    get_selectivity_service,
    get_tissue_impact_phase3_service,
    get_toxicity_phase3_service,
)
from pathmind_api.routes import router
from pathmind_api.routes_v1_phase2 import router_v1
from pathmind_api.routes_v1_phase3 import router_v1_phase3
from pathmind_api.routes_v1_phase4 import router_v1_phase4


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="PathMind API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(router_v1)
    app.include_router(router_v1_phase3)
    app.include_router(router_v1_phase4)

    @app.on_event("startup")
    async def startup() -> None:
        Base.metadata.create_all(bind=engine)

        if settings.phase3_auto_seed:
            from pathmind_api.database import SessionLocal
            from pathmind_api.services.auto_seed import auto_seed_phase3

            await auto_seed_phase3(SessionLocal, aopwiki_client=get_aopwiki_client())

    @app.on_event("shutdown")
    async def shutdown() -> None:
        service = get_analysis_service()
        await service.chembl.close()
        await service.pubchem.close()
        await service.uniprot.close()
        await service.reactome.close()
        await service.opentargets.close()
        phase2_predict = get_predict_targets_service()
        await phase2_predict.chembl.close()
        await phase2_predict.reactome.close()
        phase2_selectivity = get_selectivity_service()
        await phase2_selectivity.chembl.close()
        ingest = get_expression_ingest_service()
        await ingest.uniprot.close()
        herg = get_herg_phase3_service()
        await herg.chembl.close()
        toxicity = get_toxicity_phase3_service()
        await toxicity.chembl.close()
        aop = get_aop_phase3_service()
        await aop.chembl.close()
        tissue_impact = get_tissue_impact_phase3_service()
        await tissue_impact.chembl.close()
        # Close Phase 3 API clients
        await get_gtex_client().close()
        await get_hpa_client().close()
        await get_aopwiki_client().close()

    return app


app = create_app()

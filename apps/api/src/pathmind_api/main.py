from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pathmind_api.config import get_settings
from pathmind_api.database import Base, engine
from pathmind_api.deps import get_analysis_service
from pathmind_api.routes import router


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

    @app.on_event("startup")
    def startup() -> None:
        Base.metadata.create_all(bind=engine)

    @app.on_event("shutdown")
    async def shutdown() -> None:
        service = get_analysis_service()
        await service.chembl.close()
        await service.pubchem.close()
        await service.uniprot.close()
        await service.reactome.close()
        await service.opentargets.close()

    return app


app = create_app()

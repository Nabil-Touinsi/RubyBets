from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import settings

from app.api.data_sources import router as data_sources_router
from app.api.competitions import router as competitions_router
from app.api.matches import router as matches_router
from app.api.recommendations import router as recommendations_router
from app.api.glossary import router as glossary_router
from app.api.responsible_info import router as responsible_info_router

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(data_sources_router)
app.include_router(competitions_router)
app.include_router(matches_router)
app.include_router(recommendations_router)
app.include_router(glossary_router)
app.include_router(responsible_info_router)
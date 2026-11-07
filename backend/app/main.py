"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.orchestrator import get_provider
from app.api import ai, library, projects
from app.core.config import get_settings
from app.db.session import init_db
from app.legal import legal_info
from app.library.service import get_library_service
from app.services.eda_pipeline import get_eda_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    if settings.auto_create_tables:
        init_db()
    yield


app = FastAPI(title="PCB AI API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(projects.router)
app.include_router(library.router)
app.include_router(ai.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/legal")
def legal():
    return legal_info()


@app.get("/api/system/capabilities")
def capabilities(refresh: bool = False):
    s = get_settings()
    return {
        "eda": get_eda_engine().capabilities(force=refresh),
        "library": get_library_service().status(),
        "ai": get_provider().status(),
        "jobs": {"backend": s.job_backend},
        "validation_levels": ["preview", "structural", "rules_passed", "verified"],
    }

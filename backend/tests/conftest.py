"""Test configuration.

Tests use SQLite and synchronous ("eager") jobs by default. Set ``TEST_DATABASE_URL``
to run against PostgreSQL. KiCad integration tests run against the configured
engine (``KICAD_EXEC_MODE``, ``KICAD_PYTHON``, ...) and are skipped when KiCad is
not available.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="pcbai-tests-"))
os.environ.setdefault("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_TMP}/test.db"))
os.environ["STORAGE_ROOT"] = str(_TMP / "storage")
os.environ["JOB_BACKEND"] = "eager"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["ENVIRONMENT"] = "test"


def _clear_caches():
    from app.ai import orchestrator
    from app.core import config
    from app.db import session
    from app.jobs import queue
    from app.library import service
    from app.services import eda_pipeline
    from app.storage import base

    for fn in (config.get_settings, session.get_engine, session.get_sessionmaker, service.get_library_service,
               base.get_storage, queue.get_queue, eda_pipeline.get_eda_engine, orchestrator.get_provider):
        fn.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    _clear_caches()
    from app.db.models import Base
    from app.db.session import get_engine

    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def library():
    from app.library.service import get_library_service

    lib = get_library_service()
    if not lib.symbols.available() or not lib.footprints.available():
        pytest.skip("KiCad symbol/footprint libraries are not installed")
    return lib


@pytest.fixture(scope="session")
def kicad_caps():
    from app.services.eda_pipeline import get_eda_engine

    caps = get_eda_engine().capabilities()
    if not caps["kicad_cli_available"] or not caps["features"]["pcb_generation"]["available"]:
        pytest.skip("KiCad engine not available: " + str(caps["features"]["pcb_generation"].get("reason")))
    return caps

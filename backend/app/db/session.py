from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        db_path = url.split("///", 1)[-1]
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # enforce ON DELETE CASCADE in SQLite
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    return engine


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.db.models import Base

    Base.metadata.create_all(get_engine())

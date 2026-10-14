"""Background job interface.

Jobs are persisted in the ``jobs`` table (status, progress, log, result) so the
API can report them regardless of which backend executes them:

* ``eager``  - run synchronously in the calling thread (tests)
* ``inline`` - run in a thread pool inside the API process (local development)
* ``celery`` - dispatch to Celery workers via Redis (Docker Compose / production)
"""

from __future__ import annotations

import logging
import traceback
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Job, utcnow
from app.db.session import get_sessionmaker

log = logging.getLogger(__name__)

JOB_KINDS = {"validate", "export"}


class JobQueue:
    def submit(self, job_id: str) -> None:
        raise NotImplementedError


class EagerQueue(JobQueue):
    def submit(self, job_id: str) -> None:
        run_job(job_id)


class ThreadQueue(JobQueue):
    def __init__(self, workers: int = 2):
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pcbai-job")

    def submit(self, job_id: str) -> None:
        self.pool.submit(run_job, job_id)


class CeleryQueue(JobQueue):
    def submit(self, job_id: str) -> None:
        from app.jobs.celery_app import celery_app

        celery_app.send_task("pcbai.run_job", args=[job_id])


@lru_cache
def get_queue() -> JobQueue:
    backend = get_settings().job_backend
    if backend == "eager":
        return EagerQueue()
    if backend == "celery":
        return CeleryQueue()
    return ThreadQueue()


def create_job(db: Session, project_id: str, revision_id: str, kind: str) -> Job:
    if kind not in JOB_KINDS:
        raise ValueError(f"unknown job kind {kind!r}; expected one of {sorted(JOB_KINDS)}")
    job = Job(project_id=project_id, revision_id=revision_id, kind=kind, status="queued",
              progress="Waiting for a worker")
    db.add(job)
    db.commit()
    return job


def enqueue(db: Session, project_id: str, revision_id: str, kind: str) -> Job:
    job = create_job(db, project_id, revision_id, kind)
    get_queue().submit(job.id)
    db.refresh(job)
    return job


def run_job(job_id: str) -> None:
    """Execute a job. Called by every backend; owns its own DB session."""
    from app.services.eda_pipeline import run_pipeline

    db = get_sessionmaker()()
    try:
        job = db.get(Job, job_id)
        if job is None:
            log.error("job %s not found", job_id)
            return
        job.status = "running"
        job.started_at = utcnow()
        job.progress = "Starting"
        db.commit()
        try:
            result = run_pipeline(db, job)
            job.status = "succeeded"
            job.result = result
            job.progress = "Finished"
        except Exception as e:  # noqa: BLE001 - any failure must be recorded on the job
            db.rollback()
            job = db.get(Job, job_id)
            job.status = "failed"
            job.error = f"{type(e).__name__}: {e}"
            job.log = (job.log or "") + "\n" + traceback.format_exc()
            job.progress = "Failed"
            log.exception("job %s failed", job_id)
        job.finished_at = utcnow()
        db.commit()
    finally:
        db.close()

"""Celery application for EDA workers (``celery -A app.jobs.celery_app worker``)."""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

_settings = get_settings()

celery_app = Celery("pcbai", broker=_settings.redis_url, backend=None)
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=_settings.job_timeout_seconds,
    task_soft_time_limit=max(30, _settings.job_timeout_seconds - 15),
    broker_connection_retry_on_startup=True,
)


@celery_app.task(name="pcbai.run_job")
def run_job_task(job_id: str) -> None:
    from app.jobs.queue import run_job

    run_job(job_id)

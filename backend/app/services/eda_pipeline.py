"""EDA job pipeline: generate native KiCad files, verify, check and export.

Steps (stopping early when a prerequisite fails):

1. ``kicad_project`` - write .kicad_sch, build .kicad_pcb through pcbnew, re-load it.
2. ``netlist_match`` - KiCad exports the schematic netlist; compared with design intent.
3. ``erc`` / ``drc``  - KiCad's rule checks (``validate`` jobs).
4. exports          - Gerbers, drill files, BOM (``export`` jobs).

Every step result is stored as a :class:`CheckRecord` on the revision, every
produced file as an :class:`Artifact`.
"""

from __future__ import annotations

import shutil
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Artifact, CheckRecord, Job, Project, Revision
from app.design.model import DesignDocument
from app.kicad.engine import CheckResult, KiCadEngine, project_slug
from app.legal import export_notice
from app.library.service import get_library_service
from app.services.validation import validation_status
from app.storage.base import get_storage


@lru_cache
def get_eda_engine() -> KiCadEngine:
    return KiCadEngine(get_settings(), get_library_service())


def _progress(db: Session, job: Job, text: str, log: str | None = None) -> None:
    job.progress = text
    if log:
        job.log = ((job.log or "") + "\n" + log).strip()[-100_000:]
    db.commit()


def _store(db: Session, job: Job, rev: Revision, workdir: Path, rel: str, kind: str) -> Artifact:
    src = workdir / rel
    storage = get_storage()
    key = f"projects/{rev.project_id}/revisions/{rev.number:04d}-{rev.id[:8]}/{job.id[:8]}/{src.name}"
    size = storage.put_file(key, src)
    art = Artifact(project_id=rev.project_id, revision_id=rev.id, job_id=job.id, kind=kind,
                   filename=src.name, storage_key=key, size=size)
    db.add(art)
    db.flush()
    return art


def _record(db: Session, job: Job, rev: Revision, workdir: Path, res: CheckResult) -> CheckRecord:
    report_id = None
    if res.report_file and (workdir / res.report_file).is_file():
        report_id = _store(db, job, rev, workdir, res.report_file, f"{res.check}_report").id
    rec = CheckRecord(project_id=rev.project_id, revision_id=rev.id, job_id=job.id, check=res.check,
                      status=res.status, message=res.message, method=res.method,
                      engine_version=res.engine_version, summary=res.summary, violations=res.violations,
                      report_artifact_id=report_id)
    db.add(rec)
    _progress(db, job, f"{res.check}: {res.status}", res.log)
    return rec


def run_pipeline(db: Session, job: Job) -> dict:
    rev = db.get(Revision, job.revision_id)
    project = db.get(Project, job.project_id)
    if rev is None or project is None:
        raise LookupError("revision or project no longer exists")
    design = DesignDocument.model_validate(rev.design)
    engine = get_eda_engine()
    slug = project_slug(project.name)

    settings = get_settings()
    workdir = (settings.storage_root / "work" / job.id).resolve()
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True)
    workdir.chmod(0o777)  # the docker runner executes as the same uid, but keep it writable

    statuses: dict[str, str] = {}
    artifacts: list[str] = []
    try:
        caps = engine.capabilities()
        _progress(db, job, f"Using KiCad {caps.get('kicad_version')} ({caps['runner']['mode']} runner)")

        _progress(db, job, "Generating native KiCad project")
        gen = engine.generate_project(design, slug, rev.id, workdir)
        _record(db, job, rev, workdir, gen)
        statuses[gen.check] = gen.status
        if gen.status != "passed":
            return _finish(db, rev, statuses, artifacts)

        _progress(db, job, "Verifying netlist with KiCad")
        net = engine.verify_netlist(design, slug, workdir)
        _record(db, job, rev, workdir, net)
        statuses[net.check] = net.status

        if job.kind == "validate":
            _progress(db, job, "Running KiCad ERC")
            erc = engine.run_erc(slug, workdir)
            _record(db, job, rev, workdir, erc)
            statuses["erc"] = erc.status
            _progress(db, job, "Running KiCad DRC")
            drc = engine.run_drc(slug, workdir)
            _record(db, job, rev, workdir, drc)
            statuses["drc"] = drc.status

        if job.kind == "export":
            _progress(db, job, "Exporting manufacturing files")
            exp = engine.export_manufacturing(slug, workdir)
            _progress(db, job, f"export: {exp.status} - {exp.message}", exp.log)
            statuses["export"] = exp.status
            for kind, rel in exp.files.items():
                artifacts.append(_store(db, job, rev, workdir, rel, kind).id)

        notice = export_notice(project.name, rev.number, statuses, caps.get("kicad_version"))
        rel = engine.package_project(slug, workdir, notice)
        artifacts.append(_store(db, job, rev, workdir, rel, "kicad_project").id)
        db.commit()
        return _finish(db, rev, statuses, artifacts)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _finish(db: Session, rev: Revision, statuses: dict, artifacts: list[str]) -> dict:
    db.commit()
    status = validation_status(db, rev)
    return {"checks": statuses, "artifacts": artifacts, "validation_level": status["level"]}

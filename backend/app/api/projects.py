from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import library_dep
from app.db.models import Artifact, Job, Project, Revision
from app.db.session import get_db
from app.design.model import DesignDocument
from app.design.operations import OperationError, apply_operations, is_destructive, parse_operations
from app.jobs.queue import enqueue
from app.library.service import LibraryService, PartUnavailable
from app.render.pcb import render_pcb
from app.render.schematic import render_schematic
from app.services import projects as svc
from app.services.validation import design_model_checks, validation_status
from app.storage.base import get_storage
from app.templates.circuits import TemplateError

router = APIRouter(prefix="/api", tags=["projects"])


# ---------------------------------------------------------------- schemas
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    template_id: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class OperationsRequest(BaseModel):
    base_revision_id: str
    operations: list[dict] = Field(min_length=1, max_length=500)
    message: str = Field(default="", max_length=500)


class PreviewRequest(BaseModel):
    operations: list[dict] = Field(min_length=1, max_length=500)


class JobRequest(BaseModel):
    kind: str
    revision_id: str | None = None


# ---------------------------------------------------------------- helpers
def _project_or_404(db: Session, project_id: str) -> Project:
    try:
        return svc.get_project(db, project_id)
    except svc.NotFound as e:
        raise HTTPException(404, str(e)) from e


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def project_out(db: Session, p: Project) -> dict:
    head = db.get(Revision, p.head_revision_id) if p.head_revision_id else None
    level = validation_status(db, head)["level"] if head else "preview"
    comps = len(head.design.get("components", [])) if head else 0
    return {
        "id": p.id, "name": p.name, "description": p.description, "created_at": _iso(p.created_at),
        "updated_at": _iso(p.updated_at), "head_revision_id": p.head_revision_id,
        "head_revision_number": head.number if head else None, "component_count": comps,
        "validation_level": level,
    }


def revision_out(r: Revision) -> dict:
    return {"id": r.id, "number": r.number, "parent_id": r.parent_id, "author": r.author, "message": r.message,
            "operation_count": len(r.operations or []), "created_at": _iso(r.created_at)}


def job_out(j: Job) -> dict:
    return {"id": j.id, "project_id": j.project_id, "revision_id": j.revision_id, "kind": j.kind,
            "status": j.status, "progress": j.progress, "error": j.error, "result": j.result,
            "created_at": _iso(j.created_at), "started_at": _iso(j.started_at), "finished_at": _iso(j.finished_at)}


def artifact_out(a: Artifact) -> dict:
    return {"id": a.id, "revision_id": a.revision_id, "job_id": a.job_id, "kind": a.kind, "filename": a.filename,
            "size": a.size, "created_at": _iso(a.created_at), "download_url": f"/api/artifacts/{a.id}/download"}


def _op_error(e: OperationError) -> HTTPException:
    return HTTPException(422, {"message": str(e), "operation_error": e.to_dict()})


def _schema_error(e: ValidationError) -> HTTPException:
    return HTTPException(422, {"message": "invalid operation", "details": [
        {"loc": list(err["loc"]), "msg": err["msg"]} for err in e.errors()[:20]]})


# ---------------------------------------------------------------- projects
@router.get("/projects")
def list_projects(db: Session = Depends(get_db)):
    rows = db.scalars(select(Project).order_by(Project.updated_at.desc()))
    return [project_out(db, p) for p in rows]


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db), lib: LibraryService = Depends(library_dep)):
    try:
        p = svc.create_project(db, lib, body.name, body.description, body.template_id)
    except (TemplateError, OperationError, PartUnavailable, ValueError) as e:
        db.rollback()
        raise HTTPException(422, str(e)) from e
    return project_out(db, p)


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    return project_out(db, _project_or_404(db, project_id))


@router.patch("/projects/{project_id}")
def update_project(project_id: str, body: ProjectUpdate, db: Session = Depends(get_db)):
    p = _project_or_404(db, project_id)
    try:
        svc.rename_project(db, p, body.name, body.description)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return project_out(db, p)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, confirm: str = Query(..., description="Must equal the project name"),
                   db: Session = Depends(get_db)):
    p = _project_or_404(db, project_id)
    if confirm != p.name:
        raise HTTPException(400, "confirmation does not match the project name")
    svc.delete_project(db, get_storage(), p)


# ---------------------------------------------------------------- design
@router.get("/projects/{project_id}/design")
def get_design(project_id: str, revision_id: str | None = None, db: Session = Depends(get_db),
               lib: LibraryService = Depends(library_dep)):
    p = _project_or_404(db, project_id)
    try:
        rev = svc.get_revision(db, p, revision_id)
    except svc.NotFound as e:
        raise HTTPException(404, str(e)) from e
    design = DesignDocument.model_validate(rev.design)
    return {
        "project": project_out(db, p),
        "revision": revision_out(rev),
        "is_head": rev.id == p.head_revision_id,
        "can_undo": bool(rev.parent_id) and rev.id == p.head_revision_id,
        "can_redo": svc.redo_target(db, p) is not None and rev.id == p.head_revision_id,
        "design": design.model_dump(mode="json"),
        "validation": validation_status(db, rev),
        "design_checks": design_model_checks(design, lib),
    }


@router.post("/projects/{project_id}/operations")
def apply_operations_route(project_id: str, body: OperationsRequest, db: Session = Depends(get_db),
                           lib: LibraryService = Depends(library_dep)):
    p = _project_or_404(db, project_id)
    try:
        rev = svc.apply_to_project(db, lib, p, body.base_revision_id, body.operations, "user", body.message)
    except svc.Conflict as e:
        db.rollback()
        raise HTTPException(409, str(e)) from e
    except OperationError as e:
        db.rollback()
        raise _op_error(e) from e
    except ValidationError as e:
        db.rollback()
        raise _schema_error(e) from e
    return {"revision": revision_out(rev)}


@router.post("/projects/{project_id}/operations/preview")
def preview_operations(project_id: str, body: PreviewRequest, db: Session = Depends(get_db),
                       lib: LibraryService = Depends(library_dep)):
    p = _project_or_404(db, project_id)
    head = svc.head_revision(db, p)
    design = DesignDocument.model_validate(head.design)
    try:
        ops = parse_operations(body.operations)
        result = apply_operations(design, ops, lib)
    except OperationError as e:
        raise _op_error(e) from e
    except ValidationError as e:
        raise _schema_error(e) from e
    return {"base_revision_id": head.id, "destructive": [i for i, o in enumerate(ops) if is_destructive(o, design)],
            "design": result.model_dump(mode="json"), "design_checks": design_model_checks(result, lib)}


@router.post("/projects/{project_id}/undo")
def undo(project_id: str, db: Session = Depends(get_db)):
    p = _project_or_404(db, project_id)
    try:
        return {"revision": revision_out(svc.undo(db, p))}
    except svc.Conflict as e:
        raise HTTPException(409, str(e)) from e


@router.post("/projects/{project_id}/redo")
def redo(project_id: str, db: Session = Depends(get_db)):
    p = _project_or_404(db, project_id)
    try:
        return {"revision": revision_out(svc.redo(db, p))}
    except svc.Conflict as e:
        raise HTTPException(409, str(e)) from e


@router.get("/projects/{project_id}/revisions")
def list_revisions(project_id: str, db: Session = Depends(get_db)):
    p = _project_or_404(db, project_id)
    return [revision_out(r) | {"is_head": r.id == p.head_revision_id} for r in svc.list_revisions(db, p)]


@router.post("/projects/{project_id}/revisions/{revision_id}/restore")
def restore(project_id: str, revision_id: str, db: Session = Depends(get_db)):
    p = _project_or_404(db, project_id)
    try:
        rev = svc.get_revision(db, p, revision_id)
    except svc.NotFound as e:
        raise HTTPException(404, str(e)) from e
    return {"revision": revision_out(svc.restore_revision(db, p, rev))}


# ---------------------------------------------------------------- render models
def _render(project_id: str, revision_id: str | None, db: Session, lib: LibraryService, fn):
    p = _project_or_404(db, project_id)
    try:
        rev = svc.get_revision(db, p, revision_id)
    except svc.NotFound as e:
        raise HTTPException(404, str(e)) from e
    try:
        data = fn(DesignDocument.model_validate(rev.design), lib)
    except PartUnavailable as e:
        raise HTTPException(500, f"library data unavailable: {e}") from e
    return {"revision_id": rev.id, "kind": "preview", **data}


@router.get("/projects/{project_id}/render/schematic")
def schematic_render(project_id: str, revision_id: str | None = None, db: Session = Depends(get_db),
                     lib: LibraryService = Depends(library_dep)):
    return _render(project_id, revision_id, db, lib, render_schematic)


@router.get("/projects/{project_id}/render/pcb")
def pcb_render(project_id: str, revision_id: str | None = None, db: Session = Depends(get_db),
               lib: LibraryService = Depends(library_dep)):
    return _render(project_id, revision_id, db, lib, render_pcb)


# ---------------------------------------------------------------- jobs & artifacts
@router.post("/projects/{project_id}/jobs", status_code=202)
def create_job(project_id: str, body: JobRequest, db: Session = Depends(get_db)):
    p = _project_or_404(db, project_id)
    try:
        rev = svc.get_revision(db, p, body.revision_id)
    except svc.NotFound as e:
        raise HTTPException(404, str(e)) from e
    try:
        job = enqueue(db, p.id, rev.id, body.kind)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return job_out(job)


@router.get("/projects/{project_id}/jobs")
def list_jobs(project_id: str, limit: int = Query(20, le=100), db: Session = Depends(get_db)):
    _project_or_404(db, project_id)
    rows = db.scalars(select(Job).where(Job.project_id == project_id).order_by(Job.created_at.desc()).limit(limit))
    return [job_out(j) for j in rows]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, include_log: bool = False, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if j is None:
        raise HTTPException(404, "job not found")
    out = job_out(j)
    if include_log:
        out["log"] = j.log
    return out


@router.get("/projects/{project_id}/artifacts")
def list_artifacts(project_id: str, revision_id: str | None = None, db: Session = Depends(get_db)):
    p = _project_or_404(db, project_id)
    q = select(Artifact).where(Artifact.project_id == p.id)
    if revision_id:
        q = q.where(Artifact.revision_id == revision_id)
    return [artifact_out(a) for a in db.scalars(q.order_by(Artifact.created_at.desc()).limit(200))]


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str, db: Session = Depends(get_db)):
    a = db.get(Artifact, artifact_id)
    if a is None:
        raise HTTPException(404, "artifact not found")
    path = get_storage().local_path(a.storage_key)
    if not path.is_file():
        raise HTTPException(410, "artifact file is no longer available")
    return FileResponse(path, filename=a.filename)

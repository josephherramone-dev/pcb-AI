"""Projects and immutable design revisions.

* Every applied operation batch creates a new :class:`Revision`; revisions are
  never modified, giving a complete audit trail.
* ``Project.head_revision_id`` points at the current revision. Undo moves the
  head to the parent revision, redo moves it forward again; nothing is deleted.
* Writers must name the revision they edited (``base_revision_id``); stale
  writes are rejected instead of silently overwriting newer work.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AiMessage, Project, Revision, utcnow
from app.design.model import DesignDocument
from app.design.operations import apply_operations, parse_operations
from app.library.service import LibraryService
from app.storage.base import Storage


class NotFound(LookupError):
    pass


class Conflict(RuntimeError):
    pass


def get_project(db: Session, project_id: str) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise NotFound(f"project {project_id} not found")
    return p


def head_revision(db: Session, project: Project) -> Revision:
    rev = db.get(Revision, project.head_revision_id) if project.head_revision_id else None
    if rev is None:
        raise NotFound(f"project {project.id} has no head revision")
    return rev


def get_revision(db: Session, project: Project, revision_id: str | None) -> Revision:
    if not revision_id:
        return head_revision(db, project)
    rev = db.get(Revision, revision_id)
    if rev is None or rev.project_id != project.id:
        raise NotFound(f"revision {revision_id} not found")
    return rev


def _next_number(db: Session, project_id: str) -> int:
    n = db.scalar(select(func.max(Revision.number)).where(Revision.project_id == project_id))
    return (n or 0) + 1


def create_project(db: Session, library: LibraryService, name: str, description: str = "",
                   template_id: str | None = None) -> Project:
    name = name.strip()
    if not name or len(name) > 120:
        raise ValueError("project name must be 1-120 characters")
    project = Project(name=name, description=description.strip())
    db.add(project)
    db.flush()
    design = DesignDocument(title=name)
    ops: list[dict] = []
    message = "Project created"
    if template_id:
        ops = [{"op": "load_template", "template_id": template_id}]
        design = apply_operations(design, parse_operations(ops), library)
        design.title = name
        message = f"Project created from template '{template_id}'"
    rev = Revision(project_id=project.id, number=1, parent_id=None, author="system", message=message,
                   operations=ops, design=design.model_dump(mode="json"))
    db.add(rev)
    db.flush()
    project.head_revision_id = rev.id
    db.commit()
    return project


def rename_project(db: Session, project: Project, name: str | None, description: str | None) -> Project:
    if name is not None:
        name = name.strip()
        if not name or len(name) > 120:
            raise ValueError("project name must be 1-120 characters")
        project.name = name
    if description is not None:
        project.description = description.strip()
    project.updated_at = utcnow()
    db.commit()
    return project


def delete_project(db: Session, storage: Storage, project: Project) -> None:
    pid = project.id
    db.delete(project)
    db.commit()
    storage.delete_prefix(f"projects/{pid}")


def apply_to_project(db: Session, library: LibraryService, project: Project, base_revision_id: str,
                     raw_ops: list[dict], author: str, message: str) -> Revision:
    head = head_revision(db, project)
    if base_revision_id != head.id:
        raise Conflict(
            f"the design changed since revision {base_revision_id}; current revision is {head.id} "
            f"(#{head.number}). Reload and retry."
        )
    ops = parse_operations(raw_ops)
    design = DesignDocument.model_validate(head.design)
    new_design = apply_operations(design, ops, library)
    rev = Revision(
        project_id=project.id, number=_next_number(db, project.id), parent_id=head.id, author=author,
        message=message.strip()[:500] or ", ".join(o.op for o in ops)[:500],
        operations=[o.model_dump(mode="json") for o in ops], design=new_design.model_dump(mode="json"),
    )
    db.add(rev)
    db.flush()
    project.head_revision_id = rev.id
    project.updated_at = utcnow()
    _mark_stale_proposals(db, project.id, rev.id)
    db.commit()
    return rev


def undo(db: Session, project: Project) -> Revision:
    head = head_revision(db, project)
    if not head.parent_id:
        raise Conflict("nothing to undo")
    project.head_revision_id = head.parent_id
    project.updated_at = utcnow()
    db.commit()
    return head_revision(db, project)


def redo_target(db: Session, project: Project) -> Revision | None:
    head = head_revision(db, project)
    return db.scalar(
        select(Revision).where(Revision.project_id == project.id, Revision.parent_id == head.id)
        .order_by(Revision.number.desc()).limit(1)
    )


def redo(db: Session, project: Project) -> Revision:
    target = redo_target(db, project)
    if target is None:
        raise Conflict("nothing to redo")
    project.head_revision_id = target.id
    project.updated_at = utcnow()
    db.commit()
    return target


def restore_revision(db: Session, project: Project, revision: Revision) -> Revision:
    """Create a new head revision whose design equals an older revision (history is preserved)."""
    head = head_revision(db, project)
    rev = Revision(project_id=project.id, number=_next_number(db, project.id), parent_id=head.id,
                   author="user", message=f"Restored revision #{revision.number}", operations=[],
                   design=revision.design)
    db.add(rev)
    db.flush()
    project.head_revision_id = rev.id
    project.updated_at = utcnow()
    db.commit()
    return rev


def list_revisions(db: Session, project: Project) -> list[Revision]:
    return list(db.scalars(select(Revision).where(Revision.project_id == project.id)
                           .order_by(Revision.number.desc())))


def _mark_stale_proposals(db: Session, project_id: str, new_head: str) -> None:
    for msg in db.scalars(select(AiMessage).where(AiMessage.project_id == project_id,
                                                  AiMessage.proposal_status == "pending")):
        if msg.base_revision_id != new_head:
            msg.proposal_status = "stale"

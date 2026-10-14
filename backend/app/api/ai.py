from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.orchestrator import Orchestrator, apply_proposal, get_provider
from app.ai.provider import ProviderNotConfigured
from app.api.deps import library_dep
from app.api.projects import _project_or_404, revision_out
from app.db.models import AiMessage
from app.db.session import get_db
from app.design.operations import OperationError
from app.library.service import LibraryService
from app.services import projects as svc

router = APIRouter(prefix="/api", tags=["ai"])


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class ApplyRequest(BaseModel):
    confirm_destructive: bool = False


def message_out(m: AiMessage, head_id: str | None) -> dict:
    status = m.proposal_status
    if status == "pending" and m.base_revision_id != head_id:
        status = "stale"
    return {"id": m.id, "role": m.role, "content": m.content, "proposal": m.proposal, "proposal_status": status,
            "applied_revision_id": m.applied_revision_id, "meta": m.meta or {},
            "created_at": m.created_at.isoformat()}


@router.get("/ai/status")
def ai_status():
    return get_provider().status()


@router.get("/projects/{project_id}/ai/messages")
def list_messages(project_id: str, db: Session = Depends(get_db)):
    p = _project_or_404(db, project_id)
    rows = db.scalars(select(AiMessage).where(AiMessage.project_id == p.id).order_by(AiMessage.created_at.asc()))
    return [message_out(m, p.head_revision_id) for m in rows]


@router.post("/projects/{project_id}/ai/messages")
def send_message(project_id: str, body: ChatRequest, db: Session = Depends(get_db),
                 lib: LibraryService = Depends(library_dep)):
    p = _project_or_404(db, project_id)
    provider = get_provider()
    if not provider.status().get("configured"):
        raise HTTPException(503, provider.status().get("message", "AI provider not configured"))
    try:
        reply = Orchestrator(db, p, lib, provider).chat(body.content)
    except ProviderNotConfigured as e:
        raise HTTPException(503, str(e)) from e
    db.refresh(p)
    return message_out(reply, p.head_revision_id)


@router.post("/projects/{project_id}/ai/messages/{message_id}/apply")
def apply(project_id: str, message_id: str, body: ApplyRequest, db: Session = Depends(get_db),
          lib: LibraryService = Depends(library_dep)):
    p = _project_or_404(db, project_id)
    msg = db.get(AiMessage, message_id)
    if msg is None:
        raise HTTPException(404, "message not found")
    try:
        rev = apply_proposal(db, lib, p, msg, body.confirm_destructive)
    except svc.NotFound as e:
        raise HTTPException(404, str(e)) from e
    except svc.Conflict as e:
        db.rollback()
        raise HTTPException(409, str(e)) from e
    except OperationError as e:
        db.rollback()
        raise HTTPException(422, {"message": str(e), "operation_error": e.to_dict()}) from e
    return {"revision": revision_out(rev)}


@router.post("/projects/{project_id}/ai/messages/{message_id}/reject")
def reject(project_id: str, message_id: str, db: Session = Depends(get_db)):
    p = _project_or_404(db, project_id)
    msg = db.get(AiMessage, message_id)
    if msg is None or msg.project_id != p.id or not msg.proposal:
        raise HTTPException(404, "proposal not found")
    if msg.proposal_status != "pending":
        raise HTTPException(409, f"proposal is {msg.proposal_status}")
    msg.proposal_status = "rejected"
    db.commit()
    return message_out(msg, p.head_revision_id)

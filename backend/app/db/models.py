"""Relational schema: projects, immutable design revisions, jobs, check results, artifacts, AI messages."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JsonType = JSON().with_variant(JSONB(), "postgresql")


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    head_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    revisions: Mapped[list[Revision]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )


class Revision(Base):
    """An immutable snapshot of the design. Never updated after creation."""

    __tablename__ = "revisions"
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_revision_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    author: Mapped[str] = mapped_column(String(20))  # user | ai | system
    message: Mapped[str] = mapped_column(Text, default="")
    operations: Mapped[list] = mapped_column(JsonType, default=list)
    design: Mapped[dict] = mapped_column(JsonType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="revisions")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|succeeded|failed
    progress: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    log: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CheckRecord(Base):
    """Result of one validation step run by the EDA engine for one revision."""

    __tablename__ = "checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("revisions.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    check: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text, default="")
    method: Mapped[str | None] = mapped_column(String(120), nullable=True)
    engine_version: Mapped[str | None] = mapped_column(String(60), nullable=True)
    summary: Mapped[dict] = mapped_column(JsonType, default=dict)
    violations: Mapped[list] = mapped_column(JsonType, default=list)
    report_artifact_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("revisions.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    filename: Mapped[str] = mapped_column(String(200))
    storage_key: Mapped[str] = mapped_column(String(400))
    size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AiMessage(Base):
    __tablename__ = "ai_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")
    # A structured proposal of design operations produced by the assistant.
    proposal: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    proposal_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # pending|applied|rejected|stale
    base_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    applied_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    meta: Mapped[dict] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

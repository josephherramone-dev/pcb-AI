"""AI orchestration: tools, server-side validation of every tool call, proposals.

The assistant can read the design, the curated part catalog (with pin data from
the KiCad libraries) and the *real* ERC/DRC results stored for the current
revision. It can never change the design directly: ``propose_changes`` dry-runs
the operations against the current revision and stores a proposal that the user
must explicitly apply (destructive operations need an extra confirmation).
"""

from __future__ import annotations

import json
from functools import lru_cache

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.claude import ClaudeProvider
from app.ai.provider import DisabledProvider, LLMProvider, ToolOutcome, ToolSpec
from app.core.config import get_settings
from app.db.models import AiMessage, Project
from app.design.model import DesignDocument
from app.design.operations import OperationError, apply_operations, is_destructive, parse_operations
from app.library.service import LibraryService, PartUnavailable
from app.services import projects as project_svc
from app.services.validation import design_model_checks, validation_status
from app.templates.circuits import template_summaries

SYSTEM_PROMPT = """You are the design assistant inside an AI-native PCB design platform built on KiCad.
You help engineers turn requirements into schematics and PCB layouts.

How the platform works
- The design is a document of components, nets, PCB placement, tracks and board settings. You change it
  only by proposing typed operations with the propose_changes tool. The backend validates them against the
  KiCad libraries; the user reviews and applies them. Nothing you propose is applied automatically.
- Only parts from the curated catalog can be placed (search_parts / get_part). Pin numbers and names come
  from KiCad's official libraries via get_part - always look them up instead of assuming a pinout.
- Validation is performed by KiCad (netlist cross-check, ERC, DRC) when the user runs it. Use
  get_validation_report to read real results. Validation results apply to one revision only.

Honesty rules (mandatory)
- Never invent component specifications, datasheet contents, pin assignments or ratings. If a value
  depends on datasheet data you do not have, say so and point to the datasheet link from get_part.
- Never claim that a design passed ERC/DRC or is correct unless get_validation_report shows it for the
  current revision. A proposal that validates against the library is not an electrically verified design.
- When requirements are incomplete (supply voltage, currents, connectors, board size...), ask concise
  clarification questions with ask_user instead of guessing. Small, clearly stated assumptions are fine.
- State assumptions and uncertainty explicitly. Prefer standard, conservative design practice and label
  calculated values as estimates.

Operation conventions
- Units are millimetres. Schematic positions snap to a 1.27 mm grid; the A4 sheet is 297 x 210 mm. Keep
  symbols at least ~25 mm apart so labels do not collide. PCB coordinates are absolute KiCad coordinates;
  keep footprints inside the board outline (see get_design).
- Connections are made by assigning pins to named nets with the connect operation. A pin can belong to one
  net only. Use PWR_FLAG (part pwr_flag) on nets supplied from a connector so KiCad ERC knows they are driven.
- Removing components, deleting nets/tracks or loading a template over an existing design is destructive;
  explain why and expect the user to confirm.
- After proposing, summarise what the proposal does and what the user should check next (e.g. run
  validation). Keep answers concise and technical.
"""

OPERATIONS_DOC = """Operations (each object has "op" plus fields):
- add_component {part_id, ref?, value?, x, y, rotation? (0|90|180|270), pcb_x?, pcb_y?}
- remove_component {ref}                      [destructive]
- set_value {ref, value}
- move_symbol {ref, x, y, rotation?}
- move_footprint {ref, x, y, rotation?}
- connect {net, pins: [{ref, pin}]}           (creates the net if needed; pin = KiCad pin number as string)
- disconnect {pins: [{ref, pin}]}
- rename_net {name, new_name}
- delete_net {name}                           [destructive]
- set_no_connect {pin: {ref, pin}, enabled}
- add_track {net, layer ("F.Cu"|"B.Cu"), width?, points: [{x, y}, ...]}
- delete_track {id}                           [destructive]
- add_via {net, x, y} / delete_via {id}
- set_board {width, height, origin_x?, origin_y?}
- set_rules {clearance?, track_width?, via_diameter?, via_drill?}
- set_title {title}
- load_template {template_id}                 [destructive if the design is not empty]
Operations are applied in order; refs created earlier in the list can be used later."""


def _tools() -> list[ToolSpec]:
    empty = {"type": "object", "properties": {}, "additionalProperties": False}
    return [
        ToolSpec("get_design", "Get the current design: components, nets, PCB placement, board, revision and "
                 "validation level, plus preliminary design-model warnings.", empty, strict=True),
        ToolSpec("search_parts", "Search the curated part catalog (only these parts can be placed).", {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Keywords, e.g. 'resistor', 'regulator'."}},
            "required": ["query"], "additionalProperties": False}, strict=True),
        ToolSpec("get_part", "Get a catalog part with its KiCad symbol pins (numbers, names, electrical "
                 "types), footprint pads and datasheet link as given by the KiCad library.", {
                     "type": "object", "properties": {"part_id": {"type": "string"}},
                     "required": ["part_id"], "additionalProperties": False}, strict=True),
        ToolSpec("list_templates", "List starter circuit templates with their stated assumptions.", empty,
                 strict=True),
        ToolSpec("get_validation_report", "Get the real KiCad check results (project generation, netlist "
                 "cross-check, ERC, DRC) stored for the current revision.", empty, strict=True),
        ToolSpec("propose_changes", "Propose design operations. The backend validates them against the current "
                 "revision and the KiCad libraries and returns errors to fix, or stores a proposal for the user "
                 "to review and apply.\n\n" + OPERATIONS_DOC, {
                     "type": "object",
                     "properties": {
                         "title": {"type": "string", "description": "Short title of the change."},
                         "summary": {"type": "string", "description": "What the change does and why."},
                         "assumptions": {"type": "array", "items": {"type": "string"}},
                         "operations": {"type": "array", "items": {"type": "object"}},
                     },
                     "required": ["title", "summary", "operations"]}),
        ToolSpec("ask_user", "Ask the user clarification questions when requirements are incomplete.", {
            "type": "object",
            "properties": {"questions": {"type": "array", "items": {"type": "string"}}},
            "required": ["questions"], "additionalProperties": False}, strict=True),
    ]


@lru_cache
def get_provider() -> LLMProvider:
    s = get_settings()
    if s.ai_provider == "none":
        return DisabledProvider()
    return ClaudeProvider(s)


def design_summary(db: Session, project: Project, library: LibraryService) -> dict:
    head = project_svc.head_revision(db, project)
    design = DesignDocument.model_validate(head.design)
    status = validation_status(db, head)
    return {
        "project": project.name,
        "revision": {"id": head.id, "number": head.number},
        "validation_level": status["level"],
        "validation_label": status["label"],
        "design": design.model_dump(mode="json", exclude={"tracks"}),
        "track_count": len(design.tracks),
        "design_model_warnings": design_model_checks(design, library)[:60],
    }


class Orchestrator:
    def __init__(self, db: Session, project: Project, library: LibraryService, provider: LLMProvider):
        self.db = db
        self.project = project
        self.library = library
        self.provider = provider
        self.proposal: dict | None = None
        self.questions: list[str] = []

    # ---- tool execution (every call validated here) ----------------------
    def execute(self, name: str, args: dict) -> ToolOutcome:
        try:
            if name == "get_design":
                return self._ok(design_summary(self.db, self.project, self.library))
            if name == "search_parts":
                query = str(args.get("query", ""))[:200]
                parts = self.library.list_parts(query)
                if not parts:
                    parts = self.library.list_parts()
                    return self._ok({"note": f"no match for {query!r}; full catalog follows", "parts": parts})
                return self._ok({"parts": parts})
            if name == "get_part":
                return self._ok(self.library.resolve(str(args.get("part_id", ""))).to_detail())
            if name == "list_templates":
                return self._ok({"templates": template_summaries()})
            if name == "get_validation_report":
                head = project_svc.head_revision(self.db, self.project)
                status = validation_status(self.db, head)
                for c in status["checks"].values():
                    if len(c["violations"]) > 40:
                        c["violations"] = c["violations"][:40] + [{"note": f"{len(c['violations']) - 40} more"}]
                if not status["checks"]:
                    status["note"] = "No KiCad checks have been run on the current revision yet."
                return self._ok(status)
            if name == "propose_changes":
                return self._propose(args)
            if name == "ask_user":
                qs = [str(q)[:500] for q in args.get("questions", []) if str(q).strip()][:8]
                self.questions.extend(qs)
                return self._ok({"recorded": len(qs), "note": "Questions will be shown to the user."})
            return ToolOutcome(f"unknown tool {name!r}", is_error=True)
        except PartUnavailable as e:
            return ToolOutcome(str(e), is_error=True)
        except Exception as e:  # noqa: BLE001 - surface errors to the model instead of crashing the turn
            return ToolOutcome(f"{type(e).__name__}: {e}", is_error=True)

    def _ok(self, data) -> ToolOutcome:
        return ToolOutcome(json.dumps(data, default=str))

    def _propose(self, args: dict) -> ToolOutcome:
        raw_ops = args.get("operations")
        if not isinstance(raw_ops, list) or not raw_ops:
            return ToolOutcome("operations must be a non-empty list", is_error=True)
        if len(raw_ops) > 200:
            return ToolOutcome("too many operations in one proposal (max 200)", is_error=True)
        try:
            ops = parse_operations(raw_ops)
        except ValidationError as e:
            errs = [{"loc": list(err["loc"]), "msg": err["msg"]} for err in e.errors()[:20]]
            return ToolOutcome(json.dumps({"error": "invalid operation schema", "details": errs}), is_error=True)
        head = project_svc.head_revision(self.db, self.project)
        design = DesignDocument.model_validate(head.design)
        try:
            result = apply_operations(design, ops, self.library)
        except OperationError as e:
            return ToolOutcome(json.dumps({"error": "operation rejected", **e.to_dict()}), is_error=True)
        destructive = [i for i, op in enumerate(ops) if is_destructive(op, design)]
        self.proposal = {
            "title": str(args.get("title", "Proposed changes"))[:200],
            "summary": str(args.get("summary", ""))[:4000],
            "assumptions": [str(a)[:500] for a in (args.get("assumptions") or [])][:20],
            "operations": [o.model_dump(mode="json") for o in ops],
            "destructive_operations": destructive,
            "base_revision_id": head.id,
            "base_revision_number": head.number,
            "preview_warnings": design_model_checks(result, self.library)[:40],
        }
        return self._ok({
            "status": "validated and stored as a pending proposal; the user must review and apply it",
            "operations": len(ops),
            "destructive_operations": destructive,
            "resulting_component_count": len(result.components),
            "resulting_nets": [n.name for n in result.nets],
            "design_model_warnings_after_apply": self.proposal["preview_warnings"][:20],
        })

    # ---- one conversation turn --------------------------------------------
    def chat(self, user_text: str) -> AiMessage:
        settings = get_settings()
        head = project_svc.head_revision(self.db, self.project)
        user_msg = AiMessage(project_id=self.project.id, role="user", content=user_text.strip()[:8000],
                             base_revision_id=head.id)
        self.db.add(user_msg)
        self.db.commit()

        history = self._history()
        turn = self.provider.run_turn(SYSTEM_PROMPT, history, _tools(), self.execute,
                                      settings.ai_max_tool_iterations)
        content = turn.text.strip()
        if turn.error:
            content = f"The assistant could not complete this request: {turn.error}"
        reply = AiMessage(
            project_id=self.project.id, role="assistant", content=content,
            proposal=self.proposal, proposal_status="pending" if self.proposal else None,
            base_revision_id=self.proposal["base_revision_id"] if self.proposal else head.id,
            meta={"questions": self.questions, "tool_calls": turn.tool_calls, "stop_reason": turn.stop_reason,
                  "model": turn.model, "usage": turn.usage, "error": turn.error},
        )
        self.db.add(reply)
        self.db.commit()
        return reply

    def _history(self) -> list[dict]:
        rows = list(self.db.scalars(select(AiMessage).where(AiMessage.project_id == self.project.id)
                                    .order_by(AiMessage.created_at.desc()).limit(20)))
        rows.reverse()
        history: list[dict] = []
        for m in rows:
            text = m.content or ""
            if m.role == "assistant":
                if m.proposal:
                    text += f"\n\n[Proposal '{m.proposal.get('title')}' - status: {m.proposal_status}]"
                if m.meta.get("questions"):
                    text += "\n\n[Questions asked: " + " | ".join(m.meta["questions"]) + "]"
                if not text.strip():
                    continue
            role = "assistant" if m.role == "assistant" else "user"
            if history and history[-1]["role"] == role:
                history[-1]["content"] += "\n\n" + text
            else:
                history.append({"role": role, "content": text})
        while history and history[0]["role"] != "user":
            history.pop(0)
        if history and history[-1]["role"] == "user":
            head = project_svc.head_revision(self.db, self.project)
            history[-1]["content"] += (
                f"\n\n(Context: current revision #{head.number} of project '{self.project.name}'. "
                "Use get_design for details.)"
            )
        return history


def apply_proposal(db: Session, library: LibraryService, project: Project, message: AiMessage,
                   confirm_destructive: bool):
    if message.project_id != project.id or not message.proposal:
        raise project_svc.NotFound("proposal not found")
    if message.proposal_status != "pending":
        raise project_svc.Conflict(f"proposal is {message.proposal_status}")
    if message.proposal.get("destructive_operations") and not confirm_destructive:
        raise project_svc.Conflict("this proposal contains destructive operations; confirmation is required")
    head = project_svc.head_revision(db, project)
    if head.id != message.proposal["base_revision_id"]:
        message.proposal_status = "stale"
        db.commit()
        raise project_svc.Conflict("the design changed since this proposal was made; ask the assistant again")
    rev = project_svc.apply_to_project(db, library, project, head.id, message.proposal["operations"],
                                       author="ai", message=f"AI: {message.proposal['title']}")
    message.proposal_status = "applied"
    message.applied_revision_id = rev.id
    db.commit()
    return rev

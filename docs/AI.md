# AI assistant

## Design

```
POST /api/projects/{id}/ai/messages
  └─ Orchestrator.chat()                       backend/app/ai/orchestrator.py
       ├─ builds history (plain text turns, last 20 messages)
       └─ LLMProvider.run_turn(system, history, tools, execute)
            └─ ClaudeProvider (official Anthropic SDK)  backend/app/ai/claude.py
                 loop: messages.create → tool_use → execute() → tool_result → … → end_turn
```

- **Provider-independent**: `LLMProvider` (`backend/app/ai/provider.py`) hides message
  formats, thinking blocks, retries and stop reasons. Another vendor can be added by
  implementing `status()` and `run_turn()`.
- **Server-side key only**: `ANTHROPIC_API_KEY` is read by the backend. The browser
  calls the backend; no key or provider URL is present in frontend code.
- Model `claude-opus-5-5` with `output_config.effort` (default `high`). Server-side
  refusal fallback (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`) is
  enabled by default and can be turned off with `ANTHROPIC_ENABLE_FALLBACKS=false`.
- Errors are mapped from the SDK's typed exceptions to user-readable messages
  (authentication, permission, rate limit, connection, bad request).

## Tools

| Tool | Purpose | Validation |
|---|---|---|
| `get_design` | Current design, revision, validation level, design-model warnings | read-only |
| `search_parts` / `get_part` | Curated catalog; pins/datasheet links from KiCad libraries | read-only |
| `list_templates` | Starter circuits and their stated assumptions | read-only |
| `get_validation_report` | **Real** KiCad check results stored for the current revision | read-only |
| `propose_changes` | Design operations + summary + assumptions | parsed with the operation schema and dry-run against the head revision; errors are returned to the model to fix |
| `ask_user` | Clarification questions shown to the user | strings only |

Every tool call is executed by backend code (`Orchestrator.execute`); the model never
runs commands, SQL or file operations.

## Proposals

- A successful `propose_changes` stores a proposal on the assistant message:
  operations, destructive operation indices, assumptions, base revision, and the
  design-model warnings the change would produce.
- The user applies or rejects it in the UI. Applying re-checks that the base revision
  is still the head (otherwise the proposal is `stale`), requires
  `confirm_destructive=true` when destructive operations are present, and creates a new
  revision with author `ai`.
- Applied AI changes start at validation level `preview` like any other change.

## Honesty rules (system prompt)

The system prompt instructs the model not to invent specifications, datasheet content,
pin assignments or validation results; to look up pins via `get_part`; to ask
clarification questions when requirements are incomplete; and to state assumptions and
uncertainty. These rules are backed by mechanisms rather than trust: pins are validated
against KiCad libraries, validation status comes only from KiCad runs, and nothing is
applied without the user.

## Testing

- `tests/test_api.py` drives the orchestrator with a scripted provider (tool
  validation, invalid proposals, apply/reject, destructive confirmation).
- `tests/test_claude_provider.py` runs `ClaudeProvider` against a local mock of the
  Messages API to verify the request shape (model, effort, strict tools, fallback beta)
  and the tool-use loop. No live API calls are made in tests.
- A live end-to-end conversation has **not** been tested in this environment because no
  API key was available.

## Next steps

- Structured design planning (requirements → block diagram → part selection) with
  explicit clarification rounds.
- Datasheet ingestion (PDF via the Files API) with citations, so electrical values can
  be grounded in the actual datasheet.
- Streaming responses to the UI and per-turn progress.
- Evaluation set for proposal quality before expanding the AI's operation surface.

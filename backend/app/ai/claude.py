"""Claude implementation of :class:`LLMProvider` using the official Anthropic SDK.

The API key is read from server-side configuration only (``ANTHROPIC_API_KEY``)
and never sent to the browser.
"""

from __future__ import annotations

import json
import logging

import anthropic

from app.ai.provider import AgentTurn, LLMProvider, ProviderNotConfigured, ToolExecutor, ToolSpec
from app.core.config import Settings

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: anthropic.Anthropic | None = None

    def _get_client(self) -> anthropic.Anthropic:
        if not self.settings.anthropic_api_key:
            raise ProviderNotConfigured(
                "ANTHROPIC_API_KEY is not set on the backend. Add it to the backend environment "
                "(see .env.example) and restart the API."
            )
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key, max_retries=2,
                                               timeout=300.0, base_url=self.settings.anthropic_base_url)
        return self._client

    def status(self) -> dict:
        configured = bool(self.settings.anthropic_api_key)
        return {
            "provider": "anthropic",
            "configured": configured,
            "model": self.settings.anthropic_model,
            "effort": self.settings.anthropic_effort,
            "message": ("Claude is configured on the server." if configured else
                        "Set ANTHROPIC_API_KEY in the backend environment to enable the assistant."),
        }

    def _create(self, client, system, messages, tools):
        kwargs = dict(
            model=self.settings.anthropic_model,
            max_tokens=16000,
            system=system,
            messages=messages,
            tools=tools,
            output_config={"effort": self.settings.anthropic_effort},
        )
        if self.settings.anthropic_enable_fallbacks:
            # Server-side fallback: on a policy refusal the API re-runs the request on a fallback model.
            return client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
        return client.messages.create(**kwargs)

    def run_turn(self, system: str, history: list[dict], tools: list[ToolSpec], execute: ToolExecutor,
                 max_iterations: int) -> AgentTurn:
        client = self._get_client()
        tool_defs = []
        for t in tools:
            d = {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            if t.strict:
                d["strict"] = True
            tool_defs.append(d)
        messages: list = [dict(m) for m in history]
        trace: list[dict] = []
        usage = {"input_tokens": 0, "output_tokens": 0}
        model_used = None

        for _ in range(max_iterations):
            try:
                response = self._create(client, system, messages, tool_defs)
            except anthropic.AuthenticationError:
                return AgentTurn("", "error", error="The Anthropic API rejected the configured API key.")
            except anthropic.PermissionDeniedError:
                return AgentTurn("", "error", error="The configured API key lacks permission for this model.")
            except anthropic.NotFoundError:
                return AgentTurn("", "error", error=f"Model {self.settings.anthropic_model!r} was not found.")
            except anthropic.RateLimitError:
                return AgentTurn("", "error", error="Rate limited by the Anthropic API. Try again shortly.")
            except anthropic.BadRequestError as e:
                return AgentTurn("", "error", error=f"The Anthropic API rejected the request: {e.message}")
            except anthropic.APIStatusError as e:
                return AgentTurn("", "error", error=f"Anthropic API error {e.status_code}. Try again later.")
            except anthropic.APIConnectionError:
                return AgentTurn("", "error", error="Could not reach the Anthropic API (network error).")

            model_used = getattr(response, "model", None)
            if response.usage:
                usage["input_tokens"] += response.usage.input_tokens or 0
                usage["output_tokens"] += response.usage.output_tokens or 0
            text = "".join(b.text for b in response.content if b.type == "text")

            if response.stop_reason == "refusal":
                return AgentTurn(text or "The model declined to answer this request.", "refusal",
                                 model_used, trace, usage)
            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": response.content})
                continue
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not tool_uses:
                note = ""
                if response.stop_reason == "max_tokens":
                    note = "\n\n[Response truncated: output token limit reached.]"
                return AgentTurn(text + note, response.stop_reason, model_used, trace, usage)

            # Keep the full assistant content (including thinking blocks) for the next request.
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for tu in tool_uses:
                tool_input = tu.input if isinstance(tu.input, dict) else {}
                outcome = execute(tu.name, tool_input)
                trace.append({"tool": tu.name, "input": _truncate(tool_input), "ok": not outcome.is_error,
                              "result_preview": outcome.content[:300]})
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": outcome.content,
                                "is_error": outcome.is_error})
            messages.append({"role": "user", "content": results})

        return AgentTurn("I stopped because the tool-call limit for one turn was reached. "
                         "Please narrow the request.", "iteration_limit", model_used, trace, usage)


def _truncate(obj, limit: int = 2000):
    s = json.dumps(obj, default=str)
    return obj if len(s) <= limit else {"_truncated": s[:limit]}

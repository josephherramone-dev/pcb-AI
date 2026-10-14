"""Provider-independent LLM interface used by the AI orchestrator.

A provider runs one assistant turn: it calls the model, executes requested tools
through the supplied callback (which validates everything server-side) and
loops until the model produces a final answer. Provider-specific details such
as message formats, thinking blocks and retries stay inside the provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    strict: bool = False


@dataclass
class ToolOutcome:
    content: str
    is_error: bool = False


@dataclass
class AgentTurn:
    text: str
    stop_reason: str
    model: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    error: str | None = None


ToolExecutor = Callable[[str, dict], ToolOutcome]


class ProviderNotConfigured(RuntimeError):
    pass


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def status(self) -> dict:
        """Configuration status safe to show to users (never includes secrets)."""

    @abstractmethod
    def run_turn(self, system: str, history: list[dict], tools: list[ToolSpec], execute: ToolExecutor,
                 max_iterations: int) -> AgentTurn: ...


class DisabledProvider(LLMProvider):
    name = "none"

    def status(self) -> dict:
        return {"provider": "none", "configured": False,
                "message": "AI features are disabled (AI_PROVIDER=none)."}

    def run_turn(self, system, history, tools, execute, max_iterations) -> AgentTurn:
        raise ProviderNotConfigured("AI features are disabled (AI_PROVIDER=none).")

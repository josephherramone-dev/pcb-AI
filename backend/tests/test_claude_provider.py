"""Exercise ClaudeProvider against a local mock of the Messages API.

No real API calls are made. The test checks the request the official SDK sends
(model, effort, tools, fallback beta) and the tool-use loop handling.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.ai.claude import FALLBACK_BETA, ClaudeProvider
from app.ai.provider import ToolOutcome, ToolSpec
from app.core.config import Settings

RESPONSES = [
    {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": "Let me look."},
                    {"type": "tool_use", "id": "toolu_1", "name": "get_design", "input": {}}],
        "stop_reason": "tool_use", "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    },
    {
        "id": "msg_2", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": "The design has 5 components."}],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 20, "output_tokens": 7},
    },
]


def _serve():
    requests: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
            payload = json.dumps(RESPONSES[min(len(requests) - 1, len(RESPONSES) - 1)]).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, requests


def test_tool_loop_and_request_shape():
    server, requests = _serve()
    try:
        settings = Settings(anthropic_api_key="test-key", anthropic_base_url=f"http://127.0.0.1:{server.server_port}",
                            anthropic_effort="high", anthropic_enable_fallbacks=True)
        calls = []

        def execute(name, args):
            calls.append((name, args))
            return ToolOutcome(json.dumps({"components": 5}))

        tools = [ToolSpec("get_design", "Get the design", {"type": "object", "properties": {},
                                                           "additionalProperties": False}, strict=True)]
        turn = ClaudeProvider(settings).run_turn("system prompt", [{"role": "user", "content": "hi"}], tools,
                                                 execute, max_iterations=5)
    finally:
        server.shutdown()

    assert turn.stop_reason == "end_turn"
    assert turn.text == "The design has 5 components."
    assert calls == [("get_design", {})]
    assert turn.usage == {"input_tokens": 30, "output_tokens": 12}

    first, second = requests
    assert first["path"].startswith("/v1/messages")
    assert FALLBACK_BETA in first["headers"].get("anthropic-beta", "")
    body = first["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["output_config"] == {"effort": "high"}
    assert body["fallbacks"] == "default"
    assert body["tools"][0]["strict"] is True
    assert "thinking" not in body and "budget_tokens" not in json.dumps(body)
    # the follow-up request carries the assistant turn and the tool result
    msgs = second["body"]["messages"]
    assert msgs[1]["role"] == "assistant" and msgs[1]["content"][1]["type"] == "tool_use"
    assert msgs[2]["content"][0] == {"type": "tool_result", "tool_use_id": "toolu_1",
                                     "content": json.dumps({"components": 5}), "is_error": False}


def test_missing_key_is_reported():
    import pytest

    from app.ai.provider import ProviderNotConfigured

    provider = ClaudeProvider(Settings(anthropic_api_key=None))
    assert provider.status()["configured"] is False
    with pytest.raises(ProviderNotConfigured):
        provider.run_turn("s", [{"role": "user", "content": "x"}], [], lambda n, a: ToolOutcome(""), 1)

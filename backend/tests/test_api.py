from app.ai.provider import AgentTurn, LLMProvider


def _create(client, name="Test board", template="led_indicator"):
    r = client.post("/api/projects", json={"name": name, "template_id": template})
    assert r.status_code == 201, r.text
    return r.json()


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_project_crud_and_delete_confirmation(client, library):
    p = _create(client, "CRUD board")
    assert p["validation_level"] == "preview"
    assert p["component_count"] == 5
    assert any(x["id"] == p["id"] for x in client.get("/api/projects").json())

    r = client.patch(f"/api/projects/{p['id']}", json={"name": "Renamed board"})
    assert r.json()["name"] == "Renamed board"

    assert client.delete(f"/api/projects/{p['id']}", params={"confirm": "wrong"}).status_code == 400
    assert client.delete(f"/api/projects/{p['id']}", params={"confirm": "Renamed board"}).status_code == 204
    assert client.get(f"/api/projects/{p['id']}").status_code == 404


def test_empty_project_and_unknown_template(client, library):
    p = client.post("/api/projects", json={"name": "Empty"}).json()
    d = client.get(f"/api/projects/{p['id']}/design").json()
    assert d["design"]["components"] == []
    assert client.post("/api/projects", json={"name": "X", "template_id": "nope"}).status_code == 422


def test_operations_revisions_undo_redo(client, library):
    p = _create(client, "Ops board")
    d = client.get(f"/api/projects/{p['id']}/design").json()
    base = d["revision"]["id"]
    assert d["can_undo"] is False

    r = client.post(f"/api/projects/{p['id']}/operations", json={
        "base_revision_id": base, "message": "change value",
        "operations": [{"op": "set_value", "ref": "R1", "value": "2k2"}]})
    assert r.status_code == 200, r.text
    rev2 = r.json()["revision"]
    assert rev2["number"] == 2 and rev2["author"] == "user"

    # stale base revision is rejected
    r = client.post(f"/api/projects/{p['id']}/operations", json={
        "base_revision_id": base, "operations": [{"op": "set_value", "ref": "R1", "value": "3k3"}]})
    assert r.status_code == 409

    # invalid operation is rejected with its index
    r = client.post(f"/api/projects/{p['id']}/operations", json={
        "base_revision_id": rev2["id"], "operations": [
            {"op": "set_value", "ref": "R1", "value": "1k"},
            {"op": "connect", "net": "X", "pins": [{"ref": "R1", "pin": "9"}]}]})
    assert r.status_code == 422
    assert r.json()["detail"]["operation_error"]["index"] == 1

    r = client.post(f"/api/projects/{p['id']}/operations", json={
        "base_revision_id": rev2["id"], "operations": [{"op": "bogus"}]})
    assert r.status_code == 422

    assert client.post(f"/api/projects/{p['id']}/undo").json()["revision"]["number"] == 1
    d = client.get(f"/api/projects/{p['id']}/design").json()
    assert next(c for c in d["design"]["components"] if c["ref"] == "R1")["value"] == "1k"
    assert d["can_redo"] is True
    assert client.post(f"/api/projects/{p['id']}/redo").json()["revision"]["number"] == 2

    revs = client.get(f"/api/projects/{p['id']}/revisions").json()
    assert [r["number"] for r in revs] == [2, 1]
    r = client.post(f"/api/projects/{p['id']}/revisions/{revs[1]['id']}/restore").json()
    assert r["revision"]["number"] == 3


def test_render_models(client, library):
    p = _create(client, "Render board", "ne555_blinker")
    sch = client.get(f"/api/projects/{p['id']}/render/schematic").json()
    assert sch["kind"] == "preview"
    assert "Timer:NE555P" in sch["symbols"]
    assert len(sch["labels"]) == len(sch["wires"]) > 0
    pcb = client.get(f"/api/projects/{p['id']}/render/pcb").json()
    assert len(pcb["components"]) == 9  # PWR_FLAGs are not on the board
    assert pcb["ratsnest"], "unrouted board must show ratsnest lines"


def test_library_endpoints(client, library):
    parts = client.get("/api/library/parts").json()
    assert "Power" in parts["categories"]
    detail = client.get("/api/library/parts/ne555_dip8").json()
    assert {p["number"] for p in detail["pins"]} == {str(i) for i in range(1, 9)}
    assert detail["footprint_render"]["pads"]
    assert client.get("/api/library/parts/unknown").status_code == 404
    assert len(client.get("/api/templates").json()) == 3


def test_ai_unconfigured_reports_clearly(client, library):
    p = _create(client, "AI board")
    status = client.get("/api/ai/status").json()
    assert status["configured"] is False
    assert "ANTHROPIC_API_KEY" in status["message"]
    r = client.post(f"/api/projects/{p['id']}/ai/messages", json={"content": "hello"})
    assert r.status_code == 503


class ScriptedProvider(LLMProvider):
    """Deterministic provider that exercises the orchestrator's tool validation."""

    name = "scripted"

    def __init__(self, script):
        self.script = script
        self.results = []

    def status(self):
        return {"provider": "scripted", "configured": True}

    def run_turn(self, system, history, tools, execute, max_iterations):
        assert {t.name for t in tools} >= {"get_design", "propose_changes", "get_validation_report"}
        for name, args in self.script:
            self.results.append(execute(name, args))
        return AgentTurn(text="Proposed a change.", stop_reason="end_turn", model="scripted")


def test_ai_proposal_flow(client, library, monkeypatch):
    from app.ai import orchestrator

    p = _create(client, "AI flow board")
    provider = ScriptedProvider([
        ("get_design", {}),
        ("get_part", {"part_id": "led_0805"}),
        ("propose_changes", {"title": "bad", "summary": "x", "operations": [
            {"op": "connect", "net": "X", "pins": [{"ref": "D1", "pin": "7"}]}]}),
        ("propose_changes", {"title": "Add second LED", "summary": "Adds D2", "assumptions": ["5 V supply"],
                             "operations": [
                                 {"op": "add_component", "part_id": "led_0805", "x": 140, "y": 90},
                                 {"op": "connect", "net": "GND", "pins": [{"ref": "D2", "pin": "1"}]}]}),
        ("get_validation_report", {}),
    ])
    monkeypatch.setattr(orchestrator, "get_provider", lambda: provider)
    from app.api import ai as ai_api
    monkeypatch.setattr(ai_api, "get_provider", lambda: provider)

    r = client.post(f"/api/projects/{p['id']}/ai/messages", json={"content": "Add another LED"})
    assert r.status_code == 200, r.text
    msg = r.json()
    get_design, get_part, bad, good, report = provider.results
    assert not get_design.is_error and '"revision"' in get_design.content
    assert '"pins"' in get_part.content
    assert bad.is_error and "has no pin '7'" in bad.content
    assert not good.is_error
    assert "No KiCad checks" in report.content
    assert msg["proposal"]["title"] == "Add second LED"
    assert msg["proposal_status"] == "pending"

    r = client.post(f"/api/projects/{p['id']}/ai/messages/{msg['id']}/apply", json={})
    assert r.status_code == 200, r.text
    assert r.json()["revision"]["author"] == "ai"
    d = client.get(f"/api/projects/{p['id']}/design").json()
    assert any(c["ref"] == "D2" for c in d["design"]["components"])

    # applying twice is refused
    assert client.post(f"/api/projects/{p['id']}/ai/messages/{msg['id']}/apply", json={}).status_code == 409
    msgs = client.get(f"/api/projects/{p['id']}/ai/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["proposal_status"] == "applied"


def test_ai_destructive_proposal_requires_confirmation(client, library, monkeypatch):
    from app.ai import orchestrator
    from app.api import ai as ai_api

    p = _create(client, "AI destructive board")
    provider = ScriptedProvider([("propose_changes", {"title": "Remove LED", "summary": "x", "operations": [
        {"op": "remove_component", "ref": "D1"}]})])
    monkeypatch.setattr(orchestrator, "get_provider", lambda: provider)
    monkeypatch.setattr(ai_api, "get_provider", lambda: provider)
    msg = client.post(f"/api/projects/{p['id']}/ai/messages", json={"content": "remove the LED"}).json()
    assert msg["proposal"]["destructive_operations"] == [0]
    url = f"/api/projects/{p['id']}/ai/messages/{msg['id']}/apply"
    assert client.post(url, json={}).status_code == 409
    assert client.post(url, json={"confirm_destructive": True}).status_code == 200


def test_legal_endpoint(client):
    data = client.get("/api/legal").json()
    assert "without warranty" in data["engineering_disclaimer"]
    assert "Anthropic" in data["ai_disclosure"]
    assert {a["license"] for a in data["attributions"]} >= {"GPL-3.0-or-later", "CC-BY-SA-4.0 with design exception"}

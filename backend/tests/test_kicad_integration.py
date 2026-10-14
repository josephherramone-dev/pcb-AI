"""End-to-end tests against the configured KiCad engine (skipped when KiCad is unavailable).

These exercise the real vertical slice: template -> native KiCad project ->
KiCad netlist cross-check -> ERC/DRC -> exports -> download.
"""

import io
import zipfile

import pytest

pytestmark = pytest.mark.kicad


def _create(client, name, template):
    r = client.post("/api/projects", json={"name": name, "template_id": template})
    assert r.status_code == 201, r.text
    return r.json()


def _run(client, pid, kind):
    job = client.post(f"/api/projects/{pid}/jobs", json={"kind": kind}).json()
    job = client.get(f"/api/jobs/{job['id']}", params={"include_log": True}).json()
    assert job["status"] == "succeeded", job
    return job


def _validation(client, pid):
    return client.get(f"/api/projects/{pid}/design").json()["validation"]


@pytest.mark.parametrize("template", ["led_indicator", "ldo_3v3", "ne555_blinker"])
def test_template_validates_structurally(client, kicad_caps, template):
    p = _create(client, f"Integration {template}", template)
    job = _run(client, p["id"], "validate")
    v = _validation(client, p["id"])
    checks = v["checks"]
    assert checks["kicad_project"]["status"] == "passed", checks["kicad_project"]
    assert checks["netlist_match"]["status"] == "passed", checks["netlist_match"]
    assert v["level"] in ("structural", "rules_passed")

    erc = checks["erc"]
    if kicad_caps["features"]["erc"]["available"]:
        assert erc["status"] == "passed", erc["violations"]
    else:
        assert erc["status"] == "unavailable"

    # The board is unrouted: KiCad DRC must report unconnected items - never a fake pass.
    drc = checks["drc"]
    assert drc["status"] == "failed"
    assert any(x["category"] == "unconnected" for x in drc["violations"])
    assert v["level"] == "structural"
    assert job["result"]["validation_level"] == "structural"


def test_erc_detects_undriven_power(client, kicad_caps):
    if not kicad_caps["features"]["erc"]["available"]:
        pytest.skip("ERC not available on this engine")
    p = _create(client, "ERC negative", "ldo_3v3")
    d = client.get(f"/api/projects/{p['id']}/design").json()
    r = client.post(f"/api/projects/{p['id']}/operations", json={
        "base_revision_id": d["revision"]["id"],
        "operations": [{"op": "remove_component", "ref": "#FLG1"}, {"op": "remove_component", "ref": "#FLG2"}]})
    assert r.status_code == 200
    _run(client, p["id"], "validate")
    erc = _validation(client, p["id"])["checks"]["erc"]
    assert erc["status"] == "failed"
    assert any("power" in x["type"] for x in erc["violations"]), erc["violations"]


def _pad(pcb, ref, number):
    return next(x for x in pcb["pads"] if x["ref"] == ref and x["number"] == number)


def test_routed_board_passes_drc(client, kicad_caps):
    """Route the LED indicator by hand; KiCad DRC must then report no errors."""
    p = _create(client, "Routed LED", "led_indicator")
    pid = p["id"]
    d = client.get(f"/api/projects/{pid}/design").json()
    r = client.post(f"/api/projects/{pid}/operations", json={
        "base_revision_id": d["revision"]["id"],
        "operations": [{"op": "move_footprint", "ref": "D1", "x": 122, "y": 90, "rotation": 180}]})
    assert r.status_code == 200, r.text
    pcb = client.get(f"/api/projects/{pid}/render/pcb").json()
    j1, j2 = _pad(pcb, "J1", "1"), _pad(pcb, "J1", "2")
    r1, r2 = _pad(pcb, "R1", "1"), _pad(pcb, "R1", "2")
    k, a = _pad(pcb, "D1", "1"), _pad(pcb, "D1", "2")

    def pt(x, y):
        return {"x": x, "y": y}

    ops = [
        {"op": "add_track", "net": "VIN", "points": [pt(j1["x"], j1["y"]), pt(r1["x"], j1["y"]),
                                                     pt(r1["x"], r1["y"])]},
        {"op": "add_track", "net": "LED_A", "points": [pt(r2["x"], r2["y"]), pt(a["x"], a["y"])]},
        {"op": "add_track", "net": "GND", "points": [pt(k["x"], k["y"]), pt(k["x"], 95), pt(j2["x"], 95),
                                                     pt(j2["x"], j2["y"])]},
    ]
    head = client.get(f"/api/projects/{pid}/design").json()["revision"]["id"]
    r = client.post(f"/api/projects/{pid}/operations", json={"base_revision_id": head, "operations": ops})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/projects/{pid}/render/pcb").json()["ratsnest"] == []

    _run(client, pid, "validate")
    v = _validation(client, pid)
    drc = v["checks"]["drc"]
    assert drc["status"] == "passed", drc["violations"]
    if kicad_caps["features"]["erc"]["available"]:
        assert v["level"] == "rules_passed"
    else:
        assert v["level"] == "structural"  # ERC cannot be run, so rules cannot be claimed as passed


def test_export_and_download(client, kicad_caps):
    p = _create(client, "Export board", "ne555_blinker")
    job = _run(client, p["id"], "export")
    arts = {a["kind"]: a for a in client.get(f"/api/projects/{p['id']}/artifacts").json()}
    assert {"kicad_project", "gerbers_zip", "bom_csv"} <= set(arts), arts.keys()
    assert set(job["result"]["artifacts"]) >= {arts["kicad_project"]["id"], arts["gerbers_zip"]["id"]}

    zf = zipfile.ZipFile(io.BytesIO(client.get(arts["kicad_project"]["download_url"]).content))
    names = zf.namelist()
    for ext in (".kicad_pro", ".kicad_sch", ".kicad_pcb"):
        assert any(n.endswith(ext) for n in names), names
    sch = zf.read(next(n for n in names if n.endswith(".kicad_sch"))).decode()
    assert sch.startswith("(kicad_sch") and "Timer:NE555P" in sch

    gerbers = zipfile.ZipFile(io.BytesIO(client.get(arts["gerbers_zip"]["download_url"]).content)).namelist()
    assert any(n.endswith(".drl") for n in gerbers)
    assert any("Edge_Cuts" in n for n in gerbers)
    bom = client.get(arts["bom_csv"]["download_url"]).text
    assert "NE555P" in bom and "U1" in bom

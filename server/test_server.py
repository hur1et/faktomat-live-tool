"""
Tests für den Server-Kern – Faktomat Live (Schritt 2).

Deckt ab:
  - Item-Validierung (gültig + jede Balance-/Schema-Verletzung),
  - Session-Lifecycle (create -> join -> items -> submit),
  - Submit-Validierung (Clamp, Ein-Submit-Regel),
  - Reveal-Gate (>=15) und Host-Token-Auth.

Lauf: python -m pytest server/test_server.py -q
Nutzt server/items.example.json (Platzhalter), nie die echten Items.
"""

from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.items import ItemValidationError, load_items, validate_items

EXAMPLE = Path(__file__).with_name("items.example.json")


# --- Item-Validierung ------------------------------------------------------

def _raw_items() -> list[dict]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))["items"]


def test_example_items_valid():
    itemset = load_items(EXAMPLE)
    assert len(itemset.items) == 24


def test_missing_file_fails_loud():
    with pytest.raises(ItemValidationError, match="nicht gefunden"):
        load_items("does_not_exist.json")


def test_wrong_count_fails(tmp_path):
    raw = {"version": "x", "source": "x", "items": _raw_items()[:23]}
    p = tmp_path / "items.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ItemValidationError, match="24 Items"):
        load_items(p)


def test_uneven_truth_balance_accepted(tmp_path):
    # Ground Truth ist 14/10, nicht 6/6. Eine 7/5-Verteilung je Task muss
    # den Validator PASSIEREN (nur 12/Task und nicht-leere Zellen zählen).
    raw_items = copy.deepcopy(_raw_items())
    for it in raw_items:
        if it["task"] == "left" and it["truth_value"] is False:
            it["truth_value"] = True  # left: 7 wahr / 5 falsch
            break
    p = tmp_path / "items.json"
    p.write_text(json.dumps({"version": "x", "source": "x", "items": raw_items}), encoding="utf-8")
    itemset = load_items(p)  # darf NICHT werfen
    assert len(itemset.items) == 24


def test_empty_cell_fails(tmp_path):
    # Kein einziges falsches Item in Task-left -> d′/b′ nicht berechenbar.
    raw_items = copy.deepcopy(_raw_items())
    for it in raw_items:
        if it["task"] == "left" and it["truth_value"] is False:
            it["truth_value"] = True
    p = tmp_path / "items.json"
    p.write_text(json.dumps({"version": "x", "source": "x", "items": raw_items}), encoding="utf-8")
    with pytest.raises(ItemValidationError, match="leer"):
        load_items(p)


def test_duplicate_id_fails(tmp_path):
    raw_items = copy.deepcopy(_raw_items())
    raw_items[1]["id"] = raw_items[0]["id"]
    p = tmp_path / "items.json"
    p.write_text(json.dumps({"version": "x", "source": "x", "items": raw_items}), encoding="utf-8")
    with pytest.raises(ItemValidationError, match="Doppelte"):
        load_items(p)


# --- App-Fixture (lädt die Beispiel-Items via Env-Var) ---------------------

@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("FAKTOMAT_ITEMS", str(EXAMPLE))
    import server.app as app_module
    importlib.reload(app_module)  # Items + Store frisch pro Test
    return TestClient(app_module.app)


# --- Session-Lifecycle -----------------------------------------------------

def test_create_and_join(client):
    r = client.post("/api/session")
    assert r.status_code == 200
    body = r.json()
    code, host_token = body["code"], body["host_token"]

    r = client.post(f"/api/session/{code}/join")
    assert r.status_code == 200
    assert r.json()["participant_token"]

    r = client.get(f"/api/session/{code}/items")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 24
    assert "truth_value" in items[0]  # Client braucht sie fürs Scoring


def test_join_unknown_session_404(client):
    assert client.post("/api/session/deadbeef/join").status_code == 404


# --- Submit-Validierung ----------------------------------------------------

def _new_session(client):
    body = client.post("/api/session").json()
    return body["code"], body["host_token"]


def test_submit_ok_and_single_submit(client):
    code, _ = _new_session(client)
    token = client.post(f"/api/session/{code}/join").json()["participant_token"]

    r = client.post(f"/api/session/{code}/submit",
                    json={"participant_token": token, "d_prime": 1.0, "b_prime": -0.5})
    assert r.status_code == 200
    assert r.json()["submitted"] == 1

    # Zweiter Submit mit demselben Token -> 409.
    r = client.post(f"/api/session/{code}/submit",
                    json={"participant_token": token, "d_prime": 0.2, "b_prime": 0.1})
    assert r.status_code == 409


def test_submit_out_of_range_rejected(client):
    code, _ = _new_session(client)
    token = client.post(f"/api/session/{code}/join").json()["participant_token"]
    r = client.post(f"/api/session/{code}/submit",
                    json={"participant_token": token, "d_prime": 99.0, "b_prime": 0.0})
    assert r.status_code == 409


def test_submit_missing_fields_400(client):
    code, _ = _new_session(client)
    token = client.post(f"/api/session/{code}/join").json()["participant_token"]
    r = client.post(f"/api/session/{code}/submit", json={"participant_token": token})
    assert r.status_code == 400


# --- Reveal-Gate + Auth ----------------------------------------------------

def test_reveal_requires_host_token(client):
    code, host_token = _new_session(client)
    r = client.post(f"/api/session/{code}/reveal", json={"stage": 1})
    assert r.status_code == 403


def test_reveal_gate_blocks_below_15(client):
    code, host_token = _new_session(client)
    # 10 Teilnahmen -> unter dem Gate.
    for _ in range(10):
        t = client.post(f"/api/session/{code}/join").json()["participant_token"]
        client.post(f"/api/session/{code}/submit",
                    json={"participant_token": t, "d_prime": 0.5, "b_prime": 0.0})
    r = client.post(f"/api/session/{code}/reveal", json={"stage": 1},
                    headers={"X-Host-Token": host_token})
    assert r.status_code == 409


def test_reveal_opens_at_15(client):
    code, host_token = _new_session(client)
    for _ in range(15):
        t = client.post(f"/api/session/{code}/join").json()["participant_token"]
        client.post(f"/api/session/{code}/submit",
                    json={"participant_token": t, "d_prime": 0.5, "b_prime": 0.0})
    r = client.post(f"/api/session/{code}/reveal", json={"stage": 2},
                    headers={"X-Host-Token": host_token})
    assert r.status_code == 200
    assert r.json()["reveal_stage"] == 2


# --- Host-View: Seite, SSE-Auth, Join-Zähler, Benchmark-Flag ----------------

def test_host_page_served(client):
    code, _ = _new_session(client)
    r = client.get(f"/host/{code}")
    assert r.status_code == 200
    assert "Host" in r.text


def test_stream_rejects_missing_token(client):
    code, _ = _new_session(client)
    assert client.get(f"/api/session/{code}/stream").status_code == 403


def test_stream_accepts_query_token(client):
    code, host_token = _new_session(client)
    # ?once=1 -> endlicher Stream, sonst deadlockt der synchrone TestClient
    # am unendlichen SSE-Generator.
    r = client.get(f"/api/session/{code}/stream?token={host_token}&once=1")
    assert r.status_code == 200
    line = next(l for l in r.text.splitlines() if l.startswith("data:"))
    payload = json.loads(line[5:])
    assert {"joined", "submitted", "reveal_stage"} <= set(payload)


def test_joined_counter_increments():
    from server.store import SessionStore
    store = SessionStore()
    s = store.create_session()
    store.issue_participant_token(s.code)
    store.issue_participant_token(s.code)
    assert store.get(s.code).joined == 2


def test_benchmark_attached_at_stage2(monkeypatch, tmp_path):
    bench = {"source": "test", "d_prime": {"bin_edges": [0, 1], "densities": [1.0]},
             "b_prime": {"bin_edges": [-1, 1], "densities": [0.5]}}
    bp = tmp_path / "benchmark.json"
    bp.write_text(json.dumps(bench), encoding="utf-8")
    monkeypatch.setenv("FAKTOMAT_ITEMS", str(EXAMPLE))
    monkeypatch.setenv("FAKTOMAT_BENCHMARK", str(bp))
    import server.app as app_module
    importlib.reload(app_module)
    c = TestClient(app_module.app)

    body = c.post("/api/session").json()
    code, host_token = body["code"], body["host_token"]
    for _ in range(15):
        t = c.post(f"/api/session/{code}/join").json()["participant_token"]
        c.post(f"/api/session/{code}/submit",
               json={"participant_token": t, "d_prime": 0.5, "b_prime": 0.1})
    c.post(f"/api/session/{code}/reveal", json={"stage": 2},
           headers={"X-Host-Token": host_token})
    agg = c.get(f"/api/session/{code}/aggregate",
                headers={"X-Host-Token": host_token}).json()
    assert agg["benchmark"]["source"] == "test"
    assert "kde" in agg["b_prime"]


# --- Testmodus (?nogate=1, nur mit FAKTOMAT_DEV) -----------------------------

def test_nogate_forbidden_without_dev_flag(client, monkeypatch):
    monkeypatch.delenv("FAKTOMAT_DEV", raising=False)
    code, host_token = _new_session(client)
    r = client.get(f"/api/session/{code}/aggregate?nogate=1",
                   headers={"X-Host-Token": host_token})
    assert r.status_code == 403


def test_nogate_returns_data_below_gate_with_dev_flag(client, monkeypatch):
    monkeypatch.setenv("FAKTOMAT_DEV", "1")
    code, host_token = _new_session(client)
    for _ in range(2):  # nur 2 Testgeräte, weit unter dem Gate
        t = client.post(f"/api/session/{code}/join").json()["participant_token"]
        client.post(f"/api/session/{code}/submit",
                    json={"participant_token": t, "d_prime": 0.5, "b_prime": 0.1})
    r = client.get(f"/api/session/{code}/aggregate?nogate=1",
                   headers={"X-Host-Token": host_token})
    body = r.json()
    assert body["ungated"] is True
    assert body["submitted"] == 2
    assert "d_prime" in body and "kde" in body["b_prime"]
    # Normaler Abruf bleibt trotz Dev-Flag gegated:
    normal = client.get(f"/api/session/{code}/aggregate",
                        headers={"X-Host-Token": host_token}).json()
    assert "d_prime" not in normal


# --- Benchmark-Endpunkt (Erklärfolie + Perzentil-Einordnung) -----------------

def test_benchmark_endpoint_serves_aggregates(monkeypatch, tmp_path):
    bench = {"source": "Test N=42",
             "b_prime": {"quantiles": {"p": [50], "values": [0.0]}}}
    bp = tmp_path / "benchmark.json"
    bp.write_text(json.dumps(bench), encoding="utf-8")
    monkeypatch.setenv("FAKTOMAT_ITEMS", str(EXAMPLE))
    monkeypatch.setenv("FAKTOMAT_BENCHMARK", str(bp))
    import server.app as app_module
    importlib.reload(app_module)
    c = TestClient(app_module.app)

    code = c.post("/api/session").json()["code"]
    # Bewusst OHNE Host-Token abrufbar: enthält nur Forschungsaggregate,
    # nichts aus der Session (braucht auch das Teilnehmer-Feedback).
    r = c.get(f"/api/session/{code}/benchmark")
    assert r.status_code == 200
    assert r.json()["b_prime"]["quantiles"]["p"] == [50]


def test_benchmark_endpoint_404s(monkeypatch, tmp_path):
    # Ohne geladene Benchmark-Datei und bei unbekannter Session -> 404.
    monkeypatch.setenv("FAKTOMAT_ITEMS", str(EXAMPLE))
    monkeypatch.setenv("FAKTOMAT_BENCHMARK", str(tmp_path / "fehlt.json"))
    import server.app as app_module
    importlib.reload(app_module)
    c = TestClient(app_module.app)

    code = c.post("/api/session").json()["code"]
    assert c.get(f"/api/session/{code}/benchmark").status_code == 404
    assert c.get("/api/session/deadbeef/benchmark").status_code == 404


# --- QR-Code (Host-Lobby) ----------------------------------------------------

def test_qr_svg_served(client):
    code, _ = _new_session(client)
    r = client.get(f"/api/session/{code}/qr.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg")
    assert b"<svg" in r.content


def test_qr_unknown_session_404(client):
    assert client.get("/api/session/deadbeef/qr.svg").status_code == 404


def test_qr_respects_forwarded_host(client):
    # Hinterm Reverse Proxy muss die öffentliche Adresse in den QR, nicht
    # localhost – unterschiedliche Hosts ergeben unterschiedliche Codes.
    code, _ = _new_session(client)
    a = client.get(f"/api/session/{code}/qr.svg",
                   headers={"X-Forwarded-Host": "faktomat.uni-jena.de",
                            "X-Forwarded-Proto": "https"}).content
    b = client.get(f"/api/session/{code}/qr.svg",
                   headers={"X-Forwarded-Host": "example.org",
                            "X-Forwarded-Proto": "https"}).content
    assert a != b


# --- Teilnehmer-View (statische Auslieferung) -------------------------------

def test_join_page_served_for_existing_session(client):
    code, _ = _new_session(client)
    r = client.get(f"/join/{code}")
    assert r.status_code == 200
    assert "Faktomat Live" in r.text


def test_join_page_404_for_unknown_session(client):
    assert client.get("/join/deadbeef").status_code == 404


# --- Aggregate-Endpunkt (Auth + Gate durchgereicht) ------------------------

def test_aggregate_requires_host_token(client):
    code, _ = _new_session(client)
    assert client.get(f"/api/session/{code}/aggregate").status_code == 403


def test_aggregate_below_gate_no_distribution(client):
    code, host_token = _new_session(client)
    for _ in range(5):
        t = client.post(f"/api/session/{code}/join").json()["participant_token"]
        client.post(f"/api/session/{code}/submit",
                    json={"participant_token": t, "d_prime": 0.5, "b_prime": 0.1})
    r = client.get(f"/api/session/{code}/aggregate", headers={"X-Host-Token": host_token})
    assert r.status_code == 200
    body = r.json()
    assert body["gate_open"] is False
    assert "d_prime" not in body


def test_aggregate_after_reveal_returns_bins(client):
    code, host_token = _new_session(client)
    for i in range(20):
        t = client.post(f"/api/session/{code}/join").json()["participant_token"]
        client.post(f"/api/session/{code}/submit",
                    json={"participant_token": t, "d_prime": (i % 5) * 0.4, "b_prime": (i % 3) * 0.3 - 0.3})
    client.post(f"/api/session/{code}/reveal", json={"stage": 2},
                headers={"X-Host-Token": host_token})
    r = client.get(f"/api/session/{code}/aggregate", headers={"X-Host-Token": host_token})
    body = r.json()
    assert "d_prime" in body and "b_prime" in body
    assert all(b["count"] >= 3 for b in body["b_prime"]["bins"]) or len(body["b_prime"]["bins"]) == 1

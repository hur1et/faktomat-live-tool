"""
Tests für den Server-Kern — Faktomat Live (Schritt 2).

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

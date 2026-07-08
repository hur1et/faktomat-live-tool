# Changelog — Faktomat Live

Alle nennenswerten Änderungen an diesem Projekt. Format lose nach
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/); Arbeitsschritte
verweisen auf den Arbeitsplan in `UEBERGABE_faktomat-live.md` Abschnitt 9.

## [Unreleased]

### Item-Balance: Ground Truth korrigiert (Entscheidung Julius, 2026-07-03)

- Die reale `items.json` (Codebook Interventionsstudie) ist **14 wahr / 10 falsch**,
  nicht die im Übergabedokument angenommene 6/6-Zellbalance. Diese Verteilung ist
  die akzeptierte **Ground Truth** — das Übergabedokument war an dieser Stelle falsch.
- `validate_items` erzwingt daher **nicht mehr** 6/6 je Zelle, sondern nur die
  fürs Scoring notwendigen Bedingungen: 24 Items, eindeutige IDs, 12/Task, und je
  Task beide truth_values vorhanden. Task-Balance (12/12) bleibt hart, weil b′
  daran hängt. Das Scoring zählt die Zellen ohnehin dynamisch (n_true=14, n_false=10).
- Test `test_cell_imbalance_fails` ersetzt durch `test_uneven_truth_balance_accepted`
  (7/5 muss passieren) + `test_empty_cell_fails` (leere Zelle muss abbrechen).
  Suite jetzt 14/14 grün; Server startet real mit `items.json`.

### Schritt 2 — Server-Kern (in Arbeit)

Hinzugefügt:
- `server/items.py` — Item-Loader + Validator gegen das Schema aus UEBERGABE 5
  (genau 24 Items, 12/Task, 6 je Zelle task×truth_value). Fail-loud:
  Startabbruch mit klarer Meldung bei fehlender Datei, kaputtem JSON oder
  Balance-/Schema-Verstoß.
- `server/store.py` — Thread-sicherer RAM-Session-Store. Speichert nur geclampte
  `{d_prime, b_prime}`, abgegebene Teilnahme-Tokens und den Reveal-Stand — keine
  Rohantworten, keine IPs (UEBERGABE 7). Enthält Clamp (|score| ≤ 4.66),
  Ein-Submit-Regel und Reveal-Gate (≥ 15 Teilnahmen).
- `server/app.py` — FastAPI-App mit Endpunkten: `POST /api/session`,
  `POST .../join`, `GET .../items`, `POST .../submit`, `GET .../stream` (SSE),
  `POST .../reveal`. SSE setzt fest `X-Accel-Buffering: no` (UEBERGABE 3a.3).
  Host-Endpunkte über `X-Host-Token` authentifiziert.
- `server/items.example.json` — 24 balancierte **Platzhalter**-Items für Tests;
  `source`-Feld markiert sie klar als nicht-echt (Regel 4).
- `server/test_server.py` — 13 Tests: Item-Validierung, Session-Lifecycle,
  Submit-Clamp + Ein-Submit-Regel, Reveal-Gate, Host-Auth. **Alle grün.**
- Abhängigkeiten in `requirements.txt`: fastapi, uvicorn[standard], httpx, pytest.

### Aggregation — `/aggregate` ausgebaut (UEBERGABE 6)

Hinzugefügt:
- `server/aggregate.py` — reine Funktionen für die Host-Verteilungen:
  `histogram()` (6 Bins, Maximalwert ins letzte Bin), `merge_small_bins()`
  (Bins mit n<3 werden mit dem **kleineren Nachbarn** verschmolzen — Entscheidung
  Julius), `aggregate_scores()` (Gate ≥15; Stufe 1 → d′, Stufe 2 → +b′,
  Stufe 3 → +Median im Verteilungskontext). Unterhalb des Gates KEINE
  Verteilungsdaten. Ausgabe nur `{lo, hi, count}` — keine Einzelpunkte.
- `server/app.py`: `/aggregate` ruft jetzt `aggregate_scores`, kein Stub mehr.
- `server/test_aggregate.py` — 17 Tests (Binning, Merge-Fälle inkl. Rand,
  Gate, Stufen, kein Rohwert-Leak). Plus 3 Endpunkt-Tests in test_server.py.
- Real gegen laufenden Server verifiziert: Merge zieht kleine Bins zusammen,
  jedes verbleibende Bin ≥3, `room_median` nur in Stufe 3.

Testsumme jetzt: **31 Python (14 Server + 17 Aggregation) + 8 JS = alle grün.**

Bewusste Trade-offs:
- Client kennt `truth_value` (Scoring läuft lokal) — zugunsten des Datenschutzes,
  Rohantworten verlassen das Gerät nie (UEBERGABE 3).

### Schritt 1 — Scoring-Fundament (abgeschlossen)

Hinzugefügt:
- `scoring/scoring_reference.py` — verbindliche Python-Referenz für d′/b′
  (Probit via Acklam, Randkorrektur Hautus 1995). Aus dem Repo-Root verschoben.
- `client/scoring.js` — 1:1-JS-Port (ES-Modul): `probit()` + `computeScores()`.
  Acklam-Konstanten zeichengleich übernommen.
- `client/scoring.test.mjs` — 8 Tests (node:test) gegen die verbindlichen
  Vektoren aus UEBERGABE 4.5, inkl. bitgenauem Abgleich (1e-6) gegen Python.
  **Alle grün.**
- `ARCHITECTURE.md`, `README.md`, `.gitignore`, `requirements.txt` (Fundament).

Aufgeräumt:
- verwaiste `scoring_reference.cpython-312.pyc` entfernt; `.pyc` in `.gitignore`.

---

Noch nicht begonnen (UEBERGABE 9): Teilnehmer-View (Schritt 3), Host-View mit
Reveal-Dramaturgie (Schritt 4), Lasttest + Deployment + Generalprobe (Schritt 5).

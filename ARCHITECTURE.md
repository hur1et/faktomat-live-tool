# ARCHITECTURE — Faktomat Live

Verbindliche Referenz für Datenfluss und Entscheidungen. Ergänzt das
Übergabedokument [`UEBERGABE_faktomat-live.md`](UEBERGABE_faktomat-live.md),
das bei Konflikten Vorrang behält (dessen Abschnitte 4 Scoring und 7 Datenschutz
sind bindend).

## Zweck

Standalone-Webapp, die den IBE-Faktomat (24 Items, Stolp et al.) als Live-Format
für eine Präsenzveranstaltung bereitstellt. Teilnehmende antworten am eigenen
Smartphone; der Raum sieht eine **aggregierte** Auswertung. **Kein** Studienbetrieb,
**keine** Datenerhebung, **keine** Persistenz.

## Leitprinzip: Datenschutz durch Architektur

Der zentrale Entwurfszwang (UEBERGABE 7): **Rohantworten verlassen das Endgerät nie.**
Daraus folgt fast alles andere:

- Scoring läuft **clientseitig** (`client/scoring.js`). Übertragen wird nur
  `{d_prime, b_prime}` — zwei Fließkommazahlen.
- State liegt **nur im RAM** des Servers (ein Dict pro Session). Kein DB, kein
  Redis, keine Logfiles mit Nutzdaten. Prozess-Ende = Daten weg.
- Da b′ ein Proxy für politische Orientierung ist (DSGVO Art. 9), gelten strenge
  Anonymitätsregeln bei jeder Projektion (UEBERGABE 6).

## Datenfluss

```
Teilnehmer-Gerät                    Server (RAM)                Host-Beamer
────────────────                    ────────────                ───────────
GET items (nach Join)  ◄─────────── Item-Auslieferung
24 Antworten (lokal)
computeScores()  ──┐
                   │ nur {d′, b′}
POST submit ───────┴──────────────► Aggregation (gebinnt)
                                    SSE: {submitted: n} ───────► Fortschritt
                                    reveal(stage) ◄──── Host löst manuell aus
                                    GET aggregate ─────────────► Histogramm/KDE
privates Feedback
(bleibt auf Gerät)
```

## Stack (aus UEBERGABE 3)

| Schicht | Wahl | Verworfene Alternative & Grund |
|---|---|---|
| Server | FastAPI + Uvicorn (Python 3.11+) | — |
| Frontend | Vanilla JS + minimales CSS | React/Vue: zwei Views rechtfertigen kein Framework |
| Echtzeit | SSE (nur Host-View) | WebSockets: Overkill, fragiler im Event-WLAN |
| State | RAM-Dict pro Session | DB/Redis/Files: widerspricht "keine Persistenz" (Feature, kein Mangel) |
| Charts | D3 (Host-View) | Chart.js: weniger Kontrolle über KDE/Overlay |
| Probit | Acklam-Approximation | erf-basiert: keine Standard-erf in JS-Stdlib |

## Scoring — Source of Truth

`scoring/scoring_reference.py` ist die verbindliche Referenz. `client/scoring.js`
ist ein 1:1-Port und **muss** die Referenzwerte auf den Testvektoren innerhalb
1e-6 reproduzieren. Randkorrektur: Log-linear (Hautus 1995), einheitlich für alle
Teilnehmenden — bis Abhängigkeit C (UEBERGABE 2) etwas anderes ergibt.

Beide Testsuiten sind Gate: **kein Deployment ohne grüne Scoring-Tests.**

## Verzeichnisse

```
scoring/   Python-Referenz + Tests (Source of Truth, dient auch als Server-Validator)
client/    Vanilla-JS-Client: scoring.js (+ Tests), später Views
server/    FastAPI-App (noch nicht angelegt — Schritt 2 des Arbeitsplans)
deploy/    systemd-Unit, Proxy-Snippets (noch nicht angelegt)
```

## Status

Arbeitsplan UEBERGABE 9:

- [x] **Schritt 1** — Scoring portiert, Python- + JS-Tests grün gegen die Vektoren (4.5).
- [x] **Schritt 2** — Server: Session-Lifecycle, Item-Auslieferung, Submit-Validierung, SSE,
      Reveal + Aggregation (Binning, n<3-Merge, Gate ≥15). 31 Tests grün, läuft real mit `items.json`.
- [ ] Schritt 3 — Teilnehmer-View (mobile-first, Retry-Queue, privates Feedback).
- [ ] Schritt 4 — Host-View (Fortschritt, 3 Reveal-Stufen, Binning/Merge, Overlay-Flag, Demo-Modus).
- [ ] Schritt 5 — Lasttest, Datenschutz-Review, Deployment, Generalprobe.

## Offene Abhängigkeiten (blockieren Inhalt, nicht Bau)

A) echte 24 Items · B) Benchmark-Summary · C) tatsächliche Randkorrektur des
Online-Faktomat · D) Uniserver-Zugang. Alle bei Stolp / Server-Admin. Bis dahin:
Platzhalter-Items, Hautus-Default, Fly.io/VPS als primäres Deploy (UEBERGABE 2, 3a).

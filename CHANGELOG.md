# Changelog – Faktomat Live

Alle nennenswerten Änderungen an diesem Projekt. Format lose nach
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/); "UEBERGABE" und
"Schritt N" verweisen auf den Arbeitsplan der internen Spezifikation.

## [Unreleased]

### Schritt 5 – Lasttest, Datenschutz-Review, Deployment-Vorbereitung

Lasttest (`scripts/loadtest.py`, asyncio + httpx):
- Simuliert N Teilnehmende parallel durch den echten Pfad: Join → Items →
  plausibel zufällige Antworten → Scoring (Python-Referenz, identisch zum
  JS-Client) → Submit. Ein Host-SSE-Stream zählt parallel mit; am Ende wird
  das Aggregat gegen die Teilnehmerzahl geprüft. Fester Seed, Exit-Code
  CI-tauglich.
- Ergebnisse (lokal, ein Uvicorn-Worker): **100 Teilnehmende in 0,63 s**
  (Submit-Median 130 ms, p95 249 ms), **300 in 1,91 s** (p95 776 ms), in
  beiden Läufen 100 % erfolgreiche Submits, SSE-Zähler erreichte stabil N,
  Bin-Summe = N. Wichtig zur Einordnung: alle Clients feuern im selben
  Moment – das reale Event verteilt sich über Minuten, die Werte sind also
  Worst Case.

Datenschutz-Review (gegen die verbindlichen Constraints der Spezifikation):
- Alle fünf Punkte am Code geprüft und belegt: nur `{d_prime, b_prime}`
  verlassen das Gerät; RAM-only ohne einen einzigen Schreibzugriff aufs
  Dateisystem; keine Cookies (Token in sessionStorage); Datenschutzhinweis
  vor Start; kein Export-Pfad.
- **Ein Fund, behoben:** Uvicorns Default-Access-Log enthielte Client-IPs
  und das Host-Token aus dem SSE-Query-String (EventSource kann keine
  Header setzen). Konsequenz: `--no-access-log` ist in allen
  Deployment-Configs fest verdrahtet, ebenso Proxy-Logs ohne IPs bzw. aus.

Deployment (`deploy/`, beide Gleise, Entscheidung am Vortag):
- `faktomat-live.service`: systemd-Unit mit strikter Isolation – eigener
  User, `MemoryMax=256M`, `CPUQuota=50%`, Dateisystem read-only
  (`ProtectSystem=strict`; die App schreibt nie), localhost-Port.
- `nginx-faktomat.conf` / `apache-faktomat.conf`: SSE-taugliche
  Proxy-Snippets (`proxy_buffering off` bzw. `flushpackets=on`),
  X-Forwarded-Header für den QR-Code, Access-Log aus.
- `Dockerfile` + `fly.toml` für Fly.io als Plan B. Zwei Betriebsregeln aus
  dem RAM-only-State: exakt EINE Maschine, Auto-Stop aus.
- Einschränkung dokumentiert: Die App braucht eine eigene (Sub-)Domain,
  kein Pfad-Präfix – der Client baut absolute Pfade.

Repo:
- Whitelist-Prinzip für Dokumentation: öffentlich sind nur README und
  CHANGELOG, alle übrigen .md sind interne Arbeitsdokumente und gitignored.

### Schritt 6 – CD-konforme Gestaltung (FAKT-O-MAT-CD aus faktomat_flyer)

- CD-Assets nach `client/assets/` übernommen: Logo `fom-rgb.svg` (1,6 KB),
  gelbe Form `fom-gf.svg` (0,5 KB), Montserrat variable TTF (745 KB).
  Quelle: `projects/faktomat_flyer` (Kallinich-CD; Farbwerte aus
  rollup_faktomat_FINAL.html): Gelb #f2e61a, Orange #ef7d00, Schwarz #1a1a1a,
  Grau #f4f4f2, Montserrat.
- Teilnehmer-View: CD-Farben, Logo, Claim-Box mit Gelb-Kante, gelbe
  Primär-Buttons (Schwarz auf Gelb – Kontrast), Ergebniswerte in Orange.
  Webfont hier BEWUSST nicht geladen (745 KB vs. Mobilfunk, UEBERGABE 3) –
  Montserrat-Fallback-Stack; Seite bleibt ~15 KB.
- Host-View: Montserrat via @font-face (Beamer-Gerät), Logo im Header,
  aktive Stufe gelb, KDE/Balken in CD-Orange #ef7d00.
- Verifiziert: 41 Python-Tests grün, Assets/Seiten am laufenden Server geprüft.

### Schritt 4 – Host-View (auf `dev`)

- `server/aggregate.py`: serverseitige Gauß-KDE (Silverman-Bandbreite) –
  Rohwerte verlassen den Server nie, ausgeliefert wird nur das Gitter.
  b′-KDE ab Reveal-Stufe 2 im Aggregate. Median gerundet.
- `server/app.py`: `GET /host/{code}`; SSE akzeptiert `?token=` (EventSource
  kann keine Header) und `?once=1` (endlicher Stream für Tests/curl-Diagnose);
  SSE-Payload um `joined` erweitert (Zähler in `store.py`, keine Personendaten);
  Benchmark-Feature-Flag `FAKTOMAT_BENCHMARK` (Datei fehlt → Overlay aus).
- `client/host.html` + `client/host.js`: Fortschritt („X abgeschlossen / Y
  beigetreten"), drei manuell ausgelöste Reveal-Stufen mit Gate-Anzeige,
  Charts als handgerolltes SVG (BEWUSST kein D3: keine externe Abhängigkeit
  am Eventtag; KDE kommt fertig vom Server – Abweichung von UEBERGABE-3-
  Präferenz, dokumentiert). Balkenhöhen als Dichten (Merge-Bins ungleich
  breit!). Demo-Modus rein clientseitig, gelb gebannert, ohne Server.
- `MODERATION.md`: Briefing nach UEBERGABE 6 (Frames, b′-Sprachregelung,
  erwartbares Links-b′, Anonymitätsregeln, Technik-Ausfall).
- Fix: SSE-Test deadlockte am unendlichen Generator → `?once=1`.
- Tests: 41 Python + 13 JS grün. Smoke am echten Server: Host-Seite, SSE
  (joined/submitted), Stufe 3 mit 100-Punkt-KDE + Benchmark (N=1518) + Median.

### Benchmark-Overlay aus IBE 2.4 (Abhängigkeit B, Fallback-Pfad)

- `scoring/compute_benchmark.py` – rechnet d′/b′ aller 1.518 Completes der
  IBE-2.4-Erhebung (meta-d-pipeline, `dataset2_IBE24.csv` – ACHTUNG: dataset**2**
  = Welle 2.**4**) mit derselben Hautus-Korrektur wie das Live-Tool und schreibt
  NUR Aggregate nach `benchmark.json` (gitignored): 40-Bin-Histogramm,
  Perzentile p1–p99, Summary. Truth-Key aus `config/item_key_ibe24.json`
  (verifiziert, Stolp Jan 2026), inkl. AddIBE-Spalten-Mapping für IBE11/12/17/18.
- Validierung: mean d′ = 0.4451 vs. 0.451 in Stolps eigener Type-1-Replikation
  (Differenz = andere Randkorrektur) ✅. b′: M = 0.11, Md = 0.00, SD = 0.68.
- Item-Plausibilisierung nach Julius' Hinweis (aufsteigende Nummerierung):
  alle 24 Texte inhaltlich gegen truth_value/task/domain geprüft – konsistent.
  Restrisiko Text↔ID dokumentiert; finale Absicherung braucht das
  Codebook_Interventionsstudie.xlsx (nicht im Workspace). Präzedenzfall 2.3
  (v_12/v_13-Codebook-Fehler) bekannt.
- OFFEN: Repräsentativität der 2.4-Stichprobe unbestätigt → Event-Framing
  („…von Deutschland?") vor Nutzung mit Stolp klären. Kategorien-Schwellen des
  Original-Faktomat (links-progressiv…rechts-konservativ) unbekannt →
  nachfragen oder Quintile verwenden.

### Schritt 3 – Teilnehmer-View (auf `dev`)

Hinzugefügt:
- `client/join.html` – mobile-first, drei Screens: Datenschutzhinweis
  (Wortlaut nach UEBERGABE 7.4) → Item-Schleife → privates Feedback.
  CSS inline, daumentaugliche Buttons, Payload gesamt ~15 KB.
- `client/app.js` – Ablauf: Join (Token in sessionStorage, kein Cookie) →
  Items laden → Fisher-Yates-Shuffle → 24 Antworten → Scoring LOKAL →
  Submit nur {d′, b′} → Feedback. Antwortliste wird nie serialisiert.
- `client/submit-queue.js` – Retry mit exponentiellem Backoff (1/2/4/8 s,
  max. 5 Versuche); 4xx terminal (409 wird nicht wiederholt), Netzfehler/5xx
  transient. fetch/sleep injizierbar → ohne Browser testbar.
- `client/submit-queue.test.mjs` – 5 Tests (Backoff-Abfolge, 409-Terminalität,
  Aufgabe nach 5 Versuchen). JS-Suite jetzt 13 Tests.
- `server/app.py`: `GET /join/{code}` (404 bei unbekannter Session – Items
  nicht öffentlich verlinkt) + `/static`-Mount. 2 neue Endpunkt-Tests.

Repo:
- Erster Commit auf `main` (e4d2404, Schritt 1+2); `dev` angelegt (Regel 12).
- Echte `items.json` via .gitignore vom Repo ausgeschlossen, bis die Freigabe
  der Item-Texte geklärt ist (UEBERGABE 2, Abhängigkeit A).

Testsumme: **33 Python + 13 JS = alle grün.** Browser-Durchlauf auf echten
Geräten steht aus (Generalprobe, Schritt 5).

### Item-Balance: Ground Truth korrigiert (Entscheidung Julius, 2026-07-03)

- Die reale `items.json` (Codebook Interventionsstudie) ist **14 wahr / 10 falsch**,
  nicht die im Übergabedokument angenommene 6/6-Zellbalance. Diese Verteilung ist
  die akzeptierte **Ground Truth** – das Übergabedokument war an dieser Stelle falsch.
- `validate_items` erzwingt daher **nicht mehr** 6/6 je Zelle, sondern nur die
  fürs Scoring notwendigen Bedingungen: 24 Items, eindeutige IDs, 12/Task, und je
  Task beide truth_values vorhanden. Task-Balance (12/12) bleibt hart, weil b′
  daran hängt. Das Scoring zählt die Zellen ohnehin dynamisch (n_true=14, n_false=10).
- Test `test_cell_imbalance_fails` ersetzt durch `test_uneven_truth_balance_accepted`
  (7/5 muss passieren) + `test_empty_cell_fails` (leere Zelle muss abbrechen).
  Suite jetzt 14/14 grün; Server startet real mit `items.json`.

### Schritt 2 – Server-Kern (in Arbeit)

Hinzugefügt:
- `server/items.py` – Item-Loader + Validator gegen das Schema aus UEBERGABE 5
  (genau 24 Items, 12/Task, 6 je Zelle task×truth_value). Fail-loud:
  Startabbruch mit klarer Meldung bei fehlender Datei, kaputtem JSON oder
  Balance-/Schema-Verstoß.
- `server/store.py` – Thread-sicherer RAM-Session-Store. Speichert nur geclampte
  `{d_prime, b_prime}`, abgegebene Teilnahme-Tokens und den Reveal-Stand – keine
  Rohantworten, keine IPs (UEBERGABE 7). Enthält Clamp (|score| ≤ 4.66),
  Ein-Submit-Regel und Reveal-Gate (≥ 15 Teilnahmen).
- `server/app.py` – FastAPI-App mit Endpunkten: `POST /api/session`,
  `POST .../join`, `GET .../items`, `POST .../submit`, `GET .../stream` (SSE),
  `POST .../reveal`. SSE setzt fest `X-Accel-Buffering: no` (UEBERGABE 3a.3).
  Host-Endpunkte über `X-Host-Token` authentifiziert.
- `server/items.example.json` – 24 balancierte **Platzhalter**-Items für Tests;
  `source`-Feld markiert sie klar als nicht-echt (Regel 4).
- `server/test_server.py` – 13 Tests: Item-Validierung, Session-Lifecycle,
  Submit-Clamp + Ein-Submit-Regel, Reveal-Gate, Host-Auth. **Alle grün.**
- Abhängigkeiten in `requirements.txt`: fastapi, uvicorn[standard], httpx, pytest.

### Aggregation – `/aggregate` ausgebaut (UEBERGABE 6)

Hinzugefügt:
- `server/aggregate.py` – reine Funktionen für die Host-Verteilungen:
  `histogram()` (6 Bins, Maximalwert ins letzte Bin), `merge_small_bins()`
  (Bins mit n<3 werden mit dem **kleineren Nachbarn** verschmolzen – Entscheidung
  Julius), `aggregate_scores()` (Gate ≥15; Stufe 1 → d′, Stufe 2 → +b′,
  Stufe 3 → +Median im Verteilungskontext). Unterhalb des Gates KEINE
  Verteilungsdaten. Ausgabe nur `{lo, hi, count}` – keine Einzelpunkte.
- `server/app.py`: `/aggregate` ruft jetzt `aggregate_scores`, kein Stub mehr.
- `server/test_aggregate.py` – 17 Tests (Binning, Merge-Fälle inkl. Rand,
  Gate, Stufen, kein Rohwert-Leak). Plus 3 Endpunkt-Tests in test_server.py.
- Real gegen laufenden Server verifiziert: Merge zieht kleine Bins zusammen,
  jedes verbleibende Bin ≥3, `room_median` nur in Stufe 3.

Testsumme jetzt: **31 Python (14 Server + 17 Aggregation) + 8 JS = alle grün.**

Bewusste Trade-offs:
- Client kennt `truth_value` (Scoring läuft lokal) – zugunsten des Datenschutzes,
  Rohantworten verlassen das Gerät nie (UEBERGABE 3).

### Schritt 1 – Scoring-Fundament (abgeschlossen)

Hinzugefügt:
- `scoring/scoring_reference.py` – verbindliche Python-Referenz für d′/b′
  (Probit via Acklam, Randkorrektur Hautus 1995). Aus dem Repo-Root verschoben.
- `client/scoring.js` – 1:1-JS-Port (ES-Modul): `probit()` + `computeScores()`.
  Acklam-Konstanten zeichengleich übernommen.
- `client/scoring.test.mjs` – 8 Tests (node:test) gegen die verbindlichen
  Vektoren aus UEBERGABE 4.5, inkl. bitgenauem Abgleich (1e-6) gegen Python.
  **Alle grün.**
- `ARCHITECTURE.md`, `README.md`, `.gitignore`, `requirements.txt` (Fundament).

Aufgeräumt:
- verwaiste `scoring_reference.cpython-312.pyc` entfernt; `.pyc` in `.gitignore`.

---

Noch nicht begonnen (UEBERGABE 9): Teilnehmer-View (Schritt 3), Host-View mit
Reveal-Dramaturgie (Schritt 4), Lasttest + Deployment + Generalprobe (Schritt 5).

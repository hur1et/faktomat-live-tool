# Übergabedokument: Faktomat Live — Event-Schicht für den IBE

**Zweck dieses Dokuments:** Vollständige Spezifikation für die Umsetzung in VS Code / Claude Code. Dieses Dokument ist die verbindliche Referenz ("Source of Truth") für Architektur, Scoring und Datenschutz-Constraints. Bei Konflikten zwischen diesem Dokument und spontanen Implementierungsideen gilt dieses Dokument — insbesondere Abschnitt 4 (Scoring) und Abschnitt 7 (Datenschutz).

---

## 1. Projektkontext

- **Was:** Eine Webapp, die den bestehenden Faktomat (24 Items, IBE-Instrument nach Stolp, Finn, Ziemer, Thiel & Rothmund) als Live-Format für eine Präsenzveranstaltung verfügbar macht. Teilnehmende beantworten die Items auf dem eigenen Smartphone; anschließend wird eine aggregierte Auswertung des Raums projiziert.
- **Anlass:** Laienveranstaltung zu Desinformation, KomRex mit Panelistin vertreten.
- **Status:** Mit Arne Stolp (Erstautor des Instruments) abgesprochen; er unterstützt das Vorhaben, hat aber keine Kapazität. Eigenständige Umsetzung, standalone (NICHT in die bestehende Faktomat-Website integrieren — diese läuft bei einer externen Agentur).
- **Wissenschaftliche Grundlage:** Stolp et al., "Ideologically Biased Evaluation of Evidence — A Signal-Detection Approach to Measure Individual Differences" (PLOS-Einreichung, Rv2). Materialien: OSF osf.io/wuvk5.
- **Nicht-Ziele:** Keine Datenerhebung, keine Studie, keine Persistenz. Reines Demonstrationstool. Sobald jemand Daten behalten will, kippt es rechtlich in Datenerhebung → dann Stopp und neu bewerten.

## 2. Offene Abhängigkeiten (VOR Implementierungsbeginn klären)

| # | Abhängigkeit | Quelle | Fallback |
|---|---|---|---|
| A | ~~Aktuelle 24 Items~~ **ERLEDIGT (2026-07-03):** items.json aus Codebook_Interventionsstudie.xlsx generiert (Ground Truth lt. Julius), Kodierung gegen Tabelle 1 des Papers validiert | — | — |
| B | Benchmark-Summary der repräsentativen Stichprobe (Histogramm-Bins oder Quantile von d′ und b′, KEINE Rohdaten nötig) | Stolp | Reveal-Stufe 2 ohne Overlay ausliefern; Overlay als Feature-Flag |
| C | Randkorrektur des bestehenden Faktomat (wie werden Rates von 0/1 behandelt?) | Stolp | Log-linear-Korrektur nach Hautus (1995), siehe 4.3 — dokumentieren, dass dies ggf. vom Online-Faktomat abweicht |
| D | Uniserver: öffentliche Erreichbarkeit von außen (Mobilfunk-Test), Deploy-Zugang, sudoers-Zeile für Service-Neustart, Reverse-Proxy-Konfiguration (Apache oder nginx?) | Server-Admin des Lehrstuhls | Fly.io/VPS-Deployment wird primär (siehe 3a) |

## 3. Architektur

- **Stack:** FastAPI (Python 3.11+), Uvicorn. Frontend: Vanilla JS + minimales CSS, KEIN Framework (zwei einfache Views rechtfertigen kein React). Charts im Host-View: D3 oder Chart.js — D3 bevorzugt wegen KDE/Overlay-Kontrolle.
- **State:** Vollständig im RAM (ein Dict pro Session). Kein DB, kein Redis, keine Dateien. Daten sterben mit dem Prozess — das ist ein Feature (siehe 7).
- **Deployment (zweigleisig, Entscheidung am Vortag):**
  - **Primär — Uniserver** (dort läuft bereits eine formr-Instanz): nur unter den vier Bedingungen in Abschnitt 3a. Vorteil: uni-jena.de-Domain auf dem QR-Code (Vertrauen bei Öffentlichkeitsveranstaltung), kein externer Auftragsverarbeiter (DSGVO-relevant, da b′ ein Proxy für politische Orientierung ist).
  - **Fallback — Fly.io/kleiner VPS**: identisches Deployment als getesteter Plan B. QR-Code erst NACH der Vortags-Entscheidung finalisieren.
  - NICHT der Heimserver (IdeaPad) — kein Live-Event darf am Heim-Upload hängen. HTTPS zwingend.
- **Echtzeit:** Server-Sent Events (SSE) NUR für den Host-View (Fortschrittszähler, Reveal-Trigger). Teilnehmer-Clients machen einfache POSTs. KEINE WebSockets — Overkill und fragiler bei Veranstaltungs-WLAN.
- **Netz-Annahme:** Teilnehmende nutzen Mobilfunk, nicht Veranstaltungs-WLAN. Payloads winzig halten (< 5 KB). Submit-POST mit Retry-Queue im Client (bei Netzfehler: exponentieller Backoff, max. 5 Versuche, UI-Hinweis).

### 3a. Bedingungen für Deployment auf dem Uniserver (alle vier müssen erfüllt sein)

Leitprinzip: Das Risiko läuft in Richtung formr, nicht in Richtung Event — auf dem Server sammeln ggf. laufende Studien Daten. Die Live-App darf diese unter keinen Umständen beeinträchtigen.

1. **Öffentliche Erreichbarkeit (ZUERST prüfen, Showstopper-Kandidat):** Teilnehmende kommen über Mobilfunk. Test von einem Smartphone ohne eduroam/VPN: Ist der Server von außen über HTTPS erreichbar? Wenn nein → Uniserver-Option verwerfen (URZ-Firewall-Freigaben sind kein kurzfristiges Projekt).
2. **Strikte Isolation:** Eigener systemd-Service, eigener Unix-User, eigenes Verzeichnis, localhost-Port. Ressourcen hart begrenzen: `MemoryMax=256M`, `CPUQuota=50%`. Kein Zugriff auf formr-DB oder -Code. Beispiel-Unit ins Repo (`deploy/faktomat-live.service`).
3. **SSE durch den bestehenden Reverse Proxy:** Apache und nginx buffern per Default → SSE-Fortschrittszähler kommt nicht als Stream an. Apache: `ProxyPass /faktomat-live/ http://127.0.0.1:8xxx/ flushpackets=on`; nginx: `proxy_buffering off;` plus Response-Header `X-Accel-Buffering: no` (letzteren setzt die App selbst — in FastAPI-SSE-Response fest einbauen, schadet nirgends). VOR dem Event mit echtem Client testen.
4. **Eigenständiger Neustart-Zugriff am Eventtag:** Mindestens eine sudoers-Zeile für `systemctl restart faktomat-live` für Julius' Account. Wenn der Server-Admin das nicht einräumen kann → Fallback-VPS wird primär, denn dort besteht volle Kontrolle im Störungsfall.

**Vorgehen:** Beide Deployments aufsetzen und in der Generalprobe testen; Entscheidung am Vortag; erst danach QR-Code in Folien/Aushänge übernehmen.

### Komponenten

1. **Teilnehmer-View** (`/join/{code}`): Mobile-first. Ablauf: Datenschutzhinweis → Start → 24 Items einzeln, randomisierte Reihenfolge (clientseitig, Fisher-Yates), Antwort "wahr"/"falsch" per Button → clientseitiges Scoring → POST der zwei Kennwerte → privates Ergebnis-Feedback auf dem eigenen Display.
2. **Host-View** (`/host/{code}?token=...`): Großer Screen/Beamer. Fortschritt ("42 von 57 abgeschlossen"), Reveal-Buttons für drei Stufen (siehe 6). Reveal wird MANUELL von der Moderation ausgelöst, nie automatisch — der Reveal ist ein dramaturgischer Moment.
3. **Server:** Session-Verwaltung, Item-Auslieferung, Aggregation, SSE-Stream.

### API (minimal)

```
POST /api/session                     → Host legt Session an; Response: {code, host_token}
GET  /api/session/{code}/items        → Itemliste (ohne truth_value? NEIN — siehe Hinweis unten)
POST /api/session/{code}/submit       → Body: {d_prime: float, b_prime: float}
GET  /api/session/{code}/stream       → SSE für Host (auth: host_token): {submitted: n}
POST /api/session/{code}/reveal       → Host (auth: host_token): {stage: 1|2|3}
GET  /api/session/{code}/aggregate    → Host (auth: host_token): gebinnte Verteilungen (siehe 6)
```

**Hinweis zu truth_value im Client:** Da das Scoring clientseitig läuft, muss der Client die Wahrheitswerte kennen. Das ist ein bewusster Trade-off zugunsten des Datenschutzes (Rohantworten verlassen das Gerät nie). "Schummeln" durch DevTools ist bei einer Laien-Demoveranstaltung irrelevant. Items + truth_value werden erst NACH Session-Beitritt ausgeliefert, nicht öffentlich verlinkt.

**Submit-Validierung serverseitig:** d′ und b′ auf plausible Bereiche prüfen. Theoretische Maxima bei diesem Design mit Hautus-Korrektur: |d′| ≤ z(14.5/15) − z(0.5/11) ≈ 3.53; |b′| ≤ z(12.5/13) − z(0.5/13) ≈ 3.54. Werte mit Betrag > 3.6 → verwerfen (können nur aus fehlerhaftem Client-Scoring stammen). Ein Submit pro Session-Token (Token bei Beitritt vergeben, in sessionStorage, kein Cookie).

## 4. Scoring-Spezifikation (VERBINDLICH — nicht abweichen)

### 4.1 Datengrundlage pro Person

24 dichotome Antworten. Jedes Item hat: `truth_value ∈ {true, false}`, `task ∈ {left, right}` (Ideologie-Kongruenz der KORREKTEN Antwort), `domain ∈ {climate, security}`. Design: 12 Items pro Task, innerhalb balanciert nach truth_value (6/6) und Domäne.

### 4.2 Indizes (nach Stolp et al.)

**Diskriminationssensitivität d′** — Fähigkeit, wahre von falschen Aussagen zu unterscheiden:

```
hit_rate         = korrekt akzeptierte wahre Aussagen / alle wahren Aussagen
false_alarm_rate = fälschlich akzeptierte falsche Aussagen / alle falschen Aussagen
d′ = z(hit_rate) − z(false_alarm_rate)
```

**Ideologischer Bias b′** — Asymmetrie der Genauigkeit zwischen den Tasks:

```
right_correct_rate = korrekte Antworten (Hits + Correct Rejections) in Task-Right / 12
left_correct_rate  = korrekte Antworten in Task-Left / 12
b′ = z(right_correct_rate) − z(left_correct_rate)
```

- b′ > 0: rechtsgerichteter Bias; b′ < 0: linksgerichteter Bias; ≈ 0: keine Asymmetrie.
- z = Probit (Inverse der Standardnormal-CDF).
- **WICHTIG (Moderations- und Doku-Hinweis):** b′ ist NICHT das klassische SDT-Response-Criterion (keine generelle Ja-Sage-Tendenz), sondern ein Asymmetrie-Index der Genauigkeit über Ideologie-Kongruenz. Das Paper grenzt das explizit ab; diese Formulierung in jeden erklärenden Text übernehmen.

### 4.3 Randkorrektur (Log-linear, Hautus 1995)

z(0) und z(1) sind undefiniert. Korrektur: **einheitlich für ALLE Teilnehmenden** (nicht nur Randfälle) 0.5 auf Zähler, 1.0 auf Nenner:

```
rate_korrigiert = (Anzahl + 0.5) / (n + 1)
```

Beispiel d′: hit_rate = (hits + 0.5) / (n_true_items + 1). Beispiel b′: right_correct_rate = (correct_right + 0.5) / 13.

Falls Abhängigkeit C (Abschnitt 2) eine andere Korrektur ergibt: diese übernehmen und hier dokumentieren. Bis dahin gilt Hautus.

### 4.4 Inverse Normal-CDF in JavaScript

Scoring läuft clientseitig → Probit in JS nötig. **Acklams Algorithmus** implementieren (Standardapproximation, relative Genauigkeit ~1.15e-9). Referenzimplementierung siehe `scoring_reference.py` (beiliegend) — die JS-Implementierung MUSS gegen die dortigen Testvektoren bestehen (Toleranz 1e-6).

### 4.5 Verbindliche Testfälle

Aus dem Paper (Box 1; dort OHNE Randkorrektur gerechnet — Tests decken beide Pfade ab):

| Fall | Setup | Erwartung (ohne Korrektur) |
|---|---|---|
| Participant 1 | 7/10 korrekt in beiden Tasks; hit_rate=0.70, fa_rate=0.30 | d′ = 1.048 (±0.01), b′ = 0.0 |
| Participant 2 | Task-Right 9/10, Task-Left 5/10 | b′ = 1.28 (±0.01) |
| Randfall | 12/12 korrekt in einem Task | ohne Korrektur: undefiniert (Test: wirft Fehler); mit Hautus: endlicher Wert, rate = 12.5/13 |
| Symmetrie | Antwortvektor gespiegelt (Left↔Right) | b′ wechselt exakt das Vorzeichen |

Diese Tests als Unit-Tests in Python (Server-Referenz) UND als JS-Tests (Client) anlegen. CI-artig: kein Deployment ohne grüne Scoring-Tests.

## 5. Datenschemata

### items.json (Platzhalter im selben Schema mitliefern)

```json
{
  "version": "2026-07-XX",
  "source": "Stolp et al., OSF osf.io/wuvk5 — Stand bestätigen",
  "items": [
    {
      "id": "cc_l_t_01",
      "text": "Beispielaussage …",
      "truth_value": true,
      "task": "left",
      "domain": "climate"
    }
  ]
}
```

Validierung beim Serverstart (entspricht dem Ground-Truth-Design aus dem Codebook der Interventionsstudie): exakt 24 Items, 12 je Task, **7 wahre / 5 falsche Items je Task** (das Design ist NICHT 6/6/6/6 balanciert — symmetrisch über die Tasks, was für b′ entscheidend ist), 12 je Domäne, IDs eindeutig; sonst Startabbruch mit klarer Fehlermeldung. Hautus-Nenner ergeben sich daraus: d′ mit n_true=14 → 15, n_false=10 → 11; b′ je Task 12 → 13.

### benchmark.json (Feature-Flag; App muss ohne laufen)

```json
{
  "source": "Repräsentative Stichprobe Stolp et al., N=…",
  "d_prime": {"bin_edges": [...], "densities": [...]},
  "b_prime": {"bin_edges": [...], "densities": [...]}
}
```

## 6. Reveal-Dramaturgie (Host-View, drei manuelle Stufen)

1. **Stufe 1 — d′-Verteilung des Raums:** Unverfänglicher Einstieg ("Wie gut unterscheidet dieser Raum wahr von falsch?"). Histogramm, 5–6 Bins.
2. **Stufe 2 — b′-Verteilung mit Benchmark-Overlay:** Raumverteilung als geglättete Kurve (KDE, Gauß-Kernel, Bandbreite nach Silverman) ÜBER der repräsentativen Vergleichsverteilung. Frame: "Wie unterscheidet sich dieser Raum von Deutschland?" — nicht "Sind wir biased?".
3. **Stufe 3 — Raum-Marker:** Mittelwert/Median des Raums als Marker IN der Verteilung aus Stufe 2. NIEMALS als nackte Einzelzahl ohne Verteilungskontext (ein Raum-Mittelwert nahe 0 kann Bias-Auslöschung bei gemischtem Publikum bedeuten — das ist ein Moderationsthema, keine Entwarnung).

**Anonymitätsregeln für alle Aggregatgrafiken (VERBINDLICH):**
- Keine Einzelpunkte. Nur Histogramm (Bins ≥ 5 Personen breit gedacht: 5–6 Bins gesamt) oder KDE.
- Bins mit n < 3 mit dem Nachbarbin verschmelzen — bei b′ nicht verhandelbar (b′ ist ein Proxy für politische Orientierung → Nähe zu DSGVO-Art.-9-Kategorien), bei d′ ebenfalls anwenden.
- Reveal erst freischalten ab ≥ 15 abgeschlossenen Teilnahmen (Host-View zeigt vorher gesperrten Button mit Begründung).
- Kein Leaderboard, keine Nicknames, kein "besser als X %"-Vergleich während der Projektion. Individuelles Feedback ausschließlich privat auf dem eigenen Gerät.

**Moderations-Briefing (als MODERATION.md ins Repo):** Das wahrscheinliche Ergebnis bei selbstselektiertem zivilgesellschaftlichem Publikum ist ein Raum-b′ links von null. Die Moderation muss den Frame setzen, BEVOR das Publikum ihn setzt: "Voreingenommenheit betrifft nicht nur die anderen — das Instrument zeigt sie in beide Richtungen, und dieser Raum ist keine Ausnahme." Panelistin vorab informieren, welche drei Grafiken kommen und was sie zeigen können.

## 7. Datenschutz-Constraints (VERBINDLICH)

1. Rohantworten verlassen das Endgerät NIE. Clientseitiges Scoring, Übertragung ausschließlich `{d_prime, b_prime}`.
2. Keine Persistenz: kein DB, keine Logfiles mit Nutzdaten, State nur im RAM. Session-Ende oder Prozess-Ende = Daten weg. Explizit: Access-Logs des Reverse Proxy ohne IPs konfigurieren (Caddy: `log` ohne remote_ip, bzw. Logging ganz aus).
3. Keine Cookies. Session-Token in sessionStorage.
4. Join-Seite zeigt vor Start einen kompakten Datenschutzhinweis: was berechnet wird, dass nur zwei aggregierte Kennwerte übertragen werden, dass nichts gespeichert wird, dass die Projektion nur Gruppenverteilungen zeigt. Teilnahme = Tap auf "Verstanden, starten".
5. Kein Export, kein Download der Aggregatdaten. Wenn im Projektverlauf der Wunsch entsteht, Daten zu behalten → STOPP, das ist dann Datenerhebung mit Einwilligungserfordernis, außerhalb des Scopes dieses Tools.

## 8. Teststrategie & Generalprobe

- **Unit:** Scoring-Tests (4.5) in Python und JS. Item-Schema-Validierung. Binning-/Merge-Logik (n<3-Regel) mit synthetischen Verteilungen.
- **Lasttest:** Skript, das 100 simulierte Teilnehmende (zufällige plausible Antwortvektoren) parallel durch Join→Submit jagt; Host-SSE muss dabei stabil zählen. `locust` oder simples asyncio-Skript.
- **Generalprobe (nicht verhandelbar, vor dem Event):** 5–10 echte Smartphones, davon mindestens eines mit gedrosseltem Netz (iOS Low Data Mode / Android Datensparmodus), einmal kompletter Durchlauf inkl. Reveal auf einem Beamer/TV. Checkliste: QR lesbar aus 5 m? Buttons daumentauglich? Retry-Queue greift bei Flugmodus-an/aus?
- **Fallback fürs Event:** Wenn die Technik ausfällt: analoge Variante vorbereitet halten (Aufstellung im Raum entlang einer Achse). Der Host-View braucht außerdem einen "Demo-Modus" mit synthetischen Daten, damit die Dramaturgie auch bei Totalausfall der Teilnehmergeräte gezeigt werden kann.

## 9. Arbeitsplan für Claude Code (Reihenfolge einhalten)

1. Repo-Setup, `scoring_reference.py` + Tests portieren, JS-Scoring gegen Testvektoren (Abschnitt 4.5) — **erst wenn grün, weiterbauen**.
2. Server: Session-Lifecycle, Item-Auslieferung, Submit mit Validierung, SSE.
3. Teilnehmer-View (mobile-first, Retry-Queue, privates Feedback).
4. Host-View (Fortschritt, drei Reveal-Stufen, Binning/Merge, Benchmark-Overlay hinter Feature-Flag, Demo-Modus).
5. Lasttest, Datenschutz-Review gegen Abschnitt 7, Deployment, Generalprobe.

**Zeitrahmen (Konvention Julius):** Optimal ~10 h, Realistisch ~18 h (Faktor 1.75) — zuzüglich Klärung der Abhängigkeiten A–C und Generalprobe.

## 10. Explizit außerhalb des Scopes

- Konfidenz-Ratings / meta-d′ (nicht Teil des IBE-Instruments — nicht hinzuerfinden).
- Accounts, Mehrsprachigkeit, Wiederverwendung über mehrere Events ohne Neustart (Session = Prozesslaufzeit reicht).
- Jede Form von Datenspeicherung oder -export (siehe 7.5).

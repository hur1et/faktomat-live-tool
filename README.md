# Faktomat Live

Live-Event-Schicht für den IBE-Faktomat (24 Items, Stolp et al.). Teilnehmende
beantworten die Items am eigenen Smartphone; der Raum sieht eine aggregierte
Auswertung von d′ (Diskriminationssensitivität) und b′ (ideologischer Bias).

**Kein Studienbetrieb, keine Datenerhebung, keine Persistenz.** Rohantworten
verlassen das Endgerät nie. Das Scoring läuft auf dem Gerät, übertragen werden
nur zwei aggregierte Kennwerte. Der Server hält alles im RAM: keine Datenbank,
keine Logdateien mit Nutzdaten, keine Cookies. Die Auswertung zeigt
ausschließlich Gruppenverteilungen, freigeschaltet erst ab 15 Teilnahmen.

## Lokal ausprobieren

Du brauchst nur Python 3.11 oder neuer. Node.js ist optional (nur für die
JS-Tests).

### 1. Abhängigkeiten installieren

```
pip install -r requirements.txt
```

### 2. Items festlegen

Die echten Item-Texte liegen aus Lizenzgründen nicht im Repo. Zum Ausprobieren
liegen 24 Platzhalter-Items bei (`server/items.example.json`). Welche Datei der
Server lädt, steuert die Umgebungsvariable `FAKTOMAT_ITEMS`.

Windows (PowerShell):

```
$env:FAKTOMAT_ITEMS = "server/items.example.json"
```

macOS / Linux:

```
export FAKTOMAT_ITEMS=server/items.example.json
```

Wer die echten Items hat, legt sie als `items.json` ins Repo-Verzeichnis und
setzt die Variable auf diesen Pfad. Der Server prüft die Datei beim Start und
bricht mit einer klaren Fehlermeldung ab, wenn etwas nicht stimmt.

### 3. Server starten

```
python -m uvicorn server.app:app --port 8100
```

Der Server läuft jetzt unter `http://127.0.0.1:8100`. Es gibt keine Startseite,
alles hängt an einer Session.

### 4. Session anlegen

Eine Session legst du per POST an. Windows (PowerShell):

```
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8100/api/session"
```

macOS / Linux:

```
curl -X POST http://127.0.0.1:8100/api/session
```

Die Antwort enthält zwei Werte:

```
{"code": "a1b2c3", "host_token": "…langes Geheimnis…"}
```

Daraus bauen sich die beiden Ansichten:

| Ansicht | URL |
|---|---|
| Host (Beamer, Moderation) | `http://127.0.0.1:8100/host/a1b2c3?token=…host_token…` |
| Teilnahme (Smartphone) | `http://127.0.0.1:8100/join/a1b2c3` |

Die Host-Ansicht startet mit einer Lobby: großes Logo, QR-Code zum Beitreten,
Live-Zähler. Der Button „Zur Auswertung" wechselt zur Ansicht mit den drei
Reveal-Stufen.

### 5. Mit dem Handy beitreten

`127.0.0.1` funktioniert nur auf dem Rechner selbst. Damit ein Handy die App
erreicht, müssen Rechner und Handy im selben WLAN sein, und der Server muss an
allen Netzwerk-Schnittstellen lauschen:

```
python -m uvicorn server.app:app --host 0.0.0.0 --port 8100
```

Dann die lokale IP-Adresse des Rechners herausfinden (Windows: `ipconfig`,
Eintrag „IPv4-Adresse", z. B. `192.168.0.213`) und die Host-Ansicht im Browser
**über diese IP** öffnen, nicht über `127.0.0.1`:

```
http://192.168.0.213:8100/host/a1b2c3?token=…
```

Das ist wichtig, weil der QR-Code in der Lobby genau die Adresse kodiert, unter
der die Seite aufgerufen wurde. Öffnest du sie über die IP, zeigt der QR-Code
auf die IP, und das Handy kann ihn scannen und beitreten.

Wenn das Handy die Seite nicht lädt, blockiert vermutlich die Firewall des
Rechners eingehende Verbindungen. Windows fragt beim ersten Start meist selbst
nach („Zugriff zulassen"); falls nicht, muss Port 8100 freigegeben werden.

### 6. Demo- und Testmodus

Die Auswertung ist aus Anonymitätsgründen gesperrt, bis mindestens 15 Personen
abgegeben haben. Zum Ausprobieren gibt es zwei Wege:

**Demo-Modus (ohne Vorbereitung):** In der Host-Ansicht oben rechts auf
„Demo-Modus" klicken. Die Grafiken zeigen dann synthetische Daten, ein gelber
Banner macht das unübersehbar. Funktioniert auch komplett ohne Teilnehmende.

**Testmodus (mit 1 bis 3 echten Geräten):** Wer den echten Datenweg sehen will
(Handy gibt ab, Wert erscheint in der Grafik), startet den Server als
Dev-Instanz:

```
$env:FAKTOMAT_DEV = "1"        # Windows, vor dem Serverstart
export FAKTOMAT_DEV=1          # macOS / Linux
```

Dann zeigt der Demo-Modus statt synthetischer Daten die echten Abgaben, auch
unterhalb der 15er-Grenze, mit deutlichem Hinweis im Banner. Ohne diese
Variable ist der Weg gesperrt. Für einen echten Event-Einsatz die Variable
niemals setzen, sonst ließe sich die Anonymitätsgrenze umgehen.

## Tests

```
python -m pytest server/ -q
node --test client/scoring.test.mjs client/submit-queue.test.mjs
```

Die Scoring-Tests sind verbindlich: Die JS-Implementierung muss die
Python-Referenz (`scoring/scoring_reference.py`) auf 1e-6 genau reproduzieren.
Kein Deployment ohne grüne Tests.

## Deployment

Konfigurationen für den Event-Betrieb liegen in `deploy/`: eine systemd-Unit
mit harten Ressourcenlimits, SSE-taugliche Snippets für nginx und Apache
sowie Dockerfile und `fly.toml` für Fly.io. Zwei Regeln folgen aus dem
RAM-only-Design: genau eine Instanz (der Session-Store lebt in einem
Prozess), und der Server läuft ohne Access-Log (das Log enthielte sonst
IPs und das Host-Token aus dem SSE-Query-String). Ein Lasttest liegt unter
`scripts/loadtest.py`; Ergebnisse im CHANGELOG.

## Struktur

| Ordner | Inhalt |
|---|---|
| `scoring/` | Python-Referenz fürs Scoring, Benchmark-Berechnung |
| `client/` | Teilnehmer- und Host-Ansicht (Vanilla JS, keine Frameworks) |
| `server/` | FastAPI-Server: Sessions, Items, Aggregation, SSE |
| `deploy/` | systemd-Unit, Proxy-Snippets, Fly.io-Config |
| `scripts/` | Lasttest |

## Wissenschaftliche Grundlage

Stolp, Finn, Ziemer, Thiel & Rothmund: *Ideologically Biased Evaluation of
Evidence. A Signal-Detection Approach to Measure Individual Differences.*
Materialien: OSF [osf.io/wuvk5](https://osf.io/wuvk5). Mit dem Erstautor abgestimmt.

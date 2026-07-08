# Faktomat Live

Live-Event-Schicht für den IBE-Faktomat (24 Items, Stolp et al.). Teilnehmende
beantworten die Items am eigenen Smartphone; der Raum sieht eine aggregierte
Auswertung von d′ (Diskriminationssensitivität) und b′ (ideologischer Bias).

**Kein Studienbetrieb, keine Datenerhebung, keine Persistenz.** Rohantworten
verlassen das Endgerät nie — Scoring läuft clientseitig, übertragen werden nur
zwei aggregierte Kennwerte. Details: [`ARCHITECTURE.md`](ARCHITECTURE.md),
verbindliche Spezifikation: [`UEBERGABE_faktomat-live.md`](UEBERGABE_faktomat-live.md).

## Status

Schritt 1 des Arbeitsplans (UEBERGABE 9) ist fertig: das Scoring-Fundament steht,
Python- und JS-Tests sind grün gegen die verbindlichen Testvektoren.

## Scoring-Tests laufen lassen

```bash
# Python-Referenz (Source of Truth)
python scoring/scoring_reference.py

# JS-Port (muss die Referenz auf 1e-6 reproduzieren)
node --test client/scoring.test.mjs
```

Kein Deployment ohne grüne Scoring-Tests (UEBERGABE 4.5).

## Struktur

| Ordner | Inhalt |
|---|---|
| `scoring/` | Python-Referenzimplementierung + Tests (auch Server-Validator) |
| `client/` | Vanilla-JS-Client: `scoring.js` + Tests; später die Views |
| `server/` | FastAPI-App (Schritt 2, noch nicht angelegt) |
| `deploy/` | systemd-Unit, Reverse-Proxy-Snippets (noch nicht angelegt) |

## Wissenschaftliche Grundlage

Stolp, Finn, Ziemer, Thiel & Rothmund — *Ideologically Biased Evaluation of
Evidence: A Signal-Detection Approach to Measure Individual Differences.*
Materialien: OSF [osf.io/wuvk5](https://osf.io/wuvk5). Mit dem Erstautor abgestimmt.

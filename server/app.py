"""
FastAPI-App — Faktomat Live (Server-Kern, Schritt 2 des Arbeitsplans).

Endpunkte (UEBERGABE 3):
  POST /api/session                  -> Session anlegen; {code, host_token}
  POST /api/session/{code}/join      -> Teilnahme-Token vergeben; {participant_token}
  GET  /api/session/{code}/items     -> Itemliste (mit truth_value, siehe unten)
  POST /api/session/{code}/submit    -> {d_prime, b_prime} annehmen (geclampt, 1x/Token)
  GET  /api/session/{code}/stream    -> SSE für Host: {submitted: n}
  POST /api/session/{code}/reveal    -> Host löst Stufe 1|2|3 aus (Gate >=15)
  GET  /api/session/{code}/aggregate -> gebinnte Verteilungen  [STUB: nächster Block]

truth_value im Client: bewusster Trade-off (UEBERGABE 3). Da das Scoring
clientseitig läuft, kennt der Client die Wahrheitswerte. Rohantworten verlassen
das Gerät nie — das ist der Datenschutzgewinn. Items werden erst NACH Join
ausgeliefert, nicht öffentlich verlinkt.

Item-Pfad über Umgebungsvariable FAKTOMAT_ITEMS (Default: items.json neben dieser
Datei). Fehlt/verletzt die Datei das Schema -> Startabbruch (fail-loud).
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastapi import Body, FastAPI, Header, HTTPException, Path as PathParam
from fastapi.responses import StreamingResponse

from .aggregate import aggregate_scores
from .items import ItemSet, ItemValidationError, load_items
from .store import SessionStore, SubmitError

# --- Items beim Import laden (Startabbruch bei Verstoß) --------------------
_DEFAULT_ITEMS = Path(__file__).with_name("items.json")
_ITEMS_PATH = os.environ.get("FAKTOMAT_ITEMS", str(_DEFAULT_ITEMS))


def _load_itemset() -> ItemSet:
    """Lädt die Items oder bricht mit klarer Meldung ab."""
    try:
        return load_items(_ITEMS_PATH)
    except ItemValidationError as exc:
        raise RuntimeError(f"Item-Validierung fehlgeschlagen ({_ITEMS_PATH}): {exc}") from exc


ITEMS = _load_itemset()
STORE = SessionStore()

app = FastAPI(title="Faktomat Live", version="0.2.0")


# --- Hilfen ----------------------------------------------------------------

def _require_session(code: str):
    """Holt die Session oder wirft 404."""
    session = STORE.get(code)
    if session is None:
        raise HTTPException(status_code=404, detail="Unbekannter Session-Code.")
    return session


def _require_host(session, token: str | None) -> None:
    """Prüft das Host-Token; wirft 403 bei Fehlen/Fehlpassung."""
    if not token or token != session.host_token:
        raise HTTPException(status_code=403, detail="Host-Token fehlt oder ist ungültig.")


# --- Endpunkte -------------------------------------------------------------

@app.post("/api/session")
def create_session() -> dict:
    """Legt eine neue Session an. Response: {code, host_token}."""
    session = STORE.create_session()
    return {"code": session.code, "host_token": session.host_token}


@app.post("/api/session/{code}/join")
def join(code: str = PathParam(...)) -> dict:
    """Vergibt ein Teilnahme-Token. Response: {participant_token}."""
    _require_session(code)
    return {"participant_token": STORE.issue_participant_token(code)}


@app.get("/api/session/{code}/items")
def get_items(code: str = PathParam(...)) -> dict:
    """
    Liefert die Itemliste (inkl. truth_value) an einen beigetretenen Client.
    Nur gültig für eine existierende Session (nicht öffentlich verlinken).
    """
    _require_session(code)
    return {
        "version": ITEMS.version,
        "items": [
            {
                "id": it.id,
                "text": it.text,
                "truth_value": it.truth_value,
                "task": it.task,
                "domain": it.domain,
            }
            for it in ITEMS.items
        ],
    }


@app.post("/api/session/{code}/submit")
def submit(code: str = PathParam(...), payload: dict = Body(...)) -> dict:
    """
    Nimmt {d_prime, b_prime, participant_token} an. Clamped-Prüfung +
    Ein-Submit-Regel im Store. Response: {submitted: n}.
    """
    _require_session(code)
    token = payload.get("participant_token")
    if not isinstance(token, str) or not token:
        raise HTTPException(status_code=400, detail="participant_token fehlt.")
    try:
        d_prime = float(payload["d_prime"])
        b_prime = float(payload["b_prime"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="d_prime/b_prime fehlen oder sind keine Zahl.")

    try:
        n = STORE.submit(code, token, d_prime, b_prime)
    except SubmitError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"submitted": n}


@app.get("/api/session/{code}/stream")
async def stream(code: str = PathParam(...),
                 x_host_token: str | None = Header(default=None)) -> StreamingResponse:
    """
    SSE-Stream für den Host: sendet {submitted: n} bei jeder Änderung.
    Auth via X-Host-Token-Header.

    X-Accel-Buffering: no wird fest gesetzt (UEBERGABE 3a.3): nginx/Apache
    buffern SSE sonst weg. Schadet ohne Proxy nicht.
    """
    session = _require_session(code)
    _require_host(session, x_host_token)

    async def event_generator():
        last = -1
        while True:
            current = session.submitted_count
            if current != last:
                last = current
                data = json.dumps({"submitted": current, "reveal_stage": session.reveal_stage})
                yield f"data: {data}\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/session/{code}/reveal")
def reveal(code: str = PathParam(...),
           payload: dict = Body(...),
           x_host_token: str | None = Header(default=None)) -> dict:
    """Host löst eine Reveal-Stufe aus. Auth via Host-Token. Gate >=15 im Store."""
    session = _require_session(code)
    _require_host(session, x_host_token)
    stage = payload.get("stage")
    try:
        STORE.set_reveal(code, int(stage))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"reveal_stage": session.reveal_stage}


@app.get("/api/session/{code}/aggregate")
def aggregate(code: str = PathParam(...),
              x_host_token: str | None = Header(default=None)) -> dict:
    """
    Gebinnte Verteilungen für den Host-View. Auth via Host-Token.

    Binning + n<3-Merge + Gate (>=15) laufen in aggregate_scores (UEBERGABE 6).
    Unterhalb des Gates oder ohne freigegebene Reveal-Stufe werden KEINE
    Verteilungsdaten geliefert, nur der Zählerstand.
    """
    session = _require_session(code)
    _require_host(session, x_host_token)
    return aggregate_scores(session.scores, session.reveal_stage)

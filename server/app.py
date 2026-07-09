"""
FastAPI-App – Faktomat Live (Server-Kern, Schritt 2 des Arbeitsplans).

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
das Gerät nie – das ist der Datenschutzgewinn. Items werden erst NACH Join
ausgeliefert, nicht öffentlich verlinkt.

Item-Pfad über Umgebungsvariable FAKTOMAT_ITEMS (Default: items.json neben dieser
Datei). Fehlt/verletzt die Datei das Schema -> Startabbruch (fail-loud).
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import qrcode
import qrcode.image.svg
from fastapi import Body, FastAPI, Header, HTTPException, Path as PathParam, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

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

# Vanilla-JS-Client (Teilnehmer-View); Module unter /static.
_CLIENT_DIR = Path(__file__).parent.parent / "client"

# Benchmark-Overlay (Feature-Flag, UEBERGABE 5/6): Datei da -> Overlay an,
# Datei fehlt -> App läuft ohne (Reveal-Stufe 2 ohne Vergleichsverteilung).
_BENCHMARK_PATH = Path(os.environ.get(
    "FAKTOMAT_BENCHMARK", str(Path(__file__).parent.parent / "benchmark.json")))
BENCHMARK: dict | None = (
    json.loads(_BENCHMARK_PATH.read_text(encoding="utf-8"))
    if _BENCHMARK_PATH.is_file() else None
)

app = FastAPI(title="Faktomat Live", version="0.3.0")
app.mount("/static", StaticFiles(directory=str(_CLIENT_DIR)), name="static")


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

@app.get("/host/{code}")
def host_page(code: str = PathParam(...)) -> FileResponse:
    """
    Host-View (Beamer). Die Seite selbst ist ohne Token abrufbar – alle
    Daten-Endpunkte dahinter verlangen das Host-Token, das der Host als
    ?token=... in der URL mitbringt (liest das JS aus).
    """
    _require_session(code)
    return FileResponse(_CLIENT_DIR / "host.html", media_type="text/html")


@app.get("/api/session/{code}/qr.svg")
def qr_svg(request: Request, code: str = PathParam(...)) -> Response:
    """
    Session-spezifischer QR-Code (SVG) auf die Join-URL, für die Host-Lobby.

    Die URL wird aus den Request-Headern gebaut: hinter dem Reverse Proxy
    zählen X-Forwarded-Proto/-Host (UEBERGABE 3a), lokal der Host-Header –
    so zeigt der QR immer auf die Adresse, unter der die Seite tatsächlich
    erreichbar ist. Kein Auth: die Join-URL ist zum Projizieren gedacht.
    """
    _require_session(code)
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
    join_url = f"{scheme}://{host}/join/{code}"
    img = qrcode.make(join_url, image_factory=qrcode.image.svg.SvgPathImage,
                      box_size=20, border=2)
    return Response(content=img.to_string(), media_type="image/svg+xml",
                    headers={"Cache-Control": "no-store"})


@app.get("/join/{code}")
def join_page(code: str = PathParam(...)) -> FileResponse:
    """
    Teilnehmer-View. Nur für existierende Sessions (404 sonst) – Items und
    truth_values werden nicht öffentlich verlinkt (UEBERGABE 3, Hinweis).
    """
    _require_session(code)
    return FileResponse(_CLIENT_DIR / "join.html", media_type="text/html")


@app.get("/api/session/{code}/benchmark")
def get_benchmark(code: str = PathParam(...)) -> dict:
    """
    Aggregat-Kennwerte der Vergleichsstichprobe (publizierte Forschungsdaten,
    keine Personendaten, nichts aus diesem Raum). Genutzt von der Erklärfolie
    im Host-View und der Perzentil-Einordnung im privaten Teilnehmer-Feedback;
    deshalb bewusst ohne Host-Token. 404, wenn kein Benchmark geladen ist.
    """
    _require_session(code)
    if BENCHMARK is None:
        raise HTTPException(status_code=404, detail="Kein Benchmark geladen.")
    return BENCHMARK


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
                 token: str | None = None,
                 once: bool = False,
                 x_host_token: str | None = Header(default=None)) -> StreamingResponse:
    """
    SSE-Stream für den Host: {joined, submitted, reveal_stage} bei Änderung.

    Auth via X-Host-Token-Header ODER ?token=... – die EventSource-API im
    Browser kann keine Header setzen, daher der Query-Parameter. Unkritisch,
    weil wir keine Access-Logs führen (UEBERGABE 7.2).

    ?once=1 beendet den Stream nach dem ersten Event – für Tests und für
    curl-Diagnose am Eventtag (ein endlicher Response statt Endlosstream).

    X-Accel-Buffering: no wird fest gesetzt (UEBERGABE 3a.3): nginx/Apache
    buffern SSE sonst weg. Schadet ohne Proxy nicht.
    """
    session = _require_session(code)
    _require_host(session, x_host_token or token)

    async def event_generator():
        last = None
        while True:
            current = (session.joined, session.submitted_count, session.reveal_stage)
            if current != last:
                last = current
                data = json.dumps({"joined": current[0], "submitted": current[1],
                                   "reveal_stage": current[2]})
                yield f"data: {data}\n\n"
                if once:
                    return
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
              nogate: bool = False,
              x_host_token: str | None = Header(default=None)) -> dict:
    """
    Gebinnte Verteilungen für den Host-View. Auth via Host-Token.

    Binning + n<3-Merge + Gate (>=15) laufen in aggregate_scores (UEBERGABE 6).
    Unterhalb des Gates oder ohne freigegebene Reveal-Stufe werden KEINE
    Verteilungsdaten geliefert, nur der Zählerstand.
    """
    session = _require_session(code)
    _require_host(session, x_host_token)

    if nogate:
        # Testmodus (1-3 Geräte): Gate umgehen, feste Stufe 3. Nur erlaubt,
        # wenn der Server ausdrücklich als Dev-Instanz läuft - am Eventtag
        # fehlt FAKTOMAT_DEV und dieser Pfad ist tot.
        if not os.environ.get("FAKTOMAT_DEV"):
            raise HTTPException(status_code=403,
                                detail="Testmodus nur mit FAKTOMAT_DEV=1 am Server.")
        result = aggregate_scores(session.scores, stage=3, enforce_gate=False)
        result["ungated"] = True
        if BENCHMARK is not None and "b_prime" in result:
            result["benchmark"] = BENCHMARK
        return result

    result = aggregate_scores(session.scores, session.reveal_stage)
    # Benchmark-Overlay ab Stufe 2, nur wenn die Datei vorhanden ist (Flag).
    if session.reveal_stage >= 2 and result.get("gate_open") and BENCHMARK is not None:
        result["benchmark"] = BENCHMARK
    return result

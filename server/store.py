"""
Session-Store — Faktomat Live.

Hält den gesamten Zustand im RAM (UEBERGABE 3): ein Session-Objekt pro Event,
in einem Dict nach Code. Kein DB, keine Dateien, keine Logs mit Nutzdaten.
Prozess-Ende = Daten weg (Feature, kein Mangel — UEBERGABE 7).

Gespeichert pro Session wird ausschließlich:
  - die eingegangenen Kennwertepaare {d_prime, b_prime} (geclampt),
  - welche Teilnahme-Tokens bereits abgegeben haben (Ein-Submit-Regel),
  - der freigegebene Reveal-Stand (0 = nichts, 1|2|3 = Stufe).
Keine Rohantworten, keine IP, keine Zeitstempel pro Person.
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field


# Plausibilitäts-Clamp aus UEBERGABE 3 (Submit-Validierung).
# Theoretisches Maximum bei Hautus-Korrektur mit n=12 liegt darunter;
# Werte außerhalb gelten als korrupt und werden verworfen.
MAX_ABS_SCORE = 4.66

# Reveal erst ab dieser Teilnehmerzahl freischaltbar (UEBERGABE 6).
MIN_PARTICIPANTS_FOR_REVEAL = 15


class SubmitError(Exception):
    """Ungültiger oder doppelter Submit. Wird als 4xx an den Client gespiegelt."""


@dataclass
class Session:
    """Ein Live-Event. Alle Felder leben nur im RAM."""

    code: str
    host_token: str
    # Zwei parallele Listen wären fehleranfällig; ein Tupel pro Person.
    scores: list[tuple[float, float]] = field(default_factory=list)
    # Teilnahme-Tokens, die schon abgegeben haben (Ein-Submit-Regel).
    submitted_tokens: set[str] = field(default_factory=set)
    reveal_stage: int = 0
    # Reiner Zähler für die Host-Anzeige "X von Y" — keine Personendaten.
    joined: int = 0

    @property
    def submitted_count(self) -> int:
        return len(self.scores)


def _clamp_ok(value: float) -> bool:
    """True, wenn value eine endliche Zahl im erlaubten Betragsbereich ist."""
    return isinstance(value, (int, float)) and abs(value) <= MAX_ABS_SCORE and value == value


class SessionStore:
    """Thread-sicherer RAM-Store. FastAPI/Uvicorn kann nebenläufig zugreifen."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create_session(self) -> Session:
        """Legt eine Session mit zufälligem Code und Host-Token an."""
        with self._lock:
            # Kurzer, gut vorlesbarer Code; kollisionsfrei im Store.
            while True:
                code = secrets.token_hex(3)  # 6 Hex-Zeichen
                if code not in self._sessions:
                    break
            session = Session(code=code, host_token=secrets.token_urlsafe(24))
            self._sessions[code] = session
            return session

    def get(self, code: str) -> Session | None:
        with self._lock:
            return self._sessions.get(code)

    def issue_participant_token(self, code: str) -> str:
        """Vergibt ein Teilnahme-Token beim Join. Wirft KeyError bei unbekanntem Code."""
        with self._lock:
            session = self._sessions.get(code)
            if session is None:
                raise KeyError(code)
            session.joined += 1
        return secrets.token_urlsafe(18)

    def submit(self, code: str, token: str, d_prime: float, b_prime: float) -> int:
        """
        Nimmt ein Kennwertepaar an. Clamped-Prüfung + Ein-Submit-Regel.

        Gibt die neue Teilnehmerzahl zurück. Wirft SubmitError bei
        unplausiblen Werten oder doppeltem Token, KeyError bei unbekanntem Code.
        """
        if not (_clamp_ok(d_prime) and _clamp_ok(b_prime)):
            raise SubmitError(f"Werte außerhalb des plausiblen Bereichs (|x| <= {MAX_ABS_SCORE}).")

        with self._lock:
            session = self._sessions.get(code)
            if session is None:
                raise KeyError(code)
            if token in session.submitted_tokens:
                raise SubmitError("Dieses Teilnahme-Token hat bereits abgegeben.")
            session.submitted_tokens.add(token)
            session.scores.append((float(d_prime), float(b_prime)))
            return len(session.scores)

    def set_reveal(self, code: str, stage: int) -> Session:
        """
        Setzt den Reveal-Stand. Wirft ValueError, wenn das Gate (>=15
        Teilnahmen) noch nicht erreicht ist, KeyError bei unbekanntem Code.
        """
        if stage not in (1, 2, 3):
            raise ValueError("stage muss 1, 2 oder 3 sein.")
        with self._lock:
            session = self._sessions.get(code)
            if session is None:
                raise KeyError(code)
            if session.submitted_count < MIN_PARTICIPANTS_FOR_REVEAL:
                raise ValueError(
                    f"Reveal erst ab {MIN_PARTICIPANTS_FOR_REVEAL} Teilnahmen "
                    f"(aktuell {session.submitted_count})."
                )
            session.reveal_stage = stage
            return session

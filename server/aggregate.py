"""
Aggregation der Kennwerte für den Host-View — Faktomat Live.

Erzeugt gebinnte Verteilungen von d′ und b′ unter den verbindlichen
Anonymitätsregeln aus UEBERGABE Abschnitt 6:

  - Keine Einzelpunkte. Nur Histogramm (5–6 Bins) oder KDE.
  - Bins mit n < 3 werden mit einem Nachbarn verschmolzen (bei b′ nicht
    verhandelbar, bei d′ ebenso angewandt) — b′ ist ein Proxy für politische
    Orientierung (Nähe zu DSGVO Art. 9).
  - Reveal erst ab MIN_PARTICIPANTS_FOR_REVEAL Teilnahmen (Gate im Store).
  - Kein Leaderboard, kein "besser als X %". Höchstens ein Median-Marker in
    Stufe 3, immer IM Verteilungskontext (nie als nackte Einzelzahl).

Reine Funktionen, keine Server-Abhängigkeit — dadurch isoliert testbar.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .store import MIN_PARTICIPANTS_FOR_REVEAL

# Zielauflösung der Histogramme (UEBERGABE 6: 5–6 Bins gesamt).
DEFAULT_BINS = 6
# Schwelle für die Zusammenlegung kleiner Bins (UEBERGABE 6).
MIN_BIN_COUNT = 3


@dataclass(frozen=True)
class Bin:
    """Ein Histogramm-Bin: halboffenes Intervall [lo, hi) und die Personenzahl."""

    lo: float
    hi: float
    count: int


def histogram(values: list[float], n_bins: int = DEFAULT_BINS) -> list[Bin]:
    """
    Verteilt Werte auf n_bins gleichbreite Bins über [min, max].

    Das oberste Bin ist rechts geschlossen, damit der Maximalwert hineinfällt.
    Bei identischen Werten (Spanne 0) entsteht ein einzelnes Bin.
    """
    if not values:
        return []

    lo, hi = min(values), max(values)
    if hi == lo:
        return [Bin(lo=lo, hi=hi, count=len(values))]

    width = (hi - lo) / n_bins
    counts = [0] * n_bins
    for v in values:
        # Index über die Bin-Breite; der Maximalwert landet sonst außerhalb,
        # daher explizit ins letzte Bin klemmen.
        idx = int((v - lo) / width)
        if idx >= n_bins:
            idx = n_bins - 1
        counts[idx] += 1

    return [Bin(lo=lo + i * width, hi=lo + (i + 1) * width, count=c)
            for i, c in enumerate(counts)]


def merge_small_bins(bins: list[Bin], min_count: int = MIN_BIN_COUNT) -> list[Bin]:
    """
    Verschmilzt Bins mit count < min_count mit einem Nachbarn.

    Strategie (Entscheidung Julius): der zu kleine Bin wird mit dem
    benachbarten Bin verschmolzen, der SELBST die kleinere Personenzahl hat.
    Das verteilt die Zusammenlegung und hält die verbleibenden Bins
    gleichmäßiger. Läuft, bis kein Bin mehr unter der Schwelle liegt oder nur
    noch ein Bin übrig ist.

    Nach dem Merge sind die Intervalle wieder zusammenhängend: das neue Bin
    spannt von lo des linken bis hi des rechten Partners.
    """
    work = list(bins)
    if len(work) <= 1:
        return work

    def _merge_at(i: int, j: int) -> None:
        """Verschmilzt die benachbarten Bins i und j (j = i+1) in-place."""
        left, right = work[i], work[j]
        work[i:j + 1] = [Bin(lo=left.lo, hi=right.hi, count=left.count + right.count)]

    while len(work) > 1:
        # Erstes zu kleines Bin suchen.
        small = next((k for k, b in enumerate(work) if b.count < min_count), None)
        if small is None:
            break

        # Nachbarn bestimmen; am Rand gibt es nur einen.
        left_neighbor = small - 1 if small > 0 else None
        right_neighbor = small + 1 if small + 1 < len(work) else None

        if left_neighbor is None:
            _merge_at(small, right_neighbor)
        elif right_neighbor is None:
            _merge_at(left_neighbor, small)
        else:
            # Mit dem kleineren Nachbarn verschmelzen.
            if work[left_neighbor].count <= work[right_neighbor].count:
                _merge_at(left_neighbor, small)
            else:
                _merge_at(small, right_neighbor)

    return work


def _silverman_bandwidth(values: list[float]) -> float:
    """
    Silverman-Daumenregel: h = 0.9 * min(SD, IQR/1.34) * n^(-1/5).

    Auf identischen Werten (SD = 0) fällt sie auf einen kleinen positiven
    Wert zurück, damit die KDE definiert bleibt.
    """
    n = len(values)
    mean = sum(values) / n
    sd = (sum((x - mean) ** 2 for x in values) / (n - 1)) ** 0.5 if n > 1 else 0.0
    s = sorted(values)
    iqr = s[(3 * n) // 4] - s[n // 4]
    spread = min(sd, iqr / 1.34) if iqr > 0 else sd
    if spread <= 0:
        return 0.1
    return 0.9 * spread * n ** (-0.2)


def kde(values: list[float], n_grid: int = 100) -> dict:
    """
    Gauß-KDE auf einem festen Gitter (UEBERGABE 6, Stufe 2).

    Läuft serverseitig, weil sie die Rohwerte braucht — ausgeliefert werden
    nur die Gitterpunkte {x, density}. Gitter: [min-3h, max+3h], damit die
    Kurve sauber auf null ausläuft.
    """
    h = _silverman_bandwidth(values)
    lo = min(values) - 3 * h
    hi = max(values) + 3 * h
    step = (hi - lo) / (n_grid - 1)
    n = len(values)
    norm = 1.0 / (n * h * math.sqrt(2 * math.pi))
    xs, ds = [], []
    for i in range(n_grid):
        x = lo + i * step
        density = norm * sum(math.exp(-0.5 * ((x - v) / h) ** 2) for v in values)
        xs.append(round(x, 5))
        ds.append(round(density, 6))
    return {"x": xs, "density": ds, "bandwidth": round(h, 5)}


def _binned(values: list[float]) -> list[dict]:
    """Histogramm + Merge, als JSON-serialisierbare Bin-Liste."""
    merged = merge_small_bins(histogram(values))
    return [{"lo": b.lo, "hi": b.hi, "count": b.count} for b in merged]


def _median(values: list[float]) -> float:
    """Median einer nicht-leeren Werteliste."""
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def aggregate_scores(scores: list[tuple[float, float]], stage: int) -> dict:
    """
    Baut die gebinnten Verteilungen für eine Reveal-Stufe.

    scores: Liste von (d_prime, b_prime) aus dem Session-Store.
    stage:  0 = nichts freigegeben, 1 = d′, 2 = b′ (+Benchmark im Client),
            3 = b′ mit Median-Marker des Raums.

    Gibt ein anonymitäts-gefiltertes Dict zurück. Solange das Gate nicht
    erreicht ist, werden KEINE Verteilungsdaten geliefert (nur der Zählerstand),
    damit ein zu früher /aggregate-Aufruf nichts durchsickern lässt.
    """
    n = len(scores)
    result: dict = {"submitted": n, "reveal_stage": stage,
                    "gate": MIN_PARTICIPANTS_FOR_REVEAL, "gate_open": n >= MIN_PARTICIPANTS_FOR_REVEAL}

    if n < MIN_PARTICIPANTS_FOR_REVEAL or stage < 1:
        return result

    d_values = [d for d, _ in scores]
    b_values = [b for _, b in scores]

    if stage >= 1:
        result["d_prime"] = {"bins": _binned(d_values)}
    if stage >= 2:
        # Bins fürs Fallback, KDE für die Overlay-Kurve (UEBERGABE 6, Stufe 2).
        result["b_prime"] = {"bins": _binned(b_values), "kde": kde(b_values)}
    if stage >= 3:
        # Median IM Verteilungskontext (UEBERGABE 6, Stufe 3) — nie als
        # nackte Einzelzahl ohne die b′-Bins darüber.
        result["b_prime"]["room_median"] = round(_median(b_values), 4)

    return result

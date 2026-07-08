"""
Benchmark-Berechnung für das Reveal-Overlay — Faktomat Live.

Rechnet aus den Rohdaten der IBE-2.4-Erhebung (meta-d-pipeline-Projekt) die
d'/b'-Verteilungen und schreibt sie als reines Aggregat (benchmark.json,
Schema UEBERGABE 5). Rohdaten werden nur GELESEN, nie kopiert; das Live-Tool
sieht ausschließlich Bin-Kanten und Dichten.

Zentrale Entscheidungen:
  - Nur Completes (dispcode 31/32), complete-case: Personen mit irgendeiner
    fehlenden IBE-Antwort (Sentinels -77/-99/-66 o.ä.) werden ausgeschlossen —
    imputierte Raten würden d'/b' verzerren.
  - Scoring identisch zum Live-Tool: scoring_reference.compute_scores mit
    Hautus-Korrektur. Nur so ist das Overlay mit der Raumverteilung vergleichbar.
  - Truth-Key/Spalten-Mapping aus config/item_key_ibe24.json der meta-d-pipeline
    (verifiziert gegen Stolps Skript, Jan 2026). ACHTUNG Bezeichnung: Welle 2.4
    liegt in dataset2_IBE24.csv; die Live-IDs IBE11/12/17/18 heißen im
    Datensatz AddIBE1/4/8/11.
  - Antwortkodierung: 1 = "wahr" geantwortet, 2 = "falsch" geantwortet.
  - Repräsentativität der 2.4-Stichprobe ist NICHT bestätigt — das Event-Framing
    ("… von Deutschland?") erst nach Klärung mit Stolp verwenden. Der
    source-String im Output benennt das explizit.

Lauf (Defaults = Workspace-Layout von Julius, per CLI übersteuerbar):
    python scoring/compute_benchmark.py
    python scoring/compute_benchmark.py --data pfad/zu.csv --out benchmark.json
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from scoring_reference import ItemResponse, compute_scores

_META_D = Path("c:/workspace/projects/meta-d-pipeline")
DEFAULT_DATA = _META_D / "data/raw/dataset2_IBE24.csv"
DEFAULT_KEY = _META_D / "config/item_key_ibe24.json"
DEFAULT_OUT = Path(__file__).parent.parent / "benchmark.json"

COMPLETE_DISPCODES = {"31", "32"}


def load_key(path: Path) -> list[dict]:
    """Lädt den verifizierten 2.4-Truth-Key (24 Items, mit dataset_col-Mapping)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw["items"]
    if len(items) != 24 or any(i.get("status") != "verified" for i in items):
        raise ValueError("Truth-Key unvollständig oder nicht verifiziert — Abbruch.")
    return items


def person_responses(row: dict, key: list[dict]) -> list[ItemResponse] | None:
    """
    Baut die 24 ItemResponses einer Person. None, wenn irgendeine Antwort
    fehlt oder ungültig ist (complete-case-Ausschluss).
    """
    responses = []
    for item in key:
        value = (row.get(item["dataset_col"]) or "").strip()
        if value not in ("1", "2"):
            return None  # Sentinel (-77/-99/-66), leer oder unerwartet
        responses.append(ItemResponse(
            truth_value=(item["key"] == "true"),
            task=item["congruence"],
            answered_true=(value == "1"),
        ))
    return responses


def make_histogram(values: list[float], n_bins: int) -> dict:
    """
    Gleichbreites Histogramm als {bin_edges, densities} (Schema UEBERGABE 5).

    densities sind auf Fläche 1 normiert (count / (N * Breite)), damit der
    Host-View die Raum-KDE direkt über das Benchmark legen kann.
    """
    lo, hi = min(values), max(values)
    width = (hi - lo) / n_bins
    counts = [0] * n_bins
    for v in values:
        idx = min(int((v - lo) / width), n_bins - 1)
        counts[idx] += 1
    n = len(values)
    return {
        "bin_edges": [lo + i * width for i in range(n_bins + 1)],
        "densities": [c / (n * width) for c in counts],
    }


def quantiles(values: list[float]) -> dict:
    """
    Perzentile p1–p99 (lineare Interpolation). Erlaubt dem Host-View flexible
    Darstellungen (KDE-artige Kurve, Kategorien-Schnitte wie im Original-
    Faktomat, 'Du'-Einordnung), ohne je Einzelwerte auszuliefern — 99
    Quantile aus N>1500 sind ein reines Aggregat.
    """
    s = sorted(values)
    n = len(s)
    ps = list(range(1, 100))
    vals = []
    for p in ps:
        pos = (p / 100) * (n - 1)
        lo_i = int(pos)
        frac = pos - lo_i
        hi_i = min(lo_i + 1, n - 1)
        vals.append(round(s[lo_i] + frac * (s[hi_i] - s[lo_i]), 4))
    return {"p": ps, "values": vals}


def summarize(values: list[float]) -> dict:
    """Kennzahlen fürs Labeling im Host-View (keine Einzelwerte)."""
    s = sorted(values)
    n = len(s)
    mean = sum(s) / n
    var = sum((x - mean) ** 2 for x in s) / (n - 1)
    median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    return {"n": n, "mean": round(mean, 4), "median": round(median, 4),
            "sd": round(var ** 0.5, 4)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--key", type=Path, default=DEFAULT_KEY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--bins", type=int, default=24)
    args = parser.parse_args()

    key = load_key(args.key)

    n_rows = n_complete = n_excluded = 0
    d_values: list[float] = []
    b_values: list[float] = []

    with open(args.data, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            n_rows += 1
            if row.get("dispcode") not in COMPLETE_DISPCODES:
                continue
            n_complete += 1
            responses = person_responses(row, key)
            if responses is None:
                n_excluded += 1
                continue
            scores = compute_scores(responses, edge_correction=True)
            d_values.append(scores.d_prime)
            b_values.append(scores.b_prime)

    n = len(d_values)
    out = {
        "source": (
            f"IBE 2.4 (dataset2_IBE24.csv, Online-Erhebung Okt–Nov 2025), "
            f"N={n} von {n_complete} Completes (complete-case, {n_excluded} "
            f"mit fehlenden IBE-Antworten ausgeschlossen). Scoring: Hautus-"
            f"Korrektur, identisch zum Live-Tool. ACHTUNG: Repräsentativität "
            f"nicht bestätigt — Event-Framing vor Nutzung mit Stolp klären."
        ),
        "d_prime": {**make_histogram(d_values, args.bins),
                    "quantiles": quantiles(d_values), "summary": summarize(d_values)},
        "b_prime": {**make_histogram(b_values, args.bins),
                    "quantiles": quantiles(b_values), "summary": summarize(b_values)},
    }
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Zeilen gesamt: {n_rows} | Completes: {n_complete} | "
          f"ausgeschlossen: {n_excluded} | gescored: {n}")
    print(f"d': {out['d_prime']['summary']}")
    print(f"b': {out['b_prime']['summary']}")
    print(f"geschrieben: {args.out}")


if __name__ == "__main__":
    main()

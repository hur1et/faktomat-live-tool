"""
Lasttest – Faktomat Live (UEBERGABE 8, Schritt 5 des Arbeitsplans).

Jagt N simulierte Teilnehmende (Default 100) parallel durch den kompletten
echten Pfad: Join -> Items laden -> plausibel zufaellig antworten -> Scoring
(Python-Referenz, identisch zum JS-Client) -> Submit. Parallel dazu lauscht
ein Host-SSE-Stream und muss am Ende stabil bei N angekommen sein.

Entscheidungen:
  - asyncio + httpx statt locust: httpx ist schon Testabhaengigkeit, locust
    waere eine neue Abhaengigkeit fuer ein Skript, das einmal vor dem Event
    laeuft. Jede Zeile hier ist erklaerbar.
  - Antworten werden WIRKLICH gescored (scoring_reference), nicht als
    Zufallszahlen an /submit geschickt: so testet der Lasttest denselben
    Wertebereich und dieselbe Payload wie echte Handys.
  - Fester Seed (Reproduzierbarkeit, CLAUDE_RULES).

Voraussetzung: laufender Server, z.B.
    FAKTOMAT_ITEMS=server/items.example.json python -m uvicorn server.app:app --port 8100

Lauf:
    python scripts/loadtest.py [--base http://127.0.0.1:8100] [--n 100] [--seed 42]

Exit-Code 0 = alle Pruefungen bestanden, 1 = mindestens eine verletzt.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from pathlib import Path

import httpx

# Repo-Wurzel in den Importpfad, damit die Scoring-Referenz ladbar ist,
# egal von wo das Skript gestartet wird.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoring.scoring_reference import ItemResponse, compute_scores  # noqa: E402


def simulate_answers(items: list[dict], rng: random.Random) -> list[ItemResponse]:
    """
    Erzeugt einen plausiblen Antwortvektor fuer eine simulierte Person.

    Faehigkeit (Trefferquote) und Richtungs-Bias variieren pro Person, damit
    die Kennwerte ueber Personen streuen wie bei einem echten Publikum:
      - p_correct ~ U(0.55, 0.90): von knapp ueber Raten bis ziemlich gut.
      - bias_shift ~ U(-0.15, 0.15): verschiebt die Trefferquote je nach
        Task-Seite gegenlaeufig -> erzeugt eine b'-Streuung um null.
    """
    p_correct = rng.uniform(0.55, 0.90)
    bias_shift = rng.uniform(-0.15, 0.15)

    responses = []
    for it in items:
        p = p_correct + (bias_shift if it["task"] == "right" else -bias_shift)
        p = min(max(p, 0.05), 0.95)
        correct = rng.random() < p
        answered_true = it["truth_value"] if correct else not it["truth_value"]
        responses.append(ItemResponse(truth_value=it["truth_value"],
                                      task=it["task"],
                                      answered_true=answered_true))
    return responses


async def run_participant(client: httpx.AsyncClient, base: str, code: str,
                          rng: random.Random, latencies: dict[str, list[float]],
                          errors: list[str]) -> None:
    """Ein simuliertes Handy: Join -> Items -> Antworten -> Scoring -> Submit."""
    try:
        t0 = time.perf_counter()
        r = await client.post(f"{base}/api/session/{code}/join")
        r.raise_for_status()
        token = r.json()["participant_token"]
        latencies["join"].append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        r = await client.get(f"{base}/api/session/{code}/items")
        r.raise_for_status()
        items = r.json()["items"]
        latencies["items"].append(time.perf_counter() - t0)

        scores = compute_scores(simulate_answers(items, rng))

        t0 = time.perf_counter()
        r = await client.post(f"{base}/api/session/{code}/submit",
                              json={"participant_token": token,
                                    "d_prime": scores.d_prime,
                                    "b_prime": scores.b_prime})
        r.raise_for_status()
        latencies["submit"].append(time.perf_counter() - t0)
    except Exception as exc:  # gesammelt statt abgebrochen: wir wollen die Quote sehen
        errors.append(f"{type(exc).__name__}: {exc}")


async def watch_sse(client: httpx.AsyncClient, base: str, code: str,
                    host_token: str, n_target: int, result: dict) -> None:
    """
    Liest den Host-SSE-Stream mit und protokolliert den hoechsten gesehenen
    Zaehlerstand. Beendet sich, sobald n_target erreicht ist (oder der
    aufrufende Code ihn per Cancel beendet).
    """
    url = f"{base}/api/session/{code}/stream?token={host_token}"
    async with client.stream("GET", url, timeout=httpx.Timeout(10, read=None)) as resp:
        async for line in resp.aiter_lines():
            if not line.startswith("data:"):
                continue
            payload = json.loads(line[5:])
            result["events"] += 1
            result["max_submitted"] = max(result["max_submitted"], payload["submitted"])
            if payload["submitted"] >= n_target:
                return


def pctl(values: list[float], q: float) -> float:
    """Perzentil ueber sortierte Werte (nearest-rank, reicht fuer den Report)."""
    s = sorted(values)
    return s[min(int(q * len(s)), len(s) - 1)]


async def main() -> int:
    parser = argparse.ArgumentParser(description="Faktomat-Live-Lasttest (UEBERGABE 8)")
    parser.add_argument("--base", default="http://127.0.0.1:8100")
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    failures: list[str] = []

    limits = httpx.Limits(max_connections=args.n + 5)
    async with httpx.AsyncClient(timeout=30.0, limits=limits) as client:
        # Eigene Session anlegen: der Lasttest beruehrt nie eine fremde.
        r = await client.post(f"{args.base}/api/session")
        r.raise_for_status()
        body = r.json()
        code, host_token = body["code"], body["host_token"]
        print(f"Session {code} angelegt, starte {args.n} simulierte Teilnehmende ...")

        latencies: dict[str, list[float]] = {"join": [], "items": [], "submit": []}
        errors: list[str] = []
        sse_result = {"events": 0, "max_submitted": 0}

        sse_task = asyncio.create_task(
            watch_sse(client, args.base, code, host_token, args.n, sse_result))

        t_start = time.perf_counter()
        # Jede simulierte Person bekommt einen eigenen, aus dem Haupt-Seed
        # abgeleiteten RNG - sonst waere die Reihenfolge der Tasks relevant.
        await asyncio.gather(*(
            run_participant(client, args.base, code,
                            random.Random(rng.random()), latencies, errors)
            for _ in range(args.n)))
        wall = time.perf_counter() - t_start

        # SSE noch kurz nachlaufen lassen (Server pollt im 1s-Takt).
        try:
            await asyncio.wait_for(sse_task, timeout=5.0)
        except asyncio.TimeoutError:
            sse_task.cancel()

        # --- Pruefungen -----------------------------------------------------
        ok_submits = len(latencies["submit"])
        if ok_submits != args.n:
            failures.append(f"Nur {ok_submits}/{args.n} Submits erfolgreich.")
        if errors:
            failures.append(f"{len(errors)} Fehler, erster: {errors[0]}")
        if sse_result["max_submitted"] < args.n:
            failures.append(
                f"SSE-Zaehler blieb bei {sse_result['max_submitted']}/{args.n} stehen.")

        # Reveal + Aggregat wie am Eventtag (nur sinnvoll oberhalb des Gates).
        if args.n >= 15:
            r = await client.post(f"{args.base}/api/session/{code}/reveal",
                                  json={"stage": 3},
                                  headers={"X-Host-Token": host_token})
            if r.status_code != 200:
                failures.append(f"Reveal fehlgeschlagen: {r.status_code} {r.text}")
            r = await client.get(f"{args.base}/api/session/{code}/aggregate",
                                 headers={"X-Host-Token": host_token})
            agg = r.json()
            if "d_prime" not in agg or "b_prime" not in agg:
                failures.append("Aggregat liefert keine Verteilungen nach Reveal.")
            else:
                bin_sum = sum(b["count"] for b in agg["d_prime"]["bins"])
                if bin_sum != args.n:
                    failures.append(f"Bin-Summe {bin_sum} != {args.n} Teilnahmen.")

    # --- Report ---------------------------------------------------------------
    print(f"\nDurchlauf: {args.n} Teilnehmende in {wall:.2f}s "
          f"({args.n / wall:.0f} Submits/s Durchsatz ueber den Gesamtpfad)")
    for phase, vals in latencies.items():
        if vals:
            print(f"  {phase:7s} n={len(vals):3d}  median={statistics.median(vals)*1000:6.1f}ms"
                  f"  p95={pctl(vals, 0.95)*1000:6.1f}ms  max={max(vals)*1000:6.1f}ms")
    print(f"  SSE: {sse_result['events']} Events, hoechster Stand "
          f"{sse_result['max_submitted']}/{args.n}")

    if failures:
        print("\nFEHLGESCHLAGEN:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nAlle Pruefungen bestanden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

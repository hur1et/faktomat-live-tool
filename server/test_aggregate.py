"""
Tests für die Aggregation — Faktomat Live (Binning, n<3-Merge, Gate).

Deckt die verbindlichen Anonymitätsregeln aus UEBERGABE 6 ab:
  - Binning in feste Bins, Maximalwert fällt ins letzte Bin,
  - Merge kleiner Bins (n<3) mit dem KLEINEREN Nachbarn,
  - Gate (>=15): unterhalb keine Verteilungsdaten,
  - Reveal-Stufen liefern d′ / b′ / Median schrittweise.

Lauf: python -m pytest server/test_aggregate.py -q
"""

from __future__ import annotations

from server.aggregate import (
    MIN_BIN_COUNT,
    Bin,
    aggregate_scores,
    histogram,
    merge_small_bins,
)
from server.store import MIN_PARTICIPANTS_FOR_REVEAL


# --- Binning ---------------------------------------------------------------

def test_histogram_counts_all_values():
    values = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    bins = histogram(values, n_bins=6)
    assert sum(b.count for b in bins) == len(values)


def test_histogram_max_falls_into_last_bin():
    # Der Maximalwert darf nicht aus dem obersten Bin herausfallen.
    values = [0.0] * 3 + [10.0]
    bins = histogram(values, n_bins=5)
    assert bins[-1].count == 1
    assert sum(b.count for b in bins) == 4


def test_histogram_identical_values_single_bin():
    bins = histogram([2.5, 2.5, 2.5], n_bins=6)
    assert len(bins) == 1
    assert bins[0].count == 3


def test_histogram_empty():
    assert histogram([]) == []


# --- Merge (der heikle Teil) ----------------------------------------------

def test_merge_leaves_large_bins_untouched():
    bins = [Bin(0, 1, 5), Bin(1, 2, 4), Bin(2, 3, 6)]
    assert merge_small_bins(bins) == bins


def test_merge_small_bin_with_smaller_neighbor():
    # Mittleres Bin (count 2) zwischen 5 (links) und 3 (rechts):
    # der kleinere Nachbar ist rechts (3) -> nach rechts mergen.
    bins = [Bin(0, 1, 5), Bin(1, 2, 2), Bin(2, 3, 3)]
    merged = merge_small_bins(bins)
    assert len(merged) == 2
    assert merged[0] == Bin(0, 1, 5)
    assert merged[1] == Bin(1, 3, 5)  # 2 + 3, Intervall zusammengezogen


def test_merge_small_bin_left_when_left_is_smaller():
    # Mittleres Bin (2) zwischen 3 (links) und 5 (rechts) -> nach links.
    bins = [Bin(0, 1, 3), Bin(1, 2, 2), Bin(2, 3, 5)]
    merged = merge_small_bins(bins)
    assert len(merged) == 2
    assert merged[0] == Bin(0, 2, 5)   # 3 + 2
    assert merged[1] == Bin(2, 3, 5)


def test_merge_edge_bin_has_only_one_neighbor():
    # Erstes Bin zu klein -> muss nach rechts mergen (kein linker Nachbar).
    bins = [Bin(0, 1, 1), Bin(1, 2, 4), Bin(2, 3, 5)]
    merged = merge_small_bins(bins)
    assert merged[0] == Bin(0, 2, 5)


def test_merge_all_bins_reach_threshold_or_collapse():
    # Lauter winzige Bins -> am Ende erfüllt jedes Bin die Schwelle
    # oder es bleibt genau eines übrig.
    bins = [Bin(i, i + 1, 1) for i in range(6)]
    merged = merge_small_bins(bins)
    assert len(merged) == 1 or all(b.count >= MIN_BIN_COUNT for b in merged)
    assert sum(b.count for b in merged) == 6


# --- Aggregat + Gate + Stufen ---------------------------------------------

def _scores(n: int) -> list[tuple[float, float]]:
    # Gestreute, plausible Werte, damit mehrere Bins entstehen.
    return [((i % 5) * 0.5 - 1.0, (i % 7) * 0.3 - 1.0) for i in range(n)]


def test_gate_blocks_distribution_below_15():
    agg = aggregate_scores(_scores(10), stage=1)
    assert agg["gate_open"] is False
    assert "d_prime" not in agg  # keine Verteilungsdaten unterhalb des Gates


def test_stage1_gives_dprime_only():
    agg = aggregate_scores(_scores(MIN_PARTICIPANTS_FOR_REVEAL), stage=1)
    assert agg["gate_open"] is True
    assert "d_prime" in agg
    assert "b_prime" not in agg


def test_stage2_adds_bprime():
    agg = aggregate_scores(_scores(20), stage=2)
    assert "d_prime" in agg and "b_prime" in agg
    assert "room_median" not in agg["b_prime"]


def test_stage3_adds_room_median():
    agg = aggregate_scores(_scores(20), stage=3)
    assert "room_median" in agg["b_prime"]


def test_no_raw_scores_leak():
    # Anonymität: die Ausgabe enthält nur Bins, nie die rohe Score-Liste.
    agg = aggregate_scores(_scores(20), stage=3)
    for key in ("d_prime", "b_prime"):
        assert "bins" in agg[key]
        # Jeder Bin hat count, aber keine Einzelwerte.
        for b in agg[key]["bins"]:
            assert set(b.keys()) == {"lo", "hi", "count"}

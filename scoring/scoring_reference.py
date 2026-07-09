"""
IBE scoring reference implementation – Faktomat Live.

Source of truth for d' and b' as defined in:
Stolp, Finn, Ziemer, Thiel & Rothmund – "Ideologically Biased Evaluation
of Evidence: A Signal-Detection Approach to Measure Individual Differences".

    d' = z(hit_rate) - z(false_alarm_rate)
    b' = z(task_right_correct_rate) - z(task_left_correct_rate)

b' is NOT the classical SDT response criterion. It is an asymmetry index
of accuracy across two tasks defined by the ideological congruence of the
correct response (positive = right-leaning bias, negative = left-leaning).

Edge correction: log-linear (Hautus, 1995), applied UNIFORMLY to all
participants: rate = (count + 0.5) / (n + 1). If the original Faktomat
uses a different correction, replace `LOG_LINEAR` handling here and in
the JS port, and document the change.

The JavaScript client implementation MUST reproduce this module's outputs
within 1e-6 on the test vectors below (run: python scoring_reference.py).

No third-party dependencies (stdlib only), so the module can double as a
server-side validator.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Literal

Task = Literal["left", "right"]


# ---------------------------------------------------------------------------
# Inverse standard-normal CDF (probit), Acklam's algorithm.
# Relative error < 1.15e-9 over the open interval (0, 1).
# Port this function 1:1 to JavaScript.
# ---------------------------------------------------------------------------

_A = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
      1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
_B = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
      6.680131188771972e+01, -1.328068155288572e+01)
_C = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
      -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
_D = (7.784695709041462e-03, 3.224671290700398e-01,
      2.445134137142996e+00, 3.754408661907416e+00)

_P_LOW = 0.02425
_P_HIGH = 1.0 - _P_LOW


def probit(p: float) -> float:
    """Inverse standard-normal CDF. Defined only for 0 < p < 1."""
    if not (0.0 < p < 1.0):
        raise ValueError(f"probit undefined for p={p}; apply edge correction first")
    if p < _P_LOW:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / \
               ((((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0)
    if p <= _P_HIGH:
        q = p - 0.5
        r = q * q
        return (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5]) * q / \
               (((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0)
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / \
        ((((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ItemResponse:
    """One answered item."""
    truth_value: bool          # is the claim factually true?
    task: Task                 # ideological congruence of the CORRECT response
    answered_true: bool        # participant's response


@dataclass(frozen=True)
class Scores:
    d_prime: float
    b_prime: float


def _rate(count: int, n: int, correction: bool) -> float:
    """Proportion with optional log-linear (Hautus 1995) correction."""
    if correction:
        return (count + 0.5) / (n + 1.0)
    return count / n


def compute_scores(responses: Iterable[ItemResponse],
                   edge_correction: bool = True) -> Scores:
    """
    Compute d' and b' from a full response set.

    edge_correction=True  -> production path (log-linear, uniform).
    edge_correction=False -> raw path, used only to reproduce the worked
                             example in the paper (Box 1); raises ValueError
                             on rates of exactly 0 or 1.
    """
    responses = list(responses)

    # --- d' ---------------------------------------------------------------
    true_items = [r for r in responses if r.truth_value]
    false_items = [r for r in responses if not r.truth_value]
    if not true_items or not false_items:
        raise ValueError("need both true and false items for d'")

    hits = sum(r.answered_true for r in true_items)
    false_alarms = sum(r.answered_true for r in false_items)

    hit_rate = _rate(hits, len(true_items), edge_correction)
    fa_rate = _rate(false_alarms, len(false_items), edge_correction)
    d_prime = probit(hit_rate) - probit(fa_rate)

    # --- b' ---------------------------------------------------------------
    def correct(r: ItemResponse) -> bool:
        return r.answered_true == r.truth_value

    right_items = [r for r in responses if r.task == "right"]
    left_items = [r for r in responses if r.task == "left"]
    if not right_items or not left_items:
        raise ValueError("need items in both tasks for b'")

    right_rate = _rate(sum(map(correct, right_items)), len(right_items), edge_correction)
    left_rate = _rate(sum(map(correct, left_items)), len(left_items), edge_correction)
    b_prime = probit(right_rate) - probit(left_rate)

    return Scores(d_prime=d_prime, b_prime=b_prime)


# ---------------------------------------------------------------------------
# Test vectors – binding acceptance criteria for any port (JS client!).
# Run: python scoring_reference.py
# ---------------------------------------------------------------------------

def _make_task(task: Task, n_hits: int, n_true: int,
               n_cr: int, n_false: int) -> list[ItemResponse]:
    """Task block with exact hit / correct-rejection counts."""
    items: list[ItemResponse] = []
    for i in range(n_true):
        items.append(ItemResponse(True, task, answered_true=(i < n_hits)))
    for i in range(n_false):
        items.append(ItemResponse(False, task, answered_true=not (i < n_cr)))
    return items


def _run_tests() -> None:
    tol = 1e-2   # paper reports rounded values
    tol_exact = 1e-9

    # Probit sanity vs. known quantiles
    assert abs(probit(0.5) - 0.0) < tol_exact
    assert abs(probit(0.975) - 1.959963985) < 1e-6
    assert abs(probit(0.70) - 0.524400513) < 1e-6

    # Paper Box 1, Participant 1: 7/10 correct in both tasks, no bias.
    # Overall hit_rate = 0.70, fa_rate = 0.30 -> d' = 1.048; b' = 0.
    # Right: 4 hits/5 true, 3 CR/5 false; Left: 3 hits/5 true, 4 CR/5 false
    # -> hits 7/10, FA 3/10, per-task correct 7/10 each.
    p1 = _make_task("right", 4, 5, 3, 5) + _make_task("left", 3, 5, 4, 5)
    s1 = compute_scores(p1, edge_correction=False)
    assert abs(s1.d_prime - 1.048) < tol, s1
    assert abs(s1.b_prime - 0.0) < tol_exact, s1

    # Paper Box 1, Participant 2: Task-Right 9/10, Task-Left 5/10 correct.
    # b' = z(0.90) - z(0.50) = 1.28.
    p2 = _make_task("right", 5, 5, 4, 5) + _make_task("left", 2, 5, 3, 5)
    s2 = compute_scores(p2, edge_correction=False)
    assert abs(s2.b_prime - 1.28) < tol, s2

    # Edge case: perfect task without correction must fail loudly …
    p3 = _make_task("right", 6, 6, 6, 6) + _make_task("left", 3, 6, 3, 6)
    try:
        compute_scores(p3, edge_correction=False)
        raise AssertionError("expected ValueError on rate == 1.0 without correction")
    except ValueError:
        pass
    # … and yield a finite value with Hautus correction: rate 12.5/13.
    s3 = compute_scores(p3, edge_correction=True)
    expected_right = probit(12.5 / 13.0)
    expected_left = probit(6.5 / 13.0)
    assert abs(s3.b_prime - (expected_right - expected_left)) < tol_exact, s3

    # Symmetry: swapping tasks flips the sign of b' exactly.
    p4_mirror = [ItemResponse(r.truth_value,
                              "left" if r.task == "right" else "right",
                              r.answered_true) for r in p2]
    s4 = compute_scores(p4_mirror, edge_correction=False)
    assert abs(s4.b_prime + s2.b_prime) < tol_exact, (s2, s4)

    # Production path on the paper's participants (corrected values differ
    # slightly from Box 1 – expected, since Box 1 is uncorrected).
    s1c = compute_scores(p1, edge_correction=True)
    assert abs(s1c.b_prime) < tol_exact  # symmetry preserved under correction

    print("All scoring tests passed.")
    print(f"  P1 (uncorrected): d'={s1.d_prime:.3f}  b'={s1.b_prime:.3f}")
    print(f"  P2 (uncorrected): d'={s2.d_prime:.3f}  b'={s2.b_prime:.3f}")
    print(f"  P1 (Hautus):      d'={s1c.d_prime:.3f}  b'={s1c.b_prime:.3f}")
    print(f"  Perfect-task (Hautus): b'={s3.b_prime:.3f}")


if __name__ == "__main__":
    _run_tests()

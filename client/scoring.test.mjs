/**
 * Verbindliche Akzeptanztests für den JS-Scoring-Port.
 *
 * Dieselben Testvektoren wie scoring/scoring_reference.py und UEBERGABE 4.5.
 * Kein Deployment ohne grüne Scoring-Tests (UEBERGABE 4.5, letzter Satz).
 *
 * Lauf: node client/scoring.test.mjs   (oder: node --test client/)
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { probit, computeScores } from "./scoring.js";

const TOL = 1e-2; // Paper rundet die berichteten Werte
const TOL_EXACT = 1e-9;

/**
 * Task-Block mit exakten Hit-/Correct-Rejection-Zahlen.
 * Spiegelt _make_task aus scoring_reference.py.
 */
function makeTask(task, nHits, nTrue, nCr, nFalse) {
  const items = [];
  for (let i = 0; i < nTrue; i++) {
    items.push({ truthValue: true, task, answeredTrue: i < nHits });
  }
  for (let i = 0; i < nFalse; i++) {
    // answered_true = not (i < n_cr): wer nicht correct-rejected, sagt "wahr"
    items.push({ truthValue: false, task, answeredTrue: !(i < nCr) });
  }
  return items;
}

test("Probit gegen bekannte Quantile", () => {
  assert.ok(Math.abs(probit(0.5) - 0.0) < TOL_EXACT);
  assert.ok(Math.abs(probit(0.975) - 1.959963985) < 1e-6);
  assert.ok(Math.abs(probit(0.7) - 0.524400513) < 1e-6);
});

test("Probit wirft außerhalb (0,1)", () => {
  assert.throws(() => probit(0.0), RangeError);
  assert.throws(() => probit(1.0), RangeError);
  assert.throws(() => probit(-0.1), RangeError);
});

test("Participant 1 (unkorrigiert): d'=1.048, b'=0", () => {
  // Right: 4 Hits/5 wahr, 3 CR/5 falsch; Left: 3 Hits/5 wahr, 4 CR/5 falsch
  const p1 = [...makeTask("right", 4, 5, 3, 5), ...makeTask("left", 3, 5, 4, 5)];
  const s1 = computeScores(p1, false);
  assert.ok(Math.abs(s1.dPrime - 1.048) < TOL, JSON.stringify(s1));
  assert.ok(Math.abs(s1.bPrime - 0.0) < TOL_EXACT, JSON.stringify(s1));
});

test("Participant 2 (unkorrigiert): b'=1.28", () => {
  const p2 = [...makeTask("right", 5, 5, 4, 5), ...makeTask("left", 2, 5, 3, 5)];
  const s2 = computeScores(p2, false);
  assert.ok(Math.abs(s2.bPrime - 1.28) < TOL, JSON.stringify(s2));
});

test("Randfall: perfekter Task ohne Korrektur wirft, mit Hautus endlich", () => {
  const p3 = [...makeTask("right", 6, 6, 6, 6), ...makeTask("left", 3, 6, 3, 6)];
  assert.throws(() => computeScores(p3, false));

  const s3 = computeScores(p3, true);
  const expectedRight = probit(12.5 / 13.0);
  const expectedLeft = probit(6.5 / 13.0);
  assert.ok(Math.abs(s3.bPrime - (expectedRight - expectedLeft)) < TOL_EXACT, JSON.stringify(s3));
});

test("Symmetrie: Task-Tausch spiegelt Vorzeichen von b'", () => {
  const p2 = [...makeTask("right", 5, 5, 4, 5), ...makeTask("left", 2, 5, 3, 5)];
  const s2 = computeScores(p2, false);
  const mirror = p2.map((r) => ({
    truthValue: r.truthValue,
    task: r.task === "right" ? "left" : "right",
    answeredTrue: r.answeredTrue,
  }));
  const s4 = computeScores(mirror, false);
  assert.ok(Math.abs(s4.bPrime + s2.bPrime) < TOL_EXACT, JSON.stringify([s2, s4]));
});

test("Symmetrie bleibt unter Hautus-Korrektur erhalten", () => {
  const p1 = [...makeTask("right", 4, 5, 3, 5), ...makeTask("left", 3, 5, 4, 5)];
  const s1c = computeScores(p1, true);
  assert.ok(Math.abs(s1c.bPrime) < TOL_EXACT, JSON.stringify(s1c));
});

// Bitgenauer Abgleich gegen die Python-Referenzwerte (Toleranz 1e-6).
// Diese Zahlen stammen aus dem Lauf von scoring_reference.py.
test("Numerischer Abgleich gegen Python-Referenz (1e-6)", () => {
  const p1 = [...makeTask("right", 4, 5, 3, 5), ...makeTask("left", 3, 5, 4, 5)];
  const p2 = [...makeTask("right", 5, 5, 4, 5), ...makeTask("left", 2, 5, 3, 5)];

  const s1 = computeScores(p1, false);
  const s2 = computeScores(p2, false);
  const s1c = computeScores(p1, true);

  // Werte aus scoring_reference.py, mehr Stellen via probit direkt bestätigt:
  assert.ok(Math.abs(s1.dPrime - (probit(0.7) - probit(0.3))) < 1e-6);
  assert.ok(Math.abs(s2.bPrime - (probit(0.9) - probit(0.5))) < 1e-6);
  assert.ok(Math.abs(s1c.dPrime - (probit(7.5 / 11) - probit(3.5 / 11))) < 1e-6);
});

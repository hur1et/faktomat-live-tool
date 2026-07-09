/**
 * Tests für die Perzentil-Einordnung (benchmark-util.js).
 * Lauf: node --test client/benchmark-util.test.mjs
 */

import test from "node:test";
import assert from "node:assert/strict";
import { percentileOf } from "./benchmark-util.js";

// Lineares 99er-Gitter von -4,9 bis +4,9 (Median exakt 0).
const grid = {
  p: Array.from({ length: 99 }, (_, i) => i + 1),
  values: Array.from({ length: 99 }, (_, i) => (i + 1 - 50) / 10),
};

test("Median des Gitters liegt am 50. Perzentil", () => {
  assert.equal(percentileOf(grid, 0), 50);
});

test("Wert unterhalb des Gitters wird auf 1 begrenzt", () => {
  assert.equal(percentileOf(grid, -99), 1);
});

test("Wert oberhalb des Gitters wird auf 99 begrenzt", () => {
  assert.equal(percentileOf(grid, 99), 99);
});

test("Wert zwischen zwei Gitterpunkten liegt dazwischen", () => {
  // 74 Werte liegen unter 2.45 -> 74/99 = 74.7 % -> 75. Perzentil
  assert.equal(percentileOf(grid, 2.45), 75);
});

test("Plateau im Gitter wird mittig eingeordnet", () => {
  const plateau = { p: [1, 2, 3, 4, 5], values: [-1, 0, 0, 0, 1] };
  assert.equal(percentileOf(plateau, 0), 50); // 1 darunter + 3/2 Bindungen = 2,5 von 5
});

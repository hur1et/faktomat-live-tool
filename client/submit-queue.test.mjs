/**
 * Tests für die Retry-Queue (submit-queue.js).
 *
 * Prüft: Erfolg ohne Retry, Backoff-Abfolge bei Netzfehlern, 4xx terminal
 * (kein Retry), Aufgabe nach maxAttempts.
 *
 * Lauf: node --test client/submit-queue.test.mjs
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { submitWithRetry } from "./submit-queue.js";

const ok = { ok: true, status: 200 };
const conflict = { ok: false, status: 409 };
const serverError = { ok: false, status: 502 };

function harness(responses) {
  // Jeder Eintrag: ein Response-Objekt oder "netzfehler" (wirft).
  const calls = [];
  const sleeps = [];
  const fetchFn = async (url, init) => {
    calls.push(init);
    const next = responses.shift();
    if (next === "netzfehler") throw new TypeError("failed to fetch");
    return next;
  };
  const sleepFn = async (ms) => sleeps.push(ms);
  return { calls, sleeps, fetchFn, sleepFn };
}

test("Erfolg beim ersten Versuch: kein Retry, kein Sleep", async () => {
  const h = harness([ok]);
  const resp = await submitWithRetry("/x", { a: 1 }, { fetchFn: h.fetchFn, sleepFn: h.sleepFn });
  assert.equal(resp.status, 200);
  assert.equal(h.calls.length, 1);
  assert.deepEqual(h.sleeps, []);
});

test("Netzfehler: Backoff 1s, 2s, dann Erfolg", async () => {
  const h = harness(["netzfehler", "netzfehler", ok]);
  let retries = 0;
  const resp = await submitWithRetry("/x", {}, {
    fetchFn: h.fetchFn, sleepFn: h.sleepFn, onRetry: () => retries++,
  });
  assert.equal(resp.status, 200);
  assert.deepEqual(h.sleeps, [1000, 2000]);
  assert.equal(retries, 2);
});

test("5xx gilt als transient und wird wiederholt", async () => {
  const h = harness([serverError, ok]);
  const resp = await submitWithRetry("/x", {}, { fetchFn: h.fetchFn, sleepFn: h.sleepFn });
  assert.equal(resp.status, 200);
  assert.equal(h.calls.length, 2);
});

test("409 ist terminal: wird zurückgegeben, kein Retry", async () => {
  const h = harness([conflict, ok]);
  const resp = await submitWithRetry("/x", {}, { fetchFn: h.fetchFn, sleepFn: h.sleepFn });
  assert.equal(resp.status, 409);
  assert.equal(h.calls.length, 1); // der zweite Response wurde nie abgeholt
});

test("Nach maxAttempts Netzfehlern wird geworfen (4 Sleeps bei 5 Versuchen)", async () => {
  const h = harness(["netzfehler", "netzfehler", "netzfehler", "netzfehler", "netzfehler"]);
  await assert.rejects(
    submitWithRetry("/x", {}, { fetchFn: h.fetchFn, sleepFn: h.sleepFn }),
    TypeError,
  );
  assert.equal(h.calls.length, 5);
  assert.deepEqual(h.sleeps, [1000, 2000, 4000, 8000]);
});

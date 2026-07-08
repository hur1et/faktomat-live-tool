/**
 * Teilnehmer-Ablauf — Faktomat Live (UEBERGABE Abschnitt 3, Komponente 1).
 *
 * Join -> Items laden -> clientseitig randomisieren (Fisher-Yates) ->
 * 24 Antworten einsammeln -> Scoring LOKAL (scoring.js) -> nur {d', b'}
 * submitten (Retry-Queue) -> privates Feedback anzeigen.
 *
 * Datenschutz-Konsequenzen im Code (UEBERGABE 7):
 *  - Die Antwortliste existiert nur in dieser Seite; sie wird nie serialisiert.
 *  - Teilnahme-Token in sessionStorage (kein Cookie), stirbt mit dem Tab.
 */

import { computeScores } from "./scoring.js";
import { submitWithRetry } from "./submit-queue.js";

// Session-Code aus dem Pfad /join/{code}.
const code = window.location.pathname.split("/").filter(Boolean).pop();
const api = (p) => `/api/session/${code}/${p}`;

const $ = (id) => document.getElementById(id);
const show = (id) => {
  document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
  $(id).classList.add("active");
};

/** Fisher-Yates-Shuffle, in-place. Randomisierte Itemreihenfolge pro Person. */
function shuffle(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

let items = [];
let index = 0;
const responses = []; // {truthValue, task, answeredTrue} — verlässt die Seite nie

async function start() {
  $("btn-start").disabled = true;
  $("privacy-status").textContent = "Verbinde …";
  try {
    // Token holen (einmal pro Tab; Reload überlebt via sessionStorage).
    let token = sessionStorage.getItem(`faktomat-token-${code}`);
    if (!token) {
      const r = await fetch(api("join"), { method: "POST" });
      if (!r.ok) throw new Error(`Join fehlgeschlagen (${r.status})`);
      token = (await r.json()).participant_token;
      sessionStorage.setItem(`faktomat-token-${code}`, token);
    }

    const r = await fetch(api("items"));
    if (!r.ok) throw new Error(`Items nicht ladbar (${r.status})`);
    items = shuffle((await r.json()).items);

    index = 0;
    show("screen-items");
    render();
  } catch (err) {
    $("btn-start").disabled = false;
    $("privacy-status").textContent =
      `Verbindung fehlgeschlagen (${err.message}). Bitte erneut tippen.`;
  }
}

function render() {
  $("progress").textContent = `Aussage ${index + 1} von ${items.length}`;
  $("claim").textContent = items[index].text;
}

function answer(answeredTrue) {
  const it = items[index];
  responses.push({ truthValue: it.truth_value, task: it.task, answeredTrue });
  index++;
  if (index < items.length) {
    render();
  } else {
    finish();
  }
}

async function finish() {
  // Scoring lokal; Produktionspfad = Hautus-Korrektur (edgeCorrection true).
  const { dPrime, bPrime } = computeScores(responses, true);

  $("result-d").textContent = dPrime.toFixed(2);
  $("result-b").textContent = bPrime.toFixed(2);
  show("screen-result");

  const status = $("submit-status");
  status.textContent = "Übertrage Gruppenbeitrag …";
  try {
    const resp = await submitWithRetry(api("submit"), {
      participant_token: sessionStorage.getItem(`faktomat-token-${code}`),
      d_prime: dPrime,
      b_prime: bPrime,
    }, {
      onRetry: (attempt, max) => {
        status.textContent = `Netz wackelt — Versuch ${attempt + 1} von ${max} …`;
      },
    });
    if (resp.ok) {
      status.textContent = "Dein Beitrag zur Gruppenauswertung ist angekommen. Danke!";
    } else if (resp.status === 409) {
      status.textContent = "Dein Beitrag war bereits angekommen (kein doppelter Eintrag).";
    } else {
      status.textContent = `Übertragung abgelehnt (${resp.status}).`;
      status.classList.add("error");
    }
  } catch {
    status.textContent =
      "Übertragung nicht möglich — dein Ergebnis oben gilt trotzdem. " +
      "Es fließt nur nicht in die Raumgrafik ein.";
    status.classList.add("error");
  }
}

$("btn-start").addEventListener("click", start);
$("btn-true").addEventListener("click", () => answer(true));
$("btn-false").addEventListener("click", () => answer(false));

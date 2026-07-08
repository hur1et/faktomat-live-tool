/**
 * Submit mit Retry-Queue — Faktomat Live (UEBERGABE Abschnitt 3).
 *
 * Teilnehmende hängen am Mobilfunk; ein Submit darf an einem Funkloch nicht
 * scheitern. Strategie: exponentieller Backoff (1s, 2s, 4s, 8s), maximal
 * 5 Versuche, UI-Hinweis über onRetry-Callback.
 *
 * Wichtige Abgrenzung: 4xx-Antworten werden NICHT wiederholt — ein 409
 * (doppelter Submit) oder 400 (kaputte Payload) wird durch Wiederholen nicht
 * besser. Nur Netzfehler und 5xx gelten als transient.
 *
 * fetch/sleep sind injizierbar, damit die Logik im Node-Test-Runner ohne
 * Browser und ohne echte Wartezeiten prüfbar ist.
 */

export async function submitWithRetry(url, payload, opts = {}) {
  const {
    fetchFn = fetch,
    maxAttempts = 5,
    baseDelayMs = 1000,
    sleepFn = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
    onRetry = () => {},
  } = opts;

  let lastError;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const resp = await fetchFn(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (resp.ok) return resp;
      if (resp.status >= 400 && resp.status < 500) return resp; // terminal
      lastError = new Error(`HTTP ${resp.status}`);
    } catch (err) {
      lastError = err; // Netzfehler -> transient, erneut versuchen
    }
    if (attempt < maxAttempts) {
      onRetry(attempt, maxAttempts);
      await sleepFn(baseDelayMs * 2 ** (attempt - 1));
    }
  }
  throw lastError;
}

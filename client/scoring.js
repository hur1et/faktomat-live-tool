/**
 * IBE-Scoring — Faktomat Live (Client-seitige Implementierung).
 *
 * 1:1-Port von scoring/scoring_reference.py. Die Referenz ist die
 * verbindliche "Source of Truth" (UEBERGABE Abschnitt 4). Diese Datei
 * MUSS die Referenzwerte auf den Testvektoren innerhalb 1e-6 reproduzieren
 * (siehe scoring.test.mjs).
 *
 * Warum clientseitig? Datenschutz (UEBERGABE Abschnitt 7): Die Rohantworten
 * verlassen das Endgerät nie. Nur die berechneten Kennwerte {d_prime, b_prime}
 * werden per POST an den Server übertragen.
 *
 *   d' = z(hit_rate) - z(false_alarm_rate)
 *   b' = z(right_correct_rate) - z(left_correct_rate)
 *
 * z = Probit (Inverse der Standardnormal-CDF), Acklams Algorithmus.
 * b' ist KEIN klassisches SDT-Response-Criterion, sondern ein
 * Asymmetrie-Index der Genauigkeit über Ideologie-Kongruenz.
 *
 * Als ES-Modul geschrieben, damit derselbe Code im Browser (Teilnehmer-View)
 * und im Node-Test-Runner läuft. Kein Framework, keine Dependencies.
 */

// ---------------------------------------------------------------------------
// Inverse Standardnormal-CDF (Probit), Acklams Algorithmus.
// Relativer Fehler < 1.15e-9 über das offene Intervall (0, 1).
// Konstanten zeichengleich aus scoring_reference.py übernommen.
// ---------------------------------------------------------------------------

const A = [
  -3.969683028665376e1, 2.209460984245205e2, -2.759285104469687e2,
  1.38357751867269e2, -3.066479806614716e1, 2.506628277459239e0,
];
const B = [
  -5.447609879822406e1, 1.615858368580409e2, -1.556989798598866e2,
  6.680131188771972e1, -1.328068155288572e1,
];
const C = [
  -7.784894002430293e-3, -3.223964580411365e-1, -2.400758277161838e0,
  -2.549732539343734e0, 4.374664141464968e0, 2.938163982698783e0,
];
const D = [
  7.784695709041462e-3, 3.224671290700398e-1,
  2.445134137142996e0, 3.754408661907416e0,
];

const P_LOW = 0.02425;
const P_HIGH = 1.0 - P_LOW;

/**
 * Inverse Standardnormal-CDF. Definiert nur für 0 < p < 1.
 * Wirft bei p außerhalb des offenen Intervalls (Randkorrektur vorher anwenden).
 */
export function probit(p) {
  if (!(p > 0.0 && p < 1.0)) {
    throw new RangeError(`probit undefined for p=${p}; apply edge correction first`);
  }
  let q, r;
  if (p < P_LOW) {
    q = Math.sqrt(-2.0 * Math.log(p));
    return (((((C[0] * q + C[1]) * q + C[2]) * q + C[3]) * q + C[4]) * q + C[5]) /
           ((((D[0] * q + D[1]) * q + D[2]) * q + D[3]) * q + 1.0);
  }
  if (p <= P_HIGH) {
    q = p - 0.5;
    r = q * q;
    return (((((A[0] * r + A[1]) * r + A[2]) * r + A[3]) * r + A[4]) * r + A[5]) * q /
           (((((B[0] * r + B[1]) * r + B[2]) * r + B[3]) * r + B[4]) * r + 1.0);
  }
  q = Math.sqrt(-2.0 * Math.log(1.0 - p));
  return -(((((C[0] * q + C[1]) * q + C[2]) * q + C[3]) * q + C[4]) * q + C[5]) /
          ((((D[0] * q + D[1]) * q + D[2]) * q + D[3]) * q + 1.0);
}

// ---------------------------------------------------------------------------
// Rate mit Log-linear-Randkorrektur (Hautus 1995).
// Einheitlich für ALLE Teilnehmenden (UEBERGABE 4.3), nicht nur Randfälle.
// ---------------------------------------------------------------------------

/**
 * Anteil mit optionaler Log-linear-Korrektur (Hautus 1995).
 * correction=true -> (count + 0.5) / (n + 1)  (Produktionspfad)
 * correction=false -> count / n               (nur für Paper-Box-1-Beispiel)
 */
function rate(count, n, correction) {
  if (correction) {
    return (count + 0.5) / (n + 1.0);
  }
  return count / n;
}

// ---------------------------------------------------------------------------
// d' und b' aus dem vollständigen Antwortsatz.
// ---------------------------------------------------------------------------

/**
 * Berechnet d' und b' aus einer Liste von Antworten.
 *
 * Jede Antwort ist ein Objekt:
 *   { truthValue: boolean, task: "left"|"right", answeredTrue: boolean }
 *
 * edgeCorrection=true  -> Produktionspfad (Hautus, einheitlich).
 * edgeCorrection=false -> Rohpfad, nur zur Reproduktion von Paper-Box-1;
 *                         wirft bei Rates von exakt 0 oder 1.
 *
 * Wirft, wenn eine der vier benötigten Zellen leer ist.
 */
export function computeScores(responses, edgeCorrection = true) {
  const items = Array.from(responses);

  // --- d' ---
  const trueItems = items.filter((r) => r.truthValue);
  const falseItems = items.filter((r) => !r.truthValue);
  if (trueItems.length === 0 || falseItems.length === 0) {
    throw new Error("need both true and false items for d'");
  }

  const hits = trueItems.filter((r) => r.answeredTrue).length;
  const falseAlarms = falseItems.filter((r) => r.answeredTrue).length;

  const hitRate = rate(hits, trueItems.length, edgeCorrection);
  const faRate = rate(falseAlarms, falseItems.length, edgeCorrection);
  const dPrime = probit(hitRate) - probit(faRate);

  // --- b' ---
  const correct = (r) => r.answeredTrue === r.truthValue;

  const rightItems = items.filter((r) => r.task === "right");
  const leftItems = items.filter((r) => r.task === "left");
  if (rightItems.length === 0 || leftItems.length === 0) {
    throw new Error("need items in both tasks for b'");
  }

  const rightRate = rate(rightItems.filter(correct).length, rightItems.length, edgeCorrection);
  const leftRate = rate(leftItems.filter(correct).length, leftItems.length, edgeCorrection);
  const bPrime = probit(rightRate) - probit(leftRate);

  return { dPrime, bPrime };
}

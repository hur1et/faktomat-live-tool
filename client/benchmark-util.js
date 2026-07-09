/**
 * Perzentil-Einordnung gegen das Quantilgitter der Vergleichsstichprobe
 * (benchmark.json: b_prime.quantiles = {p: [1..99], values: [...]}).
 *
 * Geteilt zwischen Host-View (S-Kurve, Stufe 4) und Teilnehmer-Feedback.
 * Schätzung über den Anteil der Gitterwerte unterhalb des Werts; exakte
 * Treffer zählen zur Hälfte (Plateaus im Gitter werden mittig eingeordnet).
 * Ergebnis auf [1, 99] begrenzt, weil das Gitter außerhalb nichts aussagt.
 */
export function percentileOf(quantiles, value) {
  const vals = quantiles.values;
  let below = 0, equal = 0;
  for (const v of vals) {
    if (v < value) below++;
    else if (v === value) equal++;
  }
  const pct = ((below + equal / 2) / vals.length) * 100;
  return Math.min(99, Math.max(1, Math.round(pct)));
}

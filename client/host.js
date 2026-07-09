/**
 * Host-View – Faktomat Live (UEBERGABE 3 Komponente 2, Abschnitt 6).
 *
 * Fortschritt über SSE, drei MANUELL ausgelöste Reveal-Stufen, Charts als
 * handgerolltes SVG (bewusst kein D3: keine externe Abhängigkeit am
 * Event-Tag; die KDE kommt fertig gerechnet vom Server, gezeichnet werden
 * nur Flächen und Balken).
 *
 * Anonymität: dieser Client erhält ausschließlich Aggregate (gemergte Bins,
 * KDE-Gitter, Median) – nie Einzelwerte. Balkenhöhen sind DICHTEN
 * (count/Breite), weil Bins nach dem n<3-Merge ungleich breit sind.
 *
 * Gestaltungsprinzipien (Beamer, Laienpublikum, Betrachtung aus Metern):
 *  - Verbale Anker statt nackter Zahlen: "Raten", "ausgewogen",
 *    "eher links-/rechts-verzerrt". Zahlen bleiben klein darüber.
 *  - b'-Achse symmetrisch um null, sonst wirkt eine Seite optisch schwerer.
 *  - d'-Achse schließt immer die 0 ein ("Raten" als Anker).
 *  - Raum und Vergleichsstichprobe als GLEICHARTIGE Silhouetten (Flächen),
 *    Farbe trägt die Identität: Orange = Raum, Grau = Vergleich.
 *
 * Demo-Modus (UEBERGABE 8): rein clientseitig erzeugte synthetische Daten,
 * klar gebannert, berührt den Server nicht.
 */

import { percentileOf } from "./benchmark-util.js";

const code = window.location.pathname.split("/").filter(Boolean).pop();
const token = new URLSearchParams(window.location.search).get("token") || "";
const api = (p) => `/api/session/${code}/${p}`;
const authHeaders = { "X-Host-Token": token };
const GATE = 15; // UI-Anzeige; verbindlich erzwingt es der Server

const $ = (id) => document.getElementById(id);
let demoMode = false;
let currentStage = 0;

// --- SSE: Fortschritt -------------------------------------------------------

const source = new EventSource(api(`stream?token=${encodeURIComponent(token)}`));
source.onmessage = (ev) => {
  const d = JSON.parse(ev.data);
  $("progress").innerHTML =
    `${d.submitted} <small>abgeschlossen</small> / ${d.joined} <small>beigetreten</small>`;
  $("lobby-counter").innerHTML =
    `<strong>${d.joined}</strong> beigetreten · <strong>${d.submitted}</strong> abgeschlossen`;
  updateGate(d.submitted);
};
source.onerror = () => { $("status").textContent = "Verbindung zum Server unterbrochen, Verbindungsaufbau läuft …"; };

function updateGate(submitted) {
  const open = submitted >= GATE;
  // Die Erklärfolie (stage-0) bleibt immer frei: sie zeigt keine Raumdaten.
  for (const s of [1, 2, 3, 4]) $(`stage-${s}`).disabled = !open && !demoMode;
  $("gate-hint").textContent = open || demoMode
    ? "" : `Auswertung gesperrt: Freigabe ab ${GATE} Teilnahmen (aktuell ${submitted}).`;
}
updateGate(0);

// --- Lobby (QR-Einstieg) -----------------------------------------------------

$("qr").src = api("qr.svg");
$("join-url").textContent = `${window.location.host}/join/${code}`;
$("to-stages").addEventListener("click", () => {
  $("lobby").style.display = "none";
  $("main-view").style.display = "block";
  renderExplainer(); // Warte-/Erklärfolie, bis die Moderation freigibt
});

// --- Neue Session (Test-Komfort, mit Schutz vor Versehen am Eventtag) --------

/**
 * Legt eine frische Session an und lädt die Host-View unter dem neuen Code
 * neu: neuer QR, Zähler auf null. Teilnahme-Tokens der Handys gelten nur
 * für den alten Code – wer weitermachen will, scannt den neuen QR und
 * kann erneut teilnehmen.
 */
async function newSession() {
  if (!window.confirm("Neue Session anlegen? Der bisherige Code und alle Teilnahmen verfallen.")) return;
  try {
    const r = await fetch("/api/session", { method: "POST" });
    if (!r.ok) throw new Error(`${r.status}`);
    const s = await r.json();
    window.location.href = `/host/${s.code}?token=${encodeURIComponent(s.host_token)}`;
  } catch {
    $("status").textContent = "Neue Session konnte nicht angelegt werden.";
  }
}
$("new-session-btn").addEventListener("click", newSession);
$("lobby-new-session").addEventListener("click", newSession);

// --- Reveal-Stufen -----------------------------------------------------------

$("stage-0").addEventListener("click", () => renderExplainer());
for (const s of [1, 2, 3, 4]) {
  $(`stage-${s}`).addEventListener("click", () => (demoMode ? renderDemo(s) : reveal(s)));
}

async function reveal(stage) {
  $("status").textContent = "";
  const r = await fetch(api("reveal"), {
    method: "POST",
    headers: { ...authHeaders, "Content-Type": "application/json" },
    // Stufe 4 (Einordnung) ist eine Ansicht auf Stufe-3-Daten; der Server
    // kennt nur die Reveal-Stände 1-3.
    body: JSON.stringify({ stage: Math.min(stage, 3) }),
  });
  if (!r.ok) {
    $("status").textContent = (await r.json()).detail || `Fehler ${r.status}`;
    return;
  }
  const agg = await (await fetch(api("aggregate"), { headers: authHeaders })).json();
  render(stage, agg);
}

function markStage(stage) {
  currentStage = stage;
  $("stage-0").classList.toggle("active", stage === 0);
  for (const s of [1, 2, 3, 4]) $(`stage-${s}`).classList.toggle("active", s === stage);
}

// --- Rendering (SVG, ohne Bibliothek) ---------------------------------------

const W = 1000, H = 560, PAD = { l: 50, r: 30, t: 34, b: 80 };
const ORANGE = "#ef7d00", GRAU = "#c8c8c8", GRAU_KANTE = "#9a9a9a";

function clearChart() {
  const svg = $("chart");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.innerHTML = "";
  return svg;
}

function el(name, attrs) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

function text(parent, x, y, str, attrs = {}) {
  const t = el("text", { x, y, "font-size": 20, fill: "#767676",
                         "text-anchor": "middle", ...attrs });
  t.textContent = str;
  parent.appendChild(t);
  return t;
}

/** Skalen + Grundlinie; gibt x()/y()-Abbildungen in Pixelkoordinaten zurück. */
function scales(svg, xMin, xMax, yMax) {
  // Degenerierte Spannen (z.B. 1 Testgerät -> ein Bin mit lo==hi) abfangen.
  if (xMax - xMin <= 0) { xMin -= 0.5; xMax += 0.5; }
  if (yMax <= 0) yMax = 1;
  const x = (v) => PAD.l + ((v - xMin) / (xMax - xMin)) * (W - PAD.l - PAD.r);
  const y = (v) => H - PAD.b - (v / yMax) * (H - PAD.t - PAD.b);
  svg.appendChild(el("line", { x1: PAD.l, y1: H - PAD.b, x2: W - PAD.r, y2: H - PAD.b,
                               stroke: "#1a1a1a", "stroke-width": 2 }));
  return { x, y, xMin, xMax };
}

/** Zahlen-Ticks auf rundem Raster (0,5er- bzw. 1er-Schritte), klein und leise. */
function drawTicks(svg, sc) {
  const step = (sc.xMax - sc.xMin) > 4 ? 1 : 0.5;
  for (let t = Math.ceil(sc.xMin / step) * step; t <= sc.xMax + 1e-9; t += step) {
    const px = sc.x(t);
    svg.appendChild(el("line", { x1: px, y1: H - PAD.b, x2: px, y2: H - PAD.b + 8,
                                 stroke: "#767676", "stroke-width": 1.5 }));
    text(svg, px, H - PAD.b + 30, (Math.abs(t) < 1e-9 ? 0 : t).toFixed(1));
  }
}

/** Verbaler Anker in der Wortzeile unter den Zahlen-Ticks. */
function anchorWord(svg, px, str, anchor = "middle") {
  text(svg, px, H - 22, str,
       { "font-size": 22, "font-weight": 700, fill: "#1a1a1a", "text-anchor": anchor });
}

/** Vertikale Referenzlinie über die Plothöhe (z.B. null = ausgewogen). */
function refLine(svg, px, { dash = "", stroke = "#767676", width = 2 } = {}) {
  svg.appendChild(el("line", { x1: px, y1: PAD.t, x2: px, y2: H - PAD.b,
                               stroke, "stroke-width": width,
                               ...(dash ? { "stroke-dasharray": dash } : {}) }));
}

/** Teilnehmerzahl des Raums, klein in der Ecke – Kontext, reines Aggregat. */
function drawN(svg, submitted) {
  if (typeof submitted !== "number") return;
  text(svg, W - PAD.r, 24, `N = ${submitted} Teilnahmen`, { "text-anchor": "end" });
}

/** Dichte je Bin: count / (n * Breite) – vergleichbar trotz Merge-Bins. */
function binDensities(bins) {
  const n = bins.reduce((acc, b) => acc + b.count, 0);
  // Breite 0 (alle Werte identisch, z.B. 1 Testgerät) -> Anzeigebreite 1.
  return bins.map((b) => ({ ...b, density: b.count / (n * ((b.hi - b.lo) || 1)) }));
}

function drawBins(g, sc, bins) {
  for (const b of bins) {
    g.appendChild(el("rect", {
      x: sc.x(b.lo), y: sc.y(b.density),
      width: Math.max(sc.x(b.hi) - sc.x(b.lo) - 2, 1),
      height: H - PAD.b - sc.y(b.density),
      fill: ORANGE,
    }));
  }
}

/** Benchmark als Stufen-Silhouette: gleiche Form wie die Raum-Fläche. */
function drawBenchmarkArea(svg, sc, bench) {
  const { bin_edges: e, densities: d } = bench;
  const pts = [`${sc.x(e[0])},${H - PAD.b}`];
  for (let i = 0; i < d.length; i++) {
    pts.push(`${sc.x(e[i])},${sc.y(d[i])}`, `${sc.x(e[i + 1])},${sc.y(d[i])}`);
  }
  pts.push(`${sc.x(e[d.length])},${H - PAD.b}`);
  svg.appendChild(el("polygon", { points: pts.join(" "), fill: GRAU, opacity: 0.85,
                                  stroke: GRAU_KANTE, "stroke-width": 2 }));
}

/** Raum-KDE als gefüllte Fläche: trägt aus 5 m, eine dünne Linie nicht. */
function drawKdeArea(g, sc, k) {
  const top = k.x.map((xv, i) => `${sc.x(xv)},${sc.y(k.density[i])}`);
  const area = [`${sc.x(k.x[0])},${H - PAD.b}`, ...top,
                `${sc.x(k.x[k.x.length - 1])},${H - PAD.b}`];
  g.appendChild(el("polygon", { points: area.join(" "), fill: ORANGE, opacity: 0.45 }));
  g.appendChild(el("polyline", { points: top.join(" "), fill: "none",
                                 stroke: ORANGE, "stroke-width": 3 }));
}

/** Chip-Legende: nur bei zwei Serien (eine Serie benennt der Titel).
    showRoom=false auf der Erklärfolie, dort ist noch kein Raum zu sehen. */
function setChips(benchmark, showRoom = true) {
  const box = $("chips");
  if (!benchmark) { box.innerHTML = ""; return; }
  const m = /N=(\d+)/.exec(benchmark.source || "");
  const vergleich = m ? `Vergleichsstichprobe (N = ${m[1]})` : "Vergleichsstichprobe";
  box.innerHTML =
    (showRoom ? `<span><i style="background:${ORANGE}"></i>dieser Raum</span>` : "") +
    `<span><i style="background:${GRAU};border:1.5px solid ${GRAU_KANTE}"></i>${vergleich}</span>`;
}

// --- Benchmark-Abruf (Forschungsaggregate, kein Raumbezug) -------------------

let benchmarkCache; // undefined = noch nicht geholt, null = nicht verfügbar

async function ensureBenchmark() {
  if (benchmarkCache !== undefined) return benchmarkCache;
  try {
    const r = await fetch(api("benchmark"));
    benchmarkCache = r.ok ? await r.json() : null;
  } catch {
    benchmarkCache = null;
  }
  return benchmarkCache;
}

function render(stage, agg) {
  if (stage >= 4) return renderPercentile(agg);
  markStage(stage);
  const svg = clearChart();
  drawN(svg, agg.submitted);

  // Inhalt in eigener Gruppe: CSS-Animation beim Reveal (Dramaturgie).
  const g = el("g", { class: "reveal" });

  if (stage === 1) {
    setChips(null);
    $("frame-title").textContent =
      "Wie zuverlässig unterscheidet dieser Raum wahre von falschen Aussagen?";
    $("legend").textContent =
      "d′ (Diskriminationssensitivität): standardisierte Differenz aus Trefferrate " +
      "und Falsche-Alarm-Rate; d′ = 0 entspricht dem Zufallsniveau. Dargestellt ist " +
      "die Verteilung über alle Teilnahmen, keine Einzelwerte.";
    const bins = binDensities(agg.d_prime.bins);
    // Achse schließt IMMER die 0 ein: das Zufallsniveau ist der Anker.
    const sc = scales(svg, Math.min(0, bins[0].lo),
                      Math.max(0.5, bins[bins.length - 1].hi),
                      Math.max(...bins.map((b) => b.density)) * 1.1);
    drawTicks(svg, sc);
    const zx = sc.x(0);
    refLine(svg, zx, { dash: "6 6" });
    // Am linken Rand startet das Label an der Linie statt zentriert (Clipping).
    anchorWord(svg, zx, "Zufallsniveau", zx - PAD.l < 90 ? "start" : "middle");
    anchorWord(svg, W - PAD.r, "höhere Sensitivität →", "end");
    drawBins(g, sc, bins);
    svg.appendChild(g);
    return;
  }

  // Stufen 2+3: b'-Verteilung, optional über Benchmark; Stufe 3 plus Median.
  const bench = agg.benchmark ? agg.benchmark.b_prime : null;
  setChips(bench ? agg.benchmark : null);
  $("frame-title").textContent = bench
    ? "Ideologische Verzerrung b′: dieser Raum und die Vergleichsstichprobe"
    : "Ideologische Verzerrung b′ in diesem Raum";
  $("legend").textContent =
    "b′ (ideologische Verzerrung): Differenz der Antwortgenauigkeit zwischen " +
    "Aussagen, deren korrekte Antwort einer rechten bzw. linken Position " +
    "entspricht. b′ > 0: höhere Genauigkeit bei rechtskongruenten Aussagen, " +
    "b′ < 0: bei linkskongruenten. b′ erfasst keine generelle Zustimmungstendenz." +
    (stage >= 3 ? " Gestrichelte Linie: Median des Raums." : "");

  const k = agg.b_prime.kde;
  const xsAll = bench ? [...k.x, ...bench.bin_edges] : k.x;
  const ysAll = bench ? [...k.density, ...bench.densities] : k.density;
  // Symmetrisch um null: sonst wirkt eine politische Seite optisch schwerer.
  const span = Math.max(0.5, ...xsAll.map(Math.abs));
  const sc = scales(svg, -span, span, Math.max(...ysAll) * 1.1);

  drawTicks(svg, sc);
  if (bench) drawBenchmarkArea(svg, sc, bench);
  refLine(svg, sc.x(0));
  anchorWord(svg, PAD.l, "← linksgerichtete Verzerrung", "start");
  anchorWord(svg, sc.x(0), "keine Asymmetrie");
  anchorWord(svg, W - PAD.r, "rechtsgerichtete Verzerrung →", "end");
  drawKdeArea(g, sc, k);

  if (stage >= 3 && agg.b_prime.room_median !== undefined) {
    const mx = sc.x(agg.b_prime.room_median);
    g.appendChild(el("line", { x1: mx, y1: PAD.t, x2: mx, y2: H - PAD.b,
                               stroke: "#1a1a1a", "stroke-width": 3, "stroke-dasharray": "8 6" }));
    // Label klappt nach links, wenn rechts kein Platz mehr ist.
    const flip = mx > W - 300;
    const lx = mx + (flip ? -10 : 10);
    const anchor = flip ? "end" : "start";
    text(g, lx, PAD.t + 24, "Median des Raums",
         { "font-size": 24, "font-weight": 700, fill: "#1a1a1a", "text-anchor": anchor });
    text(g, lx, PAD.t + 50, `b′ = ${agg.b_prime.room_median.toFixed(2)}`,
         { "text-anchor": anchor });
  }
  svg.appendChild(g);
}

// --- Erklär-/Wartefolie (keine Raumdaten, darum ohne Gate) -------------------

/**
 * Zeigt die b'-Verteilung der Vergleichsstichprobe mit Erklär-Overlays
 * (Lesebeispiel nach Stolp et al., Box 1). Läuft als Wartefolie, während
 * das Publikum bearbeitet. Mit der Freigabe zeichnen die Stufen neu:
 * die Overlays verschwinden, die Raumverteilung erscheint über den
 * Forschungsdaten.
 */
async function renderExplainer() {
  markStage(0);
  const svg = clearChart();
  $("frame-title").textContent = "So liest man die Auswertung";

  const bench = await ensureBenchmark();
  const bp = bench ? bench.b_prime : null;
  const n = bp && bp.summary ? bp.summary.n : null;
  setChips(bench, false);
  $("legend").textContent =
    "b′ (ideologische Verzerrung): Differenz der Antwortgenauigkeit zwischen " +
    "Aussagen, deren korrekte Antwort einer rechten bzw. linken Position " +
    "entspricht. b′ erfasst keine generelle Zustimmungstendenz." +
    (bp ? ` Grau: Vergleichsstichprobe${n ? ` (N = ${n})` : ""}. ` +
          "Aus diesem Raum ist hier noch nichts zu sehen." : "");

  const edges = bp ? bp.bin_edges : [-2, 2];
  const span = Math.max(0.5, ...edges.map(Math.abs));
  const sc = scales(svg, -span, span, bp ? Math.max(...bp.densities) * 1.15 : 1);
  drawTicks(svg, sc);
  if (bp) drawBenchmarkArea(svg, sc, bp);
  refLine(svg, sc.x(0));
  anchorWord(svg, PAD.l, "← linksgerichtete Verzerrung", "start");
  anchorWord(svg, sc.x(0), "keine Asymmetrie");
  anchorWord(svg, W - PAD.r, "rechtsgerichtete Verzerrung →", "end");

  // Lesebeispiel (Stolp et al., Box 1): gleiche Trefferzahl, anderes b'.
  const panel = el("g", {});
  const px = PAD.l + 14, py = PAD.t + 6, pw = 680, ph = 148;
  panel.appendChild(el("rect", { x: px, y: py, width: pw, height: ph, rx: 10,
                                 fill: "#ffffff", opacity: 0.94,
                                 stroke: "#1a1a1a", "stroke-width": 1.5 }));
  const lines = [
    ["Lesebeispiel (zwei fiktive Personen, je 10 Aussagen pro Task):", 700],
    ["Person A: Task-Links 7/10 richtig, Task-Rechts 7/10 → b′ = 0", 400],
    ["Person B: Task-Links 5/10 richtig, Task-Rechts 9/10 → b′ = +1,28", 400],
    ["Gleich viele Treffer insgesamt, aber asymmetrisch verteilt.", 400],
  ];
  lines.forEach(([str, weight], i) => {
    text(panel, px + 16, py + 34 + i * 30, str,
         { "text-anchor": "start", fill: "#1a1a1a", "font-size": 19, "font-weight": weight });
  });
  svg.appendChild(panel);

  text(svg, W - PAD.r, 24, "Nach der Freigabe erscheint hier", { "text-anchor": "end" });
  text(svg, W - PAD.r, 48, "die Verteilung dieses Raums (orange).", { "text-anchor": "end" });
}

// --- Stufe 4: Perzentil-Einordnung (kumulative Verteilung, S-Kurve) ----------

/**
 * Kumulative b'-Verteilung der Vergleichsstichprobe aus dem Quantilgitter.
 * Der Raum-Median wird auf die Kurve projiziert; ablesbar ist, welcher
 * Anteil der Vergleichsstichprobe unterhalb liegt. Braucht Stufe-3-Daten
 * (Median) und das Benchmark – sonst Hinweis statt Chart.
 */
function renderPercentile(agg) {
  markStage(4);
  const svg = clearChart();
  const bench = agg.benchmark;
  const median = agg.b_prime ? agg.b_prime.room_median : undefined;
  if (!bench || !bench.b_prime.quantiles || median === undefined) {
    setChips(null);
    $("frame-title").textContent = "Einordnung nicht verfügbar";
    $("legend").textContent =
      "Die Perzentil-Einordnung braucht die Vergleichsdaten (benchmark.json) " +
      "und den Raum-Median aus Stufe 3.";
    return;
  }

  drawN(svg, agg.submitted);
  setChips(bench);
  const q = bench.b_prime.quantiles;
  const pct = percentileOf(q, median);
  $("frame-title").textContent = "Wo liegt dieser Raum in der Vergleichsstichprobe?";
  $("legend").textContent =
    "Kumulative Verteilung von b′ in der Vergleichsstichprobe: Die Kurve zeigt " +
    "für jeden b′-Wert, welcher Anteil der Stichprobe darunter liegt. " +
    `Der Median dieses Raums (b′ = ${median.toFixed(2)}) liegt am ${pct}. Perzentil: ` +
    `${pct} % der Vergleichsstichprobe liegen darunter, ${100 - pct} % darüber.`;

  const span = Math.max(0.5, Math.abs(median), ...q.values.map(Math.abs)) * 1.05;
  const sc = scales(svg, -span, span, 1); // y läuft hier in Prozent, nicht Dichte
  const yPct = (v) => H - PAD.b - (v / 100) * (H - PAD.t - PAD.b);

  for (const p of [25, 50, 75, 100]) {
    svg.appendChild(el("line", { x1: PAD.l, y1: yPct(p), x2: W - PAD.r, y2: yPct(p),
                                 stroke: "#e4e4e2", "stroke-width": 1.5 }));
    text(svg, PAD.l + 8, yPct(p) - 8, `${p} %`, { "text-anchor": "start" });
  }
  drawTicks(svg, sc);
  refLine(svg, sc.x(0));
  anchorWord(svg, PAD.l, "← linksgerichtete Verzerrung", "start");
  anchorWord(svg, sc.x(0), "keine Asymmetrie");
  anchorWord(svg, W - PAD.r, "rechtsgerichtete Verzerrung →", "end");

  const g = el("g", { class: "reveal" });
  const pts = q.p.map((p, i) => `${sc.x(q.values[i])},${yPct(p)}`);
  g.appendChild(el("polyline", { points: pts.join(" "), fill: "none",
                                 stroke: GRAU_KANTE, "stroke-width": 4 }));

  // Projektion des Raum-Medians: hoch zur Kurve, links zur Prozent-Achse.
  const mx = sc.x(median), my = yPct(pct);
  g.appendChild(el("line", { x1: mx, y1: H - PAD.b, x2: mx, y2: my, stroke: ORANGE,
                             "stroke-width": 3, "stroke-dasharray": "8 6" }));
  g.appendChild(el("line", { x1: mx, y1: my, x2: PAD.l, y2: my, stroke: ORANGE,
                             "stroke-width": 3, "stroke-dasharray": "8 6" }));
  g.appendChild(el("circle", { cx: mx, cy: my, r: 9, fill: ORANGE,
                               stroke: "#ffffff", "stroke-width": 2 }));

  const flip = mx > W - 360;
  const lx = mx + (flip ? -14 : 14), anchor = flip ? "end" : "start";
  const ly = Math.max(my - 12, PAD.t + 58); // Label nicht aus dem Bild schieben
  text(g, lx, ly - 26, `Median des Raums: b′ = ${median.toFixed(2)}`,
       { "font-size": 24, "font-weight": 700, fill: "#1a1a1a", "text-anchor": anchor });
  text(g, lx, ly, `≈ ${pct}. Perzentil`, { "text-anchor": anchor });
  svg.appendChild(g);
}

// --- Demo-Modus (rein clientseitig, UEBERGABE 8) -----------------------------

$("demo-btn").addEventListener("click", () => {
  demoMode = !demoMode;
  $("demo-banner").style.display = demoMode ? "block" : "none";
  $("demo-btn").textContent = demoMode ? "Demo beenden" : "Demo-Modus";
  updateGate(0);
  if (demoMode) renderDemo(currentStage || 1);
});

/** Box-Muller-Normalverteilung für synthetische Demo-Daten. */
function randn(mean, sd) {
  const u = 1 - Math.random(), v = Math.random();
  return mean + sd * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

function demoAggregate() {
  const d = Array.from({ length: 60 }, () => randn(0.9, 0.5));
  const b = Array.from({ length: 60 }, () => randn(-0.3, 0.6));
  const hist = (vals) => {
    const lo = Math.min(...vals), hi = Math.max(...vals), nb = 6, w = (hi - lo) / nb;
    const bins = Array.from({ length: nb }, (_, i) =>
      ({ lo: lo + i * w, hi: lo + (i + 1) * w, count: 0 }));
    for (const v of vals) bins[Math.min(Math.floor((v - lo) / w), nb - 1)].count++;
    return bins;
  };
  const kde = (vals) => {
    const h = 0.25, lo = Math.min(...vals) - 3 * h, hi = Math.max(...vals) + 3 * h;
    const xs = Array.from({ length: 80 }, (_, i) => lo + (i * (hi - lo)) / 79);
    const dens = xs.map((x) =>
      vals.reduce((a, v) => a + Math.exp(-0.5 * ((x - v) / h) ** 2), 0) /
      (vals.length * h * Math.sqrt(2 * Math.PI)));
    return { x: xs, density: dens };
  };
  const sorted = [...b].sort((a, c) => a - c);
  // benchmark wird vom Aufrufer angehängt, falls der Server erreichbar ist;
  // ohne Server (Totalausfall) läuft die Demo trotzdem, nur ohne Overlay.
  return {
    submitted: 60,
    d_prime: { bins: hist(d) },
    b_prime: { bins: hist(b), kde: kde(b), room_median: sorted[30] },
    benchmark: null,
  };
}

async function renderDemo(stage) {
  // Erst echte Testdaten versuchen (Gate umgangen; Server erlaubt das nur
  // als Dev-Instanz mit FAKTOMAT_DEV=1). So sieht man mit 1-3 Testgeräten
  // den kompletten echten Datenpfad in der Grafik. Sonst: synthetisch.
  try {
    const r = await fetch(api("aggregate?nogate=1"), { headers: authHeaders });
    if (r.ok) {
      const agg = await r.json();
      if (agg.ungated && agg.submitted > 0) {
        $("demo-banner").textContent =
          `TESTMODUS - ${agg.submitted} echte Teilnahme(n), Anonymitäts-Gate umgangen. ` +
          "Nie im Produktivbetrieb verwenden.";
        render(stage, agg);
        return;
      }
    }
  } catch { /* Server nicht erreichbar -> synthetischer Fallback */ }
  $("demo-banner").textContent = "DEMO-MODUS - synthetische Daten, keine echten Teilnahmen";
  const demo = demoAggregate();
  demo.benchmark = await ensureBenchmark(); // Overlay + Einordnung, wenn verfügbar
  render(stage, demo);
}

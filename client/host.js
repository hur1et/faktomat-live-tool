/**
 * Host-View — Faktomat Live (UEBERGABE 3 Komponente 2, Abschnitt 6).
 *
 * Fortschritt über SSE, drei MANUELL ausgelöste Reveal-Stufen, Charts als
 * handgerolltes SVG (bewusst kein D3: keine externe Abhängigkeit am
 * Event-Tag; die KDE kommt fertig gerechnet vom Server, gezeichnet werden
 * nur Balken und ein Pfad).
 *
 * Anonymität: dieser Client erhält ausschließlich Aggregate (gemergte Bins,
 * KDE-Gitter, Median) — nie Einzelwerte. Balkenhöhen sind DICHTEN
 * (count/Breite), weil Bins nach dem n<3-Merge ungleich breit sind.
 *
 * Demo-Modus (UEBERGABE 8): rein clientseitig erzeugte synthetische Daten,
 * klar gebannert, berührt den Server nicht.
 */

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
  updateGate(d.submitted);
};
source.onerror = () => { $("status").textContent = "Verbindung zum Server unterbrochen — SSE reconnectet …"; };

function updateGate(submitted) {
  const open = submitted >= GATE;
  for (const s of [1, 2, 3]) $(`stage-${s}`).disabled = !open && !demoMode;
  $("gate-hint").textContent = open || demoMode
    ? "" : `Reveal gesperrt: erst ab ${GATE} Teilnahmen (aktuell ${submitted}).`;
}
updateGate(0);

// --- Reveal-Stufen -----------------------------------------------------------

for (const s of [1, 2, 3]) {
  $(`stage-${s}`).addEventListener("click", () => (demoMode ? renderDemo(s) : reveal(s)));
}

async function reveal(stage) {
  $("status").textContent = "";
  const r = await fetch(api("reveal"), {
    method: "POST",
    headers: { ...authHeaders, "Content-Type": "application/json" },
    body: JSON.stringify({ stage }),
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
  for (const s of [1, 2, 3]) $(`stage-${s}`).classList.toggle("active", s === stage);
}

// --- Rendering (SVG, ohne Bibliothek) ---------------------------------------

const W = 1000, H = 520, PAD = { l: 50, r: 30, t: 20, b: 40 };

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

/** Skalen + Achse; gibt x()/y()-Abbildungen in Pixelkoordinaten zurück. */
function scales(svg, xMin, xMax, yMax) {
  const x = (v) => PAD.l + ((v - xMin) / (xMax - xMin)) * (W - PAD.l - PAD.r);
  const y = (v) => H - PAD.b - (v / yMax) * (H - PAD.t - PAD.b);
  svg.appendChild(el("line", { x1: PAD.l, y1: H - PAD.b, x2: W - PAD.r, y2: H - PAD.b,
                               stroke: "#1a1a1a", "stroke-width": 2 }));
  for (const tick of [xMin, 0, xMax].filter((t, i, a) => a.indexOf(t) === i && t >= xMin && t <= xMax)) {
    const t = el("text", { x: x(tick), y: H - PAD.b + 26, "text-anchor": "middle",
                           "font-size": 18, fill: "#767676" });
    t.textContent = tick.toFixed(1);
    svg.appendChild(t);
  }
  return { x, y };
}

/** Dichte je Bin: count / (n * Breite) — vergleichbar trotz Merge-Bins. */
function binDensities(bins) {
  const n = bins.reduce((acc, b) => acc + b.count, 0);
  return bins.map((b) => ({ ...b, density: b.count / (n * (b.hi - b.lo)) }));
}

function drawBins(svg, sc, bins, fill, opacity = 1) {
  for (const b of bins) {
    svg.appendChild(el("rect", {
      x: sc.x(b.lo), y: sc.y(b.density),
      width: sc.x(b.hi) - sc.x(b.lo) - 2,
      height: H - PAD.b - sc.y(b.density),
      fill, opacity,
    }));
  }
}

function drawBenchmark(svg, sc, bench) {
  // benchmark.json: bin_edges (n+1) + densities (n), gleichbreit.
  const { bin_edges: e, densities: d } = bench;
  for (let i = 0; i < d.length; i++) {
    svg.appendChild(el("rect", {
      x: sc.x(e[i]), y: sc.y(d[i]),
      width: sc.x(e[i + 1]) - sc.x(e[i]),
      height: H - PAD.b - sc.y(d[i]),
      fill: "#c8c8c8", opacity: 0.8,
    }));
  }
}

function drawKde(svg, sc, kdeData) {
  const pts = kdeData.x.map((xv, i) => `${sc.x(xv)},${sc.y(kdeData.density[i])}`);
  svg.appendChild(el("polyline", {
    points: pts.join(" "), fill: "none",
    stroke: "#ef7d00", "stroke-width": 4, // CD-Orange (FAKT-O-MAT)
  }));
}

function render(stage, agg) {
  markStage(stage);
  const svg = clearChart();

  if (stage === 1) {
    $("frame-title").textContent = "Wie gut unterscheidet dieser Raum wahr von falsch?";
    $("legend").textContent = "d′-Verteilung des Raums (0 = Raten, höher = besser). Nur Gruppendaten.";
    const bins = binDensities(agg.d_prime.bins);
    const sc = scales(svg, bins[0].lo, bins[bins.length - 1].hi,
                      Math.max(...bins.map((b) => b.density)) * 1.1);
    drawBins(svg, sc, bins, "#ef7d00");
    return;
  }

  // Stufen 2+3: b'-KDE, optional über Benchmark; Stufe 3 zusätzlich Median.
  const bench = agg.benchmark ? agg.benchmark.b_prime : null;
  $("frame-title").textContent = bench
    ? "Wie unterscheidet sich dieser Raum von der Vergleichsstichprobe?"
    : "Antwort-Asymmetrie b′ in diesem Raum";
  $("legend").textContent =
    "b′: Asymmetrie der Genauigkeit (links- vs. rechts-kongruente Aussagen) — " +
    "keine Ja-Sage-Tendenz. Grau: Vergleichsstichprobe, Orange: dieser Raum." +
    (stage >= 3 ? " Marker: Median des Raums." : "");

  const k = agg.b_prime.kde;
  const xsAll = bench ? [...k.x, ...bench.bin_edges] : k.x;
  const ysAll = bench ? [...k.density, ...bench.densities] : k.density;
  const sc = scales(svg, Math.min(...xsAll), Math.max(...xsAll), Math.max(...ysAll) * 1.1);

  if (bench) drawBenchmark(svg, sc, bench);
  drawKde(svg, sc, k);

  if (stage >= 3 && agg.b_prime.room_median !== undefined) {
    const mx = sc.x(agg.b_prime.room_median);
    svg.appendChild(el("line", { x1: mx, y1: PAD.t, x2: mx, y2: H - PAD.b,
                                 stroke: "#1a1a1a", "stroke-width": 3, "stroke-dasharray": "8 6" }));
    const label = el("text", { x: mx + 8, y: PAD.t + 22, "font-size": 20, fill: "#1a1a1a" });
    label.textContent = `Raum-Median: ${agg.b_prime.room_median.toFixed(2)}`;
    svg.appendChild(label);
  }
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
  // Demo ohne Benchmark-Overlay: die Dramaturgie funktioniert auch ohne,
  // und der Demo-Modus soll komplett ohne Server auskommen (Totalausfall).
  return {
    d_prime: { bins: hist(d) },
    b_prime: { bins: hist(b), kde: kde(b), room_median: sorted[30] },
    benchmark: null,
  };
}

function renderDemo(stage) {
  render(stage, demoAggregate());
}

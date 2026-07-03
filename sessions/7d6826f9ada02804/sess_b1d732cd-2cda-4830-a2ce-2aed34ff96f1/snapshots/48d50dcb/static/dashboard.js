"use strict";

// Small client for the dashboard API. Runs against the same origin.
const API = {
  signals: "/api/signals",
  ticker: (t, period) => `/api/ticker/${encodeURIComponent(t)}?period=${encodeURIComponent(period)}`,
};

let currentTicker = null;
let currentPeriod = window.DEFAULT_PERIOD || "6mo";
let priceChart = null;

// ---- helpers ---------------------------------------------------------------
function fmtScore(x) {
  return x === null || x === undefined ? "-" : (x >= 0 ? "+" : "") + x.toFixed(2);
}
function fmtPct(x) {
  return x === null || x === undefined ? "-" : Math.round(x * 100) + "%";
}
function fmtNum(x, dp = 2) {
  return x === null || x === undefined ? "-" : Number(x).toFixed(dp);
}
function labelClass(label) {
  return "badge badge-" + String(label).toLowerCase().replace("/", "");
}
async function getJSON(url) {
  const resp = await fetch(url);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.error || `request failed (${resp.status})`);
  }
  return data;
}

// ---- signals table ---------------------------------------------------------
async function loadSignals() {
  const status = document.getElementById("signals-status");
  const body = document.getElementById("signals-body");
  status.textContent = "Loading signals...";
  body.innerHTML = "";
  try {
    const data = await getJSON(API.signals);
    status.textContent = "";
    for (const row of data.signals) {
      const tr = document.createElement("tr");
      tr.className = "signal-row";
      tr.innerHTML = `
        <td class="ticker">${row.ticker}</td>
        <td>${row.sector}</td>
        <td><span class="${labelClass(row.label)}">${row.label}</span></td>
        <td>${fmtScore(row.score)}</td>
        <td>${fmtPct(row.confidence)}</td>
        <td>${fmtNum(row.close)}</td>`;
      tr.addEventListener("click", () => selectTicker(row.ticker));
      body.appendChild(tr);
    }
  } catch (err) {
    status.textContent = "Could not load signals: " + err.message;
  }
}

// ---- ticker detail ---------------------------------------------------------
async function selectTicker(ticker) {
  currentTicker = ticker;
  document.getElementById("detail-section").hidden = false;
  document.getElementById("detail-title").textContent = ticker;
  await loadDetail();
  document.getElementById("detail-section").scrollIntoView({ behavior: "smooth" });
}

async function loadDetail() {
  if (!currentTicker) return;
  const status = document.getElementById("detail-status");
  status.textContent = "Loading " + currentTicker + " (" + currentPeriod + ")...";
  try {
    const data = await getJSON(API.ticker(currentTicker, currentPeriod));
    status.textContent = "";
    renderSummary(data);
    renderBreakdown(data);
    renderChart(data);
  } catch (err) {
    status.textContent = "Could not load ticker: " + err.message;
  }
}

function renderSummary(data) {
  const el = document.getElementById("detail-summary");
  const f = data.fundamentals || {};
  const name = f.longName || f.shortName || data.ticker;
  el.innerHTML = `
    <span class="${labelClass(data.label)}">${data.label}</span>
    score <strong>${fmtScore(data.score)}</strong> (scale -1..+1),
    confidence <strong>${fmtPct(data.confidence)}</strong><br>
    <span class="muted">${name} &middot; ${data.sector}
    ${f.trailingPE ? " &middot; P/E " + fmtNum(f.trailingPE) : ""}</span>`;
}

function renderBreakdown(data) {
  const body = document.getElementById("breakdown-body");
  body.innerHTML = "";
  const weights = data.weights || {};
  for (const [name, val] of Object.entries(data.breakdown || {})) {
    const cls = val > 0 ? "pos" : (val < 0 ? "neg" : "");
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${name}</td>
      <td class="${cls}">${fmtScore(val)}</td>
      <td>${fmtNum(weights[name], 3)}</td>`;
    body.appendChild(tr);
  }
}

function renderChart(data) {
  const chart = data.chart || [];
  const labels = chart.map((p) => p.date);
  const mk = (key) => chart.map((p) => p[key]);
  const datasets = [
    { label: "Close", data: mk("close"), borderColor: "#6ea8fe", borderWidth: 1.5, pointRadius: 0, tension: 0.1 },
    { label: "SMA 20", data: mk("sma_short"), borderColor: "#4ad991", borderWidth: 1, pointRadius: 0 },
    { label: "SMA 50", data: mk("sma_long"), borderColor: "#f0b36b", borderWidth: 1, pointRadius: 0 },
  ];
  const ctx = document.getElementById("price-chart");
  if (priceChart) priceChart.destroy();
  priceChart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: "#e6e9ef" } } },
      scales: {
        x: { ticks: { color: "#9aa4b2", maxTicksLimit: 8 }, grid: { color: "#263041" } },
        y: { ticks: { color: "#9aa4b2" }, grid: { color: "#263041" } },
      },
    },
  });
}

// ---- wiring ----------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("refresh").addEventListener("click", loadSignals);
  document.querySelectorAll("#period-buttons button").forEach((btn) => {
    btn.addEventListener("click", () => {
      currentPeriod = btn.dataset.period;
      document.querySelectorAll("#period-buttons button")
        .forEach((b) => b.classList.toggle("active", b === btn));
      loadDetail();
    });
  });
  loadSignals();
});

"use strict";

// Client for the dashboard API (same-origin). Plain JS, no framework.
const API = {
  watchlist: "/api/watchlist",
  signals: "/api/signals",
  ticker: (t, p) => `/api/ticker/${encodeURIComponent(t)}?period=${encodeURIComponent(p)}`,
  backtest: (t) => `/api/backtest/${encodeURIComponent(t)}`,
};

const state = {
  quickList: [],
  sectors: [],
  watchlist: {},
  signals: [],
  activeTab: "Quick List",
  ticker: null,
  period: window.DEFAULT_PERIOD || "6mo",
};

let priceChart = null;

// ---- formatting helpers ----------------------------------------------------
const fmtScore = (x) => (x === null || x === undefined ? "-" : (x >= 0 ? "+" : "") + x.toFixed(2));
const fmtPct = (x) => (x === null || x === undefined ? "-" : Math.round(x * 100) + "%");
const fmtPctVal = (x) => (x === null || x === undefined ? "-" : (x >= 0 ? "+" : "") + Number(x).toFixed(2) + "%");
const fmtNum = (x, dp = 2) => (x === null || x === undefined ? "-" : Number(x).toFixed(dp));

function signClass(x) {
  if (x === null || x === undefined) return "flat";
  return x > 0 ? "pos" : (x < 0 ? "neg" : "flat");
}
function labelClass(label) {
  return "badge badge-" + String(label || "na").toLowerCase().replace("/", "");
}
function sigColor(label) {
  const l = String(label || "").toLowerCase();
  if (l === "buy") return "var(--buy)";
  if (l === "sell") return "var(--sell)";
  if (l === "hold") return "var(--hold)";
  return "var(--na)";
}
function fmtCap(x) {
  if (!x) return "-";
  const units = [[1e12, "T"], [1e9, "B"], [1e6, "M"]];
  for (const [size, suffix] of units) {
    if (x >= size) return "$" + (x / size).toFixed(2) + suffix;
  }
  return "$" + Number(x).toFixed(0);
}

async function getJSON(url) {
  const resp = await fetch(url);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || `request failed (${resp.status})`);
  return data;
}

// ---- tabs ------------------------------------------------------------------
function renderTabs() {
  const nav = document.getElementById("tabs");
  nav.innerHTML = "";
  const tabs = ["Quick List", ...state.sectors];
  for (const name of tabs) {
    const btn = document.createElement("button");
    btn.className = "tab" + (name === state.activeTab ? " active" : "");
    btn.textContent = name;
    btn.addEventListener("click", () => {
      state.activeTab = name;
      renderTabs();
      renderCards();
    });
    nav.appendChild(btn);
  }
}

function tickersForActiveTab() {
  if (state.activeTab === "Quick List") return state.quickList;
  return state.watchlist[state.activeTab] || [];
}

// ---- cards -----------------------------------------------------------------
function renderCards() {
  const grid = document.getElementById("card-grid");
  grid.innerHTML = "";
  const wanted = new Set(tickersForActiveTab());
  const rows = state.signals.filter((r) => wanted.has(r.ticker));

  if (!rows.length) {
    grid.innerHTML = `<p class="muted">No signals to show.</p>`;
    return;
  }

  for (const row of rows) {
    const color = sigColor(row.label);
    const card = document.createElement("div");
    card.className = "card" + (row.ticker === state.ticker ? " selected" : "");
    card.style.setProperty("--sig", color);
    card.innerHTML = `
      <div class="card-top">
        <span class="card-ticker">${row.ticker}</span>
        <span class="${labelClass(row.label)}">${row.label}</span>
      </div>
      <div class="card-sector">${row.sector}</div>
      <div class="card-mid">
        <span class="card-score ${signClass(row.score)}">${fmtScore(row.score)}</span>
        <span class="card-price">
          <span class="lbl">Close</span>
          <span class="val">${fmtNum(row.close)}</span>
        </span>
      </div>
      <div class="meter"><span style="width:${Math.round((row.confidence || 0) * 100)}%"></span></div>
      <div class="card-conf">Confidence ${fmtPct(row.confidence)}</div>`;
    card.addEventListener("click", () => openDetail(row.ticker));
    grid.appendChild(card);
  }
}

// ---- signals load ----------------------------------------------------------
async function loadSignals() {
  const status = document.getElementById("signals-status");
  status.textContent = "Loading signals...";
  try {
    const data = await getJSON(API.signals);
    state.signals = data.signals || [];
    status.textContent = "";
    setLastUpdated();
    renderCards();
    if (state.ticker) loadDetail();  // refresh open detail too
  } catch (err) {
    status.textContent = "Could not load signals: " + err.message;
  }
}

function setLastUpdated() {
  const el = document.getElementById("last-updated");
  el.textContent = new Date().toLocaleTimeString();
}

// ---- detail panel ----------------------------------------------------------
function openDetail(ticker) {
  state.ticker = ticker;
  document.getElementById("detail").hidden = false;
  document.getElementById("detail-ticker").textContent = ticker;
  renderCards(); // update .selected highlight
  loadDetail();
  loadBacktest();
  document.getElementById("detail").scrollIntoView({ behavior: "smooth", block: "start" });
}

function closeDetail() {
  state.ticker = null;
  document.getElementById("detail").hidden = true;
  renderCards();
}

async function loadDetail() {
  if (!state.ticker) return;
  const status = document.getElementById("detail-status");
  status.textContent = `Loading ${state.ticker} (${state.period})...`;
  try {
    const data = await getJSON(API.ticker(state.ticker, state.period));
    status.textContent = "";
    renderSignalHead(data);
    renderBreakdown(data);
    renderFundamentals(data);
    renderChart(data);
  } catch (err) {
    status.textContent = "Could not load ticker: " + err.message;
  }
}

function renderSignalHead(data) {
  const badge = document.getElementById("detail-badge");
  badge.className = labelClass(data.label);
  badge.textContent = data.label;
  const score = document.getElementById("detail-score");
  score.className = "detail-score " + signClass(data.score);
  score.textContent = fmtScore(data.score);
  document.getElementById("detail-confidence").textContent = "conf " + fmtPct(data.confidence);
  const f = data.fundamentals || {};
  document.getElementById("detail-name").textContent = f.longName || f.shortName || data.sector || "";
}

function renderBreakdown(data) {
  const body = document.getElementById("breakdown-body");
  body.innerHTML = "";
  const weights = data.weights || {};
  for (const [name, val] of Object.entries(data.breakdown || {})) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${name}</td>
      <td class="num ${signClass(val)}">${fmtScore(val)}</td>
      <td class="num">${fmtNum(weights[name], 3)}</td>`;
    body.appendChild(tr);
  }
}

function renderFundamentals(data) {
  const f = data.fundamentals || {};
  const rows = [
    ["Sector", f.sector || data.sector || "-"],
    ["Industry", f.industry || "-"],
    ["P/E (trailing)", fmtNum(f.trailingPE)],
    ["P/E (forward)", fmtNum(f.forwardPE)],
    ["Earnings growth", f.earningsGrowth != null ? fmtPctVal(f.earningsGrowth * 100) : "-"],
    ["Market cap", fmtCap(f.marketCap)],
    ["Dividend yield", f.dividendYield != null ? fmtPctVal(f.dividendYield * 100) : "-"],
  ];
  const body = document.getElementById("fundamentals-body");
  body.innerHTML = rows.map(([k, v]) => `<tr><td>${k}</td><td class="num">${v}</td></tr>`).join("");
}

function renderChart(data) {
  const chart = data.chart || [];
  const labels = chart.map((p) => p.date);
  const pick = (key) => chart.map((p) => p[key]);
  const datasets = [
    { label: "Close", data: pick("close"), borderColor: "#60a5fa", borderWidth: 1.6, pointRadius: 0, tension: 0.12 },
    { label: "SMA 20", data: pick("sma_short"), borderColor: "#16c784", borderWidth: 1, pointRadius: 0 },
    { label: "SMA 50", data: pick("sma_long"), borderColor: "#f5a623", borderWidth: 1, pointRadius: 0 },
  ];
  const ctx = document.getElementById("price-chart");
  if (priceChart) priceChart.destroy();
  priceChart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: "#8b97ab", boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: "#5e6a7e", maxTicksLimit: 8 }, grid: { color: "#1b2431" } },
        y: { ticks: { color: "#5e6a7e" }, grid: { color: "#1b2431" } },
      },
    },
  });
}

// ---- backtest --------------------------------------------------------------
async function loadBacktest() {
  if (!state.ticker) return;
  const body = document.getElementById("backtest-body");
  body.innerHTML = `<p class="muted">Running simulated backtest...</p>`;
  try {
    const d = await getJSON(API.backtest(state.ticker));
    if (!d.ok) {
      body.innerHTML = `<p class="bt-message">${d.message || "Backtest unavailable."}</p>`;
      return;
    }
    const verdict = d.beat_buy_and_hold
      ? `<span class="bt-verdict win">Beat buy &amp; hold</span>`
      : `<span class="bt-verdict lose">Underperformed buy &amp; hold</span>`;
    body.innerHTML = `
      <div class="bt-summary">
        <div class="bt-metric"><span class="lbl">Strategy return</span>
          <span class="val ${signClass(d.total_return_pct)}">${fmtPctVal(d.total_return_pct)}</span></div>
        <div class="bt-metric"><span class="lbl">Buy &amp; hold</span>
          <span class="val ${signClass(d.buy_and_hold_return_pct)}">${fmtPctVal(d.buy_and_hold_return_pct)}</span></div>
        <div class="bt-metric"><span class="lbl">Trades</span><span class="val">${d.num_trades}</span></div>
        <div class="bt-metric"><span class="lbl">Win rate</span><span class="val">${fmtNum(d.win_rate_pct, 1)}%</span></div>
        <div class="bt-metric"><span class="lbl">Max drawdown</span>
          <span class="val neg">${fmtNum(d.max_drawdown_pct, 1)}%</span></div>
      </div>
      ${verdict}
      <p class="bt-note">${d.disclaimer || ""} Window ${d.start_date} to ${d.end_date} (${d.trading_days} trading days).</p>`;
  } catch (err) {
    body.innerHTML = `<p class="bt-message">Could not run backtest: ${err.message}</p>`;
  }
}

// ---- wiring ----------------------------------------------------------------
async function init() {
  document.getElementById("refresh").addEventListener("click", loadSignals);
  document.getElementById("detail-close").addEventListener("click", closeDetail);
  document.querySelectorAll("#timeframe .tf-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.period = btn.dataset.period;
      document.querySelectorAll("#timeframe .tf-btn")
        .forEach((b) => b.classList.toggle("active", b === btn));
      loadDetail();
    });
  });

  try {
    const wl = await getJSON(API.watchlist);
    state.quickList = wl.quick_list || [];
    state.sectors = wl.sectors || [];
    state.watchlist = wl.watchlist || {};
  } catch (err) {
    document.getElementById("signals-status").textContent =
      "Could not load watchlist: " + err.message;
  }
  renderTabs();
  await loadSignals();
}

document.addEventListener("DOMContentLoaded", init);

"use strict";

// Client for the dashboard API (same-origin). Plain JS, no frameworks.
// Charts are drawn with Plotly (pinned in index.html). View-only: there are
// deliberately no trade actions anywhere in this UI.

const API = {
  watchlist: "/api/watchlist",
  signals: "/api/signals",
  ticker: (t, p) => `/api/ticker/${encodeURIComponent(t)}?period=${encodeURIComponent(p)}`,
  backtest: (t) => `/api/backtest/${encodeURIComponent(t)}`,
  research: "/api/research",
};

const RESEARCH_TAB = "Research";

const state = {
  quickList: [],
  sectors: [],
  watchlist: {},
  signals: [],
  research: null,         // cached static study data
  activeTab: "Quick List",
  filter: "ALL",          // ALL | BUY | HOLD | SELL
  ticker: null,
  period: window.DEFAULT_PERIOD || "6mo",
};

// theme colors for Plotly (kept in sync with style.css)
const THEME = {
  text: "#8b97ab", grid: "#1b2431", buy: "#16c784", sell: "#ea3943",
  hold: "#f5a623", blue: "#60a5fa", band: "rgba(245, 166, 35, 0.10)",
  bandLine: "rgba(245, 166, 35, 0.35)",
};

// --------------------------------------------------------------------------
// Safe formatting - a missing/NaN value must never throw
// --------------------------------------------------------------------------
function toNum(x) {
  if (x === null || x === undefined || x === "") return null;
  const n = Number(x);
  return Number.isFinite(n) ? n : null;
}
const DASH = "\u2013";
function fmtScore(x) { const n = toNum(x); return n === null ? DASH : (n >= 0 ? "+" : "") + n.toFixed(2); }
function fmtPct(x) { const n = toNum(x); return n === null ? DASH : Math.round(n * 100) + "%"; }
function fmtPctVal(x) { const n = toNum(x); return n === null ? DASH : (n >= 0 ? "+" : "") + n.toFixed(2) + "%"; }
function fmtNum(x, dp = 2) { const n = toNum(x); return n === null ? DASH : n.toFixed(dp); }
function fmtMoney(x) { const n = toNum(x); return n === null ? DASH : "$" + n.toLocaleString(undefined, { maximumFractionDigits: 2 }); }
function fmtCap(x) {
  const n = toNum(x);
  if (n === null) return DASH;
  for (const [size, suffix] of [[1e12, "T"], [1e9, "B"], [1e6, "M"]]) {
    if (n >= size) return "$" + (n / size).toFixed(2) + suffix;
  }
  return "$" + n.toFixed(0);
}

function signClass(x) { const n = toNum(x); return n === null ? "flat" : (n > 0 ? "pos" : (n < 0 ? "neg" : "flat")); }
function labelClass(label) { return "badge badge-" + String(label || "na").toLowerCase().replace("/", ""); }
function sigColor(label) {
  const l = String(label || "").toLowerCase();
  return l === "buy" ? THEME.buy : l === "sell" ? THEME.sell : l === "hold" ? THEME.hold : "var(--na)";
}

// --------------------------------------------------------------------------
// Fetch wrapper - every call surfaces a real, human message on failure
// --------------------------------------------------------------------------
async function getJSON(url) {
  let resp;
  try {
    resp = await fetch(url);
  } catch (e) {
    // Network-level failure: server down, wrong port, no connection, etc.
    throw new Error("Couldn't reach the server \u2014 is it running? (try: python app.py)");
  }
  let data = {};
  try { data = await resp.json(); } catch (e) { data = {}; }
  if (!resp.ok) throw new Error(data.error || `Request failed (${resp.status})`);
  return data;
}

function showError(el, err) {
  if (el) el.innerHTML = `<span class="err">\u26a0 ${err.message}</span>`;
}

// --------------------------------------------------------------------------
// Tabs
// --------------------------------------------------------------------------
function renderTabs() {
  const nav = document.getElementById("tabs");
  nav.innerHTML = "";
  for (const name of ["Quick List", ...state.sectors, RESEARCH_TAB]) {
    const btn = document.createElement("button");
    btn.className = "tab" + (name === state.activeTab ? " active" : "")
      + (name === RESEARCH_TAB ? " tab-research" : "");
    btn.textContent = name;
    btn.addEventListener("click", () => { state.activeTab = name; renderTabs(); renderActiveView(); });
    nav.appendChild(btn);
  }
}

// Toggle between the live-signals view and the static research view.
function renderActiveView() {
  const isResearch = state.activeTab === RESEARCH_TAB;
  document.getElementById("live-toolbar").hidden = isResearch;
  document.getElementById("signals-status").hidden = isResearch;
  document.getElementById("card-grid").hidden = isResearch;
  document.getElementById("research").hidden = !isResearch;
  if (isResearch) {
    document.getElementById("detail").hidden = true; // keep live detail out of the way
    loadResearch();
  } else {
    renderCards();
  }
}

function tickersForActiveTab() {
  return state.activeTab === "Quick List"
    ? state.quickList
    : (state.watchlist[state.activeTab] || []);
}

function sectorForTicker(ticker) {
  for (const [sector, tickers] of Object.entries(state.watchlist)) {
    if (tickers.includes(ticker)) return sector;
  }
  return null;
}

// --------------------------------------------------------------------------
// Cards
// --------------------------------------------------------------------------
function renderCards() {
  const grid = document.getElementById("card-grid");
  grid.innerHTML = "";
  const wanted = new Set(tickersForActiveTab());
  const rows = state.signals.filter(
    (r) => wanted.has(r.ticker) && (state.filter === "ALL" || r.label === state.filter)
  );

  if (!rows.length) {
    grid.innerHTML = `<p class="muted">No stocks match this view.</p>`;
    return;
  }

  for (const row of rows) {
    const card = document.createElement("div");
    card.className = "card" + (row.ticker === state.ticker ? " selected" : "");
    card.style.setProperty("--sig", sigColor(row.label));
    card.innerHTML = `
      <div class="card-top">
        <span class="card-ticker">${row.ticker}</span>
        <span class="${labelClass(row.label)}">${row.label}</span>
      </div>
      <div class="card-sector">${row.sector || ""}</div>
      <div class="card-mid">
        <span class="card-score ${signClass(row.score)}">${fmtScore(row.score)}</span>
        <span class="card-price"><span class="lbl">Close</span><span class="val">${fmtNum(row.close)}</span></span>
      </div>
      <div class="meter"><span style="width:${Math.round((toNum(row.confidence) || 0) * 100)}%"></span></div>
      <div class="card-conf">Confidence ${fmtPct(row.confidence)}</div>`;
    card.addEventListener("click", () => openDetail(row.ticker));
    grid.appendChild(card);
  }
}

// --------------------------------------------------------------------------
// Signals load
// --------------------------------------------------------------------------
async function loadSignals() {
  const status = document.getElementById("signals-status");
  status.textContent = "Loading signals...";
  try {
    const data = await getJSON(API.signals);
    state.signals = data.signals || [];
    status.textContent = "";
    document.getElementById("last-updated").textContent = new Date().toLocaleTimeString();
    renderCards();
    if (state.ticker) loadDetailFull();
  } catch (err) {
    showError(status, err);
  }
}

// --------------------------------------------------------------------------
// Detail panel
// --------------------------------------------------------------------------
function openDetail(ticker) {
  state.ticker = ticker;
  state.period = window.DEFAULT_PERIOD || "6mo";
  document.getElementById("detail").hidden = false;
  document.getElementById("detail-ticker").textContent = ticker;
  // reset timeframe highlight to default
  document.querySelectorAll("#timeframe .tf-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.period === state.period));
  // reset backtest area
  document.getElementById("backtest-body").innerHTML =
    `<p class="muted">Click &ldquo;Run backtest&rdquo; to simulate this strategy over the past year.</p>`;
  const eq = document.getElementById("equity-chart");
  eq.hidden = true; eq.innerHTML = "";

  renderCards(); // refresh .selected highlight
  loadDetailFull();
  document.getElementById("detail").scrollIntoView({ behavior: "smooth", block: "start" });
}

function closeDetail() {
  state.ticker = null;
  document.getElementById("detail").hidden = true;
  renderCards();
}

async function loadDetailFull() {
  if (!state.ticker) return;
  const status = document.getElementById("detail-status");
  status.textContent = `Loading ${state.ticker} (${state.period})...`;
  try {
    const data = await getJSON(API.ticker(state.ticker, state.period));
    status.textContent = "";
    renderSignalHead(data);
    renderBreakdown(data);
    renderFundamentals(data);
    drawPriceChart(data);
  } catch (err) {
    showError(status, err);
  }
}

// Timeframe change: re-pull ONLY the chart, leaving the rest of the panel as-is.
async function loadChartOnly() {
  if (!state.ticker) return;
  const status = document.getElementById("detail-status");
  status.textContent = `Updating chart (${state.period})...`;
  try {
    const data = await getJSON(API.ticker(state.ticker, state.period));
    status.textContent = "";
    drawPriceChart(data);
  } catch (err) {
    showError(status, err);
  }
}

function renderSignalHead(data) {
  const badge = document.getElementById("detail-badge");
  badge.className = labelClass(data.label);
  badge.textContent = data.label || DASH;
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
  const entries = Object.entries(data.breakdown || {});
  if (!entries.length) { body.innerHTML = `<tr><td class="muted">No breakdown</td></tr>`; return; }
  for (const [name, val] of entries) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${name}</td>
      <td class="num ${signClass(val)}">${fmtScore(val)}</td>
      <td class="num">${fmtNum(weights[name], 3)}</td>`;
    body.appendChild(tr);
  }
}

function renderFundamentals(data) {
  const f = data.fundamentals || {};
  const eg = toNum(f.earningsGrowth);
  const dy = toNum(f.dividendYield);
  const rows = [
    ["Sector", f.sector || data.sector || DASH],
    ["Industry", f.industry || DASH],
    ["P/E (trailing)", fmtNum(f.trailingPE)],
    ["P/E (forward)", fmtNum(f.forwardPE)],
    ["Earnings growth", eg === null ? DASH : fmtPctVal(eg * 100)],
    ["Market cap", fmtCap(f.marketCap)],
    ["Dividend yield", dy === null ? DASH : fmtPctVal(dy * 100)],
  ];
  document.getElementById("fundamentals-body").innerHTML =
    rows.map(([k, v]) => `<tr><td>${k}</td><td class="num">${v}</td></tr>`).join("");
}

// --------------------------------------------------------------------------
// Charts (Plotly)
// --------------------------------------------------------------------------
function darkLayout(extra) {
  return Object.assign({
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: THEME.text, size: 11 },
    margin: { l: 48, r: 12, t: 10, b: 36 },
    xaxis: { gridcolor: THEME.grid, zerolinecolor: THEME.grid },
    yaxis: { gridcolor: THEME.grid, zerolinecolor: THEME.grid },
    legend: { orientation: "h", y: 1.12, font: { size: 10 } },
    hovermode: "x unified",
  }, extra || {});
}

const PLOT_CONFIG = { responsive: true, displayModeBar: false };

function plotUnavailable(el) {
  el.innerHTML = `<p class="err">\u26a0 Chart library didn't load (offline?). Metrics above still work.</p>`;
}

function drawPriceChart(data) {
  const el = document.getElementById("price-chart");
  if (typeof Plotly === "undefined") return plotUnavailable(el);

  const chart = data.chart || [];
  if (!chart.length) { el.innerHTML = `<p class="muted">No chart data available.</p>`; return; }

  const x = chart.map((p) => p.date);
  const col = (k) => chart.map((p) => toNum(p[k]));

  const traces = [
    // Bollinger band: upper first, lower fills the area between them.
    { x, y: col("bb_upper"), name: "BB upper", mode: "lines", line: { color: THEME.bandLine, width: 1 }, showlegend: false, hoverinfo: "skip" },
    { x, y: col("bb_lower"), name: "Bollinger (20, 2)", mode: "lines", line: { color: THEME.bandLine, width: 1 }, fill: "tonexty", fillcolor: THEME.band, hoverinfo: "skip" },
    { x, y: col("close"), name: "Close", mode: "lines", line: { color: THEME.blue, width: 1.8 } },
    { x, y: col("sma_short"), name: "SMA 20", mode: "lines", line: { color: THEME.buy, width: 1 } },
    { x, y: col("sma_long"), name: "SMA 50", mode: "lines", line: { color: THEME.hold, width: 1 } },
  ];
  Plotly.react(el, traces, darkLayout(), PLOT_CONFIG);
}

function drawEquityChart(data) {
  const el = document.getElementById("equity-chart");
  el.hidden = false;
  if (typeof Plotly === "undefined") return plotUnavailable(el);

  const curve = data.equity_curve || [];
  if (!curve.length) { el.hidden = true; return; }

  const x = curve.map((p) => p.date);
  const y = curve.map((p) => toNum(p.equity));
  const start = toNum(data.initial_cash);
  const layout = darkLayout({ margin: { l: 60, r: 12, t: 10, b: 36 } });
  if (start !== null) {
    layout.shapes = [{
      type: "line", xref: "paper", x0: 0, x1: 1, y0: start, y1: start,
      line: { color: THEME.text, width: 1, dash: "dot" },
    }];
  }
  const trace = {
    x, y, name: "Portfolio value", mode: "lines",
    line: { color: THEME.blue, width: 1.8 }, fill: "tozeroy",
    fillcolor: "rgba(96,165,250,0.08)",
  };
  Plotly.react(el, [trace], layout, PLOT_CONFIG);
}

// --------------------------------------------------------------------------
// Backtest (button-triggered)
// --------------------------------------------------------------------------
async function runBacktest() {
  if (!state.ticker) return;
  const body = document.getElementById("backtest-body");
  const eq = document.getElementById("equity-chart");
  eq.hidden = true; eq.innerHTML = "";
  body.innerHTML = `<p class="muted">Running simulated backtest...</p>`;
  try {
    const d = await getJSON(API.backtest(state.ticker));
    if (!d.ok) { body.innerHTML = `<p class="bt-message">${d.message || "Backtest unavailable."}</p>`; return; }

    const verdict = d.beat_buy_and_hold
      ? `<span class="bt-verdict win">Beat buy &amp; hold</span>`
      : `<span class="bt-verdict lose">Underperformed buy &amp; hold</span>`;
    body.innerHTML = `
      <div class="bt-summary">
        <div class="bt-metric"><span class="lbl">Strategy return</span>
          <span class="val ${signClass(d.total_return_pct)}">${fmtPctVal(d.total_return_pct)}</span></div>
        <div class="bt-metric"><span class="lbl">Buy &amp; hold</span>
          <span class="val ${signClass(d.buy_and_hold_return_pct)}">${fmtPctVal(d.buy_and_hold_return_pct)}</span></div>
        <div class="bt-metric"><span class="lbl">Final value</span>
          <span class="val">${fmtMoney(d.final_equity)}</span></div>
        <div class="bt-metric"><span class="lbl">Trades</span><span class="val">${fmtNum(d.num_trades, 0)}</span></div>
        <div class="bt-metric"><span class="lbl">Win rate</span><span class="val">${fmtNum(d.win_rate_pct, 1)}%</span></div>
        <div class="bt-metric"><span class="lbl">Max drawdown</span><span class="val neg">${fmtNum(d.max_drawdown_pct, 1)}%</span></div>
      </div>
      ${verdict}
      <p class="bt-note">${d.disclaimer || ""} Window ${d.start_date || "?"} to ${d.end_date || "?"} (${fmtNum(d.trading_days, 0)} trading days).</p>`;
    drawEquityChart(d);
  } catch (err) {
    showError(body, err);
  }
}

// --------------------------------------------------------------------------
// Wiring
// --------------------------------------------------------------------------
async function init() {
  document.getElementById("refresh").addEventListener("click", loadSignals);
  document.getElementById("detail-close").addEventListener("click", closeDetail);
  document.getElementById("run-backtest").addEventListener("click", runBacktest);

  document.querySelectorAll("#filters .filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.filter = btn.dataset.filter;
      document.querySelectorAll("#filters .filter-btn")
        .forEach((b) => b.classList.toggle("active", b === btn));
      renderCards();
    });
  });

  document.querySelectorAll("#timeframe .tf-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.period = btn.dataset.period;
      document.querySelectorAll("#timeframe .tf-btn")
        .forEach((b) => b.classList.toggle("active", b === btn));
      loadChartOnly();  // re-pull just the chart, not the whole panel
    });
  });

  try {
    const wl = await getJSON(API.watchlist);
    state.quickList = wl.quick_list || [];
    state.sectors = wl.sectors || [];
    state.watchlist = wl.watchlist || {};
  } catch (err) {
    showError(document.getElementById("signals-status"), err);
  }
  renderTabs();
  await loadSignals();
}

document.addEventListener("DOMContentLoaded", init);

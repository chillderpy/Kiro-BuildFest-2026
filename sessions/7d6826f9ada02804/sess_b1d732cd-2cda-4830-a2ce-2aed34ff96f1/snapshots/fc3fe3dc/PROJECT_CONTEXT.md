# Project Context - Stock Signal Dashboard

## Purpose
Personal, research-only stock-signal dashboard. Pulls NASDAQ data and
computes buy/hold/sell signals from technical indicators.

## Hard Constraints
- NEVER places trades / NEVER connects to a broker or trading API
- Read-only market data + local analysis only; personal research/learning
- Flask dev server is local/no-auth - do not expose to a network as-is

## Tech Stack
- Flask + flask-cors (web framework, JSON API + dashboard page)
- yahooquery (Yahoo Finance data - price history + fundamentals, native batch)
- ta (technical indicators) + pandas
- Chart.js (CDN, client-side price chart)
- Pinned exact dependency versions

## App / API (app.py)
- GET /                     dashboard page (client-rendered SPA)
- GET /api/watchlist        watchlist + quick list + sectors
- GET /api/signals          all tickers, batched, sorted strongest first (|score|)
- GET /api/ticker/<t>       full breakdown + OHLCV/indicator series for charting
                            ?period=1mo|3mo|6mo|1y|2y (default 6mo)
- Chart warmup: fetches a larger window (CHART_FETCH_PERIOD) so SMA-50 etc. are
  populated, then trims to CHART_PERIOD_DAYS before returning
- CORS enabled; API errors -> clean JSON + status (ApiError 4xx, generic 500),
  real errors logged server-side via json_endpoint wrapper
- No auth: local-only, do not expose to the internet

## File Structure
- app.py              Flask app (JSON API + dashboard page)
- config.py           settings + watchlist (source of truth)
- data_fetcher.py     Yahoo data pull (single + batch, cached)
- analysis.py         ta indicators + [-1,+1] scoring (technicals + fundamentals)
- backtester.py       simulated strategy backtest (module; not currently routed)
- requirements.txt    pinned versions
- templates/          dashboard.html (SPA)
- static/             style.css, dashboard.js
- tests/              unit + integration tests
- cache/              on-disk JSON cache (gitignored, market data only)

## Indicator Settings (config.py)
- SMA: 20, 50 | EMA: 12, 26 | RSI: 14, bands 70/30
- MACD: 12/26/9 | Bollinger: 20, 2 std
- Weights (sum=1.0): MACD 0.25, SMA 0.15, EMA 0.15, RSI 0.10, Bollinger 0.10,
  P/E 0.125, earnings_growth 0.125  (technicals 0.75 + fundamentals 0.25)
- Scoring -1..+1: BUY >= +0.30, SELL <= -0.30, HOLD otherwise
- Each sub-score in [-1,+1]; missing/NaN -> neutral 0; confidence = share of
  active indicators agreeing with the composite direction
- Fundamentals: P/E (cheap +1 at 10, expensive -1 at 40), earnings growth
  (+/-1 at +/-20%)
- Data: period 6mo, interval 1d

## Watchlist (by sector)
- tech: AAPL, MSFT, GOOGL, META
- semiconductors: NVDA, AMD
- finance: JPM, GS
- energy: XOM, CVX
- defence: LMT, RTX
- quick list (active): NVDA, AAPL, MSFT

## Data Layer (data_fetcher.py)
- yahooquery: price history (.history) + fundamentals (.get_modules), single + batch
- Batch = one network call (space-joined symbols); results split per symbol
- Columns normalized to Open/High/Low/Close/Volume; DatetimeIndex (tz-stripped)
- Rate limit: ~2s gap between live calls (skipped on cache hit)
- Disk cache (JSON): prices TTL ~15 min, company info TTL ~60 min
- Per-ticker failures return empty/safe default, never raise up
- No secrets/keys hardcoded anywhere

## Signal Flow
config.py -> data_fetcher.py -> analysis.py -> BUY/HOLD/SELL -> app.py
                                     analysis.py -> backtester.py -> app.py

## Task Breakdown (from approved plan)
1. Seed project context + config.py
2. Pinned requirements + venv
3. data_fetcher.py
4. analysis.py - indicators
5. analysis.py - weighted scoring + labels
6. backtester.py
7. app.py + templates + static
8. End-to-end wiring + safety note

## Current Phase
Execution

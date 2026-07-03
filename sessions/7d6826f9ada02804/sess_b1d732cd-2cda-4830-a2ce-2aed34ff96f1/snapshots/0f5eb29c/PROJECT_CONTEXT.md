# Project Context - Stock Signal Dashboard

## Purpose
Personal, research-only stock-signal dashboard. Pulls NASDAQ data and
computes buy/hold/sell signals from technical indicators.

## Hard Constraints
- NEVER places trades / NEVER connects to a broker or trading API
- Read-only market data + local analysis only; personal research/learning
- Flask dev server is local/no-auth - do not expose to a network as-is

## Tech Stack
- Flask (web framework)
- yahooquery (Yahoo Finance data - price history + fundamentals, native batch)
- ta (technical indicators) + pandas
- Pinned exact dependency versions

## File Structure
- app.py              Flask app (routes + views)
- config.py           settings + watchlist (source of truth)
- data_fetcher.py     Yahoo data pull (single + batch, cached)
- analysis.py         ta indicators + [-1,+1] scoring (technicals + fundamentals)
- backtester.py       simulated strategy backtest
- requirements.txt    pinned versions
- templates/          HTML
- static/             CSS/JS
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

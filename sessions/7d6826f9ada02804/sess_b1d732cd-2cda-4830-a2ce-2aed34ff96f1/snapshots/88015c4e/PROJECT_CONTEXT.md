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
- yfinance (Yahoo Finance data)
- pandas (indicator math)
- Pinned exact dependency versions

## File Structure
- app.py              Flask app (routes + views)
- config.py           settings + watchlist (source of truth)
- data_fetcher.py     Yahoo data pull (single + batch, cached)
- analysis.py         indicators + weighted scoring
- backtester.py       simulated strategy backtest
- requirements.txt    pinned versions
- templates/          HTML
- static/             CSS/JS
- tests/              unit + integration tests
- cache/              on-disk JSON cache (gitignored, market data only)

## Indicator Settings (config.py)
- SMA: 20, 50 | EMA: 12, 26 | RSI: 14, bands 70/30
- MACD: 12/26/9 | Bollinger: 20, 2 std
- Weights (sum=1.0): MACD 0.30, SMA 0.20, EMA 0.20, RSI 0.15, Bollinger 0.15
- Scoring 0-100: BUY >= 65, SELL <= 35, HOLD otherwise
- Data: period 6mo, interval 1d

## Watchlist (by sector)
- tech: AAPL, MSFT, GOOGL, META
- semiconductors: NVDA, AMD
- finance: JPM, GS
- energy: XOM, CVX
- defence: LMT, RTX
- quick list (active): NVDA, AAPL, MSFT

## Data Layer (data_fetcher.py)
- yfinance OHLCV, single + batch functions
- Columns normalized to Open/High/Low/Close/Volume; DatetimeIndex
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

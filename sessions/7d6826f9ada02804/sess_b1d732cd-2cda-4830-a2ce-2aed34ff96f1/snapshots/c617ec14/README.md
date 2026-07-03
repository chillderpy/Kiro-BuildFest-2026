# Stock Signal Dashboard

A personal, self-hosted dashboard that pulls historical price data and
fundamentals for a watchlist of stocks, blends a handful of well-known
technical and fundamental indicators into a single **BUY / HOLD / SELL**
signal, and lets you chart each stock and run a simulated backtest of the
strategy. It runs locally on your own machine.

---

> ## ⚠️ Disclaimer — read this first
>
> **This is an educational / personal-research tool. It is NOT financial
> advice.** The signals, scores, and backtests are simplistic, may be wrong,
> and are not a recommendation to buy or sell anything. There are deliberately
> **no trading features** — it never places orders and never connects to a
> broker. Markets are risky; past (and simulated) performance does not predict
> future results. **Do your own homework and consult a licensed professional
> before making any investment decision.**
>
> There is also **no authentication** — run it locally, do not expose it to
> the internet.

---

## Why

I wanted a single place to glance at a few stocks I care about and see a
transparent, tunable signal — one where I can look at the breakdown and
understand *why* it says buy or sell, rather than a black box. Every weight and
cutoff lives in `config.py`, and the per-indicator contributions are shown in
the UI.

## What it does

- Fetches daily OHLCV price history and company fundamentals (via
  [`yahooquery`](https://github.com/dpguthrie/yahooquery)), cached to disk so it
  doesn't hammer the data source.
- Computes technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands) with the
  [`ta`](https://github.com/bukosabino/ta) library, plus two fundamental factors
  (P/E and earnings growth).
- Scores each stock from **-1 (bearish) to +1 (bullish)** and maps that to a
  BUY / HOLD / SELL label with a **confidence** measure.
- Serves a dark, single-page dashboard: filterable signal cards, a detail panel
  with a Plotly price chart (SMAs + Bollinger Bands overlaid), the indicator
  breakdown, fundamentals, and a **backtest** of the strategy over the past year.
- Includes a separate **Research** tab holding a static academic study on
  semiconductor stocks (clearly labelled as fixed, historical study data — not
  live and not advice).

## Watchlist

Defined in `config.py` (`WATCHLIST`), grouped by sector:

| Sector          | Tickers                        |
| --------------- | ------------------------------ |
| tech            | AAPL, MSFT, GOOGL, META        |
| semiconductors  | NVDA, AMD, QCOM, INTC, MU       |
| finance         | JPM, GS                        |
| energy          | XOM, CVX                       |
| defence         | LMT, RTX                       |

The **quick list** (`QUICK_LIST`) is a small active set shown first so the app
doesn't fetch everything on the very first run: **NVDA, AAPL, MSFT**.

## Quick start

Requires Python 3.13 (earlier 3.x likely works, but the pinned dependencies
were resolved against 3.13).

```bash
# 1. From the project folder, create and activate a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# 2. Install the pinned dependencies
pip install -r requirements.txt

# 3. Run the app
python app.py
```

Then open **http://localhost:5000** in your browser.

> The chart library (Plotly) loads from a CDN, so the page needs internet access
> when it first loads. Price/fundamentals data also needs internet (it's fetched
> live from Yahoo, then cached).

## How it works

Each indicator produces a sub-score in `[-1, +1]` (0 = neutral, and any missing
or NaN data is treated as neutral so nothing crashes). The sub-scores are
combined with the weights below into one composite score, still in `[-1, +1]`.

### Indicator weights

Weights are trend-leaning; technicals carry 75% and fundamentals 25%
(they sum to 1.0). Set in `config.py` → `WEIGHTS`:

| Factor            | Weight | What it looks at                                            |
| ----------------- | ------ | ----------------------------------------------------------- |
| MACD              | 0.25   | MACD line vs. its signal line, and vs. zero                 |
| SMA               | 0.15   | Price vs. SMA-20 / SMA-50, and SMA-20 vs. SMA-50 (trend)    |
| EMA               | 0.15   | Price vs. EMA-12 / EMA-26, and EMA-12 vs. EMA-26 (trend)    |
| RSI               | 0.10   | Mean reversion — oversold is bullish, overbought bearish    |
| Bollinger Bands   | 0.10   | Mean reversion via %B — near lower band bullish, upper bearish |
| P/E               | 0.125  | Cheaper is more bullish (≤10 → +1, ≥40 → −1)                 |
| Earnings growth   | 0.125  | Symmetric around 0 (±20% → ±1)                              |

Indicator periods (also in `config.py`): SMA 20/50, EMA 12/26, RSI 14 with
70/30 bands, MACD 12/26/9, Bollinger 20 / 2σ.

### Signal cutoffs

The composite score maps to a label (`config.py` → `SIGNAL_BUY` / `SIGNAL_SELL`):

| Composite score      | Signal |
| -------------------- | ------ |
| `>= +0.15`           | BUY    |
| `-0.15 … +0.15`      | HOLD   |
| `<= -0.15`           | SELL   |

**Confidence** is the share of the *active* (non-neutral) indicators that agree
with the overall direction — so you can see not just the call but how unanimous
the evidence behind it is.

## Backtesting

Open a stock's detail panel and click **Run backtest** (or call
`GET /api/backtest/<ticker>`). It runs a **strict walk-forward simulation** over
roughly the past year:

- **No look-ahead.** Warmup history is fetched separately from the test window,
  and every day's decision uses only data available up to that day. It bails out
  cleanly with a message if there isn't enough data.
- **Strategy:** long-only, all-in on a BUY signal, all-out on a SELL signal
  (backtests use the technical signals only, since fundamentals aren't available
  historically).
- **Reports:** total return, buy-and-hold return, whether it beat buy-and-hold,
  number of trades, win rate, and worst drawdown — plus a portfolio-value chart.

It's a **simulation for research only** — it shows how the strategy *would have*
done on past data, not a prediction or a promise.

## File layout

```
.
├── app.py            Flask app: dashboard page + JSON API
├── config.py         All settings: watchlist, weights, cutoffs, cache/tuning
├── data_fetcher.py   yahooquery data access (single + batch), disk cache, throttling
├── analysis.py       Indicators (ta) + weighted -1..+1 scoring, labels, confidence
├── backtester.py     Walk-forward, no-look-ahead strategy simulation
├── requirements.txt  Pinned dependency versions
├── templates/
│   └── index.html    Single-page dashboard
├── static/
│   ├── style.css     Dark theme (CSS variables)
│   └── dashboard.js  Frontend logic + Plotly charts (plain JS, no framework)
├── tests/            pytest unit + integration tests
├── conftest.py       Test path setup
├── pytest.ini        pytest config
└── smoke_test.py     End-to-end smoke check against the real stack
```

### API endpoints

| Endpoint                        | Returns                                             |
| ------------------------------- | --------------------------------------------------- |
| `GET /`                         | The dashboard page                                  |
| `GET /api/watchlist`            | Watchlist, quick list, sectors                      |
| `GET /api/signals`              | Signals for every watchlist ticker (strongest first)|
| `GET /api/ticker/<t>?period=`   | Full breakdown + price/indicator series for charting (`period` = 1mo\|3mo\|6mo\|1y\|2y) |
| `GET /api/backtest/<t>`         | Simulated 1-year backtest results                   |
| `GET /api/research`             | Static semiconductor study data (separate from live signals) |

## Customizing

Everything tunable lives in **`config.py`**:

- **Tickers** — edit `WATCHLIST` (grouped by sector) and `QUICK_LIST`.
- **Indicator periods** — `SMA_PERIODS`, `EMA_PERIODS`, `RSI_PERIOD`,
  `RSI_OVERBOUGHT` / `RSI_OVERSOLD`, `MACD`, `BOLLINGER`.
- **Weights & cutoffs** — `WEIGHTS` (must sum to 1.0), `SIGNAL_BUY`,
  `SIGNAL_SELL`.
- **Fundamentals scoring** — `PE_CHEAP`, `PE_EXPENSIVE`, `EARNINGS_GROWTH_STRONG`.
- **Backtest** — `BACKTEST_FETCH_PERIOD`, `BACKTEST_TEST_DAYS`,
  `BACKTEST_MIN_TRADING_DAYS`, `BACKTEST_INITIAL_CASH`.
- **Data fetching / caching** — `REQUEST_DELAY_SECONDS` (gap between live calls),
  `PRICE_CACHE_TTL`, `INFO_CACHE_TTL`, `CACHE_DIR`.

## Running the tests

```bash
pytest
```

(Unit + integration tests mock the network, so they run offline. `smoke_test.py`
exercises the full stack against live data if you want an end-to-end check.)

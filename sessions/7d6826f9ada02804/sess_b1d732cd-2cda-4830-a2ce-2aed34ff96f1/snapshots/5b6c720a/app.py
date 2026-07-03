"""app.py - Flask app for the personal stock signal dashboard.

Serves a single dashboard page plus a small JSON API:

    GET /                      -> the dashboard page (HTML)
    GET /api/watchlist         -> the configured watchlist + quick list
    GET /api/signals           -> signals for every watchlist ticker, strongest
                                  first (batched fetch)
    GET /api/ticker/<ticker>   -> full score breakdown + price/indicator series
                                  for charting; ?period=1mo|3mo|6mo|1y|2y

CORS is enabled so a separate frontend (or a browser fetch from file://) can
talk to the API.

SAFETY / SCOPE
--------------
Research and learning only. Signals are derived from public market data; this
app NEVER places trades and NEVER connects to a broker. There is NO login or
authentication - it is meant to run locally on your own machine, not to be
exposed on the open internet.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from functools import wraps

import pandas as pd
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

import analysis
import backtester
import config
import data_fetcher

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "Research and learning only. Signals are informational, not financial "
    "advice. This tool never places trades or connects to a broker, and has no "
    "login - run it locally, do not expose it to the internet."
)


# --------------------------------------------------------------------------- #
# Error handling
# --------------------------------------------------------------------------- #
class ApiError(Exception):
    """Raised inside API routes to return a clean JSON error + status code."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def json_endpoint(fn):
    """Wrap an API view so failures become clean JSON, not a stack trace.

    Expected client errors (bad params, unknown ticker) are raised as ApiError
    and returned with their status. Anything unexpected is logged in full on
    the server and returned as a generic 500 so no internals leak to the client.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ApiError as exc:
            logger.warning("API error %s on %s: %s", exc.status, fn.__name__, exc.message)
            return jsonify({"error": exc.message}), exc.status
        except Exception:  # noqa: BLE001 - deliberately catch-all at the boundary
            logger.exception("Unhandled error in %s", fn.__name__)
            return jsonify({"error": "internal server error"}), 500

    return wrapper


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _all_tickers() -> list[str]:
    return [t for group in config.WATCHLIST.values() for t in group]


def _sector_for(ticker: str) -> str:
    for sector, tickers in config.WATCHLIST.items():
        if ticker in tickers:
            return sector
    return "unknown"


def build_signals(tickers: list[str]) -> list[dict]:
    """Fetch prices + fundamentals for `tickers` and return signal rows."""
    prices = data_fetcher.get_price_history_batch(tickers)
    fundamentals = data_fetcher.get_fundamentals_batch(tickers)
    rows = []
    for ticker in tickers:
        frame = prices.get(ticker)
        fund = fundamentals.get(ticker) or {}
        result = analysis.analyze(frame, fund) if frame is not None else {
            "score": None, "label": "N/A", "confidence": 0.0,
            "breakdown": {}, "indicators": {}}
        indicators = result.get("indicators") or {}
        rows.append({
            "ticker": ticker,
            "sector": _sector_for(ticker),
            "label": result["label"],
            "score": result["score"],
            "confidence": result.get("confidence", 0.0),
            "close": indicators.get("Close"),
            "rsi": indicators.get("RSI"),
            "breakdown": result.get("breakdown", {}),
        })
    return rows


def _signal_strength(row: dict) -> tuple:
    """Sort key: strongest-conviction signals first (largest |score|).

    Rows with no score sink to the bottom; ties broken by confidence. Sorting
    by magnitude means strong BUYs and strong SELLs both float up, while HOLDs
    near zero settle at the bottom.
    """
    score = row.get("score")
    has_score = score is not None
    magnitude = abs(score) if has_score else -1.0
    return (has_score, magnitude, row.get("confidence", 0.0))


def _clean_number(value):
    """Return a JSON-safe float, or None for missing/NaN."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN -> None


CHART_FIELDS = {
    "Open": "open", "High": "high", "Low": "low", "Close": "close",
    "Volume": "volume", "SMA_short": "sma_short", "SMA_long": "sma_long",
    "EMA_short": "ema_short", "EMA_long": "ema_long", "RSI": "rsi",
    "MACD": "macd", "MACD_signal": "macd_signal", "MACD_hist": "macd_hist",
    "BB_upper": "bb_upper", "BB_middle": "bb_middle", "BB_lower": "bb_lower",
}


def _chart_series(enriched: pd.DataFrame) -> list[dict]:
    """Turn an enriched (indicator) frame into a list of JSON-safe rows."""
    rows = []
    for ts, row in enriched.iterrows():
        point = {"date": pd.Timestamp(ts).strftime("%Y-%m-%d")}
        for col, key in CHART_FIELDS.items():
            point[key] = _clean_number(row.get(col))
        rows.append(point)
    return rows


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #
def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)  # allow cross-origin API access for a separate frontend

    @app.route("/")
    def dashboard():
        return render_template(
            "dashboard.html",
            disclaimer=DISCLAIMER,
            periods=config.CHART_PERIODS,
            default_period=config.DEFAULT_CHART_PERIOD,
        )

    @app.route("/api/watchlist")
    @json_endpoint
    def api_watchlist():
        return jsonify({
            "watchlist": config.WATCHLIST,
            "quick_list": config.QUICK_LIST,
            "sectors": list(config.WATCHLIST.keys()),
        })

    @app.route("/api/signals")
    @json_endpoint
    def api_signals():
        rows = build_signals(_all_tickers())
        rows.sort(key=_signal_strength, reverse=True)
        return jsonify({
            "signals": rows,
            "count": len(rows),
            "buy_threshold": config.SIGNAL_BUY,
            "sell_threshold": config.SIGNAL_SELL,
            "weights": config.WEIGHTS,
        })

    @app.route("/api/ticker/<ticker>")
    @json_endpoint
    def api_ticker(ticker):
        ticker = ticker.upper()
        if ticker not in _all_tickers():
            raise ApiError(404, f"unknown ticker: {ticker}")

        period = request.args.get("period", config.DEFAULT_CHART_PERIOD)
        if period not in config.CHART_PERIODS:
            raise ApiError(
                400,
                f"invalid period '{period}'; choose one of "
                f"{', '.join(config.CHART_PERIODS)}",
            )

        # Fetch a larger window so indicators have warmup, then trim to the
        # requested window before returning.
        fetch_period = config.CHART_FETCH_PERIOD[period]
        frame = data_fetcher.get_price_history(ticker, period=fetch_period)
        fund = data_fetcher.get_fundamentals(ticker)

        # Score off the full frame (latest values are unaffected by trimming).
        result = analysis.analyze(frame, fund)

        enriched = analysis.compute_indicators(frame)
        chart = []
        if len(enriched) > 0:
            cutoff = enriched.index.max() - timedelta(days=config.CHART_PERIOD_DAYS[period])
            visible = enriched[enriched.index >= cutoff]
            chart = _chart_series(visible)

        return jsonify({
            "ticker": ticker,
            "sector": _sector_for(ticker),
            "period": period,
            "label": result["label"],
            "score": result["score"],
            "confidence": result["confidence"],
            "breakdown": result["breakdown"],
            "weights": config.WEIGHTS,
            "fundamentals": _fundamentals_summary(fund),
            "chart": chart,
            "has_data": len(chart) > 0,
        })

    @app.route("/api/backtest/<ticker>")
    @json_endpoint
    def api_backtest(ticker):
        ticker = ticker.upper()
        if ticker not in _all_tickers():
            raise ApiError(404, f"unknown ticker: {ticker}")

        result = backtester.run_for_ticker(ticker)
        result["ticker"] = ticker
        # A valid ticker that simply lacks enough history is not a client error;
        # return 200 with ok=False and a message the UI can show.
        return jsonify(result)

    return app


def _fundamentals_summary(fund: dict) -> dict:
    """A small, display-friendly subset of the raw fundamentals."""
    fund = fund or {}
    keys = ["shortName", "longName", "sector", "industry", "trailingPE",
            "forwardPE", "earningsGrowth", "earningsQuarterlyGrowth",
            "marketCap", "dividendYield"]
    return {k: fund.get(k) for k in keys if fund.get(k) is not None}


app = create_app()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Local, unauthenticated dev server - do not expose to a network.
    app.run(host="127.0.0.1", port=5000, debug=True)

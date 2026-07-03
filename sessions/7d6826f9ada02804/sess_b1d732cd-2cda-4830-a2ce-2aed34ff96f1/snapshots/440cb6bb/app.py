"""app.py - Flask dashboard for the personal stock signal tool.

Renders weighted BUY/HOLD/SELL signals for the active quick list, allows
drilling into a full sector on demand, and shows a simulated backtest per
ticker.

SAFETY / SCOPE
--------------
Research and learning only. This app displays signals derived from public
market data. It NEVER places trades and NEVER connects to a broker. The
built-in Flask server is a local, unauthenticated dev server - do not expose
it to a network as-is.
"""

from __future__ import annotations

from flask import Flask, abort, render_template

import analysis
import backtester
import config
import data_fetcher

DISCLAIMER = (
    "Research and learning only. Signals are informational, not financial "
    "advice. This tool never places trades or connects to a broker."
)


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


def create_app() -> Flask:
    app = Flask(__name__)

    @app.context_processor
    def inject_globals():
        return {
            "disclaimer": DISCLAIMER,
            "sectors": list(config.WATCHLIST.keys()),
            "buy_threshold": config.SIGNAL_BUY,
            "sell_threshold": config.SIGNAL_SELL,
        }

    @app.route("/")
    def index():
        signals = build_signals(config.QUICK_LIST)
        return render_template(
            "index.html",
            title="Quick List Signals",
            signals=signals,
            quick_list=config.QUICK_LIST,
        )

    @app.route("/sector/<sector>")
    def sector_view(sector):
        tickers = config.WATCHLIST.get(sector)
        if not tickers:
            abort(404)
        signals = build_signals(tickers)
        return render_template(
            "sector.html",
            title=f"Sector: {sector}",
            sector=sector,
            signals=signals,
        )

    @app.route("/backtest/<ticker>")
    def backtest_view(ticker):
        ticker = ticker.upper()
        all_tickers = [t for group in config.WATCHLIST.values() for t in group]
        if ticker not in all_tickers:
            abort(404)
        frame = data_fetcher.get_price_history(ticker)
        fund = data_fetcher.get_fundamentals(ticker)
        stats = backtester.backtest(frame)
        current = analysis.analyze(frame, fund)
        return render_template(
            "backtest.html",
            title=f"Backtest: {ticker}",
            ticker=ticker,
            stats=stats,
            current=current,
            has_data=frame is not None and len(frame) > 0,
        )

    return app


app = create_app()


if __name__ == "__main__":
    # Local, unauthenticated dev server - do not expose to a network.
    app.run(host="127.0.0.1", port=5000, debug=True)

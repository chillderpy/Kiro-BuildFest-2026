"""Integration tests for the Flask JSON API using mocked data."""

import numpy as np
import pandas as pd
import pytest

import config
import data_fetcher
import app as app_module


def _frame(n=400, start=50.0):
    """A long daily frame ending today, so warmup + trimming can be tested."""
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n, freq="D")
    close = pd.Series(np.linspace(start, start + n * 0.2, n), index=idx, dtype="float64")
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 0.5,
            "Low": close - 0.5,
            "Close": close,
            "Volume": pd.Series([1000] * n, index=idx),
        }
    )


@pytest.fixture
def client(monkeypatch):
    def fake_batch(tickers, period=None, interval=None):
        return {t: _frame() for t in tickers}

    def fake_single(ticker, period=None, interval=None):
        return _frame()

    def fake_funds_batch(tickers):
        return {t: {"trailingPE": 20.0, "earningsGrowth": 0.1,
                    "shortName": t + " Inc", "sector": "Tech"} for t in tickers}

    def fake_funds(ticker):
        return {"trailingPE": 20.0, "earningsGrowth": 0.1,
                "shortName": ticker + " Inc", "sector": "Tech"}

    monkeypatch.setattr(data_fetcher, "get_price_history_batch", fake_batch)
    monkeypatch.setattr(data_fetcher, "get_price_history", fake_single)
    monkeypatch.setattr(data_fetcher, "get_fundamentals_batch", fake_funds_batch)
    monkeypatch.setattr(data_fetcher, "get_fundamentals", fake_funds)

    application = app_module.create_app()
    application.config.update(TESTING=True)
    return application.test_client()


# --------------------------------------------------------------------------- #
# Dashboard page
# --------------------------------------------------------------------------- #
def test_dashboard_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Stock Signal Dashboard" in body
    assert "research" in body.lower()  # disclaimer present


# --------------------------------------------------------------------------- #
# Watchlist
# --------------------------------------------------------------------------- #
def test_watchlist(client):
    data = client.get("/api/watchlist").get_json()
    assert data["quick_list"] == config.QUICK_LIST
    assert "tech" in data["watchlist"]
    assert set(data["sectors"]) == set(config.WATCHLIST.keys())


# --------------------------------------------------------------------------- #
# Research (static study data)
# --------------------------------------------------------------------------- #
def test_research_endpoint(client):
    data = client.get("/api/research").get_json()
    assert data["is_static"] is True
    assert data["disclaimer"]
    assert len(data["stocks"]) == 5
    tickers = {s["ticker"] for s in data["stocks"]}
    assert tickers == {"AMD", "NVDA", "QCOM", "INTC", "MU"}
    # Each stock carries the fields the research cards display.
    for s in data["stocks"]:
        for key in ["hist_avg_return_pct", "predicted_return_pct", "gross_margin_pct",
                    "mean_esg", "rnd_musd", "model2_r2", "strongest_predictor",
                    "recommendation", "highlights"]:
            assert key in s
    assert data["decision_rules"] and data["limitations"] and data["key_takeaways"]


def test_research_tickers_are_live_analyzable(client):
    # The "jump to live analysis" link needs each research ticker in the
    # live watchlist so /api/ticker accepts it.
    all_tickers = [t for g in config.WATCHLIST.values() for t in g]
    for ticker in ["AMD", "NVDA", "QCOM", "INTC", "MU"]:
        assert ticker in all_tickers
        assert client.get(f"/api/ticker/{ticker}").status_code == 200


# --------------------------------------------------------------------------- #
# Signals
# --------------------------------------------------------------------------- #
def test_signals_returns_all_tickers(client):
    data = client.get("/api/signals").get_json()
    all_tickers = [t for g in config.WATCHLIST.values() for t in g]
    returned = [row["ticker"] for row in data["signals"]]
    assert set(returned) == set(all_tickers)
    assert data["count"] == len(all_tickers)


def test_signals_sorted_strongest_first(client):
    signals = client.get("/api/signals").get_json()["signals"]
    strengths = [abs(r["score"]) if r["score"] is not None else -1 for r in signals]
    assert strengths == sorted(strengths, reverse=True)


def test_signals_cors_header(client):
    resp = client.get("/api/signals", headers={"Origin": "http://example.com"})
    assert resp.headers.get("Access-Control-Allow-Origin") is not None


# --------------------------------------------------------------------------- #
# Ticker detail
# --------------------------------------------------------------------------- #
def test_ticker_detail_ok(client):
    data = client.get("/api/ticker/NVDA").get_json()
    assert data["ticker"] == "NVDA"
    assert data["period"] == config.DEFAULT_CHART_PERIOD
    assert data["label"] in ("BUY", "HOLD", "SELL", "N/A")
    assert set(data["breakdown"].keys()) == set(config.WEIGHTS.keys())
    assert len(data["chart"]) > 0
    # Chart rows carry price + indicator fields.
    assert "close" in data["chart"][0]
    assert "sma_long" in data["chart"][0]


def test_ticker_detail_lowercase_symbol(client):
    data = client.get("/api/ticker/nvda").get_json()
    assert data["ticker"] == "NVDA"


def test_ticker_period_trims_and_keeps_warmup(client):
    short = client.get("/api/ticker/NVDA?period=1mo").get_json()
    long_ = client.get("/api/ticker/NVDA?period=6mo").get_json()
    # Shorter window returns fewer points...
    assert len(short["chart"]) < len(long_["chart"])
    # ...but warmup means SMA-50 is already populated at the visible start.
    assert short["chart"][0]["sma_long"] is not None


def test_ticker_unknown_404(client):
    resp = client.get("/api/ticker/ZZZZ")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_ticker_bad_period_400(client):
    resp = client.get("/api/ticker/NVDA?period=10y")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_backtest_route_ok(client):
    data = client.get("/api/backtest/NVDA").get_json()
    assert data["ticker"] == "NVDA"
    assert data["ok"] is True
    for key in ["total_return_pct", "buy_and_hold_return_pct",
                "beat_buy_and_hold", "num_trades", "win_rate_pct",
                "max_drawdown_pct", "disclaimer", "equity_curve"]:
        assert key in data


def test_backtest_unknown_ticker_404(client):
    resp = client.get("/api/backtest/ZZZZ")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_backtest_insufficient_data_bails(client, monkeypatch):
    # Valid ticker but no history -> 200 with ok=False and a message.
    monkeypatch.setattr(data_fetcher, "get_price_history",
                        lambda ticker, period=None, interval=None: __import__("pandas").DataFrame())
    data = client.get("/api/backtest/NVDA").get_json()
    assert data["ok"] is False
    assert data["message"]


def test_unhandled_error_returns_json_500(client, monkeypatch):
    # Force an unexpected failure inside the signals route.
    def boom(tickers):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(app_module.data_fetcher, "get_price_history_batch",
                        lambda tickers: (_ for _ in ()).throw(RuntimeError("kaboom")))
    resp = client.get("/api/signals")
    assert resp.status_code == 500
    assert resp.get_json()["error"] == "internal server error"

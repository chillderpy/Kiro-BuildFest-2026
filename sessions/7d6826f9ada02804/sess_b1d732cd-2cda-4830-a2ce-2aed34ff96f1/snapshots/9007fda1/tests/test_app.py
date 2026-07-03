"""Integration tests for the Flask app using the test client + mocked data."""

import numpy as np
import pandas as pd
import pytest

import config
import data_fetcher
import app as app_module


def _frame(n=80, start=50.0, step=1.0):
    idx = pd.date_range("2023-06-01", periods=n, freq="D")
    close = pd.Series(np.arange(start, start + n * step, step)[:n], index=idx,
                      dtype="float64")
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
    # Mock the data layer so no live network calls happen in tests.
    def fake_batch(tickers, period=None, interval=None):
        return {t: _frame() for t in tickers}

    def fake_single(ticker, period=None, interval=None):
        return _frame()

    monkeypatch.setattr(data_fetcher, "get_price_history_batch", fake_batch)
    monkeypatch.setattr(data_fetcher, "get_price_history", fake_single)

    application = app_module.create_app()
    application.config.update(TESTING=True)
    return application.test_client()


def test_index_returns_200_and_shows_tickers(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    for ticker in config.QUICK_LIST:
        assert ticker in body
    # Each quick-list ticker should carry a signal label.
    assert any(lbl in body for lbl in ["BUY", "HOLD", "SELL"])


def test_index_shows_disclaimer(client):
    body = client.get("/").get_data(as_text=True)
    assert "never places trades" in body.lower() or "research" in body.lower()


def test_sector_view_ok(client):
    resp = client.get("/sector/tech")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    for ticker in config.WATCHLIST["tech"]:
        assert ticker in body


def test_unknown_sector_404(client):
    assert client.get("/sector/nonexistent").status_code == 404


def test_backtest_view_ok(client):
    resp = client.get("/backtest/NVDA")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "NVDA" in body
    assert "simulated" in body.lower()


def test_backtest_unknown_ticker_404(client):
    assert client.get("/backtest/ZZZZ").status_code == 404

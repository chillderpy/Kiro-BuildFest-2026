"""Unit tests for data_fetcher - no live network, yfinance is mocked."""

import time

import pandas as pd
import pytest

import config
import data_fetcher as df_mod


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path, monkeypatch):
    """Point the cache at a temp dir and reset the throttle clock per test."""
    monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(df_mod, "_last_live_call", 0.0)
    yield


def _sample_raw():
    """A lowercase-column frame like a raw provider response."""
    idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    return pd.DataFrame(
        {
            "open": [10.0, 11.0, 12.0],
            "high": [10.5, 11.5, 12.5],
            "low": [9.5, 10.5, 11.5],
            "close": [10.2, 11.2, 12.2],
            "volume": [1000, 1100, 1200],
            "dividends": [0.0, 0.0, 0.0],  # extra column, should be dropped
        },
        index=idx,
    )


# --------------------------------------------------------------------------- #
# Normalization
# --------------------------------------------------------------------------- #
def test_normalize_history_columns_and_index():
    out = df_mod._normalize_history(_sample_raw())
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert isinstance(out.index, pd.DatetimeIndex)
    assert len(out) == 3
    assert out["Close"].iloc[-1] == 12.2


def test_normalize_history_empty():
    out = df_mod._normalize_history(pd.DataFrame())
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(out) == 0


# --------------------------------------------------------------------------- #
# Cache helpers
# --------------------------------------------------------------------------- #
def test_cache_round_trip():
    df_mod._write_cache("k1", {"hello": "world"})
    assert df_mod._read_cache("k1", ttl=1000) == {"hello": "world"}


def test_cache_expiry():
    df_mod._write_cache("k2", {"a": 1})
    # ttl of 0 -> anything is already expired
    assert df_mod._read_cache("k2", ttl=0) is None


def test_cache_miss():
    assert df_mod._read_cache("does-not-exist", ttl=1000) is None


# --------------------------------------------------------------------------- #
# Throttle
# --------------------------------------------------------------------------- #
def test_throttle_enforces_gap(monkeypatch):
    monkeypatch.setattr(config, "REQUEST_DELAY_SECONDS", 0.2)
    df_mod._last_live_call = 0.0
    df_mod._throttle()  # first call sets the clock
    start = time.time()
    df_mod._throttle()  # second call must wait ~0.2s
    assert time.time() - start >= 0.18


# --------------------------------------------------------------------------- #
# Single-ticker price
# --------------------------------------------------------------------------- #
def test_get_price_history_success(monkeypatch):
    calls = {"n": 0}

    def fake(ticker, period, interval):
        calls["n"] += 1
        return _sample_raw()

    monkeypatch.setattr(df_mod, "_fetch_history_yf", fake)
    monkeypatch.setattr(config, "REQUEST_DELAY_SECONDS", 0.0)

    out = df_mod.get_price_history("NVDA")
    assert len(out) == 3
    assert calls["n"] == 1

    # Second call should hit the cache and NOT call the network again.
    out2 = df_mod.get_price_history("NVDA")
    assert len(out2) == 3
    assert calls["n"] == 1


def test_get_price_history_failure_returns_empty(monkeypatch):
    def boom(ticker, period, interval):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(df_mod, "_fetch_history_yf", boom)
    monkeypatch.setattr(config, "REQUEST_DELAY_SECONDS", 0.0)

    out = df_mod.get_price_history("BADX")
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(out) == 0


# --------------------------------------------------------------------------- #
# Batch price
# --------------------------------------------------------------------------- #
def test_get_price_history_batch_with_one_bad_symbol(monkeypatch):
    good = _sample_raw()
    good.columns = ["Open", "High", "Low", "Close", "Volume", "Dividends"]

    # Build a MultiIndex (symbol, field) frame with only GOOD present.
    multi = pd.concat({"GOOD": good}, axis=1)

    def fake_batch(tickers, period, interval):
        return multi

    monkeypatch.setattr(df_mod, "_fetch_history_batch_yf", fake_batch)
    monkeypatch.setattr(config, "REQUEST_DELAY_SECONDS", 0.0)

    out = df_mod.get_price_history_batch(["GOOD", "BAD"])
    assert set(out.keys()) == {"GOOD", "BAD"}
    assert len(out["GOOD"]) == 3
    assert len(out["BAD"]) == 0


# --------------------------------------------------------------------------- #
# Fundamentals
# --------------------------------------------------------------------------- #
def test_get_fundamentals_success(monkeypatch):
    def fake_info(ticker):
        return {"shortName": "NVIDIA", "sector": "Technology",
                "marketCap": 1234567, "nested": {"drop": "me"}}

    monkeypatch.setattr(df_mod, "_fetch_info_yf", fake_info)
    monkeypatch.setattr(config, "REQUEST_DELAY_SECONDS", 0.0)

    info = df_mod.get_fundamentals("NVDA")
    assert info["shortName"] == "NVIDIA"
    assert info["sector"] == "Technology"
    assert "nested" not in info  # non-primitive dropped


def test_get_fundamentals_failure_returns_empty(monkeypatch):
    def boom(ticker):
        raise RuntimeError("network down")

    monkeypatch.setattr(df_mod, "_fetch_info_yf", boom)
    monkeypatch.setattr(config, "REQUEST_DELAY_SECONDS", 0.0)

    assert df_mod.get_fundamentals("BADX") == {}

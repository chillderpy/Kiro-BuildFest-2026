"""Unit tests for data_fetcher - no live network, yahooquery is mocked."""

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
    monkeypatch.setattr(config, "REQUEST_DELAY_SECONDS", 0.0)
    yield


def _symbol_history(symbol, rows=3):
    """A yahooquery-style MultiIndex (symbol, date) frame with lowercase cols."""
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])[:rows]
    idx = pd.MultiIndex.from_product([[symbol], dates], names=["symbol", "date"])
    return pd.DataFrame(
        {
            "open": [10.0, 11.0, 12.0][:rows],
            "high": [10.5, 11.5, 12.5][:rows],
            "low": [9.5, 10.5, 11.5][:rows],
            "close": [10.2, 11.2, 12.2][:rows],
            "volume": [1000, 1100, 1200][:rows],
            "adjclose": [10.2, 11.2, 12.2][:rows],  # extra col, dropped
            "dividends": [0.0, 0.0, 0.0][:rows],     # extra col, dropped
        },
        index=idx,
    )


def _multi_history(*symbols):
    return pd.concat([_symbol_history(s) for s in symbols])


# --------------------------------------------------------------------------- #
# Normalization
# --------------------------------------------------------------------------- #
def test_normalize_history_columns_and_index():
    single = _symbol_history("NVDA").xs("NVDA", level=0)
    out = df_mod._normalize_history(single)
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert isinstance(out.index, pd.DatetimeIndex)
    assert len(out) == 3
    assert out["Close"].iloc[-1] == 12.2


def test_normalize_history_empty():
    out = df_mod._normalize_history(pd.DataFrame())
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(out) == 0


def test_extract_symbol_frame_multiindex():
    raw = _multi_history("NVDA", "AAPL")
    sub = df_mod._extract_symbol_frame(raw, "AAPL")
    assert len(sub) == 3
    missing = df_mod._extract_symbol_frame(raw, "TSLA")
    assert len(missing) == 0


# --------------------------------------------------------------------------- #
# Cache helpers
# --------------------------------------------------------------------------- #
def test_cache_round_trip():
    df_mod._write_cache("k1", {"hello": "world"})
    assert df_mod._read_cache("k1", ttl=1000) == {"hello": "world"}


def test_cache_expiry():
    df_mod._write_cache("k2", {"a": 1})
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

    def fake(symbols, period, interval):
        calls["n"] += 1
        return _symbol_history("NVDA")

    monkeypatch.setattr(df_mod, "_fetch_history_yq", fake)

    out = df_mod.get_price_history("NVDA")
    assert len(out) == 3
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert calls["n"] == 1

    # Second call should hit the cache and NOT call the network again.
    out2 = df_mod.get_price_history("NVDA")
    assert len(out2) == 3
    assert calls["n"] == 1


def test_get_price_history_failure_returns_empty(monkeypatch):
    def boom(symbols, period, interval):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(df_mod, "_fetch_history_yq", boom)

    out = df_mod.get_price_history("BADX")
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(out) == 0


def test_get_price_history_dict_error_returns_empty(monkeypatch):
    # yahooquery sometimes returns a dict/str instead of a frame on error.
    def bad_shape(symbols, period, interval):
        return {"BADX": "No data found"}

    monkeypatch.setattr(df_mod, "_fetch_history_yq", bad_shape)
    assert len(df_mod.get_price_history("BADX")) == 0


# --------------------------------------------------------------------------- #
# Batch price
# --------------------------------------------------------------------------- #
def test_get_price_history_batch_with_one_bad_symbol(monkeypatch):
    # Only GOOD is present in the returned MultiIndex frame.
    def fake_batch(symbols, period, interval):
        return _symbol_history("GOOD")

    monkeypatch.setattr(df_mod, "_fetch_history_yq", fake_batch)

    out = df_mod.get_price_history_batch(["GOOD", "BAD"])
    assert set(out.keys()) == {"GOOD", "BAD"}
    assert len(out["GOOD"]) == 3
    assert len(out["BAD"]) == 0


# --------------------------------------------------------------------------- #
# Fundamentals
# --------------------------------------------------------------------------- #
def test_get_fundamentals_success(monkeypatch):
    def fake_info(symbols):
        return {"NVDA": {"shortName": "NVIDIA", "sector": "Technology",
                         "marketCap": 1234567, "nested": {"drop": "me"}}}

    monkeypatch.setattr(df_mod, "_fetch_fundamentals_yq", fake_info)

    info = df_mod.get_fundamentals("NVDA")
    assert info["shortName"] == "NVIDIA"
    assert info["sector"] == "Technology"
    assert "nested" not in info  # non-primitive dropped


def test_get_fundamentals_failure_returns_empty(monkeypatch):
    def boom(symbols):
        raise RuntimeError("network down")

    monkeypatch.setattr(df_mod, "_fetch_fundamentals_yq", boom)
    assert df_mod.get_fundamentals("BADX") == {}


def test_get_fundamentals_batch_one_bad(monkeypatch):
    def fake_info(symbols):
        # GOOD resolves; BAD came back as an error string -> {} after merge.
        return {"GOOD": {"shortName": "Good Co"}, "BAD": {}}

    monkeypatch.setattr(df_mod, "_fetch_fundamentals_yq", fake_info)

    out = df_mod.get_fundamentals_batch(["GOOD", "BAD"])
    assert out["GOOD"]["shortName"] == "Good Co"
    assert out["BAD"] == {}

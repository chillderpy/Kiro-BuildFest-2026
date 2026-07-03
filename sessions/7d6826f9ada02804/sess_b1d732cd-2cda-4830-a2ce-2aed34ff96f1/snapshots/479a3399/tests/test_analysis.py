"""Unit tests for analysis - indicators on known series + scoring cases."""

import numpy as np
import pandas as pd
import pytest

import config
import analysis


def _frame(closes):
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    close = pd.Series(closes, index=idx, dtype="float64")
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": pd.Series([1000] * len(closes), index=idx),
        }
    )


# --------------------------------------------------------------------------- #
# Task 4: indicators
# --------------------------------------------------------------------------- #
def test_sma_known_values():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = analysis.sma(s, 3)
    # First two are NaN, then rolling means 2, 3, 4.
    assert pd.isna(out.iloc[0]) and pd.isna(out.iloc[1])
    assert out.iloc[2] == 2.0
    assert out.iloc[3] == 3.0
    assert out.iloc[4] == 4.0


def test_ema_first_value_equals_price():
    s = pd.Series([10.0, 11.0, 12.0, 13.0])
    out = analysis.ema(s, 2)
    # With adjust=False the first EMA value equals the first observation.
    assert out.iloc[0] == 10.0
    assert out.iloc[-1] > out.iloc[0]


def test_rsi_all_gains_is_100():
    s = pd.Series(np.arange(1, 30, dtype="float64"))  # strictly increasing
    out = analysis.rsi(s, config.RSI_PERIOD)
    assert out.dropna().iloc[-1] == pytest.approx(100.0)


def test_rsi_all_losses_is_0():
    s = pd.Series(np.arange(30, 1, -1, dtype="float64"))  # strictly decreasing
    out = analysis.rsi(s, config.RSI_PERIOD)
    assert out.dropna().iloc[-1] == pytest.approx(0.0)


def test_macd_constant_series_is_zero():
    s = pd.Series([50.0] * 40)
    line, signal, hist = analysis.macd(s, 12, 26, 9)
    assert line.iloc[-1] == pytest.approx(0.0)
    assert hist.iloc[-1] == pytest.approx(0.0)


def test_bollinger_bands_order():
    s = pd.Series(np.linspace(10, 20, 30))
    upper, mid, lower = analysis.bollinger(s, 20, 2)
    assert lower.iloc[-1] < mid.iloc[-1] < upper.iloc[-1]


def test_compute_indicators_columns():
    df = _frame(list(np.linspace(10, 30, 60)))
    out = analysis.compute_indicators(df)
    for col in ["SMA_short", "SMA_long", "EMA_short", "EMA_long", "RSI",
                "MACD", "MACD_signal", "MACD_hist", "BB_upper", "BB_middle",
                "BB_lower"]:
        assert col in out.columns


def test_compute_indicators_empty():
    assert len(analysis.compute_indicators(pd.DataFrame())) == 0


# --------------------------------------------------------------------------- #
# Task 5: scoring + labels
# --------------------------------------------------------------------------- #
def test_label_thresholds():
    assert analysis.label_for_score(config.SCORE_BUY) == "BUY"
    assert analysis.label_for_score(90) == "BUY"
    assert analysis.label_for_score(config.SCORE_SELL) == "SELL"
    assert analysis.label_for_score(10) == "SELL"
    assert analysis.label_for_score(50) == "HOLD"


def test_clear_buy_case():
    # Uptrend, momentum positive, oversold RSI, price near lower band.
    ind = {
        "Close": 110, "SMA_short": 105, "SMA_long": 100,
        "EMA_short": 106, "EMA_long": 101,
        "RSI": 25, "MACD": 2.0, "MACD_signal": 1.0,
        "BB_upper": 120, "BB_lower": 108,
    }
    res = analysis.score_signal(ind)
    assert res["label"] == "BUY"
    assert res["score"] >= config.SCORE_BUY


def test_clear_sell_case():
    # Downtrend, momentum negative, overbought RSI, price near upper band.
    ind = {
        "Close": 90, "SMA_short": 95, "SMA_long": 100,
        "EMA_short": 94, "EMA_long": 99,
        "RSI": 80, "MACD": -2.0, "MACD_signal": -1.0,
        "BB_upper": 92, "BB_lower": 80,
    }
    res = analysis.score_signal(ind)
    assert res["label"] == "SELL"
    assert res["score"] <= config.SCORE_SELL


def test_hold_case():
    # Mixed / neutral signals around the middle.
    ind = {
        "Close": 100, "SMA_short": 100, "SMA_long": 100,
        "EMA_short": 100, "EMA_long": 100,
        "RSI": 50, "MACD": 0.0, "MACD_signal": 0.0,
        "BB_upper": 110, "BB_lower": 90,
    }
    res = analysis.score_signal(ind)
    assert res["label"] == "HOLD"


def test_missing_indicators_are_neutral():
    res = analysis.score_signal({})
    # All sub-scores neutral -> ~50 -> HOLD.
    assert res["label"] == "HOLD"
    assert 35 < res["score"] < 65


def test_analyze_empty_frame():
    res = analysis.analyze(pd.DataFrame())
    assert res["label"] == "N/A"

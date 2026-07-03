"""Unit tests for analysis - ta-based indicators + [-1,+1] scoring."""

import math

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
# Indicators (ta)
# --------------------------------------------------------------------------- #
def test_compute_indicators_columns():
    df = _frame(list(np.linspace(10, 40, 80)))
    out = analysis.compute_indicators(df)
    for col in ["SMA_short", "SMA_long", "EMA_short", "EMA_long", "RSI",
                "MACD", "MACD_signal", "MACD_hist", "BB_upper", "BB_middle",
                "BB_lower"]:
        assert col in out.columns


def test_compute_indicators_empty():
    assert len(analysis.compute_indicators(pd.DataFrame())) == 0


def test_latest_indicators_uptrend_is_bullish_trend():
    df = _frame(list(np.linspace(10, 50, 80)))
    ind = analysis.latest_indicators(df)
    assert ind["SMA_short"] > ind["SMA_long"]
    assert analysis.score_sma(ind) > 0
    assert analysis.score_ema(ind) > 0


# --------------------------------------------------------------------------- #
# Clamp + neutral-on-missing
# --------------------------------------------------------------------------- #
def test_clamp_bounds():
    assert analysis.clamp(5) == 1.0
    assert analysis.clamp(-5) == -1.0
    assert analysis.clamp(0.4) == 0.4


def test_missing_indicators_are_neutral():
    empty = {}
    for scorer in analysis.TECHNICAL_SCORERS.values():
        assert scorer(empty) == 0.0
    # None values also neutral, not a crash.
    noneful = {k: None for k in analysis.INDICATOR_KEYS}
    for scorer in analysis.TECHNICAL_SCORERS.values():
        assert scorer(noneful) == 0.0


def test_nan_is_neutral():
    ind = {"RSI": float("nan"), "Close": float("nan")}
    assert analysis.score_rsi(ind) == 0.0
    assert analysis.score_bollinger(ind) == 0.0


# --------------------------------------------------------------------------- #
# Individual technical scores in [-1, +1]
# --------------------------------------------------------------------------- #
def test_score_sma_directions():
    up = {"Close": 110, "SMA_short": 105, "SMA_long": 100}
    down = {"Close": 90, "SMA_short": 95, "SMA_long": 100}
    flat = {"Close": 100, "SMA_short": 100, "SMA_long": 100}
    assert analysis.score_sma(up) == 1.0
    assert analysis.score_sma(down) == -1.0
    assert analysis.score_sma(flat) == 0.0


def test_score_macd_directions():
    assert analysis.score_macd({"MACD": 2, "MACD_signal": 1}) == 1.0
    assert analysis.score_macd({"MACD": -2, "MACD_signal": -1}) == -1.0
    assert analysis.score_macd({"MACD": 0, "MACD_signal": 0}) == 0.0


def test_score_rsi_mean_reversion():
    assert analysis.score_rsi({"RSI": config.RSI_OVERSOLD}) == pytest.approx(1.0)
    assert analysis.score_rsi({"RSI": config.RSI_OVERBOUGHT}) == pytest.approx(-1.0)
    assert analysis.score_rsi({"RSI": 50}) == pytest.approx(0.0)


def test_score_bollinger_bands():
    # At lower band -> +1, upper band -> -1, middle -> 0.
    assert analysis.score_bollinger(
        {"Close": 100, "BB_upper": 120, "BB_lower": 100}) == pytest.approx(1.0)
    assert analysis.score_bollinger(
        {"Close": 120, "BB_upper": 120, "BB_lower": 100}) == pytest.approx(-1.0)
    assert analysis.score_bollinger(
        {"Close": 110, "BB_upper": 120, "BB_lower": 100}) == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# Fundamental scores
# --------------------------------------------------------------------------- #
def test_score_pe():
    assert analysis.score_pe({"trailingPE": config.PE_CHEAP}) == pytest.approx(1.0)
    assert analysis.score_pe({"trailingPE": config.PE_EXPENSIVE}) == pytest.approx(-1.0)
    # negative / missing / zero -> neutral
    assert analysis.score_pe({"trailingPE": -5}) == 0.0
    assert analysis.score_pe({}) == 0.0
    # forwardPE is used as a fallback
    assert analysis.score_pe({"forwardPE": config.PE_CHEAP}) == pytest.approx(1.0)


def test_score_earnings_growth():
    strong = config.EARNINGS_GROWTH_STRONG
    assert analysis.score_earnings_growth({"earningsGrowth": strong}) == pytest.approx(1.0)
    assert analysis.score_earnings_growth({"earningsGrowth": -strong}) == pytest.approx(-1.0)
    assert analysis.score_earnings_growth({}) == 0.0
    # huge growth clamps to +1
    assert analysis.score_earnings_growth({"earningsGrowth": 5.0}) == 1.0


# --------------------------------------------------------------------------- #
# Composite score + label + confidence
# --------------------------------------------------------------------------- #
def test_label_thresholds():
    assert analysis.label_for_score(config.SIGNAL_BUY) == "BUY"
    assert analysis.label_for_score(0.9) == "BUY"
    assert analysis.label_for_score(config.SIGNAL_SELL) == "SELL"
    assert analysis.label_for_score(-0.9) == "SELL"
    assert analysis.label_for_score(0.0) == "HOLD"


def test_clear_buy_case():
    ind = {"Close": 110, "SMA_short": 105, "SMA_long": 100,
           "EMA_short": 106, "EMA_long": 101, "RSI": 25,
           "MACD": 2.0, "MACD_signal": 1.0, "BB_upper": 120, "BB_lower": 108}
    fund = {"trailingPE": 8, "earningsGrowth": 0.3}
    res = analysis.score(ind, fund)
    assert res["label"] == "BUY"
    assert res["score"] > config.SIGNAL_BUY
    assert res["confidence"] == 1.0


def test_clear_sell_case():
    ind = {"Close": 90, "SMA_short": 95, "SMA_long": 100,
           "EMA_short": 94, "EMA_long": 99, "RSI": 80,
           "MACD": -2.0, "MACD_signal": -1.0, "BB_upper": 92, "BB_lower": 80}
    fund = {"trailingPE": 60, "earningsGrowth": -0.3}
    res = analysis.score(ind, fund)
    assert res["label"] == "SELL"
    assert res["score"] < config.SIGNAL_SELL
    assert res["confidence"] == 1.0


def test_neutral_case_is_hold():
    res = analysis.score({}, {})
    assert res["label"] == "HOLD"
    assert res["score"] == pytest.approx(0.0)
    assert res["confidence"] == 0.0


def test_confidence_reflects_disagreement():
    # Trend indicators bullish (3), mean-reversion bearish (2); net bullish.
    ind = {"Close": 110, "SMA_short": 105, "SMA_long": 100,
           "EMA_short": 106, "EMA_long": 101, "RSI": 75,
           "MACD": 2.0, "MACD_signal": 1.0, "BB_upper": 111, "BB_lower": 100}
    res = analysis.score(ind)  # no fundamentals -> pe/earnings neutral (excluded)
    assert res["label"] == "BUY"
    # 3 of 5 active technicals agree with the bullish direction.
    assert res["confidence"] == pytest.approx(0.6)


def test_score_always_in_range():
    ind = {"Close": 1e6, "SMA_short": 1, "SMA_long": 1, "EMA_short": 1,
           "EMA_long": 1, "RSI": 0, "MACD": 1e9, "MACD_signal": -1e9,
           "BB_upper": 2, "BB_lower": 1}
    fund = {"trailingPE": 1, "earningsGrowth": 99}
    res = analysis.score(ind, fund)
    assert -1.0 <= res["score"] <= 1.0
    for v in res["breakdown"].values():
        assert -1.0 <= v <= 1.0


def test_breakdown_has_all_weighted_components():
    res = analysis.score({}, {})
    assert set(res["breakdown"].keys()) == set(config.WEIGHTS.keys())


def test_analyze_empty_frame():
    res = analysis.analyze(pd.DataFrame())
    assert res["label"] == "N/A"
    assert res["confidence"] == 0.0

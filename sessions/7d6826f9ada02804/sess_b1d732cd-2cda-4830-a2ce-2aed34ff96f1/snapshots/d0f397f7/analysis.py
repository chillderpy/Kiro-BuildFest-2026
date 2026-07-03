"""analysis.py - technical indicators and weighted buy/hold/sell scoring.

All indicators are computed with pure pandas from an OHLCV frame (as produced
by data_fetcher). Indicator parameters, weights, and score thresholds come from
config.py, so behaviour is tuned there without touching this logic.

Scoring model
-------------
Each indicator emits a sub-score in [0, 100] where 0 = strong sell, 50 =
neutral, 100 = strong buy. Sub-scores are combined with config.WEIGHTS (which
sum to 1.0) into a final 0-100 score, then mapped to a label:

    score >= config.SCORE_BUY   -> "BUY"
    score <= config.SCORE_SELL  -> "SELL"
    otherwise                   -> "HOLD"

Research/learning only. These are not trade recommendations.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import config


# --------------------------------------------------------------------------- #
# Indicators (each returns a pandas Series aligned to the input index)
# --------------------------------------------------------------------------- #
def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int) -> pd.Series:
    """Relative Strength Index using Wilder's smoothing."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    out = 100.0 - (100.0 / (1.0 + rs))
    # When there are no losses at all, RSI is defined as 100.
    out = out.where(avg_loss != 0, 100.0)
    # When there are no gains at all, RSI is 0.
    out = out.where(~((avg_gain == 0) & (avg_loss != 0)), 0.0)
    return out


def macd(series: pd.Series, fast: int, slow: int, signal: int):
    """MACD line, signal line, and histogram."""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def bollinger(series: pd.Series, period: int, std_dev: float):
    """Bollinger upper, middle (SMA), and lower bands."""
    middle = series.rolling(window=period, min_periods=period).mean()
    std = series.rolling(window=period, min_periods=period).std(ddof=0)
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return upper, middle, lower


# --------------------------------------------------------------------------- #
# Aggregate indicator computation
# --------------------------------------------------------------------------- #
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Return the input frame with indicator columns appended.

    Expects a normalized OHLCV frame with a 'Close' column. Returns a copy;
    an empty input yields an empty frame.
    """
    if df is None or len(df) == 0 or "Close" not in df.columns:
        return pd.DataFrame()

    out = df.copy()
    close = out["Close"]

    out["SMA_short"] = sma(close, config.SMA_PERIODS["short"])
    out["SMA_long"] = sma(close, config.SMA_PERIODS["long"])
    out["EMA_short"] = ema(close, config.EMA_PERIODS["short"])
    out["EMA_long"] = ema(close, config.EMA_PERIODS["long"])
    out["RSI"] = rsi(close, config.RSI_PERIOD)

    macd_line, signal_line, hist = macd(
        close, config.MACD["fast"], config.MACD["slow"], config.MACD["signal"]
    )
    out["MACD"] = macd_line
    out["MACD_signal"] = signal_line
    out["MACD_hist"] = hist

    upper, mid, lower = bollinger(
        close, config.BOLLINGER["period"], config.BOLLINGER["std_dev"]
    )
    out["BB_upper"] = upper
    out["BB_middle"] = mid
    out["BB_lower"] = lower
    return out


def latest_indicators(df: pd.DataFrame) -> dict:
    """Return the most recent row of indicator values as a plain dict."""
    enriched = compute_indicators(df)
    if len(enriched) == 0:
        return {}
    row = enriched.iloc[-1]
    keys = [
        "Close", "SMA_short", "SMA_long", "EMA_short", "EMA_long", "RSI",
        "MACD", "MACD_signal", "MACD_hist", "BB_upper", "BB_middle", "BB_lower",
    ]
    result = {}
    for k in keys:
        val = row.get(k)
        result[k] = None if val is None or pd.isna(val) else float(val)
    return result


# --------------------------------------------------------------------------- #
# Per-indicator sub-scores (0 = sell, 50 = neutral, 100 = buy)
# --------------------------------------------------------------------------- #
def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _score_ma(close, short, long_) -> float:
    """Trend score from a short/long moving-average pair vs price."""
    if close is None or short is None or long_ is None:
        return 50.0
    conditions = [close > short, close > long_, short > long_]
    return 100.0 * sum(bool(c) for c in conditions) / len(conditions)


def score_sma(ind: dict) -> float:
    return _score_ma(ind.get("Close"), ind.get("SMA_short"), ind.get("SMA_long"))


def score_ema(ind: dict) -> float:
    return _score_ma(ind.get("Close"), ind.get("EMA_short"), ind.get("EMA_long"))


def score_macd(ind: dict) -> float:
    """Momentum score: MACD above its signal and above zero are bullish."""
    line = ind.get("MACD")
    sig = ind.get("MACD_signal")
    if line is None or sig is None:
        return 50.0
    conditions = [line > sig, line > 0.0]
    return 100.0 * sum(bool(c) for c in conditions) / len(conditions)


def score_rsi(ind: dict) -> float:
    """Mean-reversion score: oversold -> buy (high), overbought -> sell (low)."""
    r = ind.get("RSI")
    if r is None:
        return 50.0
    ob = config.RSI_OVERBOUGHT
    os_ = config.RSI_OVERSOLD
    # Linear map: RSI==oversold -> 100, RSI==overbought -> 0.
    score = 100.0 * (ob - r) / (ob - os_)
    return _clamp(score)


def score_bollinger(ind: dict) -> float:
    """Mean-reversion score from %B: near lower band -> buy, upper band -> sell."""
    close = ind.get("Close")
    upper = ind.get("BB_upper")
    lower = ind.get("BB_lower")
    if close is None or upper is None or lower is None or upper == lower:
        return 50.0
    pct_b = (close - lower) / (upper - lower)
    return _clamp(100.0 * (1.0 - pct_b))


SUB_SCORERS = {
    "macd": score_macd,
    "sma": score_sma,
    "ema": score_ema,
    "rsi": score_rsi,
    "bollinger": score_bollinger,
}


# --------------------------------------------------------------------------- #
# Weighted score + label
# --------------------------------------------------------------------------- #
def label_for_score(score: float) -> str:
    if score >= config.SCORE_BUY:
        return "BUY"
    if score <= config.SCORE_SELL:
        return "SELL"
    return "HOLD"


def score_signal(ind: dict) -> dict:
    """Combine sub-scores via config.WEIGHTS into a 0-100 score + label.

    Returns a dict with the final score, label, and the per-indicator
    sub-score breakdown for transparency.
    """
    breakdown = {name: round(scorer(ind), 2) for name, scorer in SUB_SCORERS.items()}
    total = sum(config.WEIGHTS[name] * breakdown[name] for name in SUB_SCORERS)
    score = round(total, 2)
    return {
        "score": score,
        "label": label_for_score(score),
        "breakdown": breakdown,
    }


def analyze(df: pd.DataFrame) -> dict:
    """Full pipeline for one ticker: indicators -> latest values -> score."""
    ind = latest_indicators(df)
    if not ind:
        return {"score": None, "label": "N/A", "breakdown": {}, "indicators": {}}
    result = score_signal(ind)
    result["indicators"] = ind
    return result


# --------------------------------------------------------------------------- #
# Manual demo
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import data_fetcher

    prices = data_fetcher.get_price_history_batch(config.QUICK_LIST)
    for tkr, frame in prices.items():
        res = analyze(frame)
        print(f"{tkr}: score={res['score']} label={res['label']} "
              f"breakdown={res['breakdown']}")

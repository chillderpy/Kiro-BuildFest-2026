"""analysis.py - technical + fundamental scoring for buy/hold/sell signals.

Indicators are computed with the `ta` library using the periods in config.py.
Each indicator (and two fundamentals, P/E and earnings growth) is turned into a
sub-score in the range [-1, +1]:

    +1  strongly bullish
     0  neutral / no opinion (also used when data is missing or NaN)
    -1  strongly bearish

The sub-scores are blended with config.WEIGHTS (which sum to 1.0) into a single
composite score, still in [-1, +1], which maps to a label:

    score >= config.SIGNAL_BUY   -> "BUY"
    score <= config.SIGNAL_SELL  -> "SELL"
    otherwise                    -> "HOLD"

A "confidence" value (0..1) reports how much the active indicators agree with
the composite direction, so you can see not just *what* the call is but *how
unanimous* the evidence behind it is.

Design goals: readable and transparent - the per-indicator breakdown makes it
easy to see exactly why a signal is what it is. Missing/NaN data never crashes;
it is simply treated as neutral (0). Every score is clamped to [-1, +1].

Research/learning only. These are not trade recommendations.
"""

from __future__ import annotations

import math

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD, SMAIndicator
from ta.volatility import BollingerBands

import config


# --------------------------------------------------------------------------- #
# Small numeric helpers
# --------------------------------------------------------------------------- #
def clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    """Clamp x into [lo, hi]."""
    return max(lo, min(hi, x))


def _is_num(x) -> bool:
    """True if x is a real, non-NaN number."""
    return isinstance(x, (int, float)) and not (isinstance(x, float) and math.isnan(x))


def _num(x):
    """Return x as a float, or None if it is missing/NaN."""
    return float(x) if _is_num(x) else None


def _direction(a, b) -> int:
    """+1 if a>b, -1 if a<b, 0 if equal."""
    if a > b:
        return 1
    if a < b:
        return -1
    return 0


# --------------------------------------------------------------------------- #
# Indicators (via the `ta` library)
# --------------------------------------------------------------------------- #
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of `df` with indicator columns appended.

    Expects a normalized OHLCV frame with a 'Close' column. Warmup rows are
    left as NaN (the `ta` library does not backfill), which the scorers treat
    as neutral. An empty/invalid input yields an empty frame.
    """
    if df is None or len(df) == 0 or "Close" not in df.columns:
        return pd.DataFrame()

    out = df.copy()
    close = out["Close"].astype("float64")

    out["SMA_short"] = SMAIndicator(close, window=config.SMA_PERIODS["short"]).sma_indicator()
    out["SMA_long"] = SMAIndicator(close, window=config.SMA_PERIODS["long"]).sma_indicator()
    out["EMA_short"] = EMAIndicator(close, window=config.EMA_PERIODS["short"]).ema_indicator()
    out["EMA_long"] = EMAIndicator(close, window=config.EMA_PERIODS["long"]).ema_indicator()
    out["RSI"] = RSIIndicator(close, window=config.RSI_PERIOD).rsi()

    macd = MACD(
        close,
        window_fast=config.MACD["fast"],
        window_slow=config.MACD["slow"],
        window_sign=config.MACD["signal"],
    )
    out["MACD"] = macd.macd()
    out["MACD_signal"] = macd.macd_signal()
    out["MACD_hist"] = macd.macd_diff()

    bb = BollingerBands(
        close,
        window=config.BOLLINGER["period"],
        window_dev=config.BOLLINGER["std_dev"],
    )
    out["BB_upper"] = bb.bollinger_hband()
    out["BB_middle"] = bb.bollinger_mavg()
    out["BB_lower"] = bb.bollinger_lband()
    return out


INDICATOR_KEYS = [
    "Close", "SMA_short", "SMA_long", "EMA_short", "EMA_long", "RSI",
    "MACD", "MACD_signal", "MACD_hist", "BB_upper", "BB_middle", "BB_lower",
]


def latest_indicators(df: pd.DataFrame) -> dict:
    """Return the most recent row of indicator values as a plain dict.

    Values that are missing or NaN come back as None.
    """
    enriched = compute_indicators(df)
    if len(enriched) == 0:
        return {}
    row = enriched.iloc[-1]
    return {k: _num(row.get(k)) for k in INDICATOR_KEYS}


def row_to_indicators(row) -> dict:
    """Convert an enriched frame row (Series) into an indicator dict."""
    return {k: _num(row.get(k)) for k in INDICATOR_KEYS}


# --------------------------------------------------------------------------- #
# Technical sub-scores  (each returns a value in [-1, +1]; 0 = neutral)
# --------------------------------------------------------------------------- #
def _trend_score(close, short, long_) -> float:
    """Average of three trend votes: price vs short MA, price vs long MA,
    and short MA vs long MA. Bullish when price leads and short leads long."""
    if close is None or short is None or long_ is None:
        return 0.0
    votes = [_direction(close, short), _direction(close, long_),
             _direction(short, long_)]
    return clamp(sum(votes) / len(votes))


def score_sma(ind: dict) -> float:
    return _trend_score(ind.get("Close"), ind.get("SMA_short"), ind.get("SMA_long"))


def score_ema(ind: dict) -> float:
    return _trend_score(ind.get("Close"), ind.get("EMA_short"), ind.get("EMA_long"))


def score_macd(ind: dict) -> float:
    """Bullish when the MACD line is above its signal and above zero."""
    line = ind.get("MACD")
    sig = ind.get("MACD_signal")
    if line is None or sig is None:
        return 0.0
    votes = [_direction(line, sig), _direction(line, 0.0)]
    return clamp(sum(votes) / len(votes))


def score_rsi(ind: dict) -> float:
    """Mean-reversion: oversold is bullish, overbought is bearish.

    Maps RSI==oversold -> +1, RSI==overbought -> -1, midpoint -> 0.
    """
    r = ind.get("RSI")
    if r is None:
        return 0.0
    midpoint = (config.RSI_OVERBOUGHT + config.RSI_OVERSOLD) / 2.0
    half_range = (config.RSI_OVERBOUGHT - config.RSI_OVERSOLD) / 2.0
    if half_range == 0:
        return 0.0
    return clamp((midpoint - r) / half_range)


def score_bollinger(ind: dict) -> float:
    """Mean-reversion from %B: at/below lower band bullish, at/above upper bearish.

    %B = (close - lower) / (upper - lower); score = 1 - 2*%B so that
    lower band -> +1, middle -> 0, upper band -> -1.
    """
    close = ind.get("Close")
    upper = ind.get("BB_upper")
    lower = ind.get("BB_lower")
    if close is None or upper is None or lower is None or upper == lower:
        return 0.0
    pct_b = (close - lower) / (upper - lower)
    return clamp(1.0 - 2.0 * pct_b)


# --------------------------------------------------------------------------- #
# Fundamental sub-scores  (each returns a value in [-1, +1]; 0 = neutral)
# --------------------------------------------------------------------------- #
def _get_pe(fund: dict):
    for key in ("trailingPE", "forwardPE"):
        val = _num(fund.get(key))
        if val is not None:
            return val
    return None


def _get_earnings_growth(fund: dict):
    for key in ("earningsGrowth", "earningsQuarterlyGrowth"):
        val = _num(fund.get(key))
        if val is not None:
            return val
    return None


def score_pe(fund: dict) -> float:
    """Cheaper valuation is more bullish.

    P/E <= config.PE_CHEAP -> +1, P/E >= config.PE_EXPENSIVE -> -1, linear
    between. Missing or non-positive P/E (e.g. no/negative earnings) -> neutral.
    """
    pe = _get_pe(fund or {})
    if pe is None or pe <= 0:
        return 0.0
    span = config.PE_EXPENSIVE - config.PE_CHEAP
    if span == 0:
        return 0.0
    # 0 at PE_CHEAP, 1 at PE_EXPENSIVE -> map to +1..-1.
    frac = (pe - config.PE_CHEAP) / span
    return clamp(1.0 - 2.0 * frac)


def score_earnings_growth(fund: dict) -> float:
    """Positive earnings growth is bullish, symmetric around zero.

    growth >= +STRONG -> +1, growth <= -STRONG -> -1, linear between.
    Missing -> neutral.
    """
    growth = _get_earnings_growth(fund or {})
    if growth is None or config.EARNINGS_GROWTH_STRONG == 0:
        return 0.0
    return clamp(growth / config.EARNINGS_GROWTH_STRONG)


# --------------------------------------------------------------------------- #
# Score assembly
# --------------------------------------------------------------------------- #
TECHNICAL_SCORERS = {
    "macd": score_macd,
    "sma": score_sma,
    "ema": score_ema,
    "rsi": score_rsi,
    "bollinger": score_bollinger,
}

FUNDAMENTAL_SCORERS = {
    "pe": score_pe,
    "earnings_growth": score_earnings_growth,
}


def label_for_score(score: float) -> str:
    """Map a composite score in [-1, +1] to BUY / HOLD / SELL."""
    if score >= config.SIGNAL_BUY:
        return "BUY"
    if score <= config.SIGNAL_SELL:
        return "SELL"
    return "HOLD"


def _confidence(breakdown: dict, composite: float) -> float:
    """Fraction of active (non-neutral) sub-scores agreeing with the direction.

    Returns 0.0 when the composite is neutral or nothing is active.
    """
    active = [s for s in breakdown.values() if abs(s) > 1e-9]
    if not active or composite == 0:
        return 0.0
    bullish = composite > 0
    agree = sum(1 for s in active if (s > 0) == bullish)
    return round(agree / len(active), 3)


def score(indicators: dict, fundamentals: dict | None = None) -> dict:
    """Blend technical + fundamental sub-scores into a composite result.

    Returns a dict with:
      score       composite in [-1, +1] (None if there is nothing to score)
      label       BUY / HOLD / SELL
      confidence  0..1 agreement of active indicators with the direction
      breakdown   {name: sub-score} for every weighted component
    """
    fundamentals = fundamentals or {}

    breakdown = {}
    for name, scorer in TECHNICAL_SCORERS.items():
        breakdown[name] = round(scorer(indicators or {}), 4)
    for name, scorer in FUNDAMENTAL_SCORERS.items():
        breakdown[name] = round(scorer(fundamentals), 4)

    composite = clamp(sum(config.WEIGHTS[name] * breakdown[name]
                          for name in config.WEIGHTS))
    composite = round(composite, 4)

    return {
        "score": composite,
        "label": label_for_score(composite),
        "confidence": _confidence(breakdown, composite),
        "breakdown": breakdown,
    }


def analyze(df: pd.DataFrame, fundamentals: dict | None = None) -> dict:
    """Full pipeline for one ticker: indicators -> latest values -> composite.

    `fundamentals` is an optional company-info dict (as from data_fetcher); when
    omitted, the two fundamental sub-scores are simply neutral.
    """
    ind = latest_indicators(df)
    if not ind:
        return {"score": None, "label": "N/A", "confidence": 0.0,
                "breakdown": {}, "indicators": {}}
    result = score(ind, fundamentals)
    result["indicators"] = ind
    return result


# --------------------------------------------------------------------------- #
# Manual demo
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import data_fetcher

    prices = data_fetcher.get_price_history_batch(config.QUICK_LIST)
    funds = data_fetcher.get_fundamentals_batch(config.QUICK_LIST)
    for tkr, frame in prices.items():
        res = analyze(frame, funds.get(tkr))
        print(f"{tkr}: score={res['score']} label={res['label']} "
              f"confidence={res['confidence']}")
        print(f"    breakdown={res['breakdown']}")

"""data_fetcher.py - data access layer for the stock signal dashboard.

Pulls price history and fundamentals from Yahoo Finance via yfinance, for
single tickers and batches. Output is normalized (Open/High/Low/Close/Volume
with a DatetimeIndex), disk-cached as JSON with TTLs, politely rate-limited to
avoid 429s, and failure-isolated so one bad ticker never breaks a run.

Research/learning only. No trading, no broker integration, no secrets/keys.
"""

from __future__ import annotations

import json
import logging
import os
import time
from io import StringIO

import pandas as pd

import config

logger = logging.getLogger(__name__)

# Canonical OHLCV columns for normalized price frames.
OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

# Timestamp of the last live (network) call; used to enforce the delay.
_last_live_call = 0.0


# --------------------------------------------------------------------------- #
# Cache + throttle helpers
# --------------------------------------------------------------------------- #
def _cache_path(key: str) -> str:
    """Build the on-disk path CACHE_DIR/<key>.json for a cache key."""
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    safe_key = key.replace(os.sep, "_").replace("/", "_")
    return os.path.join(config.CACHE_DIR, f"{safe_key}.json")


def _read_cache(key: str, ttl: float):
    """Return cached ``data`` for key if present and younger than ttl, else None."""
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        age = time.time() - float(payload.get("ts", 0))
        if age > ttl:
            return None
        return payload.get("data")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("cache read failed for %s: %s", key, exc)
        return None


def _write_cache(key: str, data) -> None:
    """Store {"ts": epoch, "data": data} as JSON at the cache path for key."""
    path = _cache_path(key)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"ts": time.time(), "data": data}, fh)
    except (OSError, TypeError) as exc:
        logger.warning("cache write failed for %s: %s", key, exc)


def _throttle() -> None:
    """Sleep so at least REQUEST_DELAY_SECONDS pass between live calls."""
    global _last_live_call
    elapsed = time.time() - _last_live_call
    wait = config.REQUEST_DELAY_SECONDS - elapsed
    if wait > 0:
        time.sleep(wait)
    _last_live_call = time.time()


# --------------------------------------------------------------------------- #
# Normalization / (de)serialization
# --------------------------------------------------------------------------- #
def _normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    """Return a frame with title-case OHLCV columns and a DatetimeIndex.

    Missing OHLCV columns are added as NaN so downstream code can rely on the
    full set. Any extra columns (Dividends, Adj Close, ...) are dropped.
    """
    if df is None or len(df) == 0:
        return _empty_price_frame()

    out = df.copy()
    # Map any-case column names to the canonical title case.
    rename = {}
    for col in out.columns:
        key = str(col).strip().lower()
        for canon in OHLCV_COLUMNS:
            if key == canon.lower():
                rename[col] = canon
    out = out.rename(columns=rename)

    # Keep only the canonical columns, adding any that are missing.
    for canon in OHLCV_COLUMNS:
        if canon not in out.columns:
            out[canon] = pd.NA
    out = out[OHLCV_COLUMNS]

    # Ensure a proper DatetimeIndex.
    out.index = pd.to_datetime(out.index, errors="coerce", utc=False)
    out.index.name = "Date"
    out = out[~out.index.isna()]

    # Numeric dtypes.
    for canon in OHLCV_COLUMNS:
        out[canon] = pd.to_numeric(out[canon], errors="coerce")
    return out


def _empty_price_frame() -> pd.DataFrame:
    """An empty, correctly-shaped OHLCV frame with a DatetimeIndex."""
    idx = pd.DatetimeIndex([], name="Date")
    return pd.DataFrame({c: pd.Series(dtype="float64") for c in OHLCV_COLUMNS}, index=idx)


def _df_to_cacheable(df: pd.DataFrame) -> str:
    """Serialize a DataFrame to a JSON string (orient='split')."""
    return df.to_json(orient="split", date_format="iso")


def _df_from_cacheable(data: str) -> pd.DataFrame:
    """Reconstruct a normalized price frame from a cached JSON string."""
    try:
        df = pd.read_json(StringIO(data), orient="split")
    except ValueError:
        return _empty_price_frame()
    return _normalize_history(df)


# --------------------------------------------------------------------------- #
# Network wrappers (thin, so tests can monkeypatch these)
# --------------------------------------------------------------------------- #
def _fetch_history_yf(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """Raw single-ticker price history from yfinance."""
    import yfinance as yf

    return yf.Ticker(ticker).history(period=period, interval=interval)


def _fetch_history_batch_yf(tickers, period: str, interval: str) -> pd.DataFrame:
    """Raw multi-ticker price history from yfinance (grouped by ticker)."""
    import yfinance as yf

    return yf.download(
        tickers=" ".join(tickers),
        period=period,
        interval=interval,
        group_by="ticker",
        progress=False,
        auto_adjust=True,
        threads=False,
    )


def _fetch_info_yf(ticker: str) -> dict:
    """Raw fundamentals/company info dict from yfinance."""
    import yfinance as yf

    return dict(yf.Ticker(ticker).info)


# --------------------------------------------------------------------------- #
# Prices
# --------------------------------------------------------------------------- #
def get_price_history(ticker: str, period: str | None = None,
                      interval: str | None = None) -> pd.DataFrame:
    """Return normalized OHLCV history for a single ticker.

    Uses the disk cache first (skipping the network + delay on a hit). On any
    failure returns an empty, correctly-shaped frame - never raises.
    """
    period = period or config.DATA_PERIOD
    interval = interval or config.DATA_INTERVAL
    key = f"price_{ticker}_{period}_{interval}"

    cached = _read_cache(key, config.PRICE_CACHE_TTL)
    if cached is not None:
        return _df_from_cacheable(cached)

    try:
        _throttle()
        raw = _fetch_history_yf(ticker, period, interval)
        df = _normalize_history(raw)
        if len(df) == 0:
            logger.warning("no price data returned for %s", ticker)
            return _empty_price_frame()
        _write_cache(key, _df_to_cacheable(df))
        return df
    except Exception as exc:  # isolate any provider/parse failure
        logger.warning("price fetch failed for %s: %s", ticker, exc)
        return _empty_price_frame()


def get_price_history_batch(tickers, period: str | None = None,
                            interval: str | None = None) -> dict:
    """Return {ticker: normalized OHLCV frame} for a list of tickers.

    Cached tickers are served from disk; the rest are fetched in one batched
    call. Every requested ticker is present in the result (empty frame on
    failure), so callers can rely on complete keys.
    """
    period = period or config.DATA_PERIOD
    interval = interval or config.DATA_INTERVAL

    result: dict[str, pd.DataFrame] = {}
    to_fetch: list[str] = []

    for ticker in tickers:
        key = f"price_{ticker}_{period}_{interval}"
        cached = _read_cache(key, config.PRICE_CACHE_TTL)
        if cached is not None:
            result[ticker] = _df_from_cacheable(cached)
        else:
            to_fetch.append(ticker)

    if not to_fetch:
        return result

    try:
        _throttle()
        raw = _fetch_history_batch_yf(to_fetch, period, interval)
    except Exception as exc:
        logger.warning("batch price fetch failed for %s: %s", to_fetch, exc)
        raw = None

    for ticker in to_fetch:
        try:
            sub = _extract_symbol_frame(raw, ticker, single=len(to_fetch) == 1)
            df = _normalize_history(sub)
            if len(df) == 0:
                result[ticker] = _empty_price_frame()
                continue
            _write_cache(f"price_{ticker}_{period}_{interval}",
                         _df_to_cacheable(df))
            result[ticker] = df
        except Exception as exc:
            logger.warning("batch parse failed for %s: %s", ticker, exc)
            result[ticker] = _empty_price_frame()

    return result


def _extract_symbol_frame(raw, ticker: str, single: bool) -> pd.DataFrame:
    """Pull a single symbol's frame out of a yfinance batch result."""
    if raw is None or len(raw) == 0:
        return _empty_price_frame()

    # Single-ticker download: columns are not a symbol MultiIndex.
    if single and not isinstance(raw.columns, pd.MultiIndex):
        return raw

    if isinstance(raw.columns, pd.MultiIndex):
        # group_by="ticker" -> level 0 is the symbol.
        if ticker in raw.columns.get_level_values(0):
            return raw[ticker]
        return _empty_price_frame()

    # Fallback: flat columns for a single symbol.
    return raw


# --------------------------------------------------------------------------- #
# Fundamentals
# --------------------------------------------------------------------------- #
def get_fundamentals(ticker: str) -> dict:
    """Return a company-info dict for a ticker (cached ~1h). {} on failure."""
    key = f"info_{ticker}"
    cached = _read_cache(key, config.INFO_CACHE_TTL)
    if cached is not None:
        return cached

    try:
        _throttle()
        info = _fetch_info_yf(ticker)
        clean = _clean_info(info)
        _write_cache(key, clean)
        return clean
    except Exception as exc:
        logger.warning("fundamentals fetch failed for %s: %s", ticker, exc)
        return {}


def get_fundamentals_batch(tickers) -> dict:
    """Return {ticker: info dict} for a list of tickers. {} per failed ticker."""
    result: dict[str, dict] = {}
    for ticker in tickers:
        result[ticker] = get_fundamentals(ticker)
    return result


def _clean_info(info: dict) -> dict:
    """Keep only JSON-serializable primitive values from a raw info dict."""
    clean = {}
    for k, v in (info or {}).items():
        if v is None or isinstance(v, (str, int, float, bool)):
            clean[k] = v
    return clean


# --------------------------------------------------------------------------- #
# Manual smoke test
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Fetching quick list:", config.QUICK_LIST)
    prices = get_price_history_batch(config.QUICK_LIST)
    for tkr, frame in prices.items():
        if len(frame):
            last = frame["Close"].iloc[-1]
            print(f"  {tkr}: {len(frame)} rows, last close = {last:.2f}")
        else:
            print(f"  {tkr}: no data")

    funds = get_fundamentals_batch(config.QUICK_LIST)
    for tkr, info in funds.items():
        name = info.get("shortName") or info.get("longName") or "?"
        sector = info.get("sector", "?")
        print(f"  {tkr}: {name} ({sector})")

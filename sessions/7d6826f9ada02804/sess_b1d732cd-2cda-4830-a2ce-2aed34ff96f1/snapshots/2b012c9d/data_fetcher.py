"""data_fetcher.py - data access layer for the stock signal dashboard.

Pulls price history and fundamentals from Yahoo Finance via ``yahooquery``, for
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

# Yahoo module names merged into a flat fundamentals dict per symbol.
FUNDAMENTAL_MODULES = [
    "price",
    "summaryDetail",
    "assetProfile",
    "defaultKeyStatistics",
    "financialData",
]

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

    Handles yahooquery's lowercase columns (open/high/low/close/volume plus
    extras like adjclose/dividends/splits). Missing OHLCV columns are added as
    NaN; extra columns are dropped.
    """
    if df is None or not isinstance(df, pd.DataFrame) or len(df) == 0:
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

    # Ensure a proper DatetimeIndex (yahooquery dates may be date or datetime).
    out.index = pd.to_datetime(out.index, errors="coerce", utc=False)
    # Drop any tz info so cached ISO strings round-trip cleanly.
    try:
        if getattr(out.index, "tz", None) is not None:
            out.index = out.index.tz_localize(None)
    except (TypeError, AttributeError):
        pass
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
def _fetch_history_yq(symbols, period: str, interval: str):
    """Raw price history from yahooquery for one or more space-joined symbols.

    Returns whatever yahooquery gives back (typically a MultiIndex DataFrame
    keyed by symbol+date; may be a dict/str on error).
    """
    from yahooquery import Ticker

    ticker = Ticker(symbols, validate=False)
    return ticker.history(period=period, interval=interval)


def _fetch_fundamentals_yq(symbols) -> dict:
    """Raw fundamentals from yahooquery, merged to {symbol: flat_dict}.

    Uses a single batched get_modules call. Per-symbol error responses (which
    yahooquery returns as strings) are collapsed to empty dicts.
    """
    from yahooquery import Ticker

    ticker = Ticker(symbols, validate=False)
    raw = ticker.get_modules(FUNDAMENTAL_MODULES)

    out: dict[str, dict] = {}
    for sym, data in (raw or {}).items():
        merged: dict = {}
        if isinstance(data, dict):
            for mod_data in data.values():
                if isinstance(mod_data, dict):
                    merged.update(mod_data)
        out[sym] = merged
    return out


# --------------------------------------------------------------------------- #
# History extraction
# --------------------------------------------------------------------------- #
def _extract_symbol_frame(raw, ticker: str) -> pd.DataFrame:
    """Pull a single symbol's frame out of a yahooquery history result."""
    if not isinstance(raw, pd.DataFrame) or len(raw) == 0:
        return _empty_price_frame()

    if isinstance(raw.index, pd.MultiIndex):
        # yahooquery indexes by (symbol, date); symbol is level 0.
        symbols = set(raw.index.get_level_values(0))
        if ticker in symbols:
            return raw.xs(ticker, level=0)
        return _empty_price_frame()

    # Single-symbol result with a plain date index.
    return raw


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
        raw = _fetch_history_yq(ticker, period, interval)
        df = _normalize_history(_extract_symbol_frame(raw, ticker))
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
    yahooquery call. Every requested ticker is present in the result (empty
    frame on failure), so callers can rely on complete keys.
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
        raw = _fetch_history_yq(" ".join(to_fetch), period, interval)
    except Exception as exc:
        logger.warning("batch price fetch failed for %s: %s", to_fetch, exc)
        raw = None

    for ticker in to_fetch:
        try:
            df = _normalize_history(_extract_symbol_frame(raw, ticker))
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
        raw = _fetch_fundamentals_yq(ticker)
        info = raw.get(ticker, {}) if isinstance(raw, dict) else {}
        clean = _clean_info(info)
        _write_cache(key, clean)
        return clean
    except Exception as exc:
        logger.warning("fundamentals fetch failed for %s: %s", ticker, exc)
        return {}


def get_fundamentals_batch(tickers) -> dict:
    """Return {ticker: info dict} for a list of tickers, one batched call.

    Cached tickers are served from disk; the rest fetched together. Every
    requested ticker is present ({} on failure).
    """
    result: dict[str, dict] = {}
    to_fetch: list[str] = []

    for ticker in tickers:
        cached = _read_cache(f"info_{ticker}", config.INFO_CACHE_TTL)
        if cached is not None:
            result[ticker] = cached
        else:
            to_fetch.append(ticker)

    if not to_fetch:
        return result

    try:
        _throttle()
        raw = _fetch_fundamentals_yq(" ".join(to_fetch))
    except Exception as exc:
        logger.warning("batch fundamentals fetch failed for %s: %s", to_fetch, exc)
        raw = {}

    for ticker in to_fetch:
        try:
            info = raw.get(ticker, {}) if isinstance(raw, dict) else {}
            clean = _clean_info(info)
            _write_cache(f"info_{ticker}", clean)
            result[ticker] = clean
        except Exception as exc:
            logger.warning("batch fundamentals parse failed for %s: %s", ticker, exc)
            result[ticker] = {}

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

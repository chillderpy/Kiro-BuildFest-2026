"""backtester.py - strictly simulated replay of the signal strategy.

Walks historical OHLCV data, recomputes the same weighted BUY/HOLD/SELL signal
used live, and simulates a simple long-only strategy to report hypothetical
performance stats (return, win rate, signal/trade counts).

IMPORTANT: This is a simulation for research/learning only. It never places
trades, never connects to a broker, and makes no recommendation. Past
hypothetical results do not predict future performance.
"""

from __future__ import annotations

import analysis
import config


def backtest(df, initial_cash: float = 10_000.0) -> dict:
    """Replay signals over `df` and return hypothetical performance stats.

    Strategy (long-only, all-in/all-out):
      - On a BUY signal while flat: buy at that day's close.
      - On a SELL signal while long: sell at that day's close.
      - HOLD: do nothing.
    A final open position is marked-to-market at the last close.

    Returns a dict with:
      initial_cash, final_equity, total_return_pct, buy_and_hold_return_pct,
      num_signals, num_buy_signals, num_sell_signals, num_trades,
      num_winning_trades, win_rate_pct, trades (list).
    """
    empty = _empty_result(initial_cash)
    if df is None or len(df) == 0 or "Close" not in df.columns:
        return empty

    enriched = analysis.compute_indicators(df)
    if len(enriched) == 0:
        return empty

    cash = float(initial_cash)
    shares = 0.0
    entry_price = None
    trades = []
    num_buy = num_sell = 0

    closes = enriched["Close"]

    for ts, row in enriched.iterrows():
        close = row.get("Close")
        if close is None or _isnan(close):
            continue

        ind = analysis.row_to_indicators(row)
        # Skip warmup rows where the core trend indicators are not ready.
        if _isnan(row.get("SMA_long")) or _isnan(row.get("MACD_signal")):
            continue

        # Backtest uses technical signals only; fundamentals are not available
        # historically and are left neutral.
        label = analysis.score(ind)["label"]

        if label == "BUY":
            num_buy += 1
            if shares == 0.0 and close > 0:
                shares = cash / close
                entry_price = close
                cash = 0.0
        elif label == "SELL":
            num_sell += 1
            if shares > 0.0:
                cash = shares * close
                ret = (close - entry_price) / entry_price * 100.0
                trades.append({
                    "entry": round(entry_price, 4),
                    "exit": round(close, 4),
                    "return_pct": round(ret, 4),
                })
                shares = 0.0
                entry_price = None

    last_close = float(closes.iloc[-1])
    final_equity = cash + shares * last_close if shares > 0 else cash
    # Note any still-open position (marked to market, not counted as a trade).
    open_position = shares > 0.0

    first_close = float(closes.iloc[0])
    bh_return = (last_close - first_close) / first_close * 100.0 if first_close else 0.0

    num_trades = len(trades)
    num_winning = sum(1 for t in trades if t["return_pct"] > 0)
    win_rate = (num_winning / num_trades * 100.0) if num_trades else 0.0

    return {
        "initial_cash": round(float(initial_cash), 2),
        "final_equity": round(final_equity, 2),
        "total_return_pct": round((final_equity - initial_cash) / initial_cash * 100.0, 4),
        "buy_and_hold_return_pct": round(bh_return, 4),
        "num_signals": num_buy + num_sell,
        "num_buy_signals": num_buy,
        "num_sell_signals": num_sell,
        "num_trades": num_trades,
        "num_winning_trades": num_winning,
        "win_rate_pct": round(win_rate, 2),
        "open_position": open_position,
        "trades": trades,
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _isnan(x) -> bool:
    return x is None or (isinstance(x, float) and x != x)


def _row_to_indicator_dict(row) -> dict:
    """Convert an enriched frame row into the dict score_signal expects."""
    keys = [
        "Close", "SMA_short", "SMA_long", "EMA_short", "EMA_long", "RSI",
        "MACD", "MACD_signal", "MACD_hist", "BB_upper", "BB_middle", "BB_lower",
    ]
    out = {}
    for k in keys:
        val = row.get(k)
        out[k] = None if _isnan(val) else float(val)
    return out


def _empty_result(initial_cash: float) -> dict:
    return {
        "initial_cash": round(float(initial_cash), 2),
        "final_equity": round(float(initial_cash), 2),
        "total_return_pct": 0.0,
        "buy_and_hold_return_pct": 0.0,
        "num_signals": 0,
        "num_buy_signals": 0,
        "num_sell_signals": 0,
        "num_trades": 0,
        "num_winning_trades": 0,
        "win_rate_pct": 0.0,
        "open_position": False,
        "trades": [],
    }


# --------------------------------------------------------------------------- #
# Manual demo
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import data_fetcher

    ticker = config.QUICK_LIST[0]
    df = data_fetcher.get_price_history(ticker)
    stats = backtest(df)
    print(f"Backtest for {ticker} (SIMULATED, research only):")
    for key in ["initial_cash", "final_equity", "total_return_pct",
                "buy_and_hold_return_pct", "num_signals", "num_trades",
                "win_rate_pct"]:
        print(f"  {key}: {stats[key]}")

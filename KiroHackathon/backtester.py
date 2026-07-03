"""backtester.py - strict walk-forward simulation of the signal strategy.

Walks the test window one day at a time and, at each day, decides using ONLY
the information that would have been known up to and including that day. The
technical indicators used are all backward-looking (rolling / exponential
windows over past closes), so a value at day *t* is a function of days <= *t*
only - there is no look-ahead.

To guarantee that, warmup history is kept separate from the test window:

  * We fetch a long history (e.g. 2 years).
  * The test window is only the most recent `test_days` (the "past year").
  * Everything before the window is warmup - it exists solely so indicators
    like SMA-50 are already "warm" on the first test day. No trades happen in
    the warmup region.

Strategy (long-only, all-in / all-out):
  * BUY signal while flat  -> buy the full position at that day's close.
  * SELL signal while long -> sell the whole position at that day's close.
  * HOLD -> do nothing.
A position still open on the last day is marked to market for the final value.

IMPORTANT: This is a simulation for research/learning only. It shows how the
strategy *would have* performed on past data - it is not a prediction, a
recommendation, or a promise of future results. It never places real trades.
"""

from __future__ import annotations

from datetime import timedelta

import analysis
import config

DISCLAIMER = (
    "Hypothetical: this shows how the strategy WOULD have performed on past "
    "data. It is not a prediction, recommendation, or promise of future "
    "results. No real trades were placed."
)


def backtest(df, test_days: int | None = None,
             initial_cash: float | None = None) -> dict:
    """Run a walk-forward backtest over the last `test_days` of `df`.

    `df` should be a normalized OHLCV frame that includes extra warmup history
    before the test window. Returns a result dict; on insufficient data it
    returns ``{"ok": False, "message": ...}`` rather than raising.
    """
    test_days = test_days or config.BACKTEST_TEST_DAYS
    initial_cash = config.BACKTEST_INITIAL_CASH if initial_cash is None else initial_cash

    if df is None or len(df) == 0 or "Close" not in df.columns:
        return _insufficient("No price history available to backtest.", initial_cash)

    # Indicators are causal, so computing them once over the full history and
    # then slicing is identical to recomputing them expanding-window each day.
    enriched = analysis.compute_indicators(df)
    if len(enriched) == 0:
        return _insufficient("No price history available to backtest.", initial_cash)

    # --- separate the test window from warmup history ---
    last_date = enriched.index.max()
    cutoff = last_date - timedelta(days=test_days)
    window = enriched[enriched.index >= cutoff]

    # Only days whose indicators are fully warmed up are tradeable. If warmup
    # was insufficient these cold days sit at the very start of the window and
    # are dropped; if too few remain we bail cleanly.
    warm = window[window["SMA_long"].notna() & window["MACD_signal"].notna()]
    if len(warm) < config.BACKTEST_MIN_TRADING_DAYS:
        return _insufficient(
            "Not enough data for a meaningful backtest: need at least "
            f"{config.BACKTEST_MIN_TRADING_DAYS} warmed-up trading days in the "
            f"test window, found {len(warm)}.",
            initial_cash,
        )

    # --- walk the window day by day (chronological, no peeking ahead) ---
    cash = float(initial_cash)
    shares = 0.0
    entry_price = None
    entry_date = None
    trades: list[dict] = []
    equity_curve: list[dict] = []

    for ts, row in warm.iterrows():
        close = float(row["Close"])
        # Decision uses only this row's indicators (a function of days <= ts).
        indicators = analysis.row_to_indicators(row)
        label = analysis.score(indicators)["label"]  # technicals only

        if label == "BUY" and shares == 0.0 and close > 0:
            shares = cash / close
            entry_price = close
            entry_date = ts
            cash = 0.0
        elif label == "SELL" and shares > 0.0:
            cash = shares * close
            trades.append({
                "entry_date": entry_date.strftime("%Y-%m-%d"),
                "entry": round(entry_price, 4),
                "exit_date": ts.strftime("%Y-%m-%d"),
                "exit": round(close, 4),
                "return_pct": round((close - entry_price) / entry_price * 100.0, 4),
            })
            shares = 0.0
            entry_price = None
            entry_date = None

        equity = cash + shares * close
        equity_curve.append({"date": ts.strftime("%Y-%m-%d"), "equity": round(equity, 2)})

    # --- metrics ---
    closes = warm["Close"]
    first_close = float(closes.iloc[0])
    last_close = float(closes.iloc[-1])
    final_equity = equity_curve[-1]["equity"]

    total_return = (final_equity - initial_cash) / initial_cash * 100.0
    bh_return = (last_close - first_close) / first_close * 100.0 if first_close else 0.0

    num_trades = len(trades)
    num_winning = sum(1 for t in trades if t["return_pct"] > 0)
    win_rate = (num_winning / num_trades * 100.0) if num_trades else 0.0

    return {
        "ok": True,
        "message": "",
        "disclaimer": DISCLAIMER,
        "start_date": warm.index.min().strftime("%Y-%m-%d"),
        "end_date": last_date.strftime("%Y-%m-%d"),
        "trading_days": len(warm),
        "initial_cash": round(float(initial_cash), 2),
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return, 4),
        "buy_and_hold_return_pct": round(bh_return, 4),
        "beat_buy_and_hold": total_return > bh_return,
        "num_trades": num_trades,
        "num_winning_trades": num_winning,
        "win_rate_pct": round(win_rate, 2),
        "max_drawdown_pct": _max_drawdown_pct(equity_curve),
        "open_position": shares > 0.0,
        "trades": trades,
        "equity_curve": equity_curve,
    }


def run_for_ticker(ticker: str, test_days: int | None = None) -> dict:
    """Fetch history for `ticker` (with warmup) and backtest the last year."""
    import data_fetcher

    df = data_fetcher.get_price_history(ticker, period=config.BACKTEST_FETCH_PERIOD)
    return backtest(df, test_days=test_days)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _max_drawdown_pct(equity_curve: list[dict]) -> float:
    """Worst peak-to-trough decline of the equity curve, as a % (<= 0)."""
    peak = float("-inf")
    worst = 0.0
    for point in equity_curve:
        eq = point["equity"]
        peak = max(peak, eq)
        if peak > 0:
            worst = min(worst, eq / peak - 1.0)
    return round(worst * 100.0, 4)


def _insufficient(message: str, initial_cash: float) -> dict:
    """Clean bail-out result when there is not enough data to backtest."""
    return {
        "ok": False,
        "message": message,
        "disclaimer": DISCLAIMER,
        "start_date": None,
        "end_date": None,
        "trading_days": 0,
        "initial_cash": round(float(initial_cash), 2),
        "final_equity": round(float(initial_cash), 2),
        "total_return_pct": 0.0,
        "buy_and_hold_return_pct": 0.0,
        "beat_buy_and_hold": False,
        "num_trades": 0,
        "num_winning_trades": 0,
        "win_rate_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "open_position": False,
        "trades": [],
        "equity_curve": [],
    }


# --------------------------------------------------------------------------- #
# Manual demo
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    ticker = config.QUICK_LIST[0]
    stats = run_for_ticker(ticker)
    print(f"Backtest for {ticker} (SIMULATED - would-have-done, not a promise):")
    if not stats["ok"]:
        print("  ", stats["message"])
    else:
        for key in ["start_date", "end_date", "trading_days", "final_equity",
                    "total_return_pct", "buy_and_hold_return_pct",
                    "beat_buy_and_hold", "num_trades", "win_rate_pct",
                    "max_drawdown_pct"]:
            print(f"  {key}: {stats[key]}")

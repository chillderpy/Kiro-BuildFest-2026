"""Deterministic tests for the simulated backtester."""

import numpy as np
import pandas as pd

import backtester


def _frame(closes):
    idx = pd.date_range("2023-01-01", periods=len(closes), freq="D")
    close = pd.Series(closes, index=idx, dtype="float64")
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 0.5,
            "Low": close - 0.5,
            "Close": close,
            "Volume": pd.Series([1_000] * len(closes), index=idx),
        }
    )


def _wave_series(n=200):
    """A smooth up/down wave so the strategy generates trades deterministically."""
    x = np.linspace(0, 6 * np.pi, n)
    return list(100.0 + 20.0 * np.sin(x) + 0.05 * np.arange(n))


def test_empty_frame_returns_flat_result():
    res = backtester.backtest(pd.DataFrame())
    assert res["num_trades"] == 0
    assert res["final_equity"] == res["initial_cash"]
    assert res["total_return_pct"] == 0.0


def test_result_has_expected_keys():
    res = backtester.backtest(_frame(_wave_series()))
    for key in ["initial_cash", "final_equity", "total_return_pct",
                "buy_and_hold_return_pct", "num_signals", "num_buy_signals",
                "num_sell_signals", "num_trades", "num_winning_trades",
                "win_rate_pct", "open_position", "trades"]:
        assert key in res


def test_backtest_is_deterministic():
    df = _frame(_wave_series())
    r1 = backtester.backtest(df)
    r2 = backtester.backtest(df)
    assert r1 == r2


def test_uptrend_buy_and_hold_positive():
    # Strictly rising series -> buy-and-hold return must be positive.
    df = _frame(list(np.linspace(50, 150, 120)))
    res = backtester.backtest(df)
    assert res["buy_and_hold_return_pct"] > 0


def test_win_rate_within_bounds_and_trade_accounting():
    res = backtester.backtest(_frame(_wave_series()))
    assert 0.0 <= res["win_rate_pct"] <= 100.0
    assert res["num_winning_trades"] <= res["num_trades"]
    assert res["num_signals"] == res["num_buy_signals"] + res["num_sell_signals"]
    # The wave should produce at least one completed round-trip trade.
    assert res["num_trades"] >= 1

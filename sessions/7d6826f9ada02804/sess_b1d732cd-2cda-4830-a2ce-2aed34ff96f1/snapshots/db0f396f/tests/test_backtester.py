"""Tests for the walk-forward backtester, including a no-look-ahead check."""

import numpy as np
import pandas as pd

import config
import backtester


def _frame(closes, end="2024-12-31"):
    idx = pd.date_range(end=end, periods=len(closes), freq="D")
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


def _wave(n=500):
    """A long up/down wave so the strategy makes several round-trip trades."""
    x = np.linspace(0, 14 * np.pi, n)
    return list(100.0 + 25.0 * np.sin(x) + 0.03 * np.arange(n))


# --------------------------------------------------------------------------- #
# Insufficient-data bail-out
# --------------------------------------------------------------------------- #
def test_empty_frame_bails_cleanly():
    res = backtester.backtest(pd.DataFrame())
    assert res["ok"] is False
    assert res["message"]
    assert res["num_trades"] == 0


def test_too_little_data_bails_cleanly():
    res = backtester.backtest(_frame(list(np.linspace(10, 20, 30))))
    assert res["ok"] is False
    assert "enough data" in res["message"].lower()


# --------------------------------------------------------------------------- #
# Shape + metrics
# --------------------------------------------------------------------------- #
def test_result_has_expected_keys():
    res = backtester.backtest(_frame(_wave()))
    assert res["ok"] is True
    for key in ["disclaimer", "start_date", "end_date", "trading_days",
                "initial_cash", "final_equity", "total_return_pct",
                "buy_and_hold_return_pct", "beat_buy_and_hold", "num_trades",
                "num_winning_trades", "win_rate_pct", "max_drawdown_pct",
                "open_position", "trades", "equity_curve"]:
        assert key in res


def test_metrics_are_sane():
    res = backtester.backtest(_frame(_wave()))
    assert 0.0 <= res["win_rate_pct"] <= 100.0
    assert res["num_winning_trades"] <= res["num_trades"]
    assert res["max_drawdown_pct"] <= 0.0
    assert res["num_trades"] >= 1
    # Equity curve spans the (warmed-up) test window.
    assert len(res["equity_curve"]) == res["trading_days"]


def test_test_window_is_about_a_year():
    # Two years of daily data -> the test window should be ~last 365 days only,
    # proving warmup is excluded from the measured window.
    res = backtester.backtest(_frame(_wave(730)), test_days=365)
    assert res["ok"] is True
    assert 240 <= res["trading_days"] <= 366


def test_deterministic():
    df = _frame(_wave())
    assert backtester.backtest(df) == backtester.backtest(df)


def test_beat_buy_and_hold_flag_matches_numbers():
    res = backtester.backtest(_frame(_wave()))
    assert res["beat_buy_and_hold"] == (
        res["total_return_pct"] > res["buy_and_hold_return_pct"])


# --------------------------------------------------------------------------- #
# No look-ahead: mutating the future must not change earlier decisions
# --------------------------------------------------------------------------- #
def test_no_lookahead_future_prices_do_not_change_past_trades():
    closes = _wave(500)
    df1 = _frame(closes)

    # Corrupt the last 60 closes with a wild spike; keep all earlier bars.
    mod_start_idx = len(closes) - 60
    mod_date = df1.index[mod_start_idx]
    df2 = df1.copy()
    df2.iloc[mod_start_idx:, df2.columns.get_loc("Close")] *= 3.0

    r1 = backtester.backtest(df1)
    r2 = backtester.backtest(df2)

    # Trades that both entered AND exited before the corrupted region are
    # decided purely from pre-mod data, so they must be byte-for-byte identical.
    def before(res):
        cut = mod_date.strftime("%Y-%m-%d")
        return [t for t in res["trades"] if t["exit_date"] < cut]

    trades1, trades2 = before(r1), before(r2)
    assert trades1 == trades2
    assert len(trades1) >= 1  # the test is only meaningful if some exist


def test_no_lookahead_equity_curve_matches_before_mutation():
    closes = _wave(500)
    df1 = _frame(closes)
    mod_start_idx = len(closes) - 60
    mod_date = df1.index[mod_start_idx].strftime("%Y-%m-%d")
    df2 = df1.copy()
    df2.iloc[mod_start_idx:, df2.columns.get_loc("Close")] *= 3.0

    c1 = {p["date"]: p["equity"] for p in backtester.backtest(df1)["equity_curve"]}
    c2 = {p["date"]: p["equity"] for p in backtester.backtest(df2)["equity_curve"]}

    # Portfolio value on every day before the mutation must be unchanged.
    for date, equity in c1.items():
        if date < mod_date:
            assert c2[date] == equity

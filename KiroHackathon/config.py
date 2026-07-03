# config.py - settings for personal, research-only stock signal dashboard
# NOTE: research/learning only. No trading, no broker integration.

import os

# --- Watchlist grouped by sector ---
WATCHLIST = {
    "tech":           ["AAPL", "MSFT", "GOOGL", "META"],
    "semiconductors": ["NVDA", "AMD", "QCOM", "INTC", "MU"],
    "finance":        ["JPM", "GS"],
    "energy":         ["XOM", "CVX"],
    "defence":        ["LMT", "RTX"],
}

# Small active list used on normal runs (avoid hammering Yahoo)
QUICK_LIST = ["NVDA", "AAPL", "MSFT"]

# --- Indicator parameters ---
SMA_PERIODS = {"short": 20, "long": 50}
EMA_PERIODS = {"short": 12, "long": 26}
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
MACD = {"fast": 12, "slow": 26, "signal": 9}
BOLLINGER = {"period": 20, "std_dev": 2}

# --- Signal weights (trend-leaning; must sum to 1.0) ---
# Technicals carry 0.75 of the weight, fundamentals 0.25.
WEIGHTS = {
    # Technical indicators (0.75 total)
    "macd": 0.25,
    "sma": 0.15,
    "ema": 0.15,
    "rsi": 0.10,
    "bollinger": 0.10,
    # Fundamentals (0.25 total)
    "pe": 0.125,
    "earnings_growth": 0.125,
}

# --- Signal thresholds (composite score is on a -1..+1 scale) ---
# FIX: tightened the neutral band (was +/-0.30). Trend and mean-reversion
# sub-scores often offset each other, so the composite clustered near 0 and
# almost everything read HOLD. +/-0.15 surfaces actual BUY/SELL calls. Tune here.
SIGNAL_BUY = 0.15    # score >= +0.15 -> BUY
SIGNAL_SELL = -0.15  # score <= -0.15 -> SELL
                     # otherwise      -> HOLD

# --- Fundamental scoring reference points ---
# P/E: cheaper is more bullish. <= PE_CHEAP scores +1, >= PE_EXPENSIVE scores -1.
PE_CHEAP = 10.0
PE_EXPENSIVE = 40.0
# Earnings growth (as a fraction, e.g. 0.20 = +20%). Symmetric around zero:
# >= +STRONG scores +1, <= -STRONG scores -1.
EARNINGS_GROWTH_STRONG = 0.20

# --- Data fetch settings ---
DATA_PERIOD = "6mo"
DATA_INTERVAL = "1d"

# --- Chart settings ---
# Periods the dashboard chart can request.
CHART_PERIODS = ["1mo", "3mo", "6mo", "1y", "2y"]
DEFAULT_CHART_PERIOD = "6mo"
# Calendar-day span of each requested window (used to trim the visible range).
CHART_PERIOD_DAYS = {"1mo": 30, "3mo": 91, "6mo": 182, "1y": 365, "2y": 730}
# Larger window actually fetched so indicators (e.g. SMA-50) have warmup data
# before the start of the visible window; trimmed back before sending.
# FIX: widened the short windows (1mo/3mo now pull 1y) so there are always well
# over 50 trading days of warmup ahead of the visible range -> the first candle's
# SMA-50/Bollinger values are populated, not blank.
CHART_FETCH_PERIOD = {"1mo": "1y", "3mo": "1y", "6mo": "1y", "1y": "2y", "2y": "5y"}

# --- Backtest settings ---
# History pulled for a backtest (must exceed the test window + indicator warmup).
BACKTEST_FETCH_PERIOD = "2y"
# Size of the walk-forward test window, in calendar days (the "past year").
BACKTEST_TEST_DAYS = 365
# Bail out if fewer than this many warmed-up trading days fall in the window.
BACKTEST_MIN_TRADING_DAYS = 60
BACKTEST_INITIAL_CASH = 10_000.0

# --- Data fetch / cache settings ---
# FIX: more conservative after getting 429'd on a full refresh. Bigger gap
# between live calls, and longer cache TTLs so repeat refreshes serve from disk
# instead of re-hitting Yahoo. Fundamentals barely move intraday, so their cache
# is much longer than prices.
CACHE_DIR = "/tmp/cache" if os.environ.get("VERCEL") else "cache"
REQUEST_DELAY_SECONDS = 5.0        # was 2.0 - slower but far less likely to be throttled
PRICE_CACHE_TTL = 30 * 60          # was 15 min
INFO_CACHE_TTL = 6 * 60 * 60       # was 60 min (fundamentals change slowly)


# =============================================================================
# STATIC RESEARCH STUDY DATA  --  NOT live signals
# -----------------------------------------------------------------------------
# This is a fixed, self-contained snapshot of an academic research project on
# semiconductor stocks over 2015-2024 (Group 33, BUS1004). It is historical and
# illustrative ONLY: it is not live, never updated from any data source, and is
# NOT investment advice. It is deliberately kept separate from the live signal
# pipeline (data_fetcher / analysis / backtester) and is served on its own
# endpoint (/api/research). Do not wire this into the live scoring logic.
# =============================================================================

RESEARCH_STUDY = {
    "is_static": True,
    "title": "Buy, Sell, or Hold? - Semiconductor Industry Study",
    "subtitle": "Semiconductor Industry (SIC 3670 / 3674)",
    "course": "BUS1004 Data-Driven Business Analysis",
    "authors": "Group 33",
    "period": "2015-2024",
    "research_question": (
        "How do ESG performance, profitability (Gross Margin), R&D intensity, "
        "liquidity (bid-ask spread), and firm size explain and predict "
        "semiconductor stock returns?"
    ),
    "summary": (
        "Semiconductors are the foundational layer of modern technology, from "
        "smartphones and data centres to AI accelerators and 5G networks. Over "
        "2015-2024 the sector saw extraordinary transformation driven by the AI "
        "boom, cloud computing expansion, and the global chip shortage. This "
        "study analyses five major firms spanning the full spectrum of "
        "semiconductor business models, from high-growth AI computing to "
        "cyclical memory markets."
    ),
    "data_sources": [
        "WRDS CRSP (monthly returns)",
        "WRDS LSEG (ESG scores)",
        "Bloomberg (gross margin, R&D)",
    ],
    "disclaimer": (
        "Static study data from a 2015-2024 academic project. Historical and "
        "illustrative only - not live, not updated, and not investment advice. "
        "Completely separate from this app's live signals."
    ),

    # Portfolio-level statistics (as reported in the study).
    "portfolio": {
        "mean_return_pct": 37.5,             # headline (overview / recommendations)
        "descriptive_mean_return_pct": 32.9,  # descriptive-statistics table
        "std_dev": 0.359,
        "gross_margin_pct": 50.1,
        "mean_esg": 0.750,
        "rnd_musd": 5596,
        "model1_r2": 0.941,                   # explanatory
        "model1_significant": "Gross Margin (t=4.29)",
        "model2_r2": 0.474,                   # predictive
        "model2_predictor": "R&D Expense (t=1.29)",
    },

    # Decision rules used to turn predicted vs. historical returns into a call.
    "decision_rules": [
        {"label": "BUY", "rule": "Predicted return is greater than the historical average."},
        {"label": "HOLD", "rule": "Predicted return is positive but below the historical average."},
        {"label": "SELL", "rule": "Predicted return is negative."},
    ],

    # Conclusion / key takeaways.
    "key_takeaways": [
        {
            "title": "Current drivers",
            "text": (
                "Gross margin is the most consistent same-period driver of "
                "returns, especially for Micron and Intel - current "
                "profitability is a key signal of present stock performance."
            ),
        },
        {
            "title": "Future signals",
            "text": (
                "R&D is a stronger forward-looking predictor at the firm level, "
                "particularly for Micron and Intel in the predictive model - "
                "innovation investment may support future competitive advantage "
                "and next-period returns."
            ),
        },
        {
            "title": "Final investment stance",
            "text": (
                "Overall the results support BUY recommendations across all "
                "five firms; predicted returns remain positive relative to "
                "historical benchmarks, supporting a favourable forward outlook."
            ),
        },
    ],

    # Study limitations (kept visible so results are not mistaken for certainty).
    "limitations": [
        {
            "limitation": "Annual sample size (n=10)",
            "impact": (
                "The limited annual observations per firm can make coefficient "
                "estimates and p-values less stable, potentially overstating "
                "model strength."
            ),
            "fix": (
                "Panel data setup: increase sample size by extending the period "
                "or using a richer panel setup to improve estimation accuracy "
                "and robustness."
            ),
        },
        {
            "limitation": "Multicollinearity",
            "impact": (
                "Predictors like R&D are strongly correlated with ESG and "
                "market cap, making it harder to isolate the individual impact "
                "of each variable."
            ),
            "fix": (
                "Alternative model specifications: test more parsimonious "
                "versions of the model, e.g. one operating variable at a time or "
                "transforming market cap, to improve interpretability and check "
                "robustness."
            ),
        },
        {
            "limitation": "Omitted variables",
            "impact": (
                "Returns are influenced by broader market conditions, "
                "semiconductor cycles, and macroeconomic shocks not captured in "
                "the current model."
            ),
            "fix": (
                "Additional control variables: include market-return proxies, "
                "semiconductor-cycle indicators, or interest-rate environments "
                "to capture external forces."
            ),
        },
    ],

    # Per-stock findings.
    "stocks": [
        {
            "ticker": "AMD",
            "name": "Advanced Micro Devices",
            "focus": "CPUs & GPUs (Gaming, AI, Cloud)",
            "recommendation": "BUY",
            "hist_avg_return_pct": 54.0,
            "predicted_return_pct": 57.9,
            "signal_vs_hist_pct": 3.9,
            "gross_margin_pct": 42.7,
            "gross_margin_2024_pct": 49.5,
            "mean_esg": 0.717,
            "rnd_musd": 3544,
            "std_dev": 0.658,
            "model1_r2": 0.349,
            "model1_significant": "No significant regressors (p > 0.05)",
            "model2_r2": 0.618,
            "strongest_predictor": "Gross Margin (t=1.45)",
            "highlights": [
                {"title": "AI accelerators", "text": "Strong forward outlook driven by data-centre growth."},
                {"title": "Margin transformation", "text": "Gross margin rose materially over the decade."},
                {"title": "Improved outlook", "text": "Predicted return (57.9%) significantly exceeds the historical average."},
            ],
        },
        {
            "ticker": "NVDA",
            "name": "NVIDIA",
            "focus": "AI Accelerators & GPUs",
            "recommendation": "BUY",
            "hist_avg_return_pct": 68.2,
            "predicted_return_pct": 69.5,
            "signal_vs_hist_pct": 1.3,
            "gross_margin_pct": 56.5,
            "mean_esg": 0.761,
            "rnd_musd": 4039,
            "std_dev": 0.616,
            "market_cap": "$2.7T",
            "model1_r2": 0.958,
            "model1_significant": "All regressors",
            "model2_r2": 0.894,
            "strongest_predictor": "R&D Expense (t=4.82)",
            "highlights": [
                {"title": "Exceptional base", "text": "Past returns (68.2%) set an extremely high bar."},
                {"title": "Growth moderation", "text": "Predicted return is set to stabilise somewhat in future years."},
                {"title": "Consistent performance", "text": "Future returns expected to remain at a high bar."},
            ],
        },
        {
            "ticker": "QCOM",
            "name": "Qualcomm",
            "focus": "Mobile Processors & 5G",
            "recommendation": "BUY",
            "hist_avg_return_pct": 17.0,
            "predicted_return_pct": 22.2,
            "signal_vs_hist_pct": 5.2,
            "gross_margin_pct": 58.2,
            "mean_esg": 0.730,
            "rnd_musd": 6815,
            "std_dev": 0.357,
            "model1_r2": 0.962,
            "model1_significant": "All regressors",
            "model2_r2": 0.956,
            "strongest_predictor": "Gross Margin (t=5.56)",
            "highlights": [
                {"title": "Stable fundamentals", "text": "Licensing model provides a strong floor."},
                {"title": "Modest upside", "text": "Predicted return (22.2%) exceeds the historical average (17.0%)."},
            ],
        },
        {
            "ticker": "INTC",
            "name": "Intel",
            "focus": "CPUs & IDM Foundry",
            "recommendation": "BUY",
            "hist_avg_return_pct": 8.1,
            "predicted_return_pct": 9.8,
            "signal_vs_hist_pct": 1.7,
            "gross_margin_pct": 52.9,
            "mean_esg": 0.882,
            "rnd_musd": 10668,
            "std_dev": 0.283,
            "model1_r2": 0.927,
            "model1_significant": "Gross Margin, R&D, Annual Spread",
            "model2_r2": 0.978,
            "strongest_predictor": "R&D Expense (t=7.21)",
            "highlights": [
                {"title": "Recovery momentum", "text": "Model indicates potential stabilisation."},
                {"title": "Improving outlook", "text": "Predicted return (9.8%) exceeds the historical average (8.1%)."},
            ],
        },
        {
            "ticker": "MU",
            "name": "Micron Technology",
            "focus": "DRAM & NAND Memory",
            "recommendation": "BUY",
            "hist_avg_return_pct": 17.4,
            "predicted_return_pct": 28.1,
            "signal_vs_hist_pct": 10.7,
            "gross_margin_pct": 40.1,
            "mean_esg": 0.660,
            "rnd_musd": 2914,
            "std_dev": 0.514,
            "model1_r2": 0.994,
            "model1_significant": "Gross Margin, R&D, Annual Spread",
            "model2_r2": 0.998,
            "strongest_predictor": "R&D Expense (t=15.76)",
            "highlights": [
                {"title": "Cyclical upswing", "text": "Memory market entering a favourable phase."},
                {"title": "Strong upside", "text": "Predicted return (28.1%) significantly exceeds the historical average (17.4%)."},
            ],
        },
    ],
}

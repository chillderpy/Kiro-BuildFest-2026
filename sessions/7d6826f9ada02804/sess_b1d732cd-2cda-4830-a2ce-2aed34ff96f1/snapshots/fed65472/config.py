# config.py - settings for personal, research-only stock signal dashboard
# NOTE: research/learning only. No trading, no broker integration.

# --- Watchlist grouped by sector ---
WATCHLIST = {
    "tech":           ["AAPL", "MSFT", "GOOGL", "META"],
    "semiconductors": ["NVDA", "AMD"],
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
SIGNAL_BUY = 0.30    # score >= +0.30 -> BUY
SIGNAL_SELL = -0.30  # score <= -0.30 -> SELL
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

# --- Data fetch / cache settings ---
CACHE_DIR = "cache"
REQUEST_DELAY_SECONDS = 2.0
PRICE_CACHE_TTL = 15 * 60     # 15 minutes
INFO_CACHE_TTL = 60 * 60      # 60 minutes

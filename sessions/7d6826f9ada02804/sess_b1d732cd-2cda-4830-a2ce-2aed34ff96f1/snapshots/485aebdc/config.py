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
WEIGHTS = {
    "macd": 0.30,
    "sma": 0.20,
    "ema": 0.20,
    "rsi": 0.15,
    "bollinger": 0.15,
}

# --- Score thresholds (0-100 scale) ---
SCORE_BUY = 65    # score >= 65  -> BUY
SCORE_SELL = 35   # score <= 35  -> SELL
                  # otherwise    -> HOLD

# --- Data fetch settings ---
DATA_PERIOD = "6mo"
DATA_INTERVAL = "1d"

# --- Data fetch / cache settings ---
CACHE_DIR = "cache"
REQUEST_DELAY_SECONDS = 2.0
PRICE_CACHE_TTL = 15 * 60     # 15 minutes
INFO_CACHE_TTL = 60 * 60      # 60 minutes

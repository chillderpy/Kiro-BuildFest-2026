import numpy as np
import pandas as pd

try:
    from ta.trend import SMAIndicator, EMAIndicator, MACD
    from ta.momentum import RSIIndicator
    from ta.volatility import BollingerBands
    close = pd.Series(np.linspace(10, 40, 80) + np.sin(np.arange(80)))
    sma = SMAIndicator(close, window=20).sma_indicator()
    ema = EMAIndicator(close, window=12).ema_indicator()
    rsi = RSIIndicator(close, window=14).rsi()
    macd = MACD(close, window_fast=12, window_slow=26, window_sign=9)
    bb = BollingerBands(close, window=20, window_dev=2)
    print("SMA last:", round(float(sma.iloc[-1]), 3))
    print("EMA last:", round(float(ema.iloc[-1]), 3))
    print("RSI last:", round(float(rsi.iloc[-1]), 3))
    print("MACD last:", round(float(macd.macd().iloc[-1]), 3),
          "signal:", round(float(macd.macd_signal().iloc[-1]), 3),
          "hist:", round(float(macd.macd_diff().iloc[-1]), 3))
    print("BB hi/lo:", round(float(bb.bollinger_hband().iloc[-1]), 3),
          round(float(bb.bollinger_lband().iloc[-1]), 3))
    print("TA_CHECK OK")
except Exception as exc:
    import traceback
    traceback.print_exc()
    print("TA_CHECK FAIL:", exc)

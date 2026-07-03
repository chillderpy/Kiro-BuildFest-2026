"""Ad-hoc live check of the real yahooquery integration (network required)."""
import logging
logging.basicConfig(level=logging.WARNING)

import data_fetcher as d

# Inspect raw shape once so we know the real API contract.
try:
    raw = d._fetch_history_yq("NVDA AAPL", "1mo", "1d")
    print("raw type:", type(raw).__name__)
    if hasattr(raw, "index"):
        print("index is MultiIndex:", raw.index.__class__.__name__)
        print("columns:", list(raw.columns))
except Exception as exc:
    print("raw history call failed:", exc)

prices = d.get_price_history_batch(["NVDA", "AAPL"])
for t, f in prices.items():
    print(t, "rows=", len(f), "cols=", list(f.columns),
          "last=", (round(float(f['Close'].iloc[-1]), 2) if len(f) else None))

funds = d.get_fundamentals_batch(["NVDA"])
info = funds["NVDA"]
print("NVDA fundamentals keys:", len(info),
      "name=", info.get("shortName") or info.get("longName"),
      "sector=", info.get("sector"))

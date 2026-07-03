import collections
import app as app_module

c = app_module.create_app().test_client()

sig = c.get("/api/signals").get_json()["signals"]
dist = collections.Counter(s["label"] for s in sig)
print("label distribution:", dict(dist))
print("sample:", [(s["ticker"], s["label"], s["score"]) for s in sig[:6]])

d = c.get("/api/ticker/NVDA?period=1mo").get_json()
ch = d.get("chart", [])
print("1mo chart points:", len(ch),
      "| first sma_long:", ch[0]["sma_long"] if ch else None,
      "| first sma_short:", ch[0]["sma_short"] if ch else None)

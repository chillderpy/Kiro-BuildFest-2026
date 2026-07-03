import app as app_module

html = app_module.create_app().test_client().get("/").get_data(as_text=True)
markers = ["Stock Signal Dashboard", "card-grid", "id=\"tabs\"", "timeframe",
           "detail", "breakdown-body", "fundamentals-body", "backtest-body",
           "price-chart", "research", ">1M<", ">3M<", ">6M<", ">1Y<", ">2Y<",
           "dashboard.js", "style.css"]
for m in markers:
    print(("OK " if m in html else "MISS "), m)
print("BAD-LABEL 1MO present:", ">1MO<" in html)

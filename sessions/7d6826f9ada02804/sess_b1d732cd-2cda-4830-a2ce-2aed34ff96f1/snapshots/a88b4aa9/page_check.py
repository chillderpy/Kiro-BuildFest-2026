import app as app_module

html = app_module.create_app().test_client().get("/").get_data(as_text=True)
markers = [
    "Stock Signal Dashboard", "cdn.plot.ly/plotly-2.35.2.min.js",
    'id="filters"', 'data-filter="BUY"', 'data-filter="HOLD"', 'data-filter="SELL"',
    'id="price-chart"', 'id="equity-chart"', 'id="run-backtest"',
    ">1M<", ">2Y<", "dashboard.js", "Research", "no trade",
]
for m in markers:
    print(("OK  " if m in html else "MISS"), m)
print("chartjs removed:", "chart.umd" not in html)

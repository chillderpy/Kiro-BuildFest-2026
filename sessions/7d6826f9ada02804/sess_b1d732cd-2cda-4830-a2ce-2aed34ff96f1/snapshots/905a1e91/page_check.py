import app as app_module

html = app_module.create_app().test_client().get("/").get_data(as_text=True)
markers = [
    'id="research"', 'id="research-cards"', 'id="research-rules"',
    'id="research-limitations"', 'id="research-takeaways"', 'id="research-overview"',
    'id="live-toolbar"', "research-banner", "Static study data",
]
for m in markers:
    print(("OK  " if m in html else "MISS"), m)

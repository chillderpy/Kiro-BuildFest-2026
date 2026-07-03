"""End-to-end smoke test: real stack, no mocks.

Exercises config -> data_fetcher -> analysis -> backtester -> Flask routes.
Network failures are tolerated (safe defaults yield N/A rather than errors),
so this confirms wiring and resilience, not live market values.
"""

import app as app_module
import config


def main():
    client = app_module.create_app().test_client()

    r_index = client.get("/")
    print("GET /            ->", r_index.status_code)

    first_sector = next(iter(config.WATCHLIST))
    r_sector = client.get(f"/sector/{first_sector}")
    print(f"GET /sector/{first_sector:<6}->", r_sector.status_code)

    ticker = config.QUICK_LIST[0]
    r_bt = client.get(f"/backtest/{ticker}")
    print(f"GET /backtest/{ticker:<5}->", r_bt.status_code)

    r_404 = client.get("/sector/does-not-exist")
    print("GET bad sector   ->", r_404.status_code)

    body = r_index.get_data(as_text=True)
    labels = {t: None for t in config.QUICK_LIST}
    for t in config.QUICK_LIST:
        present = t in body
        labels[t] = "shown" if present else "MISSING"
    print("Quick-list tickers on index:", labels)

    ok = (
        r_index.status_code == 200
        and r_sector.status_code == 200
        and r_bt.status_code == 200
        and r_404.status_code == 404
        and all(t in body for t in config.QUICK_LIST)
        and "research" in body.lower()
    )
    print("SMOKE RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

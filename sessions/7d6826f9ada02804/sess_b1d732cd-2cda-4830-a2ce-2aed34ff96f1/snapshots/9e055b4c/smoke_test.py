"""End-to-end smoke test: real stack, no mocks.

Exercises the dashboard page and the JSON API through the full pipeline
(config -> data_fetcher -> analysis -> Flask). Network failures are tolerated
by the data layer's safe defaults, so this confirms wiring and error handling,
not live market values.
"""

import app as app_module
import config


def main():
    client = app_module.create_app().test_client()
    ok = True

    r = client.get("/")
    print("GET /                     ->", r.status_code)
    ok &= r.status_code == 200 and "Stock Signal Dashboard" in r.get_data(as_text=True)

    r = client.get("/api/watchlist")
    print("GET /api/watchlist        ->", r.status_code)
    ok &= r.status_code == 200 and r.get_json()["quick_list"] == config.QUICK_LIST

    r = client.get("/api/signals")
    print("GET /api/signals          ->", r.status_code)
    sigs = r.get_json().get("signals", []) if r.status_code == 200 else []
    strengths = [abs(s["score"]) if s["score"] is not None else -1 for s in sigs]
    sorted_ok = strengths == sorted(strengths, reverse=True)
    print("   signals:", len(sigs), "| sorted strongest-first:", sorted_ok)
    ok &= r.status_code == 200 and sorted_ok

    tkr = config.QUICK_LIST[0]
    r = client.get(f"/api/ticker/{tkr}?period=3mo")
    print(f"GET /api/ticker/{tkr}?3mo  ->", r.status_code)
    if r.status_code == 200:
        d = r.get_json()
        print(f"   {tkr}: label={d['label']} score={d['score']} "
              f"conf={d['confidence']} chart_points={len(d['chart'])}")
        if d["chart"]:
            print("   first visible SMA-50:", d["chart"][0]["sma_long"])
    ok &= r.status_code == 200

    r = client.get("/api/ticker/ZZZZ")
    print("GET /api/ticker/ZZZZ      ->", r.status_code, "(expect 404)")
    ok &= r.status_code == 404

    r = client.get(f"/api/ticker/{tkr}?period=10y")
    print(f"GET /api/ticker/{tkr}?10y  ->", r.status_code, "(expect 400)")
    ok &= r.status_code == 400

    print("SMOKE RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

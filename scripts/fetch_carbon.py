"""Fetch GB grid carbon intensity from the NESO Carbon Intensity API.

https://api.carbonintensity.org.uk - free, no key, half-hourly actuals.
Returns the mean actual intensity (gCO2/kWh) over the trailing 7 days.
Optional feed: callers must tolerate failure.
"""

import datetime as dt
import requests

BASE = "https://api.carbonintensity.org.uk"


def fetch_carbon_intensity(days=7):
    """Mean gCO2/kWh over the trailing `days` (max 13 per API range call)."""
    end = dt.datetime.now(dt.UTC).replace(minute=0, second=0, microsecond=0)
    start = end - dt.timedelta(days=days)
    r = requests.get(
        f"{BASE}/intensity/{start.strftime('%Y-%m-%dT%H:%MZ')}/"
        f"{end.strftime('%Y-%m-%dT%H:%MZ')}",
        headers={"Accept": "application/json"}, timeout=60)
    r.raise_for_status()
    rows = r.json().get("data", [])
    vals = []
    for row in rows:
        inten = row.get("intensity", {})
        v = inten.get("actual")
        if v is None:
            v = inten.get("forecast")
        if isinstance(v, (int, float)):
            vals.append(v)
    if not vals:
        raise RuntimeError("carbon intensity API returned no values")
    mean = sum(vals) / len(vals)
    print(f"grid CI: mean {mean:.0f} gCO2/kWh over {len(vals)} half-hours "
          f"({days} days)")
    return {"g_per_kwh": round(mean, 0),
            "window_days": days,
            "to": end.date().isoformat()}


if __name__ == "__main__":
    print(fetch_carbon_intensity())

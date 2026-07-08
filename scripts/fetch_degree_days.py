"""Fetch daily mean temperatures from Open-Meteo (ERA5-derived) and compute
population-weighted GB heating/cooling degree days, plus a separate NI series.

Single batched request for all locations, with retries. No API key.
Attribution: Open-Meteo.com (CC BY 4.0) / ERA5 (Copernicus).
"""

import datetime as dt
import time
import requests

GB_POINTS = [
    ("London",      51.51,  -0.13, 24.0),
    ("Birmingham",  52.48,  -1.90, 10.0),
    ("Manchester",  53.48,  -2.24, 10.0),
    ("Leeds",       53.80,  -1.55,  7.0),
    ("Glasgow",     55.86,  -4.25,  6.0),
    ("Newcastle",   54.98,  -1.61,  4.0),
    ("Bristol",     51.45,  -2.59,  4.0),
    ("Cardiff",     51.48,  -3.18,  3.5),
    ("Edinburgh",   55.95,  -3.19,  3.5),
    ("Southampton", 50.90,  -1.40,  4.0),
    ("Nottingham",  52.95,  -1.15,  4.0),
    ("Sheffield",   53.38,  -1.47,  4.0),
]
NI_POINT = ("Belfast", 54.60, -5.93)

HDD_BASES = [14.5, 15.5, 16.5]
CDD_BASES = [18.0, 22.0]   # 18.0 used for UK cooling shape; 22.0 retained

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def _fetch_all(start, end, retries=4):
    """One batched request for all GB points + Belfast."""
    pts = GB_POINTS + [(NI_POINT[0], NI_POINT[1], NI_POINT[2], 0.0)]
    params = {
        "latitude": ",".join(str(p[1]) for p in pts),
        "longitude": ",".join(str(p[2]) for p in pts),
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "daily": "temperature_2m_mean", "timezone": "UTC",
    }
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(ARCHIVE_URL, params=params, timeout=120)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else [data]
        except Exception as e:
            last_err = e
            wait = 15 * (attempt + 1)
            print(f"open-meteo attempt {attempt+1} failed ({e}); retry in {wait}s")
            time.sleep(wait)
    raise last_err


def fetch_degree_days(days=400):
    end = dt.date.today() - dt.timedelta(days=1)
    start = end - dt.timedelta(days=days)
    results = _fetch_all(start, end)

    total_w = sum(p[3] for p in GB_POINTS)
    series, counts = {}, {}
    for (name, lat, lon, w), res in zip(GB_POINTS, results):
        d = res["daily"]
        for date, t in zip(d["time"], d["temperature_2m_mean"]):
            if t is None:
                continue
            series[date] = series.get(date, 0.0) + t * w
            counts[date] = counts.get(date, 0.0) + w

    dates = sorted(d for d in series if counts[d] >= 0.9 * total_w)
    gb_mean = {d: series[d] / counts[d] for d in dates}

    out = {"dates": dates,
           "gb_mean_temp": [round(gb_mean[d], 2) for d in dates],
           "hdd": {}, "cdd": {},
           "ni": {"dates": [], "mean_temp": [], "hdd_15_5": []}}

    for base in HDD_BASES:
        out["hdd"][str(base)] = [round(max(0.0, base - gb_mean[d]), 2)
                                 for d in dates]
    for base in CDD_BASES:
        out["cdd"][str(base)] = [round(max(0.0, gb_mean[d] - base), 2)
                                 for d in dates]

    ni = results[-1]["daily"]
    for date, t in zip(ni["time"], ni["temperature_2m_mean"]):
        if t is None:
            continue
        out["ni"]["dates"].append(date)
        out["ni"]["mean_temp"].append(round(t, 2))
        out["ni"]["hdd_15_5"].append(round(max(0.0, 15.5 - t), 2))

    return out


if __name__ == "__main__":
    dd = fetch_degree_days(days=30)
    print(f"{len(dd['dates'])} GB days, latest {dd['dates'][-1]}, "
          f"HDD15.5 latest = {dd['hdd']['15.5'][-1]}, "
          f"CDD18 latest = {dd['cdd']['18.0'][-1]}")

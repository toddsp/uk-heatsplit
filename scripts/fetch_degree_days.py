"""Fetch daily mean temperatures from Open-Meteo (ERA5-derived) and compute
population-weighted GB heating/cooling degree days, plus a separate NI series.

No API key required. Attribution: Open-Meteo.com (CC BY 4.0) / ERA5 (Copernicus).
"""

import datetime as dt
import requests

# Population-weighted GB station set (ONS mid-year estimates, rounded weights).
# Weights are relative; they are normalised in code.
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

HDD_BASES = [14.5, 15.5, 16.5]   # regression selects best-fitting base
CDD_BASE = 22.0                  # stored now, unused until Phase 4

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def _fetch_daily_mean(lat, lon, start, end):
    """Daily mean 2m temperature (deg C) for one point. Returns {date: temp}."""
    r = requests.get(ARCHIVE_URL, params={
        "latitude": lat, "longitude": lon,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "daily": "temperature_2m_mean", "timezone": "UTC",
    }, timeout=60)
    r.raise_for_status()
    d = r.json()["daily"]
    return dict(zip(d["time"], d["temperature_2m_mean"]))


def fetch_degree_days(days=400):
    """Returns dict with GB population-weighted daily mean temp, HDD at each
    base, CDD, and the NI (Belfast) series kept separate."""
    end = dt.date.today() - dt.timedelta(days=1)   # ERA5T lags ~5 days; nulls handled
    start = end - dt.timedelta(days=days)

    total_w = sum(p[3] for p in GB_POINTS)
    series = {}   # date -> weighted sum
    counts = {}   # date -> weight accumulated (handles per-point nulls)

    for name, lat, lon, w in GB_POINTS:
        temps = _fetch_daily_mean(lat, lon, start, end)
        for date, t in temps.items():
            if t is None:
                continue
            series[date] = series.get(date, 0.0) + t * w
            counts[date] = counts.get(date, 0.0) + w

    dates = sorted(d for d in series if counts[d] >= 0.9 * total_w)
    gb_mean = {d: series[d] / counts[d] for d in dates}

    ni_temps = _fetch_daily_mean(*NI_POINT[1:], start, end)

    out = {"dates": dates,
           "gb_mean_temp": [round(gb_mean[d], 2) for d in dates],
           "hdd": {}, "cdd": [],
           "ni": {"dates": [], "mean_temp": [], "hdd_15_5": []}}

    for base in HDD_BASES:
        out["hdd"][str(base)] = [round(max(0.0, base - gb_mean[d]), 2) for d in dates]
    out["cdd"] = [round(max(0.0, gb_mean[d] - CDD_BASE), 2) for d in dates]

    for d in sorted(ni_temps):
        t = ni_temps[d]
        if t is None:
            continue
        out["ni"]["dates"].append(d)
        out["ni"]["mean_temp"].append(round(t, 2))
        out["ni"]["hdd_15_5"].append(round(max(0.0, 15.5 - t), 2))

    return out


if __name__ == "__main__":
    dd = fetch_degree_days(days=30)
    print(f"{len(dd['dates'])} GB days, latest {dd['dates'][-1]}, "
          f"HDD15.5 latest = {dd['hdd']['15.5'][-1]}")

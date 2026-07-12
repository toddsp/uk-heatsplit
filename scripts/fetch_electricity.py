"""Fetch GB half-hourly demand from the NESO Data Portal (CKAN, no key) and
return daily *underlying* demand: ND plus embedded solar and wind added back.

Embedded solar suppresses transmission-metered demand precisely on hot sunny
days, which would bias any cooling regression downward - reconstruction is
mandatory, not optional.

Self-resolving: finds the historic-demand-data resources for the requested
years from the CKAN package listing. Optional feed: callers tolerate failure.
"""

import datetime as dt
import requests

CKAN = "https://api.neso.energy/api/3/action"
PACKAGE_CANDIDATES = ["historic-demand-data"]


def _resources():
    for pkg in PACKAGE_CANDIDATES:
        r = requests.get(f"{CKAN}/package_show", params={"id": pkg}, timeout=60)
        if r.status_code != 200:
            continue
        data = r.json()
        if data.get("success"):
            return data["result"]["resources"]
    raise RuntimeError("NESO historic-demand-data package not found")


def fetch_daily_underlying_demand(years):
    """Returns {date_iso: GWh} of daily underlying GB demand for the given
    calendar years (e.g. [2025, 2026])."""
    resources = _resources()
    wanted = {}
    for res in resources:
        name = (res.get("name") or "").lower()
        for y in years:
            if str(y) in name:
                wanted[y] = res["id"]
    missing = [y for y in years if y not in wanted]
    if missing:
        names = "\n".join(r.get("name", "?") for r in resources)
        raise RuntimeError(f"No NESO resource for {missing}. Available:\n{names}")

    daily_mw_sum = {}   # date -> sum of half-hourly underlying MW
    daily_counts = {}
    for y, rid in wanted.items():
        offset = 0
        while True:
            r = requests.get(f"{CKAN}/datastore_search", params={
                "resource_id": rid, "limit": 32000, "offset": offset,
            }, timeout=120)
            r.raise_for_status()
            result = r.json()["result"]
            records = result.get("records", [])
            if not records:
                break
            for rec in records:
                date = str(rec.get("SETTLEMENT_DATE", ""))[:10]
                try:
                    nd = float(rec.get("ND") or 0)
                    sol = float(rec.get("EMBEDDED_SOLAR_GENERATION") or 0)
                    wind = float(rec.get("EMBEDDED_WIND_GENERATION") or 0)
                except (TypeError, ValueError):
                    continue
                daily_mw_sum[date] = daily_mw_sum.get(date, 0.0) + nd + sol + wind
                daily_counts[date] = daily_counts.get(date, 0) + 1
            offset += len(records)
            if offset >= result.get("total", 0):
                break

    out = {}
    for date, s in daily_mw_sum.items():
        n = daily_counts[date]
        if n >= 40:                      # near-complete day only
            out[date] = round(s * 0.5 / 1000.0, 1)   # MW half-hours -> GWh
    if not out:
        raise RuntimeError("NESO demand fetch returned no complete days")
    print(f"NESO demand: {len(out)} days, {min(out)} to {max(out)}")
    return out


if __name__ == "__main__":
    d = fetch_daily_underlying_demand([2026])
    ds = sorted(d)[-3:]
    for k in ds:
        print(k, d[k], "GWh underlying")

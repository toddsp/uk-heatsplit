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
UPDATE_PACKAGES = ["demand-data-update", "daily-demand-update"]


def _resources(candidates=PACKAGE_CANDIDATES):
    for pkg in candidates:
        r = requests.get(f"{CKAN}/package_show", params={"id": pkg}, timeout=60)
        if r.status_code != 200:
            continue
        data = r.json()
        if data.get("success"):
            return data["result"]["resources"]
    raise RuntimeError(f"NESO package not found among {candidates}")


def _pull_records(rid, out_sum, out_n):
    """Accumulate ND + embedded into per-date sums from one resource."""
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
            out_sum[date] = out_sum.get(date, 0.0) + nd + sol + wind
            out_n[date] = out_n.get(date, 0) + 1
        offset += len(records)
        if offset >= result.get("total", 0):
            break


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
        _pull_records(rid, daily_mw_sum, daily_counts)

    # overlay the daily-updated Demand Data Update (recent days, ~D-1) on top
    # of the periodically refreshed Historic file. Update rows REPLACE
    # historic rows for the same date (fresher revision).
    try:
        upd_resources = _resources(UPDATE_PACKAGES)
        upd_sum, upd_n = {}, {}
        for res in upd_resources:
            _pull_records(res["id"], upd_sum, upd_n)
        replaced = 0
        for date, s in upd_sum.items():
            if upd_n[date] >= 40:
                daily_mw_sum[date] = s
                daily_counts[date] = upd_n[date]
                replaced += 1
        print(f"NESO demand update overlay: {replaced} days merged"
              + (f", latest {max(upd_sum)}" if upd_sum else ""))
    except Exception as e:                       # overlay is best-effort
        print(f"NESO demand-update overlay unavailable ({e}); "
              "historic file only")

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

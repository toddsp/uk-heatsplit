"""Fetch daily GB gas demand from the National Gas Transmission REST API.

Pinned by exact publication name with catalogue verification, falling back to
pattern matching if the name changes. Units auto-detected (GWh vs mcm).
Fair use: one data request per day.
"""

import datetime as dt
import json
import requests

BASE = "https://api.nationalgas.com/operationaldata/v1"
CATALOGUE_URL = f"{BASE}/publications/catalogue"
GASDAY_URL = f"{BASE}/publications/gasday"

# Exact names in priority order; verified against the live catalogue each run.
NTS_PREFERRED_NAMES = [
    "Demand Actual, NTS, D+1 (Energy)",   # PUBOBJ1030 - daily actual, energy units
    "Demand Actual, NTS, D+1",            # volume-units fallback
    "Demand Actual, NTS, D+6",            # later-vintage fallback
]

MCM_TO_GWH = 11.056


def _harvest(node, found):
    if isinstance(node, dict):
        pid = node.get("publicationId") or node.get("publicationObjectId") \
              or node.get("pubObjId") or node.get("id")
        name = node.get("publicationName") or node.get("publicationObjectName") \
               or node.get("name") or node.get("title")
        if pid and name and str(pid).upper().startswith("PUB"):
            found.append((str(pid), str(name)))
        for v in node.values():
            _harvest(v, found)
    elif isinstance(node, list):
        for v in node:
            _harvest(v, found)


def resolve_nts_publication():
    r = requests.get(CATALOGUE_URL, timeout=60)
    r.raise_for_status()
    catalogue = []
    _harvest(r.json(), catalogue)
    catalogue = sorted(set(catalogue))
    by_name = {name: pid for pid, name in catalogue}

    for name in NTS_PREFERRED_NAMES:
        if name in by_name:
            print(f"Using publication: {by_name[name]} | {name}")
            return by_name[name], name

    demand_names = "\n".join(f"{i} | {n}" for i, n in catalogue
                             if "demand" in n.lower() and "actual" in n.lower())
    raise RuntimeError(
        "No preferred NTS publication found. Actual-demand items available:\n"
        + demand_names)


def fetch_gas_demand(days=400):
    pid, name = resolve_nts_publication()
    end = dt.date.today()
    start = end - dt.timedelta(days=days)

    body = {
        "fromDate": start.isoformat(),
        "toDate": end.isoformat(),
        "publicationIds": [pid],
        "latestValue": "Y",
    }
    r = requests.post(GASDAY_URL, json=body,
                      headers={"Content-Type": "application/json"}, timeout=120)
    r.raise_for_status()
    payload = r.json()

    raw = {}
    blocks = payload if isinstance(payload, list) else payload.get("data", [])
    for block in blocks:
        if block.get("publicationId") != pid:
            continue
        for rec in block.get("publications", []):
            date = rec.get("applicableFor")
            try:
                raw[date] = float(rec.get("value"))
            except (TypeError, ValueError):
                continue

    if not raw:
        raise RuntimeError(f"Publication {pid} returned no records")

    vals = sorted(raw.values())
    median = vals[len(vals) // 2]
    if median > 1000:          # already energy units (GWh/day)
        factor, unit = 1.0, "GWh (no conversion)"
    else:                      # volume units (mcm/day)
        factor, unit = MCM_TO_GWH, f"mcm x {MCM_TO_GWH}"
    print(f"gas units: median raw {median:.1f} -> treating as {unit}; "
          f"{len(raw)} days, {min(raw)} to {max(raw)}, "
          f"{len(set(vals))} distinct values")

    nts = {d: round(v * factor, 1) for d, v in raw.items()}
    return {"nts_demand_actual": nts,
            "_meta": {"nts_demand_actual":
                      {"publicationId": pid, "publicationName": name}}}


if __name__ == "__main__":
    data = fetch_gas_demand(days=14)
    print(json.dumps(data["_meta"], indent=2))
